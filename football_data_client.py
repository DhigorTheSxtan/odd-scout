import httpx
import logging
import asyncio
import time
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timezone, timedelta

try:
    from zoneinfo import ZoneInfo
    TIMEZONE_BR = ZoneInfo("America/Sao_Paulo")
except Exception:
    TIMEZONE_BR = timezone(timedelta(hours=-3))

from config import (
    FOOTBALL_DATA_TOKEN,
    FOOTBALL_DATA_BASE_URL,
    REQUEST_TIMEOUT_SECONDS,
    CACHE_TTL_FOOTBALL_DATA_SECONDS,
    FOOTBALL_DATA_COMPETICOES,
    is_football_data_configured
)
from cache import app_cache

logger = logging.getLogger("football_data_client")
logging.basicConfig(level=logging.INFO)


def mask_key(key: str) -> str:

    if not key or len(key) < 8:
        return "****"
    return f"{key[:4]}{'*' * (len(key) - 8)}{key[-4:]}"


class SlidingWindowRateLimiter:


    def __init__(self, max_requests: int = 10, window_seconds: float = 60.0):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._timestamps: List[float] = []
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:

        async with self._lock:
            now = time.time()

            self._timestamps = [ts for ts in self._timestamps if now - ts < self.window_seconds]

            if len(self._timestamps) >= self.max_requests:
                oldest = self._timestamps[0]
                espera = self.window_seconds - (now - oldest) + 0.2
                if espera > 0:
                    logger.warning(
                        f"[Football-Data.org] Limite de 10 req/min atingido. "
                        f"Throttling ativado: aguardando {espera:.2f}s..."
                    )
                    await asyncio.sleep(espera)
                    now = time.time()
                    self._timestamps = [ts for ts in self._timestamps if now - ts < self.window_seconds]

            self._timestamps.append(time.time())


class FootballDataAdapter:


    STATUS_MAP = {
        "SCHEDULED": ("NS", "Não Iniciado"),
        "TIMED": ("NS", "Agendado"),
        "IN_PLAY": ("LIVE", "Ao Vivo"),
        "PAUSED": ("HT", "Intervalo"),
        "EXTRA_TIME": ("ET", "Prorrogação"),
        "PENALTY_SHOOTOUT": ("PEN", "Pênaltis"),
        "FINISHED": ("FT", "Finalizado"),
        "AWARDED": ("FT", "Encerrado"),
        "POSTPONED": ("PST", "Adiado"),
        "SUSPENDED": ("SUSP", "Suspenso"),
        "CANCELLED": ("CANC", "Cancelado")
    }

    @classmethod
    def normalizar_status(cls, status_raw: Optional[str]) -> Tuple[str, str]:

        if not status_raw:
            return ("NS", "Não Iniciado")
        clean = str(status_raw).strip().upper()
        return cls.STATUS_MAP.get(clean, ("NS", clean.replace("_", " ").title()))

    @classmethod
    def formatar_data_hora(cls, utc_date_str: Optional[str]) -> Tuple[str, str]:

        if not utc_date_str or not isinstance(utc_date_str, str):
            agora = datetime.now(TIMEZONE_BR)
            return (agora.isoformat(), agora.strftime("%H:%M"))

        try:
            clean_str = utc_date_str.strip().replace("Z", "+00:00")
            dt_utc = datetime.fromisoformat(clean_str)
            dt_local = dt_utc.astimezone(TIMEZONE_BR)
            return (dt_local.isoformat(), dt_local.strftime("%H:%M"))
        except Exception:
            return (utc_date_str, "--:--")

    @classmethod
    def adaptar_partida(cls, match_raw: Dict[str, Any]) -> Dict[str, Any]:

        match_id = match_raw.get("id", 0)
        home_t = match_raw.get("homeTeam", {}) or {}
        away_t = match_raw.get("awayTeam", {}) or {}
        comp = match_raw.get("competition", {}) or {}
        area = match_raw.get("area", {}) or {}
        score = match_raw.get("score", {}) or {}
        full_time = score.get("fullTime", {}) or {}


        data_hora_iso, horario = cls.formatar_data_hora(match_raw.get("utcDate"))


        status_code, status_desc = cls.normalizar_status(match_raw.get("status"))


        matchday = match_raw.get("matchday")
        stage = match_raw.get("stage", "Rodada Atual")
        if matchday:
            rodada_formatada = f"Rodada {matchday}"
        elif stage:
            rodada_formatada = str(stage).replace("_", " ").title()
        else:
            rodada_formatada = "Rodada Atual"


        nome_casa = home_t.get("shortName") or home_t.get("name") or "Mandante"
        nome_fora = away_t.get("shortName") or away_t.get("name") or "Visitante"


        estadio = match_raw.get("venue") or "Estádio Principal"
        cidade = area.get("name", "")

        return {
            "id": int(match_id) if str(match_id).isdigit() else 0,
            "mandante": {
                "id": int(home_t.get("id", 0)) if str(home_t.get("id", "")).isdigit() else 0,
                "nome": str(nome_casa).strip(),
                "logo": str(home_t.get("crest") or "").strip(),
                "sigla": str(home_t.get("tla") or "").strip()
            },
            "visitante": {
                "id": int(away_t.get("id", 0)) if str(away_t.get("id", "")).isdigit() else 0,
                "nome": str(nome_fora).strip(),
                "logo": str(away_t.get("crest") or "").strip(),
                "sigla": str(away_t.get("tla") or "").strip()
            },
            "campeonato": {
                "id": int(comp.get("id", 0)) if str(comp.get("id", "")).isdigit() else 0,
                "nome": str(comp.get("name") or "Campeonato").strip(),
                "pais": str(area.get("name") or "").strip(),
                "logo": str(comp.get("emblem") or area.get("flag") or "").strip(),
                "rodada": rodada_formatada
            },
            "horario": horario,
            "data_hora": data_hora_iso,
            "status": status_code,
            "status_descricao": status_desc,
            "estadio": estadio,
            "cidade": cidade,
            "placar": {
                "mandante": full_time.get("home"),
                "visitante": full_time.get("away")
            },
            "estatisticas": {
                "corners": {"home": 0, "away": 0},
                "shots_total": {"home": 0, "away": 0},
                "shots_on_target": {"home": 0, "away": 0},
                "throw_ins": {"home": None, "away": None},
                "possession": {"home": "50%", "away": "50%"}
            },
            "provedor": "football_data",
            "raw_data": match_raw
        }


class FootballDataClient:


    def __init__(self):
        self.base_url = FOOTBALL_DATA_BASE_URL.rstrip("/")
        self.timeout = httpx.Timeout(REQUEST_TIMEOUT_SECONDS)
        self.rate_limiter = SlidingWindowRateLimiter(max_requests=10, window_seconds=60.0)
        self._cooldown_until = 0.0

    def _get_headers(self) -> Dict[str, str]:

        token = FOOTBALL_DATA_TOKEN
        return {
            "X-Auth-Token": token,
            "Accept": "application/json",
            "User-Agent": "SportsPredictorAI-FootballData/1.0"
        }

    async def _make_request(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:

        if not is_football_data_configured():
            logger.info("[Football-Data.org] Token FOOTBALL_DATA_TOKEN não configurado no .env.")
            return {
                "results": 0,
                "matches": [],
                "status_code": 0,
                "errors": {"auth": "Token FOOTBALL_DATA_TOKEN pendente no .env"}
            }

        if time.time() < self._cooldown_until:
            tempo_espera = int(self._cooldown_until - time.time())
            return {
                "results": 0,
                "matches": [],
                "status_code": 429,
                "errors": {"rateLimit": f"Cooldown ativo da Football-Data.org (aguarde {tempo_espera}s)"}
            }

        await self.rate_limiter.acquire()

        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        param_str = "&".join([f"{k}={v}" for k, v in (params or {}).items()])
        full_query = f"{url}?{param_str}" if param_str else url

        print(f"\n[Football-Data.org] >>> REQUISIÇÃO: GET {full_query}")
        print(f"[Football-Data.org] Auth Header: {{'X-Auth-Token': '{mask_key(FOOTBALL_DATA_TOKEN)}'}} | Timeout: {REQUEST_TIMEOUT_SECONDS}s")

        start_time = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, headers=self._get_headers(), params=params)
                latency_ms = (time.perf_counter() - start_time) * 1000

                print(f"[Football-Data.org] <<< RESPOSTA: HTTP {response.status_code} ({latency_ms:.1f} ms)")

                if response.status_code == 401:
                    logger.error(f"[Football-Data.org] [ERRO 401] Token inválido ou não autorizado: {mask_key(FOOTBALL_DATA_TOKEN)}")
                    return {
                        "results": 0,
                        "matches": [],
                        "status_code": 401,
                        "errors": {"auth": "Token da Football-Data.org inválido ou expirado (HTTP 401)"}
                    }

                elif response.status_code == 403:
                    logger.warning(
                        "[Football-Data.org] [ERRO 403] Acesso proibido. "
                        "Recurso ou competição não coberta pelo plano da chave."
                    )
                    return {
                        "results": 0,
                        "matches": [],
                        "status_code": 403,
                        "errors": {"forbidden": "Competição ou recurso não disponível no plano atual (HTTP 403)"}
                    }

                elif response.status_code == 429:
                    logger.warning(
                        "[Football-Data.org] [ERRO 429] Limite de requisições excedido (10 req/min). "
                        "Ativando cooldown de 60s."
                    )
                    self._cooldown_until = time.time() + 60.0
                    return {
                        "results": 0,
                        "matches": [],
                        "status_code": 429,
                        "errors": {"rateLimit": "Limite de taxa atingido na Football-Data.org (HTTP 429)"}
                    }

                elif response.status_code >= 500:
                    logger.error(f"[Football-Data.org] [ERRO {response.status_code}] Falha interna nos servidores da Football-Data.org.")
                    return {
                        "results": 0,
                        "matches": [],
                        "status_code": response.status_code,
                        "errors": {"server": f"Erro interno do servidor remoto ({response.status_code})"}
                    }

                data = response.json()
                matches_list = data.get("matches", [])
                print(f"[Football-Data.org] Partidas retornadas: {len(matches_list)}")

                return {
                    "results": len(matches_list),
                    "matches": matches_list,
                    "filters": data.get("filters", {}),
                    "status_code": response.status_code,
                    "errors": {}
                }

        except httpx.TimeoutException:
            logger.warning(f"[Football-Data.org] Timeout de {REQUEST_TIMEOUT_SECONDS}s excedido na requisição.")
            return {
                "results": 0,
                "matches": [],
                "status_code": 408,
                "errors": {"timeout": f"Timeout após {REQUEST_TIMEOUT_SECONDS} segundos"}
            }
        except httpx.RequestError as exc:
            logger.error(f"[Football-Data.org] Erro de transporte HTTP: {exc}")
            return {
                "results": 0,
                "matches": [],
                "status_code": 500,
                "errors": {"network": str(exc)}
            }
        except Exception as exc:
            logger.error(f"[Football-Data.org] Erro inesperado: {exc}")
            return {
                "results": 0,
                "matches": [],
                "status_code": 500,
                "errors": {"unexpected": str(exc)}
            }

    async def buscar_jogos_dia(self, data_str: str, force_refresh: bool = False) -> List[Dict[str, Any]]:

        cache_key = f"football_data_matches_{data_str}"

        if not force_refresh:
            cached_data = await app_cache.get(cache_key)
            if cached_data is not None:
                logger.info(f"[Football-Data.org] Cache HIT para {data_str} ({len(cached_data)} partidas).")
                return cached_data

        if not is_football_data_configured():
            logger.info("[Football-Data.org] Chave não configurada. Retornando lista vazia.")
            return []


        try:
            dt_base = datetime.strptime(data_str, "%Y-%m-%d")
            dia_seguinte = (dt_base + timedelta(days=1)).strftime("%Y-%m-%d")
        except Exception:
            dia_seguinte = data_str


        params = {
            "dateFrom": data_str,
            "dateTo": dia_seguinte
        }

        res = await self._make_request("matches", params=params)
        matches = res.get("matches", [])


        if matches:
            await app_cache.set(cache_key, matches, ttl_seconds=CACHE_TTL_FOOTBALL_DATA_SECONDS)

        return matches

    async def buscar_jogos_competicao(
        self,
        codigo_competicao: str,
        data_str: Optional[str] = None
    ) -> List[Dict[str, Any]]:

        endpoint = f"competitions/{codigo_competicao}/matches"
        params: Dict[str, Any] = {}
        if data_str:
            try:
                dt_base = datetime.strptime(data_str, "%Y-%m-%d")
                dia_seguinte = (dt_base + timedelta(days=1)).strftime("%Y-%m-%d")
                params["dateFrom"] = data_str
                params["dateTo"] = dia_seguinte
            except Exception:
                params["dateFrom"] = data_str
                params["dateTo"] = data_str

        res = await self._make_request(endpoint, params=params if params else None)
        return res.get("matches", [])

    async def obter_status_conexao(self) -> Dict[str, Any]:
        """Verifica a conectividade e integridade do token Football-Data.org."""
        if not is_football_data_configured():
            return {"status": "chave_pendente", "configurado": False}

        cache_key = "football_data_status_check"
        cached = await app_cache.get(cache_key)
        if cached:
            return cached

        res = await self._make_request("competitions/PL")
        status_res = {
            "status": "online" if res.get("status_code") == 200 else "alerta",
            "configurado": True,
            "status_code": res.get("status_code"),
            "erros": res.get("errors", {})
        }
        await app_cache.set(cache_key, status_res, ttl_seconds=300)
        return status_res


football_data_client = FootballDataClient()
