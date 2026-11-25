import httpx
import logging
import time
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone, timedelta

try:
    from zoneinfo import ZoneInfo
    TIMEZONE_BR = ZoneInfo("America/Sao_Paulo")
except Exception:
    TIMEZONE_BR = timezone(timedelta(hours=-3))

from config import (
    API_FUTEBOL_KEY,
    API_FUTEBOL_BASE_URL,
    REQUEST_TIMEOUT_SECONDS,
    CACHE_TTL_FIXTURES_SECONDS,
    CACHE_TTL_STATS_SECONDS,
    API_FUTEBOL_CAMPEONATOS_PADRAO,
    is_api_futebol_configured
)
from cache import app_cache

logger = logging.getLogger("api_futebol")
logging.basicConfig(level=logging.INFO)


def mask_key(key: str) -> str:

    if not key or len(key) < 8:
        return "****"
    return f"{key[:4]}{'*' * (len(key) - 8)}{key[-4:]}"


class ApiFutebolClient:


    def __init__(self):
        self.base_url = API_FUTEBOL_BASE_URL.rstrip('/')
        self.timeout = httpx.Timeout(REQUEST_TIMEOUT_SECONDS)
        self._cooldown_until = 0.0

    def _get_headers(self) -> Dict[str, str]:

        return {
            "Authorization": f"Bearer {API_FUTEBOL_KEY}",
            "Accept": "application/json",
            "User-Agent": "SportsPredictorAI-Brazil/1.0"
        }

    async def _make_request(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:

        if not is_api_futebol_configured():
            logger.info("[API-Futebol] Chave API_FUTEBOL_KEY não configurada no .env.")
            return {
                "results": 0,
                "data": None,
                "errors": {"auth": "Chave API_FUTEBOL_KEY pendente no .env"}
            }

        if time.time() < self._cooldown_until:
            tempo_espera = int(self._cooldown_until - time.time())
            return {
                "results": 0,
                "data": None,
                "status_code": 429,
                "errors": {"rateLimit": f"Cooldown ativo da API-Futebol (aguarde {tempo_espera}s)"}
            }

        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        param_str = "&".join([f"{k}={v}" for k, v in (params or {}).items()])
        full_query = f"{url}?{param_str}" if param_str else url

        print(f"\n[API-Futebol] >>> REQUISIÇÃO: GET {full_query}")
        print(f"[API-Futebol] Auth: Bearer {mask_key(API_FUTEBOL_KEY)} | Timeout: {REQUEST_TIMEOUT_SECONDS}s")

        start_time = time.perf_counter()
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(url, headers=self._get_headers(), params=params)
                latency_ms = (time.perf_counter() - start_time) * 1000

                print(f"[API-Futebol] <<< RESPOSTA: HTTP {response.status_code} ({latency_ms:.1f} ms)")


                if response.status_code == 401:
                    print(f"[API-Futebol] [ERRO 401] Token Bearer ausente, expirado ou inválido: {mask_key(API_FUTEBOL_KEY)}")
                    self._cooldown_until = time.time() + 60.0
                    return {
                        "results": 0,
                        "data": None,
                        "status_code": 401,
                        "errors": {"auth": "API Key da API-Futebol ausente ou inválida (HTTP 401)"}
                    }
                elif response.status_code == 403:
                    print("[API-Futebol] [ERRO 403] Acesso proibido. Plano não cobre o recurso ou campeonato.")
                    return {
                        "results": 0,
                        "data": None,
                        "status_code": 403,
                        "errors": {"forbidden": "Plano não dá acesso ao recurso solicitado (HTTP 403)"}
                    }
                elif response.status_code == 429:
                    print("[API-Futebol] [ERRO 429] Limite de requisições do plano atingido (Rate Limit). Ativando cooldown de 60s.")
                    self._cooldown_until = time.time() + 60.0
                    return {
                        "results": 0,
                        "data": None,
                        "status_code": 429,
                        "errors": {"rateLimit": "Limite de requisições da API-Futebol atingido (HTTP 429)"}
                    }
                elif response.status_code >= 500:
                    print(f"[API-Futebol] [ERRO {response.status_code}] Falha interna nos servidores remotos da API-Futebol.")
                    return {
                        "results": 0,
                        "data": None,
                        "status_code": response.status_code,
                        "errors": {"server": f"Erro do servidor API-Futebol ({response.status_code})"}
                    }
                elif response.status_code == 404:
                    return {
                        "results": 0,
                        "data": None,
                        "status_code": 404,
                        "errors": {"notFound": "Recurso não encontrado (HTTP 404)"}
                    }

                data = response.json()
                return {
                    "results": len(data) if isinstance(data, list) else 1,
                    "data": data,
                    "status_code": response.status_code,
                    "latency_ms": round(latency_ms, 1),
                    "errors": {}
                }

            except httpx.TimeoutException:
                latency_ms = (time.perf_counter() - start_time) * 1000
                print(f"[API-Futebol] [TIMEOUT] Requisição excedeu o limite estrito de {REQUEST_TIMEOUT_SECONDS}s ({latency_ms:.1f}ms).")
                return {
                    "results": 0,
                    "data": None,
                    "status_code": 408,
                    "errors": {"timeout": f"Timeout de requisição (> {REQUEST_TIMEOUT_SECONDS}s)"}
                }
            except httpx.RequestError as exc:
                latency_ms = (time.perf_counter() - start_time) * 1000
                print(f"[API-Futebol] [FALHA DE REDE] Erro de conexão com a API-Futebol: {exc} ({latency_ms:.1f}ms)")
                return {
                    "results": 0,
                    "data": None,
                    "status_code": 503,
                    "errors": {"network": str(exc)}
                }

    async def get_me(self) -> Dict[str, Any]:

        cache_key = "api_futebol_me"
        cached = await app_cache.get(cache_key)
        if cached is not None:
            return cached

        res = await self._make_request("me")
        if res.get("data"):
            await app_cache.set(cache_key, res["data"], ttl_seconds=3600)
            return res["data"]
        return res

    async def get_campeonatos(self) -> List[Dict[str, Any]]:

        cache_key = "api_futebol_campeonatos"
        cached = await app_cache.get(cache_key)
        if cached is not None:
            return cached

        res = await self._make_request("campeonatos")
        data = res.get("data")
        if isinstance(data, list):
            await app_cache.set(cache_key, data, ttl_seconds=CACHE_TTL_STATS_SECONDS)
            return data
        return []

    async def get_partidas_campeonato(self, campeonato_id: int) -> Dict[str, Any]:

        cache_key = f"api_futebol_partidas_camp_{campeonato_id}"
        cached = await app_cache.get(cache_key)
        if cached is not None:
            return cached

        res = await self._make_request(f"campeonatos/{campeonato_id}/partidas")
        data = res.get("data")
        if isinstance(data, dict):
            await app_cache.set(cache_key, data, ttl_seconds=CACHE_TTL_FIXTURES_SECONDS)
            return data
        return {}

    async def get_partidas_ao_vivo(self) -> List[Dict[str, Any]]:

        cache_key = "api_futebol_ao_vivo"
        cached = await app_cache.get(cache_key)
        if cached is not None:
            return cached

        res = await self._make_request("ao-vivo")
        data = res.get("data")
        if isinstance(data, list):
            await app_cache.set(cache_key, data, ttl_seconds=60)
            return data
        return []

    async def get_partida_detalhes(self, partida_id: int) -> Dict[str, Any]:

        cache_key = f"api_futebol_partida_{partida_id}"
        cached = await app_cache.get(cache_key)
        if cached is not None:
            return cached

        res = await self._make_request(f"partidas/{partida_id}")
        data = res.get("data")
        if isinstance(data, dict):
            status = (data.get("status") or "").lower()
            ttl = CACHE_TTL_STATS_SECONDS if status in ("finalizado", "encerrado") else 180
            await app_cache.set(cache_key, data, ttl_seconds=ttl)
            return data
        return {}

    async def get_team_recent_matches(self, team_id: int, last: int = 10) -> List[Dict[str, Any]]:

        cache_key = f"api_futebol_team_recent_{team_id}_{last}"
        cached = await app_cache.get(cache_key)
        if cached is not None:
            return cached

        res = await self._make_request(f"times/{team_id}/partidas/anteriores")
        data = res.get("data")
        matches = []
        if isinstance(data, list):
            matches = data[:last]
        elif isinstance(data, dict):

            for camp_partidas in data.values():
                if isinstance(camp_partidas, list):
                    matches.extend(camp_partidas)
            matches = matches[:last]

        if matches:
            await app_cache.set(cache_key, matches, ttl_seconds=CACHE_TTL_STATS_SECONDS)
        return matches

    async def get_fixtures_by_date(self, target_date: str) -> Dict[str, Any]:

        cache_key = f"api_futebol_fixtures_{target_date}"
        cached = await app_cache.get(cache_key)
        if cached is not None:
            return {
                "source": "api_futebol",
                "data": cached,
                "total": len(cached),
                "is_cached": True,
                "errors": {}
            }

        if not is_api_futebol_configured():
            return {
                "source": "api_futebol",
                "data": [],
                "total": 0,
                "is_configured": False,
                "errors": {"auth": "Chave API_FUTEBOL_KEY não configurada no .env"}
            }

        if time.time() < self._cooldown_until:
            tempo_espera = int(self._cooldown_until - time.time())
            return {
                "source": "api_futebol",
                "data": [],
                "total": 0,
                "is_configured": True,
                "errors": {"rateLimit": f"Cooldown de taxa ativo na API-Futebol (aguarde {tempo_espera}s)"}
            }


        try:
            date_dt = datetime.strptime(target_date, "%Y-%m-%d")
            target_date_br = date_dt.strftime("%d/%m/%Y")
        except ValueError:
            target_date_br = target_date

        partidas_encontradas: List[Dict[str, Any]] = []
        ids_partidas_processadas = set()
        erros_coletados = {}


        try:
            live_matches = await self.get_partidas_ao_vivo()
            for m in live_matches:
                p_id = m.get("partida_id")
                if not p_id or p_id in ids_partidas_processadas:
                    continue

                d_iso = m.get("data_realizacao_iso") or ""
                d_br = m.get("data_realizacao") or ""
                if d_iso.startswith(target_date) or d_br == target_date_br:
                    ids_partidas_processadas.add(p_id)
                    partidas_encontradas.append(m)
        except Exception as exc:
            erros_coletados["ao_vivo"] = str(exc)

        # Se já estiver em cooldown após a tentativa do ao-vivo, encerra busca sem martelar campeonatos
        if time.time() < self._cooldown_until:
            erros_coletados["rateLimit"] = "Limite de taxa atingido na chamada ao vivo."
            return {
                "source": "api_futebol",
                "data": partidas_encontradas,
                "total": len(partidas_encontradas),
                "is_cached": False,
                "errors": erros_coletados
            }


        campeonatos_ids = list(API_FUTEBOL_CAMPEONATOS_PADRAO.keys())
        try:
            user_me = await self.get_me()
            user_camps = user_me.get("campeonatos", []) if isinstance(user_me, dict) else []
            if user_camps:
                campeonatos_ids = [c.get("campeonato_id") for c in user_camps if c.get("campeonato_id")]
        except Exception:
            pass


        for camp_id in campeonatos_ids:
            if time.time() < self._cooldown_until:
                break
            try:
                camp_data = await self.get_partidas_campeonato(camp_id)
                if not camp_data:
                    continue

                campeonato_meta = camp_data.get("campeonato", {})
                partidas_agrupadas = camp_data.get("partidas", {})


                if isinstance(partidas_agrupadas, dict):
                    for fase_nome, fases_ou_rodadas in partidas_agrupadas.items():
                        if isinstance(fases_ou_rodadas, dict):
                            for rodada_nome, lista_jogos in fases_ou_rodadas.items():
                                if isinstance(lista_jogos, list):
                                    for j in lista_jogos:
                                        p_id = j.get("partida_id")
                                        if not p_id or p_id in ids_partidas_processadas:
                                            continue

                                        d_iso = j.get("data_realizacao_iso") or ""
                                        d_br = j.get("data_realizacao") or ""

                                        if d_iso.startswith(target_date) or d_br == target_date_br:
                                            ids_partidas_processadas.add(p_id)

                                            j_enriquecido = dict(j)
                                            if not j_enriquecido.get("campeonato"):
                                                j_enriquecido["campeonato"] = campeonato_meta
                                            if not j_enriquecido.get("rodada"):
                                                j_enriquecido["rodada"] = rodada_nome
                                            partidas_encontradas.append(j_enriquecido)

            except Exception as exc:
                erros_coletados[f"camp_{camp_id}"] = str(exc)


        await app_cache.set(cache_key, partidas_encontradas, ttl_seconds=CACHE_TTL_FIXTURES_SECONDS)

        return {
            "source": "api_futebol",
            "data": partidas_encontradas,
            "total": len(partidas_encontradas),
            "is_cached": False,
            "errors": erros_coletados
        }

    async def obter_status_conexao(self) -> Dict[str, Any]:
        """Retorna o estado de saúde e plano da API-Futebol sem queimar requisições desnecessárias."""
        if not is_api_futebol_configured():
            return {"status": "chave_pendente", "configurado": False}

        if time.time() < self._cooldown_until:
            return {
                "status": "rate_limit_429",
                "configurado": True,
                "cooldown_segundos": int(self._cooldown_until - time.time())
            }

        try:
            me = await self.get_me()
            if isinstance(me, dict) and me.get("nome"):
                return {
                    "status": "online",
                    "configurado": True,
                    "conta": me.get("nome"),
                    "plano": me.get("plano", {}).get("nome", "Ativo")
                }
        except Exception as e:
            return {"status": "erro", "configurado": True, "erro": str(e)}

        return {"status": "online", "configurado": True}


api_futebol_client = ApiFutebolClient()
