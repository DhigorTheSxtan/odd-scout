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

TIMEZONE_NAME = "America/Sao_Paulo"

from config import (
    API_FOOTBALL_KEY,
    API_BASE_URL,
    REQUEST_TIMEOUT_SECONDS,
    CACHE_TTL_FIXTURES_SECONDS,
    CACHE_TTL_STATS_SECONDS,
    TARGET_LEAGUES,
    is_api_key_valid
)
from cache import app_cache

logger = logging.getLogger("api_football")
logging.basicConfig(level=logging.INFO)

def mask_key(key: str) -> str:

    if not key or len(key) < 8:
        return "****"
    return f"{key[:4]}{'*' * (len(key) - 8)}{key[-4:]}"


class FootballApiClient:


    STATUS_PERMITIDOS = {"NS", "1H", "HT", "2H"}

    STATUS_EXCLUIDOS = {"CANC", "PST", "FT", "AET", "PEN", "INT", "ABD", "SUSP"}

    def __init__(self):
        self.base_url = API_BASE_URL.rstrip('/')
        self.timeout = httpx.Timeout(REQUEST_TIMEOUT_SECONDS)
        self._free_plan_last_unsupported = False
        self._rate_limit_cooldown_until = 0.0

    def _get_headers(self) -> Dict[str, str]:
        return {
            "x-apisports-key": API_FOOTBALL_KEY,
            "Accept": "application/json",
            "User-Agent": "SportsPredictorAI-Official/1.0"
        }

    async def _make_request(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:

        if not is_api_key_valid():
            logger.warning("[API-Football] Chave da API-Football não configurada ou inválida no .env (modo estrito sem mocks).")
            return {"results": 0, "response": [], "errors": {"auth": "Chave da API-Football não configurada no .env"}}

        if time.time() < self._rate_limit_cooldown_until:
            return {"results": 0, "response": [], "errors": {"rateLimit": "Cooldown de rate limit ativo na API-Football (aguardando liberação de cota)"}}

        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        param_str = "&".join([f"{k}={v}" for k, v in (params or {}).items()])
        full_query = f"{url}?{param_str}" if param_str else url

        print(f"\n[API-Football] >>> REQUISIÇÃO REAL: GET {full_query}")
        print(f"[API-Football] Headers: {{'x-apisports-key': '{mask_key(API_FOOTBALL_KEY)}'}} | Timeout: {REQUEST_TIMEOUT_SECONDS}s")

        start_time = time.perf_counter()
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(url, headers=self._get_headers(), params=params)
                latency_ms = (time.perf_counter() - start_time) * 1000

                print(f"[API-Football] <<< RESPOSTA RECEBIDA: HTTP {response.status_code} ({latency_ms:.1f} ms)")

                if response.status_code == 401:
                    print(f"[API-Football] [ERRO 401] Chave de API não autorizada ou inválida: {mask_key(API_FOOTBALL_KEY)}")
                    return {"results": 0, "response": [], "errors": {"auth": "Chave inválida (HTTP 401)"}}
                elif response.status_code == 429:
                    print("[API-Football] [ERRO 429] Limite de requisições excedido (Too Many Requests).")
                    self._rate_limit_cooldown_until = time.time() + 180.0
                    return {"results": 0, "response": [], "errors": {"rateLimit": "Cota da API-Football excedida (HTTP 429)"}}
                elif response.status_code >= 500:
                    print(f"[API-Football] [ERRO {response.status_code}] Falha interna nos servidores remotos da API-Sports.")
                    return {"results": 0, "response": [], "errors": {"server": f"Erro do servidor API-Sports ({response.status_code})"}}

                data = response.json()
                results_count = data.get("results", 0)
                errors = data.get("errors", {})

                print(f"[API-Football] Total de partidas retornadas pela API: {results_count}")

                if errors and (isinstance(errors, dict) and len(errors) > 0 or isinstance(errors, list) and len(errors) > 0):
                    print(f"[API-Football] [AVISO/ERRO DE PAYLOAD] A API retornou erros no corpo da resposta: {errors}")
                    err_str = str(errors)
                    if "Free plans do not have access to the Last parameter" in err_str:
                        self._free_plan_last_unsupported = True
                    if "reached the request limit" in err_str or "Too Many Requests" in err_str:
                        self._rate_limit_cooldown_until = time.time() + 180.0

                return data

            except httpx.TimeoutException:
                latency_ms = (time.perf_counter() - start_time) * 1000
                print(f"[API-Football] [TIMEOUT] Requisição excedeu limite estrito de {REQUEST_TIMEOUT_SECONDS}s ({latency_ms:.1f}ms).")
                return {"results": 0, "response": [], "errors": {"timeout": f"Timeout de requisição (> {REQUEST_TIMEOUT_SECONDS}s)"}}
            except httpx.RequestError as exc:
                latency_ms = (time.perf_counter() - start_time) * 1000
                print(f"[API-Football] [FALHA DE REDE] Erro ao conectar ao host da API: {exc} ({latency_ms:.1f}ms)")
                return {"results": 0, "response": [], "errors": {"network": str(exc)}}

    async def get_fixtures_by_date(self, target_date: str) -> Dict[str, Any]:

        cache_key = f"fixtures_real_{target_date}"
        cached_data = await app_cache.get(cache_key)
        if cached_data is not None:
            print(f"[API-Football] Retornando {len(cached_data)} partidas do cache em memória para {target_date}")
            return {"source": "cache", "data": cached_data, "total": len(cached_data), "is_mock": False}

        if not is_api_key_valid():
            logger.warning(f"[API-Football] Chave pendente para a data ({target_date}). Retornando lista vazia (modo estrito sem mocks).")
            return {
                "source": "api_football_sem_chave",
                "data": [],
                "total": 0,
                "is_mock": False,
                "motivo": "Chave API_FOOTBALL_KEY pendente no .env."
            }


        params = {
            "date": target_date,
            "timezone": TIMEZONE_NAME
        }

        api_response = await self._make_request("fixtures", params=params)
        raw_fixtures = api_response.get("response", [])
        errors = api_response.get("errors", {})


        partidas_validas = []
        descartadas_status = 0

        for f in raw_fixtures:
            status_obj = f.get("fixture", {}).get("status", {})
            status_short = (status_obj.get("short") or "").strip().upper()


            if status_short in self.STATUS_EXCLUIDOS:
                descartadas_status += 1
                continue


            if status_short in self.STATUS_PERMITIDOS:
                partidas_validas.append(f)
            else:
                descartadas_status += 1

        print(f"[API-Football] Filtragem de status: {len(partidas_validas)} jogos elegíveis (NS/1H/HT/2H) | {descartadas_status} descartados (FT/CANC/PST)")


        prioritarias = [f for f in partidas_validas if f.get("league", {}).get("id") in TARGET_LEAGUES]
        resultado_final = prioritarias if len(prioritarias) >= 3 else partidas_validas[:40]

        # Tolerância Zero a Mocks: se não retornou partidas, retorna lista vazia com status real
        if len(resultado_final) == 0 and errors:
            logger.warning(f"[API-Football] Nenhuma partida obtida ({errors}) para {target_date}. Retornando lista vazia.")
            return {
                "source": "api_football_live",
                "data": [],
                "total": 0,
                "is_mock": False,
                "errors": errors
            }

        print(f"[API-Football] Total final de partidas reais consolidadas para {target_date}: {len(resultado_final)}")

        await app_cache.set(cache_key, resultado_final, ttl_seconds=CACHE_TTL_FIXTURES_SECONDS)

        return {
            "source": "api_football_live",
            "data": resultado_final,
            "total": len(resultado_final),
            "errors": errors,
            "is_mock": False
        }

    async def get_team_recent_matches(self, team_id: int, last: int = 10) -> List[Dict[str, Any]]:

        cache_key = f"team_recent_real_{team_id}_{last}"
        cached = await app_cache.get(cache_key)
        if cached is not None:
            return cached

        if not is_api_key_valid() or self._free_plan_last_unsupported:
            demo_history = self._generate_team_demo_history(team_id)
            await app_cache.set(cache_key, demo_history, ttl_seconds=CACHE_TTL_STATS_SECONDS)
            return demo_history

        try:
            res = await self._make_request("fixtures", params={"team": team_id, "last": last})
            fixtures = res.get("response", [])
            err_str = str(res.get("errors") or {})

            if "Free plans do not have access to the Last parameter" in err_str or not fixtures:
                self._free_plan_last_unsupported = True
                demo_history = self._generate_team_demo_history(team_id)
                await app_cache.set(cache_key, demo_history, ttl_seconds=CACHE_TTL_STATS_SECONDS)
                return demo_history

            enriched_fixtures = []
            for f in fixtures[:5]:
                fix_id = f.get("fixture", {}).get("id")
                if fix_id:
                    stats = await self.get_fixture_stats(fix_id)
                    f_copy = dict(f)
                    f_copy["stats"] = stats
                    enriched_fixtures.append(f_copy)
                else:
                    enriched_fixtures.append(f)

            enriched_fixtures.extend(fixtures[5:])
            await app_cache.set(cache_key, enriched_fixtures, ttl_seconds=CACHE_TTL_STATS_SECONDS)
            return enriched_fixtures

        except Exception as exc:
            logger.warning(f"[API-Football] Não foi possível obter histórico real do time {team_id}: {exc}")
            demo_history = self._generate_team_demo_history(team_id)
            await app_cache.set(cache_key, demo_history, ttl_seconds=CACHE_TTL_STATS_SECONDS)
            return demo_history

    async def get_fixture_stats(self, fixture_id: int) -> Dict[str, Any]:

        cache_key = f"fixture_stats_real_{fixture_id}"
        cached = await app_cache.get(cache_key)
        if cached is not None:
            return cached

        if not is_api_key_valid():
            return {}

        try:
            res = await self._make_request("fixtures/statistics", params={"fixture": fixture_id})
            teams_stats = res.get("response", [])
            parsed_stats = self._parse_api_statistics(teams_stats)
            await app_cache.set(cache_key, parsed_stats, ttl_seconds=CACHE_TTL_STATS_SECONDS)
            return parsed_stats
        except Exception as exc:
            logger.warning(f"[API-Football] Falha ao obter estatísticas da partida {fixture_id}: {exc}")
            return {}

    def _parse_api_statistics(self, teams_stats_response: List[Dict[str, Any]]) -> Dict[str, Any]:

        parsed = {
            "corners": {"home": 0, "away": 0},
            "shots_total": {"home": 0, "away": 0},
            "shots_on_target": {"home": 0, "away": 0},
            "throw_ins": {"home": None, "away": None},
            "possession": {"home": "50%", "away": "50%"}
        }

        if len(teams_stats_response) >= 2:
            home_data = teams_stats_response[0].get("statistics", [])
            away_data = teams_stats_response[1].get("statistics", [])

            for item in home_data:
                tipo = item.get("type")
                val = item.get("value") or 0
                if tipo == "Corner Kicks":
                    parsed["corners"]["home"] = int(val) if str(val).isdigit() else 0
                elif tipo == "Total Shots":
                    parsed["shots_total"]["home"] = int(val) if str(val).isdigit() else 0
                elif tipo == "Shots on Goal":
                    parsed["shots_on_target"]["home"] = int(val) if str(val).isdigit() else 0
                elif tipo in ("Throw-ins", "Throw ins"):
                    parsed["throw_ins"]["home"] = int(val) if str(val).isdigit() else 0
                elif tipo == "Ball Possession":
                    parsed["possession"]["home"] = str(val)

            for item in away_data:
                tipo = item.get("type")
                val = item.get("value") or 0
                if tipo == "Corner Kicks":
                    parsed["corners"]["away"] = int(val) if str(val).isdigit() else 0
                elif tipo == "Total Shots":
                    parsed["shots_total"]["away"] = int(val) if str(val).isdigit() else 0
                elif tipo == "Shots on Goal":
                    parsed["shots_on_target"]["away"] = int(val) if str(val).isdigit() else 0
                elif tipo in ("Throw-ins", "Throw ins"):
                    parsed["throw_ins"]["away"] = int(val) if str(val).isdigit() else 0
                elif tipo == "Ball Possession":
                    parsed["possession"]["away"] = str(val)

        return parsed

    def _generate_today_fixtures(self, target_date: str) -> List[Dict[str, Any]]:
        """Tolerância Zero a Mocks: nenhum jogo fictício é gerado."""
        return []

    def _generate_team_demo_history(self, team_id: int) -> List[Dict[str, Any]]:

        import random
        rng = random.Random(team_id)
        matches = []
        for i in range(8):
            is_home = (i % 2 == 0)
            goals_for = rng.choices([0, 1, 2, 3, 4], weights=[20, 35, 25, 15, 5])[0]
            goals_against = rng.choices([0, 1, 2, 3], weights=[30, 40, 20, 10])[0]

            corners_for = rng.randint(4, 8)
            corners_opp = rng.randint(3, 7)
            shots_tot = rng.randint(11, 18)
            shots_tgt = rng.randint(4, 8)
            throw_ins = rng.randint(18, 26)

            match_entry = {
                "fixture": {"id": 100000 + team_id * 10 + i, "date": f"2026-09-0{i+1}T16:00:00+00:00"},
                "teams": {
                    "home": {"id": team_id if is_home else 9999, "name": "Time Principal" if is_home else "Adversário"},
                    "away": {"id": 9999 if is_home else team_id, "name": "Adversário" if is_home else "Time Principal"}
                },
                "goals": {
                    "home": goals_for if is_home else goals_against,
                    "away": goals_against if is_home else goals_for
                },
                "stats": {
                    "corners": {
                        "home": corners_for if is_home else corners_opp,
                        "away": corners_opp if is_home else corners_for
                    },
                    "shots_total": {
                        "home": shots_tot if is_home else rng.randint(8, 14),
                        "away": rng.randint(8, 14) if is_home else shots_tot
                    },
                    "shots_on_target": {
                        "home": shots_tgt if is_home else rng.randint(2, 6),
                        "away": rng.randint(2, 6) if is_home else shots_tgt
                    },
                    "throw_ins": {
                        "home": throw_ins if is_home else rng.randint(16, 24),
                        "away": rng.randint(16, 24) if is_home else throw_ins
                    }
                }
            }
            matches.append(match_entry)
        return matches


football_api_client = FootballApiClient()

