"""
sharpapi_service.py - Cliente Assíncrono Oficial da SharpAPI (https://api.sharpapi.io/api/v1)
Desenvolvido estritamente para consulta de partidas e cotações reais da NFL (Futebol Americano).
Em conformidade com as diretrizes:
- Exclusividade para NFL (sport="football", league="nfl").
- Rate limiting automático de 12 requisições por minuto com sliding window.
- Cache inteligente em memória com TTL configurável.
- Tratamento de status online, bookmakers (DraftKings, FanDuel) e mapeamento em PT-BR.
"""

import os
import logging
import asyncio
import time
import unicodedata
import re
import difflib
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional, Tuple

try:
    from zoneinfo import ZoneInfo
    TIMEZONE_BR = ZoneInfo("America/Sao_Paulo")
except Exception:
    TIMEZONE_BR = timezone(timedelta(hours=-3))

import httpx

import config
from config import (
    SHARPAPI_KEY,
    SHARPAPI_BASE_URL,
    CACHE_TTL_SHARPAPI_SECONDS,
    REQUEST_TIMEOUT_SECONDS,
    is_sharpapi_configured,
)
from cache import app_cache

logger = logging.getLogger("sharpapi_service")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)


def mask_key(key: str) -> str:
    """Oculta a maior parte da chave para logs seguros."""
    if not key or len(key) < 10:
        return "***"
    return f"{key[:7]}...{key[-4:]}"


class SharpApiRateLimiter:
    """
    Controlador de Taxa de Requisições da SharpAPI.
    Garante respeito ao plano gratuito de no máximo 12 req/min (janela deslizante de 60 segundos).
    """

    def __init__(self, max_requests: int = 12, window_seconds: float = 60.0):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._timestamps: List[float] = []
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.time()
            # Remove timestamps mais antigos que a janela
            self._timestamps = [ts for ts in self._timestamps if now - ts < self.window_seconds]

            if len(self._timestamps) >= self.max_requests:
                oldest = self._timestamps[0]
                wait_time = self.window_seconds - (now - oldest) + 0.1
                if wait_time > 0:
                    logger.warning(
                        f"[SharpAPI] Limite de {self.max_requests} req/min atingido. Throttling ativo: aguardando {wait_time:.2f}s..."
                    )
                    await asyncio.sleep(wait_time)
                    now = time.time()
                    self._timestamps = [ts for ts in self._timestamps if now - ts < self.window_seconds]

            self._timestamps.append(time.time())


class SharpApiService:
    """
    Serviço central de integração à API oficial da SharpAPI.
    Especializado no ecossistema da NFL (DraftKings e FanDuel).
    """

    def __init__(self):
        base = SHARPAPI_BASE_URL or "https://api.sharpapi.io/api/v1"
        self.base_url = base.rstrip("/")
        self.rate_limiter = SharpApiRateLimiter(max_requests=12, window_seconds=60.0)
        self._cooldown_until = 0.0

    def _get_key(self) -> str:
        """Obtém a chave da SharpAPI dinamicamente."""
        return (config.SHARPAPI_KEY or os.getenv("SHARPAPI_KEY", "")).strip()

    def _get_headers(self) -> Dict[str, str]:
        """Gera os headers oficiais exigidos pela SharpAPI."""
        return {
            "X-API-Key": self._get_key(),
            "Accept": "application/json",
            "User-Agent": "SportsPredictorSharpAPI/1.0"
        }

    @classmethod
    def normalizar_nome_equipe(cls, nome: str) -> str:
        """Remove acentos, caracteres especiais e palavras de parada para comparação fuzzy."""
        if not nome:
            return ""
        nfkd = unicodedata.normalize("NFKD", nome)
        sem_acento = "".join([c for c in nfkd if not unicodedata.combining(c)])
        limpo = re.sub(r"[^\w\s]", " ", sem_acento.lower())
        tokens = [p.strip() for p in limpo.split() if p.strip()]
        return " ".join(tokens)

    @classmethod
    def calcular_similaridade(cls, nome_a: str, nome_b: str) -> float:
        """Calcula similaridade textual entre nomes de equipes."""
        na = cls.normalizar_nome_equipe(nome_a)
        nb = cls.normalizar_nome_equipe(nome_b)
        if not na or not nb:
            return 0.0
        if na == nb or na in nb or nb in na:
            return 1.0
        return difflib.SequenceMatcher(None, na, nb).ratio()

    async def _make_request(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Executa requisição HTTP assíncrona com controle de concorrência e cooldown."""
        if not is_sharpapi_configured():
            logger.warning("[SharpAPI] Chave SHARPAPI_KEY não configurada no .env.")
            return {
                "status_code": 401,
                "data": [],
                "errors": {"auth": "Chave SHARPAPI_KEY pendente no .env"}
            }

        now = time.time()
        if now < self._cooldown_until:
            tempo_espera = self._cooldown_until - now
            return {
                "status_code": 429,
                "data": [],
                "errors": {"rateLimit": f"Cooldown ativo da SharpAPI (aguarde {tempo_espera:.1f}s)"}
            }

        await self.rate_limiter.acquire()

        clean_endpoint = endpoint.lstrip("/")
        url = f"{self.base_url}/{clean_endpoint}"
        start_time = time.time()

        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
                response = await client.get(url, headers=self._get_headers(), params=params)
                latency_ms = int((time.time() - start_time) * 1000)

                if response.status_code == 200:
                    data = response.json()
                    items = data.get("data", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
                    return {
                        "status_code": 200,
                        "data": items,
                        "raw": data,
                        "latency_ms": latency_ms
                    }

                elif response.status_code == 401:
                    logger.error(f"[SharpAPI] [ERRO 401] Chave de API inválida ou não autorizada: {mask_key(self._get_key())}")
                    return {
                        "status_code": 401,
                        "data": [],
                        "errors": {"auth": "Chave da SharpAPI inválida ou expirada (HTTP 401)"},
                        "latency_ms": latency_ms
                    }

                elif response.status_code == 429:
                    logger.warning("[SharpAPI] [ERRO 429] Limite de 12 req/min atingido. Ativando cooldown de 30s.")
                    self._cooldown_until = time.time() + 30.0
                    return {
                        "status_code": 429,
                        "data": [],
                        "errors": {"rateLimit": "Limite de taxa atingido na SharpAPI (HTTP 429)"},
                        "latency_ms": latency_ms
                    }

                else:
                    logger.error(f"[SharpAPI] [ERRO {response.status_code}] Falha interna nos servidores da SharpAPI.")
                    return {
                        "status_code": response.status_code,
                        "data": [],
                        "errors": {"server": f"Erro do servidor SharpAPI ({response.status_code})"},
                        "latency_ms": latency_ms
                    }

        except httpx.TimeoutException:
            latency_ms = int((time.time() - start_time) * 1000)
            logger.warning(f"[SharpAPI] Timeout de {REQUEST_TIMEOUT_SECONDS}s excedido ({latency_ms}ms).")
            return {
                "status_code": 408,
                "data": [],
                "errors": {"timeout": "Timeout de requisição"},
                "latency_ms": latency_ms
            }

        except Exception as exc:
            latency_ms = int((time.time() - start_time) * 1000)
            logger.error(f"[SharpAPI] Erro de transporte HTTP: {exc}")
            return {
                "status_code": 500,
                "data": [],
                "errors": {"network": str(exc)},
                "latency_ms": latency_ms
            }

    async def buscar_odds(
        self,
        sport: Optional[str] = None,
        league: Optional[str] = None,
        market_type: Optional[str] = None,
        force_refresh: bool = False
    ) -> Dict[str, Any]:
        """Consulta cotações na SharpAPI com suporte a filtros e cache em memória."""
        cache_key = f"sharpapi_odds_{sport or 'all'}_{league or 'all'}_{market_type or 'all'}"
        if not force_refresh:
            cached = await app_cache.get(cache_key)
            if cached:
                return cached

        params: Dict[str, Any] = {}
        if sport:
            params["sport"] = sport
        if league:
            params["league"] = league
        if market_type:
            params["market_type"] = market_type

        res = await self._make_request("odds", params=params)
        items = res.get("data", [])

        resultado = {
            "status": "success" if res.get("status_code") == 200 else "error",
            "status_code": res.get("status_code", 500),
            "provedor": "SharpAPI (https://api.sharpapi.io/api/v1)",
            "total_odds": len(items),
            "odds": items,
            "filtros": {"sport": sport, "league": league, "market_type": market_type},
            "timestamp": datetime.now(TIMEZONE_BR).isoformat()
        }

        if res.get("status_code") == 200:
            ttl = CACHE_TTL_SHARPAPI_SECONDS or 300
            await app_cache.set(cache_key, resultado, ttl_seconds=ttl)

        return resultado

    async def buscar_odds_nfl(self, force_refresh: bool = False) -> Dict[str, Any]:
        """Obtém e consolida cotações reais da NFL dos bookmakers DraftKings e FanDuel."""
        raw_res = await self.buscar_odds(league="nfl", force_refresh=force_refresh)
        odds_list = raw_res.get("odds", [])

        confrontos: Dict[str, Any] = {}
        for item in odds_list:
            home = item.get("home_team") or (item.get("home") or {}).get("name", "")
            away = item.get("away_team") or (item.get("away") or {}).get("name", "")
            if not home or not away:
                continue

            sportsbook = (item.get("sportsbook") or "sharpapi").title()
            if sportsbook.lower() == "draftkings":
                sportsbook = "DraftKings"
            elif sportsbook.lower() == "fanduel":
                sportsbook = "FanDuel"

            market_type = str(item.get("market_type", "")).lower()
            selection = item.get("selection", "")
            odd_dec = float(item.get("odds_decimal", 0.0) or 0.0)
            line = item.get("line")
            is_main = bool(item.get("is_main_line", True))

            match_key = f"{home} vs {away}"
            if match_key not in confrontos:
                confrontos[match_key] = {
                    "mandante": home,
                    "visitante": away,
                    "start_time": item.get("event_start_time") or item.get("timestamp"),
                    "bookmakers": {
                        "DraftKings": {"moneyline": {"casa": None, "fora": None}},
                        "FanDuel": {"moneyline": {"casa": None, "fora": None}}
                    },
                    "mercados": {
                        "moneyline": {},
                        "spreads": [],
                        "totais": []
                    }
                }

            match_data = confrontos[match_key]
            if sportsbook not in match_data["bookmakers"]:
                match_data["bookmakers"][sportsbook] = {"moneyline": {"casa": None, "fora": None}}

            if market_type == "moneyline" or "moneyline" in market_type:
                team_side = item.get("team_side") or ("casa" if home in selection else "fora")
                match_data["bookmakers"][sportsbook]["moneyline"][team_side] = odd_dec
                match_data["mercados"]["moneyline"][f"{sportsbook}_{team_side}"] = {
                    "selecao": selection,
                    "odd": odd_dec,
                    "sportsbook": sportsbook
                }

            elif "spread" in market_type:
                match_data["mercados"]["spreads"].append({
                    "sportsbook": sportsbook,
                    "selecao": selection,
                    "linha": line,
                    "odd": odd_dec,
                    "is_main_line": is_main
                })

            elif "total" in market_type:
                match_data["mercados"]["totais"].append({
                    "sportsbook": sportsbook,
                    "selecao": selection,
                    "linha": line,
                    "odd": odd_dec,
                    "is_main_line": is_main
                })

        return {
            "status": "success",
            "provedor": "SharpAPI NFL",
            "casas_mapeadas": ["DraftKings", "FanDuel"],
            "total_confrontos": len(confrontos),
            "confrontos": confrontos,
            "raw_items_count": len(odds_list),
            "timestamp": datetime.now(TIMEZONE_BR).isoformat()
        }

    async def buscar_odds_futebol(self, league: Optional[str] = None, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Método de retrocompatibilidade.
        Nota: A SharpAPI está configurada para atuar EXCLUSIVAMENTE na NFL.
        Futebol é coberto com precisão pelo OwlsInsight.
        """
        return await self.buscar_odds(sport="soccer", league=league, force_refresh=force_refresh)

    async def obter_esportes(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """Obtém lista de esportes suportados pela SharpAPI."""
        cache_key = "sharpapi_sports_list"
        if not force_refresh:
            cached = await app_cache.get(cache_key)
            if cached:
                return cached

        res = await self._make_request("sports")
        data = res.get("data", [])
        if res.get("status_code") == 200:
            await app_cache.set(cache_key, data, ttl_seconds=14400)
        return data

    async def obter_ligas(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """Obtém lista de ligas suportadas pela SharpAPI."""
        cache_key = "sharpapi_leagues_list"
        if not force_refresh:
            cached = await app_cache.get(cache_key)
            if cached:
                return cached

        res = await self._make_request("leagues")
        data = res.get("data", [])
        if res.get("status_code") == 200:
            await app_cache.set(cache_key, data, ttl_seconds=14400)
        return data

    async def obter_status_conexao(self) -> Dict[str, Any]:
        """Verifica a conectividade e saúde da credencial SharpAPI."""
        if not is_sharpapi_configured():
            return {
                "status": "chave_pendente",
                "configurado": False,
                "provedor": "SharpAPI",
                "mensagem": "Chave SHARPAPI_KEY não configurada no .env"
            }

        cache_key = "sharpapi_status_check"
        cached = await app_cache.get(cache_key)
        if cached:
            return cached

        res = await self._make_request("odds", params={"limit": 1})
        is_online = (res.get("status_code") == 200)

        status_info = {
            "status": "online" if is_online else "alerta",
            "configurado": True,
            "provedor": "SharpAPI (https://api.sharpapi.io/api/v1)",
            "status_code": res.get("status_code"),
            "plano": "Free (12 req/min)",
            "casas_suportadas": ["DraftKings", "FanDuel"],
            "latencia_ms": res.get("latency_ms", 0),
            "erros": res.get("errors", {}),
            "timestamp": datetime.now(TIMEZONE_BR).isoformat()
        }

        if is_online:
            await app_cache.set(cache_key, status_info, ttl_seconds=300)

        return status_info

    async def encontrar_odds_confronto(
        self,
        home_team: str,
        away_team: str,
        sport: Optional[str] = None,
        league: Optional[str] = "nfl"
    ) -> Optional[Dict[str, Any]]:
        """Cruza um confronto mandante vs visitante com as odds disponíveis na SharpAPI."""
        odds_pack = await self.buscar_odds(sport=sport, league=league)
        items = odds_pack.get("odds", [])
        if not items:
            return None

        melhor_match = None
        for it in items:
            it_home = it.get("home_team") or (it.get("home") or {}).get("name", "")
            it_away = it.get("away_team") or (it.get("away") or {}).get("name", "")
            sim_home = self.calcular_similaridade(home_team, it_home)
            sim_away = self.calcular_similaridade(away_team, it_away)

            if sim_home >= 0.7 and sim_away >= 0.7:
                sb = (it.get("sportsbook") or "sharpapi").title()
                if not melhor_match:
                    melhor_match = {
                        "mandante": it_home,
                        "visitante": it_away,
                        "mercados": [],
                        "casas": set()
                    }
                melhor_match["casas"].add(sb)
                melhor_match["mercados"].append({
                    "sportsbook": sb,
                    "mercado": it.get("market_type"),
                    "selecao": it.get("selection"),
                    "odd": it.get("odds_decimal"),
                    "linha": it.get("line")
                })

        if melhor_match:
            melhor_match["casas"] = list(melhor_match["casas"])
            melhor_match["total_cotacoes"] = len(melhor_match["mercados"])
            return melhor_match

        return None


# Instância Singleton Exportada
sharpapi_service = SharpApiService()
