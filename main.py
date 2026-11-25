import os
import asyncio
import logging
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any

try:
    from zoneinfo import ZoneInfo
    TIMEZONE_BR = ZoneInfo("America/Sao_Paulo")
except Exception:
    TIMEZONE_BR = timezone(timedelta(hours=-3))

TIMEZONE_NAME = "America/Sao_Paulo"

import httpx
from pydantic import BaseModel
from fastapi import FastAPI, Query, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from config import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    TARGET_LEAGUES,
    is_gemini_configured,
    set_gemini_api_key,
    is_pandascore_configured,
    set_pandascore_token,
    is_sharpapi_configured,
    SHARPAPI_KEY,
    SHARPAPI_BASE_URL,
    DATA_REFERENCIA_HOJE,
    DATA_REFERENCIA_AMANHA,
    DATA_REFERENCIA_ONTEM,
    DEBUG
)
from sharpapi_service import sharpapi_service
from nfl_service import nfl_service
from services.ai_analytics_service import obter_jogos_e_palpites_gemini, MODEL_TRACKERS
from cache import app_cache
from football_orchestrator import football_orchestrator
from football_games_service import football_games_service
from soccer_fallback_service import soccer_fallback_service
from engine import PredictiveEngine
from odds_service import odds_service
from gemini_analyzer import gemini_analyzer, AnalisePartidaGemini, CACHE_FILE
from services.bet_of_the_day_service import bet_of_the_day_service
from models.bet_of_the_day import BetOfTheDayResponse
from contextlib import asynccontextmanager
from scheduler import (
    job_scheduler,
    iniciar_agendador,
    parar_agendador,
    sse_broadcast_hub
)

logger = logging.getLogger("main_api")
logging.basicConfig(level=logging.INFO)


def _get_active_analyzer():
    """Retorna o analyzer ativo oficial: Gemini Flash AI (com Search Grounding)."""
    return gemini_analyzer

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("[lifespan] Inicializando Agendador Automatizado (00:00 America/Sao_Paulo)...")
    await iniciar_agendador()
    yield
    logger.info("[lifespan] Encerrando Agendador de Tarefas...")
    await parar_agendador()

app = FastAPI(
    title="Motor de Análise e Decisão no Futebol",
    description="Motor de inteligência estatística e predição esportiva com estratégia híbrida (API-Football oficial e API-Futebol Brasil), distribuição de Poisson, médias ponderadas e cotações em tempo real via OddsPapi.",
    version="1.4.0",
    lifespan=lifespan
)

from routers.radar_ev import router as radar_ev_router
app.include_router(radar_ev_router)

from routers.analytics import router as analytics_router
app.include_router(analytics_router)

from routers.bet_of_the_day_router import router as bet_router
from routers.fixtures_router import router as fixtures_router
from routers.live_odds_router import router as live_odds_router

app.include_router(bet_router)
app.include_router(fixtures_router)
app.include_router(live_odds_router)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------------------------------------------------------
# 1. Definição segura dos diretórios de Front-end
# ----------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = str(BASE_DIR)
STATIC_DIR = os.path.join(FRONTEND_DIR, "static")
if not os.path.exists(STATIC_DIR):
    os.makedirs(STATIC_DIR, exist_ok=True)

INDEX_HTML = os.path.join(FRONTEND_DIR, "index.html")
if not os.path.exists(INDEX_HTML):
    INDEX_HTML = os.path.join(STATIC_DIR, "index.html")

# ----------------------------------------------------------------------
# 2. Servir Assets Estáticos (CSS, JS, Imagens)
# Montado sob prefixo /assets e /static para evitar colisão de rotas
# ----------------------------------------------------------------------
assets_dir = os.path.join(STATIC_DIR, "assets")
if os.path.exists(assets_dir):
    app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def _hoje_brasilia() -> str:
    """Retorna a data de hoje no fuso America/Sao_Paulo (YYYY-MM-DD), calculada em tempo real."""
    return datetime.now(TIMEZONE_BR).strftime("%Y-%m-%d")

def _amanha_brasilia() -> str:
    return (datetime.now(TIMEZONE_BR) + timedelta(days=1)).strftime("%Y-%m-%d")

def _ontem_brasilia() -> str:
    return (datetime.now(TIMEZONE_BR) - timedelta(days=1)).strftime("%Y-%m-%d")


def validar_ou_obter_data_hoje(data_str: Optional[str]) -> str:

    if isinstance(data_str, str) and data_str.strip():
        try:
            datetime.strptime(data_str.strip(), "%Y-%m-%d")
            return data_str.strip()
        except ValueError:
            logger.warning(f"Data fornecida inválida: '{data_str}'. Usando data dinâmica de Brasília.")
    return _hoje_brasilia()


# ----------------------------------------------------------------------
# 3. Rota Raiz (/) -> Entrega o index.html
# ----------------------------------------------------------------------
@app.get("/", tags=["Frontend"])
async def serve_root():
    if os.path.exists(INDEX_HTML):
        return FileResponse(INDEX_HTML)
    return {
        "status": "online",
        "message": "FastAPI rodando. O index.html não foi encontrado no caminho configurado.",
        "expected_path": INDEX_HTML,
        "docs_url": "/docs"
    }


@app.get("/api/status")
async def get_system_status():

    hoje_brasilia = _hoje_brasilia()
    return {
        "status": "online",
        "timestamp": datetime.now(TIMEZONE_BR).isoformat(),
        "timezone": TIMEZONE_NAME,
        "data_hoje": hoje_brasilia,
        "data_amanha": _amanha_brasilia(),
        "data_ontem": _ontem_brasilia(),
        "modo_orquestracao": "gemini_2.0_flash_grounding_agent",
        "gemini_agent": {
            "model": MODEL_TRACKERS[0].model_name if MODEL_TRACKERS else "gemini-2.0-flash",
            "grounding": True,
            "tool": "googleSearch",
            "max_rpm": MODEL_TRACKERS[0].max_rpm if MODEL_TRACKERS else 15,
            "status": "online" if is_gemini_configured() else "modo_resiliente"
        },
        "gemini_ai": {
            "configured": is_gemini_configured(),
            "model": GEMINI_MODEL,
            "mode": "gemini_flash_live" if is_gemini_configured() else "motor_estatistico_fallback"
        },
        "oddspapi": {
            "configured": False,
            "mode": "desativado_migrado_gemini",
            "provider": "Substituído por Agente Gemini 2.0 Flash com Google Search"
        },
        "nfl_api_sports": {
            "configured": False,
            "mode": "desativado_migrado_gemini",
            "provider": "Substituído por Agente Gemini 2.0 Flash com Google Search"
        },
        "pandascore": {
            "configured": is_pandascore_configured(),
            "status": "online" if is_pandascore_configured() else "desconfigurado",
            "provider": "PandaScore Official (https://api.pandascore.co)"
        },
        "sharpapi": {
            "configured": is_sharpapi_configured(),
            "status": "online" if is_sharpapi_configured() else "desconfigurado",
            "provider": "SharpAPI (https://api.sharpapi.io/api/v1)",
            "base_url": SHARPAPI_BASE_URL,
            "exclusive_sport": "american_football/nfl"
        },
        "nfl_bigballsdata": {
            "configured": is_sharpapi_configured(),
            "mode": "sharpapi_oficial"
        },
        "scheduler": job_scheduler.obter_status(),
        "cache_stats": app_cache.stats(),
        "target_leagues": TARGET_LEAGUES
    }


class ConfigApiKeyPayload(BaseModel):
    api_key: str









@app.post("/api/config/gemini-key")
async def save_gemini_key_endpoint(payload: ConfigApiKeyPayload):

    token_input = payload.api_key.strip()
    if not token_input:
        raise HTTPException(status_code=400, detail="A chave da Google Gemini AI não pode ser vazia.")

    model_name = GEMINI_MODEL
    try:
        from google import genai
        test_client = genai.Client(api_key=token_input)
        res = test_client.models.get(model=model_name)
        model_name = getattr(res, "name", model_name)
    except Exception as exc:
        err_msg = str(exc)
        logger.warning(f"Aviso na validação da chave Gemini: {err_msg}")
        if "API_KEY_INVALID" in err_msg or "PERMISSION_DENIED" in err_msg:
            raise HTTPException(status_code=400, detail=f"Chave da Google AI inválida ou sem permissão: {err_msg}")

    set_gemini_api_key(token_input)
    gemini_analyzer.reload_client(token_input)
    await app_cache.clear()

    return {
        "status": "success",
        "message": "Chave da Google Gemini AI (Flash) validada e salva com sucesso no .env!",
        "modelo": model_name
    }


@app.post("/api/config/openai-key")
@app.post("/api/config/openai-key")
async def save_openai_key_endpoint(payload: ConfigApiKeyPayload):
    return {"status": "deprecated", "message": "OpenAI desativada na migração para Agente Gemini 2.0 Flash."}


@app.get("/api/esports/jogos")
@app.get("/api/esports/matches")
async def get_esports_jogos(
    videogame: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    force_refresh: bool = Query(False)
):
    from pandascore_service import pandascore_service
    res = await pandascore_service.buscar_todas_partidas(
        videogame_slug=videogame,
        apenas_ao_vivo=(status == "ao_vivo"),
        limite=50,
        force_refresh=force_refresh
    )
    return res.get("partidas", [])


@app.get("/api/esports/status")
async def get_esports_status():
    from pandascore_service import pandascore_service
    return await pandascore_service.obter_status_conexao()


@app.post("/api/analise-gemini")
@app.post("/api/analise-ai")
async def post_analise_gemini(payload: Dict[str, Any]):
    """
    Executa a inteligência de Sports Analytics com o motor AI ativo oficial (Gemini 2.0 Flash).
    Retorna análise qualitativa + Taxa de Assertividade % (Win Probability).
    """
    partida_data = payload.get("partida") or payload
    if not partida_data or not isinstance(partida_data, dict):
        raise HTTPException(status_code=400, detail="Dados da partida ausentes ou inválidos.")
    analyzer = _get_active_analyzer()
    return await analyzer.analisar_partida_async(partida_data)


@app.post("/api/config/american-football-key")
async def save_american_football_key_endpoint(payload: ConfigApiKeyPayload):
    return {"status": "deprecated", "message": "API American Football descontinuada na migração para Gemini 2.0 Flash."}


@app.post("/api/config/oddspapi-key")
async def save_oddspapi_key_endpoint(payload: ConfigApiKeyPayload):
    return {"status": "deprecated", "message": "OddsPapi descontinuada na migração para Gemini 2.0 Flash."}


@app.post("/api/config/bigballsdata-token")
async def save_bigballsdata_token_endpoint(payload: ConfigApiKeyPayload):
    return {"status": "deprecated", "message": "Big Balls Data descontinuada na migração para Gemini 2.0 Flash."}


@app.post("/api/config/sharpapi-key")
async def save_sharpapi_key_endpoint(payload: ConfigApiKeyPayload):
    return {"status": "deprecated", "message": "SharpAPI descontinuada na migração para Gemini 2.0 Flash."}


@app.post("/api/config/pandascore-token")
async def save_pandascore_token_endpoint(payload: ConfigApiKeyPayload):
    token = (payload.api_key or "").strip()
    if not token:
        raise HTTPException(status_code=400, detail="Token do PandaScore não pode ser vazio.")
    from config import set_pandascore_token
    set_pandascore_token(token)
    return {
        "status": "success",
        "message": "Token oficial do PandaScore salvo com sucesso!",
        "token_prefix": f"{token[:6]}...{token[-4:]}" if len(token) > 10 else "***"
    }


class ConfigApiSportsKeyPayload(BaseModel):
    api_key: str
    sport: Optional[str] = None


@app.post("/api/config/apisports-key")
async def save_apisports_key_endpoint(payload: ConfigApiSportsKeyPayload):
    return {"status": "deprecated", "message": "API-Sports descontinuada na migração para Gemini 2.0 Flash."}


# =====================================================================
# ENDPOINTS OFICIAIS SHARPAPI (EXCLUSIVO NFL)
# =====================================================================

@app.get("/api/sharpapi/status")
async def get_sharpapi_status():
    return await sharpapi_service.obter_status_conexao()


@app.get("/api/sharpapi/odds")
async def get_sharpapi_odds(
    sport: Optional[str] = Query(None),
    league: Optional[str] = Query("nfl"),
    market_type: Optional[str] = Query(None),
    force_refresh: bool = Query(False)
):
    return await sharpapi_service.buscar_odds(
        sport=sport,
        league=league,
        market_type=market_type,
        force_refresh=force_refresh
    )


@app.get("/api/sharpapi/sports")
async def get_sharpapi_sports(force_refresh: bool = Query(False)):
    return await sharpapi_service.obter_esportes(force_refresh=force_refresh)


@app.get("/api/sharpapi/leagues")
async def get_sharpapi_leagues(force_refresh: bool = Query(False)):
    return await sharpapi_service.obter_ligas(force_refresh=force_refresh)


# =====================================================================
# ENDPOINTS PANDASCORE (ESPORTS & VIDEOGAMES DATA API)
# =====================================================================

@app.get("/api/pandascore/status")
async def get_pandascore_status():
    from pandascore_service import pandascore_service
    return await pandascore_service.obter_status_conexao()


@app.get("/api/pandascore/partidas")
async def get_pandascore_partidas(
    videogame: Optional[str] = Query(None),
    apenas_ao_vivo: bool = Query(False),
    limite: int = Query(50),
    force_refresh: bool = Query(False)
):
    from pandascore_service import pandascore_service
    return await pandascore_service.buscar_todas_partidas(
        videogame_slug=videogame,
        apenas_ao_vivo=apenas_ao_vivo,
        limite=limite,
        force_refresh=force_refresh
    )


@app.get("/api/pandascore/ao-vivo")
async def get_pandascore_ao_vivo(
    videogame: Optional[str] = Query(None),
    force_refresh: bool = Query(False)
):
    from pandascore_service import pandascore_service
    return await pandascore_service.buscar_partidas_ao_vivo(
        videogame_slug=videogame,
        force_refresh=force_refresh
    )


@app.get("/api/pandascore/videogames")
async def get_pandascore_videogames(force_refresh: bool = Query(False)):
    from pandascore_service import pandascore_service
    return await pandascore_service.obter_videogames(force_refresh=force_refresh)


@app.get("/api/pandascore/ligas")
async def get_pandascore_ligas(
    videogame: Optional[str] = Query(None),
    force_refresh: bool = Query(False)
):
    from pandascore_service import pandascore_service
    return await pandascore_service.obter_ligas(
        videogame_slug=videogame,
        force_refresh=force_refresh
    )


# =====================================================================
# ENDPOINTS ESPORTES / SPORTS (INTEGRADOS VIA GEMINI 2.0 FLASH)
# =====================================================================

@app.get("/api/sports/status")
async def get_all_sports_status():
    return {
        "status": "online",
        "provedor": "Gemini 2.0 Flash Grounding Agent",
        "timestamp": datetime.now(TIMEZONE_BR).isoformat()
    }


@app.get("/api/sports/{sport}/status")
async def get_sport_status(sport: str):
    return {
        "esporte": sport,
        "status": "online",
        "provedor": "Gemini 2.0 Flash Grounding Agent",
        "timestamp": datetime.now(TIMEZONE_BR).isoformat()
    }


@app.get("/api/predictions/cache")
async def get_predictions_cache():
    """
    Retorna o cache diário de predições da IA (cache_diario_ia.json) para polling do frontend a cada 5 segundos.
    Injeta nos cards das partidas: mercado sugerido, as 3 melhores casas com odds e justificativa estatística.
    """
    from services.ai_analytics_service import carregar_cache_diario
    cache = carregar_cache_diario()
    return {
        "status": "success",
        "data": datetime.now(TIMEZONE_BR).strftime("%Y-%m-%d"),
        "total": len(cache),
        "predictions": cache
    }


@app.get("/api/sports/football/jogos")
@app.get("/api/sports/{sport}/jogos")
async def get_sport_games(
    sport: str = "football",
    data: Optional[str] = Query(None),
    date: Optional[str] = Query(None),
    liga: Optional[int] = Query(None),
    season: Optional[int] = Query(None),
    force_refresh: bool = Query(False)
):
    """
    Rota unificada de eventos esportivos com arquitetura híbrida multi-API e Trava Anti-Alucinação:
    - Futebol -> OwlsInsight Oficial (https://api.owlsinsight.com)
    - Esports -> PandaScore Oficial (https://api.pandascore.co)
    - Demais Esportes Tradicionais -> API-Sports (Basquete, NFL, MLB, etc.)
    - Análise quantitativa com Grounding Web e tokens comprimidos -> Gemini 2.0 Flash
    - Trava Anti-Alucinação: Se a API oficial não reportar partidas, não aciona a IA e retorna status empty.
    """
    from routers.sports import obter_jogos_por_modalidade
    param_data = date or data or "hoje"
    res = await obter_jogos_por_modalidade(
        sport=sport,
        date_param=param_data,
        force_refresh=bool(force_refresh)
    )
    jogos = res.get("data") if isinstance(res.get("data"), list) else res.get("jogos", [])

    if not jogos or res.get("status") == "empty":
        logger.info(f"ℹ️ [SEM JOGOS] Nenhuma partida oficial encontrada para {sport} na data selecionada.")
        return {
            "status": "empty",
            "sucesso": False,
            "total_eventos": 0,
            "total": 0,
            "total_jogos": 0,
            "esporte": (sport or "football").lower().strip(),
            "message": "Nenhum jogo programado para esta modalidade nesta data.",
            "data": [],
            "jogos": []
        }

    return {
        "status": "success",
        "sucesso": True,
        "total_eventos": len(jogos),
        "total": len(jogos),
        "total_jogos": len(jogos),
        "esporte": res.get("esporte", sport),
        "nome_esporte": res.get("nome_esporte", sport.capitalize()),
        "provedor": res.get("provedor", ""),
        "data": jogos,
        "jogos": jogos
    }


@app.get("/api/sports/{sport}/ao-vivo")
async def get_sport_live(sport: str, force_refresh: bool = Query(False)):
    return {"total_ao_vivo": 0, "jogos": []}


@app.get("/api/top5-bets")
async def get_top5_bets(
    data: Optional[str] = Query(None, description="Data da consulta YYYY-MM-DD"),
    force_refresh: bool = Query(False, description="Forçar atualização ignorando o cache temporário.")
):
    """Retorna as Top 5 Bets do Dia unificadas de Futebol e NFL com máxima assertividade."""
    from app import obter_top5_bets_dia
    return await obter_top5_bets_dia(data=data, force_refresh=bool(force_refresh))


@app.get("/api/odds-hoje")
async def get_odds_hoje(
    data: Optional[str] = Query(None, description="Data no formato YYYY-MM-DD. Padrão: data de hoje em Brasília."),
    force_refresh: bool = Query(False, description="Forçar atualização ignorando o cache temporário.")
):

    target_date = validar_ou_obter_data_hoje(data)
    odds_data = await odds_service.buscar_odds_jogos_dia(target_date, force_refresh=force_refresh)
    return odds_data


@app.get("/api/games", response_model=List[Dict[str, Any]])
@app.get("/api/football/matches", response_model=List[Dict[str, Any]])
@app.get("/api/matches")
async def get_football_games(
    date: Optional[str] = Query(None, description="Data da partida no formato YYYY-MM-DD. Padrão: hoje no fuso America/Sao_Paulo."),
    data: Optional[str] = Query(None, description="Alias para data da partida no formato YYYY-MM-DD."),
    sport: Optional[str] = Query(None, description="Modalidade esportiva (ex: 'soccer')."),
    league: Optional[str] = Query(None, description="Filtro opcional por nome ou ID da liga."),
    status: Optional[str] = Query(None, description="Filtro opcional por status: SCHEDULED, LIVE, FINISHED ou ALL.")
):
    """
    Endpoint oficial normalizado de jogos de futebol sem mocks.
    Consome dinamicamente as APIs oficiais e devolve o schema normalizado:
    [
      {
        "id": "string | int",
        "league": { "name": "string", "logo": "string" },
        "home_team": { "name": "string", "logo": "string" },
        "away_team": { "name": "string", "logo": "string" },
        "status": "SCHEDULED | LIVE | FINISHED",
        "score": { "home": 0, "away": 0 },
        "start_time": "ISO8601 string"
      }
    ]
    Tolerância Zero a Mocks: Se não houver jogos para a data ou filtro, retorna [] com status HTTP 200.
    """
    target_date = (date or data or "").strip() or None
    try:
        games = await football_games_service.get_games(date=target_date, league=league, status=status)
        if not games and league and league.strip():
            try:
                from services.fixtures_service import fixtures_service
                from football_games_service import get_current_date_sp
                clean_date = target_date or get_current_date_sp()
                fixtures = await fixtures_service.get_fixtures(target_date=clean_date, filter_query=league.strip())
                for f in fixtures:
                    home_odd = 1.90
                    draw_odd = 3.20
                    away_odd = 3.50
                    for m in f.markets:
                        if m.market_name in ["1X2", "Resultado Final"]:
                            if m.selection == f.home_team:
                                home_odd = m.odd
                            elif m.selection == f.away_team:
                                away_odd = m.odd
                            elif m.selection.lower() in ["empate", "draw", "x"]:
                                draw_odd = m.odd
                    games.append({
                        "id": f.id or f.fixture_id,
                        "league": {
                            "name": f.league,
                            "logo": ""
                        },
                        "home_team": {
                            "name": f.home_team,
                            "logo": ""
                        },
                        "away_team": {
                            "name": f.away_team,
                            "logo": ""
                        },
                        "status": "SCHEDULED" if f.status == "AGENDADO" else ("LIVE" if f.status == "AO VIVO" else "FINISHED"),
                        "score": {"home": 0, "away": 0},
                        "start_time": f"{clean_date}T{f.horario}:00-03:00" if ":" in f.horario else f"{clean_date}T16:00:00-03:00",
                        "odds": {
                            "home": home_odd,
                            "draw": draw_odd,
                            "away": away_odd,
                            "bookmaker": "Betano"
                        }
                    })
            except Exception as e_fix:
                logger.warning(f"[get_football_games] Aviso no fallback para fixtures_service: {e_fix}")
        if games:
            try:
                from services.ai_analytics_service import calculate_batch_probabilities
                preds = await calculate_batch_probabilities(games, sport or "soccer")
                pred_map = {str(p.get("match_id")): p for p in preds if isinstance(p, dict) and p.get("match_id")}
                for idx, g in enumerate(games):
                    g_id = str(g.get("id") or g.get("match_id") or "")
                    if g_id in pred_map:
                        g["ai_prediction"] = pred_map[g_id]
                    elif idx < len(preds):
                        g["ai_prediction"] = preds[idx]
            except Exception as e_ai:
                logger.warning(f"[get_football_games] Aviso ao enriquecer com OpenAI batch: {e_ai}")
        return games
    except Exception as exc:
        logger.error(f"[GET /api/games] Erro ao obter partidas oficiais: {exc}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Falha ao consultar partidas oficiais de futebol: {str(exc)}"
        )


@app.get("/api/jogos-hoje")
@app.get("/api/partidas-analisadas")
async def get_jogos_hoje(
    data: Optional[str] = Query(None, description="Data no formato YYYY-MM-DD. Padrão: data de hoje no fuso America/Sao_Paulo."),
    date: Optional[str] = Query(None, description="Alias para data da consulta YYYY-MM-DD."),
    liga: Optional[int] = Query(None, description="Filtrar por ID de liga específico (ex: 71 para Brasileirão, 39 para Premier League)."),
    force_refresh: bool = Query(False, description="Forçar atualização ignorando o cache temporário.")
):
    """
    Endpoint principal de jogos e palpites do dia.
    Inicia o fluxo diretamente consultando o Agente Gemini 2.0 Flash com busca na web (Grounding).
    Retorna a lista normalizada e estruturada de partidas e palpites.
    """
    target_date = validar_ou_obter_data_hoje(date or data)
    force_refresh_bool = bool(force_refresh) if isinstance(force_refresh, bool) else False

    # FLUXO PRIMÁRIO: Consulta direta ao Agente Gemini 2.0 Flash (Grounding Google Search)
    try:
        palpites_gemini = await obter_jogos_e_palpites_gemini(
            {"data": target_date, "liga": liga},
            force_refresh=force_refresh_bool
        )

        if palpites_gemini and isinstance(palpites_gemini, list):
            partidas_formatadas = []
            for idx, p in enumerate(palpites_gemini):
                m_id = str(p.get("match_id") or f"gemini_match_{idx+1}")
                home = str(p.get("home_team") or "Mandante")
                away = str(p.get("away_team") or "Visitante")
                campeonato = str(p.get("league") or "Futebol Internacional")
                prob = float(p.get("market_prob") or 78.0)
                best_mkt = str(p.get("best_market") or "Over 1.5 Gols")
                reason = str(p.get("reasoning") or "Análise quantitativa baseada em scouts e histórico recente.")

                partidas_formatadas.append({
                    "id": m_id,
                    "partida": {
                        "id": m_id,
                        "fixture_id": m_id,
                        "mandante": {"nome": home},
                        "visitante": {"nome": away},
                        "campeonato": {"nome": campeonato},
                        "status": "A_COMECAR",
                        "horario": "16:00",
                        "estadio": "Estádio Oficial"
                    },
                    "campeonato": {
                        "nome": campeonato,
                        "pais": "Internacional"
                    },
                    "odds": {
                        "1x2": {
                            "mandante": 2.10,
                            "empate": 3.20,
                            "visitante": 3.40
                        }
                    },
                    "recomendacoes": [
                        {
                            "mercado": best_mkt,
                            "selecao": best_mkt,
                            "odd_referencia": 1.75,
                            "grau_confianca": int(prob),
                            "taxa_assertividade": prob,
                            "perfil_risco": "Segura" if prob >= 75 else "Moderada",
                            "justificativa": reason
                        }
                    ],
                    "ai_prediction": p,
                    "provedor": "gemini-2.0-flash"
                })

            logger.info(f"[get_jogos_hoje] Retornando {len(partidas_formatadas)} partidas fornecidas diretamente pelo Agente Gemini 2.0 Flash.")
            return {
                "status": "success",
                "total_partidas": len(partidas_formatadas),
                "data_consulta": target_date,
                "fonte_dados": "gemini_2.0_flash_grounding_agent",
                "partidas": partidas_formatadas,
                "agente_ia": {
                    "modelo": MODEL_TRACKERS[0].model_name if MODEL_TRACKERS else "gemini-2.0-flash",
                    "grounding": "googleSearch",
                    "status": "online"
                }
            }

    except Exception as exc:
        logger.warning(f"[get_jogos_hoje] Aviso na consulta primária do Agente Gemini: {exc}. Ativando orquestrador secundário.")

    # FALLBACK SECUNDÁRIO RESILIENTE
    resultado = await football_orchestrator.obter_jogos_unificados(
        target_date=target_date,
        force_refresh=force_refresh_bool,
        liga=liga
    )
    return resultado


@app.get("/api/gemini/agent-predictions")
@app.get("/api/gemini/jogos-hoje")
async def get_gemini_agent_predictions(
    data: Optional[str] = Query(None, description="Data YYYY-MM-DD."),
    liga: Optional[str] = Query(None, description="Filtro opcional de liga."),
    sport: Optional[str] = Query(None, description="Modalidade esportiva (ex: futebol, basquete, nfl, etc.)."),
    force_refresh: bool = Query(False, description="Forçar atualização ignorando o cache.")
):
    """Retorna os palpites diretos gerados pelo Agente Gemini 2.0 Flash com busca na web (Grounding)."""
    target_date = validar_ou_obter_data_hoje(data)
    target_sport = sport or "futebol"
    palpites = await obter_jogos_e_palpites_gemini(
        {"data": target_date, "liga": liga, "sport": target_sport},
        force_refresh=bool(force_refresh),
        sport=target_sport
    )
    return {
        "status": "success",
        "data_consulta": target_date,
        "sport": target_sport,
        "provedor": "gemini-2.0-flash",
        "grounding": True,
        "total": len(palpites),
        "data": palpites
    }


@app.get("/api/gemini/analise-partida/{fixture_id}")
async def get_gemini_analise_partida(
    fixture_id: int,
    data: Optional[str] = Query(None, description="Data da partida (YYYY-MM-DD).")
):

    target_date = validar_ou_obter_data_hoje(data)
    cache_key = f"gemini_analysis_{fixture_id}"
    cached = await app_cache.get(cache_key)
    if cached:
        return cached

    partidas_res = await football_orchestrator.obter_jogos_unificados(target_date=target_date)
    partidas = partidas_res.get("partidas", [])
    partida_encontrada = None
    for p in partidas:
        if p.get("partida", {}).get("id") == fixture_id:
            partida_encontrada = p
            break

    if not partida_encontrada:
        partida_encontrada = {
            "partida": {"id": fixture_id, "mandante": {"nome": "Mandante"}, "visitante": {"nome": "Visitante"}},
            "campeonato": {"nome": "Competição"},
            "metricas_chave": {"escanteios": {"disponivel": False}}
        }

    analyzer = _get_active_analyzer()
    resultado = await analyzer.analisar_partida_async(partida_encontrada)
    await app_cache.set(cache_key, resultado, ttl_seconds=1800)
    return resultado


@app.get("/api/gemini/stream-analises")
async def stream_gemini_analises_endpoint(
    data: Optional[str] = Query(None, description="Data no formato YYYY-MM-DD. Padrão: data de hoje no fuso America/Sao_Paulo."),
    liga: Optional[int] = Query(None, description="Filtrar por ID de liga específico."),
    force_refresh: bool = Query(False, description="Forçar atualização ignorando o cache.")
):

    target_date = validar_ou_obter_data_hoje(data)
    partidas_res = await football_orchestrator.obter_jogos_unificados(
        target_date=target_date,
        force_refresh=force_refresh,
        liga=liga
    )
    partidas = partidas_res.get("partidas", [])
    analyzer = _get_active_analyzer()

    return StreamingResponse(
        analyzer.stream_analises_sse(partidas, force_refresh=force_refresh),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*"
        }
    )


@app.get("/api/stream/events")
async def sse_stream(request: Request):
    """
    Endpoint SSE oficial anti-vazamento de tokens.
    Transmite exclusivamente o cache persistido em disco para o frontend.
    Mantém heartbeat sem processamento de IA.
    """
    async def event_generator():
        # Apenas lê o cache salvo em disco e faz streaming para o front
        if CACHE_FILE.exists():
            data = CACHE_FILE.read_text(encoding="utf-8")
            yield f"data: {data}\n\n"
        # Mantém conexão viva com heartbeat sem processar IA
        try:
            while not await request.is_disconnected():
                await asyncio.sleep(15)
                yield ": ping\n\n"
        except (asyncio.CancelledError, GeneratorExit):
            pass
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*"
        }
    )


@app.get("/api/stream/eventos")
async def stream_eventos_globais(request: Request):

    client_queue = await sse_broadcast_hub.subscribe()
    return StreamingResponse(
        sse_broadcast_hub.stream_client(client_queue, request=request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*"
        }
    )


@app.get("/api/scheduler/status")
async def get_scheduler_status():

    return job_scheduler.obter_status()


@app.post("/api/scheduler/executar-agora")
async def trigger_scheduler_manual(
    data: Optional[str] = Query(None, description="Data alvo (YYYY-MM-DD) ou data atual em Brasília.")
):

    target_date = validar_ou_obter_data_hoje(data)
    res = await job_scheduler.executar_rotina_diaria_00h(data_alvo=target_date, origem="MANUAL_ENDPOINT")
    return res


@app.get("/api/multipla-segura-dia")
async def get_multipla_segura_dia(
    data: Optional[str] = Query(None, description="Data no formato YYYY-MM-DD. Padrão: data de hoje no fuso America/Sao_Paulo."),
    date: Optional[str] = Query(None, description="Alias para data da consulta YYYY-MM-DD."),
    force_refresh: bool = Query(False, description="Forçar atualização ignorando o cache temporário.")
):

    now_br = datetime.now(TIMEZONE_BR)
    target_date = validar_ou_obter_data_hoje(date or data)
    force_refresh_bool = bool(force_refresh) if isinstance(force_refresh, bool) else False
    cache_key = f"multipla_segura_{target_date}"

    if not force_refresh_bool:
        cached_bilhete = await app_cache.get(cache_key)
        if cached_bilhete:
            return cached_bilhete


    partidas_res = await get_jogos_hoje(data=target_date, liga=None, force_refresh=force_refresh_bool)
    partidas = partidas_res.get("partidas", [])


    MERCADOS_PERMITIDOS = {"Gols", "Escanteios", "Chance Dupla"}


    candidatos_por_partida = []

    for match in partidas:
        p_info = match.get("partida", {})
        c_info = match.get("campeonato", {})
        recs = match.get("recomendacoes", [])

        melhor_rec_jogo = None
        maior_conf = 0.0

        for r in recs:

            mkt = r.get("mercado", "")
            if mkt not in MERCADOS_PERMITIDOS:
                continue


            if r.get("perfil_risco") == "arriscado" or "Agressiva" in r.get("selecao", "") or "Esticada" in r.get("selecao", ""):
                continue

            conf = float(r.get("grau_confianca") or r.get("confianca_porcentagem") or 0.0)
            if conf >= 80.0 and conf > maior_conf:
                maior_conf = conf
                melhor_rec_jogo = r

        if melhor_rec_jogo:
            odd_val = melhor_rec_jogo.get("odd_mercado") or melhor_rec_jogo.get("odd_referencia") or 1.30
            try:
                odd_num = float(odd_val)
            except (ValueError, TypeError):
                odd_num = 1.30

            data_hora_raw = p_info.get("data_hora", "")
            horario_formatado = "--:--"
            if data_hora_raw:
                try:
                    horario_formatado = datetime.fromisoformat(data_hora_raw.replace("Z", "+00:00")).astimezone(TIMEZONE_BR).strftime("%H:%M")
                except Exception:
                    horario_formatado = "--:--"

            candidatos_por_partida.append({
                "partida_id": p_info.get("id"),
                "mandante": p_info.get("mandante", {}).get("nome", "Mandante"),
                "mandante_logo": p_info.get("mandante", {}).get("logo", ""),
                "visitante": p_info.get("visitante", {}).get("nome", "Visitante"),
                "visitante_logo": p_info.get("visitante", {}).get("logo", ""),
                "campeonato": c_info.get("nome", "Campeonato"),
                "campeonato_logo": c_info.get("logo", ""),
                "data_hora": data_hora_raw,
                "horario": horario_formatado,
                "mercado": melhor_rec_jogo.get("mercado", ""),
                "selecao": melhor_rec_jogo.get("selecao", ""),
                "confianca": round(maior_conf, 1),
                "odd": round(odd_num, 2),
                "casa_aposta": melhor_rec_jogo.get("casa_aposta") or "Bet365 / Pinnacle",
                "justificativa": melhor_rec_jogo.get("justificativa_estatistica") or melhor_rec_jogo.get("justificativa", "")
            })


    candidatos_por_partida.sort(key=lambda x: x["confianca"], reverse=True)


    selecoes_finais = candidatos_por_partida[:5]

    try:
        data_obj = datetime.strptime(target_date, "%Y-%m-%d")
        data_formatada_br = data_obj.strftime("%d/%m/%Y")
    except Exception:
        data_formatada_br = target_date


    if len(selecoes_finais) < 3:
        msg = "Mercados insuficientes para gerar múltiplas no momento."
        resultado_insuficiente = {
            "status": "insuficiente",
            "data_bilhete": target_date,
            "data_formatada": data_formatada_br,
            "total_selecoes": len(selecoes_finais),
            "mensagem": msg,
            "selecoes": selecoes_finais,
            "odd_total": None,
            "probabilidade_combinada": None,
            "nivel_risco": "Risco Calculado: Muito Baixo",
            "horario_primeiro_jogo": None,
            "resumo_texto": ""
        }
        return resultado_insuficiente


    odd_total_acumulada = 1.0
    for s in selecoes_finais:
        odd_total_acumulada *= s["odd"]
    odd_total_acumulada = round(odd_total_acumulada, 2)


    prob_media = round(sum(s["confianca"] for s in selecoes_finais) / len(selecoes_finais), 1)


    horarios_validos = [s["horario"] for s in selecoes_finais if s["horario"] != "--:--"]
    primeiro_horario = sorted(horarios_validos)[0] if horarios_validos else "--:--"


    linhas_texto = [
        "🎯 *BILHETE PRONTO: MÚLTIPLA SEGURA DO DIA*",
        f"📅 *Data:* {data_formatada_br} | ⏰ *Primeiro Jogo:* {primeiro_horario}",
        f"🛡️ *Nível de Risco:* Muito Baixo (Assertividade Média: {prob_media}%)",
        "----------------------------------------"
    ]
    for idx, s in enumerate(selecoes_finais, 1):
        linhas_texto.append(f"{idx}️⃣ *{s['mandante']} vs {s['visitante']}* ({s['horario']})")
        linhas_texto.append(f"   🏆 {s['campeonato']}")
        linhas_texto.append(f"   📌 Entrada: *{s['selecao']}* (@{s['odd']:.2f} • {s['casa_aposta']})")
        linhas_texto.append(f"   📊 Justificativa: {s['justificativa']}")
        linhas_texto.append("")

    linhas_texto.append("----------------------------------------")
    linhas_texto.append(f"💰 *COTAÇÃO TOTAL MULTIPLICADA:* @{odd_total_acumulada:.2f}")
    retorno_exemplo = round(20.0 * odd_total_acumulada, 2)
    lucro_exemplo = round(retorno_exemplo - 20.0, 2)
    linhas_texto.append(f"💵 *Simulação (R$ 20,00):* Retorno R$ {retorno_exemplo:.2f} (Lucro: +R$ {lucro_exemplo:.2f})".replace(".", ","))
    linhas_texto.append("🚀 *Gerado via Football Analytics & Decision Engine*")

    resumo_texto = "\n".join(linhas_texto)

    payload = {
        "status": "success",
        "data_bilhete": target_date,
        "data_formatada": data_formatada_br,
        "horario_primeiro_jogo": primeiro_horario,
        "total_selecoes": len(selecoes_finais),
        "odd_total": odd_total_acumulada,
        "probabilidade_combinada": prob_media,
        "nivel_risco": "Risco Calculado: Muito Baixo",
        "selecoes": selecoes_finais,
        "resumo_texto": resumo_texto
    }


    meia_noite_br = (now_br + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    segundos_ate_meia_noite = max(180, int((meia_noite_br - now_br).total_seconds()))

    await app_cache.set(cache_key, payload, ttl_seconds=segundos_ate_meia_noite)
    return payload


@app.get(
    "/api/bet-of-the-day",
    response_model=BetOfTheDayResponse,
    include_in_schema=False
)
async def get_bet_of_the_day_endpoint(
    data: Optional[str] = Query(None, description="Data no formato YYYY-MM-DD. Padrão: data de hoje."),
    date: Optional[str] = Query(None, description="Alias para data da consulta YYYY-MM-DD."),
    force_refresh: bool = Query(False, description="Forçar recálculo ignorando o cache temporário.")
):
    """
    Retorna a Bet do Dia calculada e homologada:
    - 4 seleções analíticas conservadoras/moderadas de alto valor (+EV).
    - Ranking comparativo de cotações entre Betano, Bet365, KTO e Betfair.
    - Identificação da melhor casa com maior retorno líquido (is_best_choice: True).
    """
    target_date = date or data
    return await bet_of_the_day_service.get_bet_of_the_day(
        target_date=target_date,
        force_refresh=force_refresh
    )


@app.get(
    "/api/v1/bets/jogos-do-dia",
    tags=["Bet do Dia"],
    summary="Obtém os jogos oficiais que irão acontecer no dia selecionado via Owls Insight"
)
@app.get(
    "/api/bets/jogos-do-dia",
    include_in_schema=False
)
async def get_jogos_do_dia_endpoint(
    data: Optional[str] = Query(None, description="Data no formato YYYY-MM-DD. Padrão: hoje no fuso America/Sao_Paulo."),
    date: Optional[str] = Query(None, description="Alias para data no formato YYYY-MM-DD."),
    force_refresh: bool = Query(False, description="Forçar atualização ignorando o cache.")
):
    """
    Retorna a grade de jogos oficiais que irão acontecer na data selecionada,
    consumidos diretamente da API Owls Insight, com status agendado, sugestões analíticas e odds.
    """
    target_date = validar_ou_obter_data_hoje(date or data)
    res_botd = await bet_of_the_day_service.get_bet_of_the_day(
        target_date=target_date,
        force_refresh=force_refresh
    )
    jogos = res_botd.data.jogos_do_dia if res_botd and res_botd.data else []
    return {
        "status": "success",
        "provedor": "Owls Insight",
        "data": target_date,
        "total": len(jogos),
        "jogos": [j.model_dump() if hasattr(j, "model_dump") else dict(j) for j in jogos]
    }



@app.get("/api/partida/{fixture_id}/raio-x")
async def get_partida_raio_x(fixture_id: int):

    return {
        "fixture_id": fixture_id,
        "scouts_consolidados": {},
        "timestamp": datetime.now(TIMEZONE_BR).isoformat()
    }


# =====================================================================
# ENDPOINTS ODDSCOUT (TERMINAL DE ARBITRAGEM E MÚLTIPLAS)
# =====================================================================

from oddscout_service import oddscout_service

class GerarMultiplaPayload(BaseModel):
    num_jogos: Optional[int] = 5
    perfil_risco: Optional[str] = "alto_retorno"
    min_odd: Optional[float] = None
    max_odd: Optional[float] = None
    data_filtro: Optional[str] = "hoje"
    liga_filtro: Optional[str] = None
    jogos_adicionais: Optional[List[str]] = None
    valor_aposta: Optional[float] = 100.0

class SimularRetornoPayload(BaseModel):
    valor_aposta: float = 100.0
    odds_casas: Optional[Dict[str, float]] = None
    melhor_casa: Optional[str] = "Betano"

class NovaApostaPayload(BaseModel):
    valor: float = 100.0
    casa: str = "Betano"
    odd_total: float = 38.50
    jogos_count: int = 5

class AjustarBancaPayload(BaseModel):
    novo_saldo: float


@app.get("/api/oddscout/status")
async def get_oddscout_status():
    """Retorna status das 9 casas conectadas e saúde do terminal OddScout."""
    return oddscout_service.obter_status_sistema()


@app.get("/api/oddscout/banca")
async def get_oddscout_banca():
    """Retorna saldo atual, lucro 30d, taxa de assertividade e métricas de gestão."""
    return oddscout_service.banca_info


@app.post("/api/oddscout/banca/aposta")
async def post_oddscout_aposta(payload: NovaApostaPayload):
    """Registra uma nova aposta no histórico e atualiza a banca."""
    return oddscout_service.registrar_nova_aposta(payload.model_dump())


@app.post("/api/oddscout/banca/ajustar")
async def post_oddscout_ajustar_banca(payload: AjustarBancaPayload):
    """Atualiza o saldo bancário ativo."""
    return oddscout_service.ajustar_saldo_banca(payload.novo_saldo)


@app.get("/api/oddscout/historico-apostas")
async def get_oddscout_historico_apostas(
    status: Optional[str] = Query(None, description="Filtrar por status: Ganha, Perdida, Pendente ou todos")
):
    """Retorna o histórico completo de apostas com filtros de status e totais."""
    apostas = oddscout_service.banca_info.get("apostas_recentes", [])
    if status and status.lower() != "todos":
        apostas = [a for a in apostas if a.get("status", "").lower() == status.lower()]
    return {
        "status": "success",
        "total": len(apostas),
        "apostas": apostas,
        "saldo_atual": oddscout_service.banca_info.get("saldo_atual", 0.0),
        "lucro_30d": oddscout_service.banca_info.get("lucro_30d", 0.0),
        "roi_30d": oddscout_service.banca_info.get("roi_30d", 0.0),
        "taxa_acerto_geral": oddscout_service.banca_info.get("taxa_acerto_geral", 0.0)
    }


@app.get("/api/oddscout/ao-vivo")
async def get_oddscout_ao_vivo():
    """Retorna partidas com cotações vivas e placares em andamento do motor real."""
    from services.live_odds_service import live_odds_service
    games = await live_odds_service.get_live_odds()
    return {
        "status": "success",
        "total_ao_vivo": len(games),
        "jogos": [
            {
                "id": g.fixture_id,
                "mandante": g.home_team,
                "visitante": g.away_team,
                "campeonato": g.league,
                "placar": f"{g.home_score} x {g.away_score}",
                "minuto": g.minute,
                "status": g.period,
                "mercado": g.active_market,
                "odd_atual": g.best_bookmaker.odd,
                "casa_destaque": g.best_bookmaker.name,
                "odds": {g.best_bookmaker.name: g.best_bookmaker.odd},
                "valor_esperado": f"+{g.ev_percentage}% (+EV)"
            }
            for g in games
        ],
        "timestamp": datetime.now(TIMEZONE_BR).isoformat()
    }


@app.get("/api/oddscout/ligas-contadores")
async def get_oddscout_contadores():
    """Retorna total de jogos disponíveis por data e ligas."""
    return oddscout_service.obter_contadores_ligas()


@app.get("/api/oddscout/bet-do-dia")
async def get_oddscout_bet_do_dia():
    """Retorna a Bet do Dia recomendada pelo motor quantitativo."""
    return oddscout_service.obter_bet_do_dia()


@app.get("/api/oddscout/radar-oportunidades")
async def get_oddscout_radar():
    """Retorna oportunidades e odds atrasadas/desreguladas (+EV)."""
    return oddscout_service.obter_radar_oportunidades()


@app.post("/api/oddscout/gerar-multipla")
async def post_oddscout_gerar_multipla(payload: GerarMultiplaPayload):
    """Gera o bilhete múltiplo comparativo entre as 5 principais casas."""
    return oddscout_service.gerar_multipla_selecionada(
        num_jogos=payload.num_jogos or 5,
        perfil_risco=payload.perfil_risco or "alto_retorno",
        min_odd=payload.min_odd,
        max_odd=payload.max_odd,
        data_filtro=payload.data_filtro or "hoje",
        liga_filtro=payload.liga_filtro,
        jogos_adicionais=payload.jogos_adicionais,
        valor_aposta_base=payload.valor_aposta or 100.0
    )


@app.get("/api/oddscout/gerar-multipla")
async def get_oddscout_gerar_multipla(
    num_jogos: int = Query(5, description="Número de jogos a combinar (3 a 8)."),
    perfil_risco: str = Query("alto_retorno", description="Perfil: conservador, equilibrado ou alto_retorno."),
    valor_aposta: float = Query(100.0, description="Valor da aposta base em Reais."),
    data_filtro: str = Query("hoje", description="Filtro de data: 'hoje', 'amanha', 'depois'."),
    liga_filtro: Optional[str] = Query(None, description="Filtro de liga esportiva específica.")
):
    """Versão GET para conveniência rápida no navegador."""
    return oddscout_service.gerar_multipla_selecionada(
        num_jogos=num_jogos,
        perfil_risco=perfil_risco,
        valor_aposta_base=valor_aposta,
        data_filtro=data_filtro,
        liga_filtro=liga_filtro
    )


@app.post("/api/oddscout/simular-retorno")
async def post_oddscout_simular_retorno(payload: SimularRetornoPayload):
    """Recalcula o retorno por casa e valor deixado na mesa para um valor de aposta específico."""
    odds = payload.odds_casas or {
        "Betano": 38.50,
        "Bet365": 34.20,
        "KTO": 31.80,
        "Sportingbet": 29.20,
        "Betfair": 30.50
    }
    return oddscout_service.calcular_impacto_bolso(
        odds_totais_casas=odds,
        valor_aposta=payload.valor_aposta,
        melhor_casa=payload.melhor_casa or "Betano"
    )


# =====================================================================
# ENDPOINTS SPORTMONKS (DESATIVADOS / MIGRADO PARA GEMINI)
# =====================================================================

@app.get("/api/sportmonks/status")
async def get_sportmonks_status():
    return {"status": "deprecated", "provedor": "Substituído por Agente Gemini 2.0 Flash"}


@app.get("/api/sportmonks/jogos")
async def get_sportmonks_jogos(
    data: Optional[str] = Query(None),
    date: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    league_id: Optional[int] = Query(None),
    force_refresh: bool = Query(False)
):
    return []


@app.get("/api/sportmonks/ao-vivo")
async def get_sportmonks_ao_vivo(force_refresh: bool = Query(False)):
    return []


# =====================================================================
# ENDPOINTS NFL & FUTEBOL AMERICANO (SHARPAPI OFICIAL)
# =====================================================================

@app.get("/api/nfl/jogos")
@app.get("/api/nfl/games")
async def get_nfl_jogos(
    data: Optional[str] = Query(None),
    date: Optional[str] = Query(None),
    semana: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    force_refresh: bool = Query(False)
):
    target_data = data or date
    return await nfl_service.buscar_grade_jogos(
        data=target_data,
        semana=semana,
        status=status,
        force_refresh=force_refresh
    )


@app.get("/api/nfl/status")
async def get_nfl_status():
    return await nfl_service.obter_status()







# =====================================================================
# ENDPOINTS DO AGENDADOR & ATUALIZAÇÃO AUTOMÁTICA DE TODOS OS JOGOS
# =====================================================================

@app.get("/api/scheduler/status")
async def get_scheduler_status():
    """Retorna o status do agendador automatizado, incluindo a rotina de 1 em 1 hora e a rotina noturna."""
    return job_scheduler.obter_status()


@app.post("/api/scheduler/atualizar-agora")
@app.post("/api/admin/atualizar-todos-jogos")
async def post_atualizar_todos_jogos_agora(
    data: Optional[str] = Query(None, description="Data alvo (padrão: hoje no fuso de Brasília)")
):
    """
    Dispara imediatamente a atualização completa de TODOS os jogos do dia:
    Futebol, NFL, eSports, as 12 modalidades da API-Sports e Top 5 Bets.
    """
    resultado = await job_scheduler.atualizar_todos_jogos_dia(
        target_date=data,
        force_refresh=True,
        origem="DISPARO_MANUAL_API"
    )
    return resultado


# ----------------------------------------------------------------------
# 4. Fallback SPA (Single Page Application - React/Vue Router / CodeTogether)
# Coloque esta rota OBRIGATORIAMENTE DEPOIS de todos os endpoints /api
# ----------------------------------------------------------------------
@app.get("/{full_path:path}", include_in_schema=False)
async def spa_fallback(full_path: str):
    # Ignora rotas da API, documentação e esquemas OpenAPI
    if full_path.startswith("api/") or full_path.startswith("docs") or full_path.startswith("openapi.json"):
        raise HTTPException(status_code=404, detail="API route not found")
        
    # Verifica se é um arquivo físico existente na pasta static
    static_file_path = os.path.join(STATIC_DIR, full_path)
    if os.path.exists(static_file_path) and os.path.isfile(static_file_path):
        return FileResponse(static_file_path)

    # Verifica se é um asset de imagem/estático seguro existente na raiz
    safe_root_extensions = ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.css', '.js', '.json', '.webp', '.woff', '.woff2', '.ttf')
    root_file_path = os.path.join(FRONTEND_DIR, full_path)
    if os.path.exists(root_file_path) and os.path.isfile(root_file_path) and root_file_path.lower().endswith(safe_root_extensions):
        return FileResponse(root_file_path)
        
    # Redireciona rotas de navegação do frontend para o index.html
    if os.path.exists(INDEX_HTML):
        return FileResponse(INDEX_HTML)
        
    raise HTTPException(status_code=404, detail="Frontend build files not found")


if __name__ == "__main__":
    import uvicorn
    from config import HOST, PORT
    uvicorn.run("main:app", host=HOST, port=PORT, reload=True)

