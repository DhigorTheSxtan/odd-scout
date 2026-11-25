import logging
import time
from typing import List, Dict, Any, Optional, Tuple, Set
from datetime import datetime

from schemas import MatchSchema, TeamSchema, LeagueSchema, ScoreSchema
from cache import app_cache
from football_service import is_allowed_league

logger = logging.getLogger("soccer_waterfall_service")
logging.basicConfig(level=logging.INFO)


class QuotaExceededException(Exception):
    """Exceção levantada quando um provedor atinge limite de cota, rate limit (429) ou crédito esgotado."""
    def __init__(self, provider: str, message: str, status_code: Optional[int] = None):
        super().__init__(f"[{provider}] Cota esgotada/Rate Limit: {message}")
        self.provider = provider
        self.message = message
        self.status_code = status_code


class BaseSoccerAdapter:
    """Interface base para os adaptadores da cadeia de contingência."""
    name: str = "base"

    async def get_matches(self, date: str, league: Optional[int] = None, force_refresh: bool = False, **kwargs) -> List[MatchSchema]:
        raise NotImplementedError

    async def get_fixtures_by_date(self, date: str, **kwargs) -> List[MatchSchema]:
        return await self.get_matches(date=date, **kwargs)


# ==============================================================================
# 1. Adaptador: Owls Insight (Desativado)
# ==============================================================================
class OwlsInsightAdapter(BaseSoccerAdapter):
    name = "owlsinsight"

    async def get_matches(self, date: str, league: Optional[int] = None, force_refresh: bool = False, **kwargs) -> List[MatchSchema]:
        # Desativado: chamadas HTTP a api.owlsinsight.com foram permanentemente descontinuadas.
        # Todo o fluxo de futebol opera diretamente via Agente Gemini 2.0 Flash.
        return []


# ==============================================================================
# 2. Adaptador: API-SPORTS (1º Fallback)
# ==============================================================================
class ApiSportsSoccerAdapter(BaseSoccerAdapter):
    name = "apisports"

    async def get_matches(self, date: str, league: Optional[int] = None, force_refresh: bool = False, **kwargs) -> List[MatchSchema]:
        return []


# ==============================================================================
# 3. Adaptador: Football-Data.org (2º Fallback)
# ==============================================================================
class FootballDataOrgAdapter(BaseSoccerAdapter):
    name = "football_data_org"

    async def get_matches(self, date: str, league: Optional[int] = None, force_refresh: bool = False, **kwargs) -> List[MatchSchema]:
        from config import is_football_data_configured
        if not is_football_data_configured():
            raise QuotaExceededException(self.name, "Chave FOOTBALL_DATA_ORG_KEY não configurada.", 401)

        from football_data_client import football_data_client, FootballDataAdapter
        try:
            raw_matches = await football_data_client.buscar_jogos_dia(data_str=date, force_refresh=force_refresh)
        except Exception as exc:
            err_str = str(exc).lower()
            if "429" in err_str or "rate limit" in err_str or "quota" in err_str or "too many" in err_str:
                raise QuotaExceededException(self.name, str(exc), 429)
            if "403" in err_str or "forbidden" in err_str:
                raise QuotaExceededException(self.name, str(exc), 403)
            raise exc

        # Se o cliente ativou cooldown por HTTP 429
        if getattr(football_data_client, "_cooldown_until", 0) > time.time():
            raise QuotaExceededException(self.name, "Football-Data.org rate limit/cooldown ativo.", 429)

        matches: List[MatchSchema] = []
        for m in raw_matches:
            adapted = FootballDataAdapter.adaptar_partida(m)
            if league and adapted.get("campeonato", {}).get("id") != league:
                continue
            matches.append(MatchSchema(
                id=adapted.get("id"),
                data=date,
                data_hora=adapted.get("data_hora") or f"{date}T16:00:00-03:00",
                horario=adapted.get("horario", "16:00"),
                status=adapted.get("status", "SCHEDULED"),
                status_descricao=adapted.get("status_descricao", "Agendado"),
                estadio=adapted.get("estadio", "Estádio Principal"),
                cidade=adapted.get("cidade", ""),
                placar=ScoreSchema(
                    mandante=adapted.get("placar", {}).get("mandante"),
                    visitante=adapted.get("placar", {}).get("visitante")
                ),
                tempo_decorrido=None,
                mandante=TeamSchema(
                    id=adapted.get("mandante", {}).get("id", 0),
                    nome=adapted.get("mandante", {}).get("nome", "Mandante"),
                    logo=adapted.get("mandante", {}).get("logo", ""),
                    sigla=adapted.get("mandante", {}).get("sigla", "")
                ),
                visitante=TeamSchema(
                    id=adapted.get("visitante", {}).get("id", 0),
                    nome=adapted.get("visitante", {}).get("nome", "Visitante"),
                    logo=adapted.get("visitante", {}).get("logo", ""),
                    sigla=adapted.get("visitante", {}).get("sigla", "")
                ),
                campeonato=LeagueSchema(
                    id=adapted.get("campeonato", {}).get("id", 0),
                    nome=adapted.get("campeonato", {}).get("nome", "Futebol Internacional"),
                    pais=adapted.get("campeonato", {}).get("pais", "Europa"),
                    logo=adapted.get("campeonato", {}).get("logo", ""),
                    rodada=adapted.get("campeonato", {}).get("rodada", "Rodada Regular")
                ),
                estatisticas=adapted.get("estatisticas") or {},
                provedor="football-data.org",
                provedores_integrados=["football-data.org"]
            ))
        return matches


# ==============================================================================
# 4. Adaptador: Sportmonks (3º Fallback)
# ==============================================================================
class SportmonksSoccerAdapter(BaseSoccerAdapter):
    name = "sportmonks"

    async def get_matches(self, date: str, league: Optional[int] = None, force_refresh: bool = False, **kwargs) -> List[MatchSchema]:
        from config import is_sportmonks_configured
        if not is_sportmonks_configured():
            raise QuotaExceededException(self.name, "Chave SPORTMONKS_KEY não configurada.", 401)

        from sportmonks_service import sportmonks_service
        try:
            res = await sportmonks_service.buscar_jogos(data=date, league_id=league, force_refresh=force_refresh)
        except Exception as exc:
            err_str = str(exc).lower()
            if "429" in err_str or "rate limit" in err_str or "quota" in err_str or "too many" in err_str:
                raise QuotaExceededException(self.name, str(exc), 429)
            if "403" in err_str or "forbidden" in err_str:
                raise QuotaExceededException(self.name, str(exc), 403)
            raise exc

        if res.get("status") == "erro" or res.get("erro"):
            err_msg = str(res.get("erro", ""))
            if any(term in err_msg.lower() for term in ("429", "rate limit", "cooldown", "cota")):
                raise QuotaExceededException(self.name, err_msg, 429)

        jogos_raw = res.get("jogos", [])
        matches: List[MatchSchema] = []
        for j in jogos_raw:
            st_raw = j.get("status", "A_COMECAR")
            status_can = "LIVE" if st_raw == "AO_VIVO" else ("FINISHED" if st_raw == "FINALIZADO" else "SCHEDULED")
            status_desc = "Ao Vivo" if status_can == "LIVE" else ("Finalizado" if status_can == "FINISHED" else "Agendado")

            matches.append(MatchSchema(
                id=j.get("id"),
                data=j.get("data", date),
                data_hora=f"{date}T{j.get('horario', '16:00')}:00-03:00",
                horario=j.get("horario", "16:00"),
                status=status_can,
                status_descricao=status_desc,
                estadio=j.get("estadio", "Estádio Principal"),
                cidade="",
                placar=ScoreSchema(
                    mandante=j.get("placar", {}).get("casa") if isinstance(j.get("placar", {}).get("casa"), int) else None,
                    visitante=j.get("placar", {}).get("fora") if isinstance(j.get("placar", {}).get("fora"), int) else None
                ),
                tempo_decorrido=None,
                mandante=TeamSchema(
                    id=abs(hash(j.get("mandante", ""))) % 1000000,
                    nome=j.get("mandante", "Mandante"),
                    logo=j.get("mandante_logo", ""),
                    sigla=""
                ),
                visitante=TeamSchema(
                    id=abs(hash(j.get("visitante", ""))) % 1000000,
                    nome=j.get("visitante", "Visitante"),
                    logo=j.get("visitante_logo", ""),
                    sigla=""
                ),
                campeonato=LeagueSchema(
                    id=abs(hash(j.get("campeonato", ""))) % 100000,
                    nome=j.get("campeonato", "Futebol Profissional"),
                    pais="Mundo",
                    logo=j.get("campeonato_logo", ""),
                    rodada="Rodada Regular"
                ),
                estatisticas={},
                provedor="Sportmonks API v3",
                provedores_integrados=["Sportmonks API v3"]
            ))
        return matches


# ==============================================================================
# 5. Adaptador: API-Futebol (Contingência Final)
# ==============================================================================
class ApiFutebolSoccerAdapter(BaseSoccerAdapter):
    name = "api_futebol"

    async def get_matches(self, date: str, league: Optional[int] = None, force_refresh: bool = False, **kwargs) -> List[MatchSchema]:
        from config import is_api_futebol_configured
        if not is_api_futebol_configured():
            raise QuotaExceededException(self.name, "Chave API_FUTEBOL_KEY não configurada.", 401)

        from api_futebol_client import api_futebol_client
        from api_futebol_adapter import ApiFutebolAdapter
        try:
            res = await api_futebol_client.get_fixtures_by_date(target_date=date)
        except Exception as exc:
            err_str = str(exc).lower()
            if "429" in err_str or "rate limit" in err_str or "quota" in err_str or "too many" in err_str:
                raise QuotaExceededException(self.name, str(exc), 429)
            if "403" in err_str or "forbidden" in err_str:
                raise QuotaExceededException(self.name, str(exc), 403)
            raise exc

        errors = res.get("errors", {})
        if "rateLimit" in errors or "quota" in str(errors).lower():
            raise QuotaExceededException(self.name, str(errors), 429)

        raw_matches = res.get("data", [])
        matches: List[MatchSchema] = []
        for m in raw_matches:
            adapted = ApiFutebolAdapter.adaptar_partida(m)
            if league and adapted.get("campeonato", {}).get("id") != league:
                continue
            matches.append(MatchSchema(
                id=adapted.get("id"),
                data=date,
                data_hora=adapted.get("data_hora") or f"{date}T16:00:00-03:00",
                horario=adapted.get("horario", "16:00"),
                status=adapted.get("status", "SCHEDULED"),
                status_descricao=adapted.get("status_descricao", "Agendado"),
                estadio=adapted.get("estadio", "Estádio Principal"),
                cidade=adapted.get("cidade", ""),
                placar=ScoreSchema(
                    mandante=adapted.get("placar", {}).get("mandante"),
                    visitante=adapted.get("placar", {}).get("visitante")
                ),
                tempo_decorrido=None,
                mandante=TeamSchema(
                    id=adapted.get("mandante", {}).get("id", 0),
                    nome=adapted.get("mandante", {}).get("nome", "Mandante"),
                    logo=adapted.get("mandante", {}).get("logo", ""),
                    sigla=adapted.get("mandante", {}).get("sigla", "")
                ),
                visitante=TeamSchema(
                    id=adapted.get("visitante", {}).get("id", 0),
                    nome=adapted.get("visitante", {}).get("nome", "Visitante"),
                    logo=adapted.get("visitante", {}).get("logo", ""),
                    sigla=adapted.get("visitante", {}).get("sigla", "")
                ),
                campeonato=LeagueSchema(
                    id=adapted.get("campeonato", {}).get("id", 0),
                    nome=adapted.get("campeonato", {}).get("nome", "Brasileirão"),
                    pais="Brasil",
                    logo=adapted.get("campeonato", {}).get("logo", ""),
                    rodada=adapted.get("campeonato", {}).get("rodada", "Rodada Regular")
                ),
                estatisticas=adapted.get("estatisticas") or {},
                provedor="API-Futebol",
                provedores_integrados=["API-Futebol"]
            ))
        return matches


class GeminiSoccerAdapter(BaseSoccerAdapter):
    name = "gemini_agent"

    async def get_matches(self, date: str, league: Optional[int] = None, force_refresh: bool = False, **kwargs) -> List[MatchSchema]:
        from services.ai_analytics_service import obter_jogos_e_palpites_gemini
        try:
            res = await obter_jogos_e_palpites_gemini(data=date, force_refresh=force_refresh)
            partidas = res if isinstance(res, list) else (res.get("partidas") or res.get("jogos") or [])
            matches: List[MatchSchema] = []
            for j in partidas:
                m_id = j.get("id") or j.get("match_id") or f"gemini_{len(matches) + 1}"
                matches.append(MatchSchema(
                    id=m_id,
                    data=j.get("data", date),
                    data_hora=j.get("data_hora") or f"{date}T16:00:00-03:00",
                    horario=j.get("horario", "16:00"),
                    status=j.get("status", "SCHEDULED"),
                    status_descricao=j.get("status_descricao", "Agendado"),
                    estadio=j.get("estadio", "Estádio Oficial"),
                    cidade=j.get("cidade", ""),
                    placar=ScoreSchema(
                        mandante=j.get("placar", {}).get("mandante"),
                        visitante=j.get("placar", {}).get("visitante")
                    ),
                    tempo_decorrido=j.get("tempo_decorrido"),
                    mandante=TeamSchema(
                        id=j.get("mandante", {}).get("id", 0),
                        nome=j.get("mandante", {}).get("nome", "Mandante"),
                        logo=j.get("mandante", {}).get("logo", ""),
                        sigla=j.get("mandante", {}).get("sigla", "")
                    ),
                    visitante=TeamSchema(
                        id=j.get("visitante", {}).get("id", 0),
                        nome=j.get("visitante", {}).get("nome", "Visitante"),
                        logo=j.get("visitante", {}).get("logo", ""),
                        sigla=j.get("visitante", {}).get("sigla", "")
                    ),
                    campeonato=LeagueSchema(
                        id=j.get("campeonato", {}).get("id", 0),
                        nome=j.get("campeonato", {}).get("nome", "Futebol"),
                        pais=j.get("campeonato", {}).get("pais", "Mundo"),
                        logo=j.get("campeonato", {}).get("logo", ""),
                        rodada=j.get("campeonato", {}).get("rodada", "Rodada Regular")
                    ),
                    estatisticas=j.get("estatisticas") or {},
                    provedor="Gemini 2.0 Flash",
                    provedores_integrados=["Gemini 2.0 Flash"]
                ))
            return matches
        except Exception as exc:
            logger.warning(f"[GeminiSoccerAdapter] Erro ao obter partidas do Gemini: {exc}")
            return []


gemini_soccer_client = GeminiSoccerAdapter()

PROVIDERS_CHAIN: List[Tuple[str, BaseSoccerAdapter]] = [
    ("gemini_agent", gemini_soccer_client),
]


class SoccerWaterfallService:
    """
    Gerenciador de requisições de futebol com contingência em cascata (Waterfall Pattern).
    Percorre a fila de provedores até encontrar um que retorne com sucesso.
    Em caso de cota esgotada (429 / rate limit), armazena o provedor na sessão e comuta
    imediatamente para o próximo sem interrupção para o usuário.
    """

    def __init__(self, chain: Optional[List[Tuple[str, BaseSoccerAdapter]]] = None):
        self.providers = chain or PROVIDERS_CHAIN
        self.exhausted_providers: Set[str] = set()
        self.last_used_provider: Optional[str] = None

    def reset_exhausted(self, provider_name: Optional[str] = None):
        """Reseta a marcação de provedores esgotados."""
        if provider_name:
            self.exhausted_providers.discard(provider_name)
        else:
            self.exhausted_providers.clear()

    async def fetch_soccer_matches(
        self,
        date: str,
        league: Optional[int] = None,
        force_refresh: bool = False
    ) -> List[MatchSchema]:
        """
        Executa a busca em cascata de partidas de futebol na ordem canônica.
        """
        last_error = None

        for name, client in self.providers:
            if name in self.exhausted_providers:
                logger.warning(f"[Waterfall] Provedor '{name}' já marcado como esgotado nesta sessão. Pulando para o próximo...")
                continue

            try:
                logger.info(f"[Waterfall] Tentando consumir futebol via: {name}")
                matches = await client.get_matches(date=date, league=league, force_refresh=force_refresh)
                
                # Sucesso: registra o provedor utilizado e retorna a lista estritamente filtrada
                self.last_used_provider = name
                matches_filtradas = [
                    m for m in matches 
                    if is_allowed_league(getattr(m.campeonato, "nome", ""), getattr(m.campeonato, "pais", ""))
                ]
                logger.info(f"[Waterfall] Sucesso via '{name}': {len(matches_filtradas)} partidas autorizadas obtidas (de {len(matches)} brutas).")
                return matches_filtradas

            except QuotaExceededException as q_err:
                logger.error(
                    f"[Waterfall] COTA ESGOTADA no provedor '{name}': {q_err}. "
                    f"Chaveando automaticamente para o próximo da fila..."
                )
                self.exhausted_providers.add(name)
                last_error = q_err
                continue

            except Exception as err:
                # Falha de rede / timeout ou outro erro técnico: comuta para o próximo
                logger.error(
                    f"[Waterfall] Falha ao consultar '{name}': {err}. "
                    f"Tentando próximo fallback da fila..."
                )
                last_error = err
                continue

        logger.warning(f"[Waterfall] Nenhum evento de futebol retornado para {date}. Último detalhe: {last_error}")
        return []

    async def get_fixtures_by_date(self, date: str) -> List[MatchSchema]:
        """Alias de conveniência solicitado na especificação técnica."""
        return await self.fetch_soccer_matches(date=date)


soccer_fallback_service = SoccerWaterfallService()
soccer_service = soccer_fallback_service
