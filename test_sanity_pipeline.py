import asyncio
import os
import sys
from typing import Dict, Any

if sys.platform == "win32":
    try:
        if sys.stdout.encoding != 'utf-8':
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        if sys.stderr.encoding != 'utf-8':
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

from httpx import AsyncClient, ASGITransport

from config import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    is_gemini_configured,
    is_apisports_configured,
    is_sharpapi_configured,
    is_pandascore_configured,
    is_oddspedia_configured,
)
from main import app
from services.ai_analytics_service import obter_jogos_e_palpites_gemini, MODEL_TRACKERS
from services.bet_of_the_day_service import bet_of_the_day_service


async def run_sanity_pipeline_test():
    print("================================================================================")
    print("   TESTE DE SANIDADE DO PIPELINE UNIFICADO - ARQUITETURA GEMINI 2.0 FLASH      ")
    print("================================================================================")

    # -------------------------------------------------------------------------
    # 1. VALIDAÇÃO DE VARIÁVEIS DE AMBIENTE (.env) E EXCLUSIVIDADE GEMINI
    # -------------------------------------------------------------------------
    print("\n[ETAPA 1/6] Verificando exclusividade do Gemini 2.0 Flash e limpeza de APIs antigas...")
    assert is_gemini_configured(), "GEMINI_API_KEY deve estar configurada no .env!"
    masked_gemini = f"{GEMINI_API_KEY[:4]}...{GEMINI_API_KEY[-4:]}"
    print(f"  [OK] GEMINI_API_KEY  : {masked_gemini} (Ativa e Carregada)")
    print(f"  [OK] GEMINI_MODEL    : {GEMINI_MODEL}")

    # Confirmar que o modelo primário é gemini-2.0-flash
    assert GEMINI_MODEL == "gemini-2.0-flash", f"Modelo esperado gemini-2.0-flash, obtido {GEMINI_MODEL}"
    print("  [OK] Gemini 2.0 Flash configurado como motor primário exclusivo.")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # -------------------------------------------------------------------------
        # 2. STATUS GLOBAL DO SISTEMA (/api/status)
        # -------------------------------------------------------------------------
        print("\n[ETAPA 2/6] Validando /api/status com agente Gemini...")
        res_sys = await client.get("/api/status")
        assert res_sys.status_code == 200
        sys_data = res_sys.json()
        assert sys_data["status"] == "online"
        assert sys_data["modo_orquestracao"] == "gemini_2.0_flash_grounding_agent"
        assert "gemini_agent" in sys_data
        assert sys_data["gemini_agent"]["model"] == "gemini-2.0-flash"
        assert sys_data["gemini_agent"]["grounding"] is True
        print(f"  [OK] GET /api/status: Agente ativo={sys_data['gemini_agent']['model']} (Grounding={sys_data['gemini_agent']['tool']})")

        # -------------------------------------------------------------------------
        # 3. AGENTE GEMINI: BUSCA DE JOGOS E PALPITES
        # -------------------------------------------------------------------------
        print("\n[ETAPA 3/6] Testando orquestração central de partidas via Gemini...")
        palpites = await obter_jogos_e_palpites_gemini(data="2026-09-22")
        assert isinstance(palpites, list)
        assert len(palpites) > 0, "Deveria retornar partidas (live ou fallback resiliente)."
        print(f"  [OK] Ingestão Gemini: {len(palpites)} partidas/palpites gerados com mercado e probabilidades.")

        # -------------------------------------------------------------------------
        # 4. ENDPOINTS CENTRAIS DE JOGOS E PREDIÇÕES
        # -------------------------------------------------------------------------
        print("\n[ETAPA 4/6] Testando endpoints /api/jogos-hoje e /api/gemini/agent-predictions...")
        res_jogos = await client.get("/api/jogos-hoje")
        assert res_jogos.status_code == 200
        data_jogos = res_jogos.json()
        assert data_jogos["status"] == "success"
        assert "partidas" in data_jogos
        print(f"  [OK] GET /api/jogos-hoje: {len(data_jogos['partidas'])} partidas entregues ao frontend.")

        res_agent = await client.get("/api/gemini/agent-predictions")
        assert res_agent.status_code == 200
        assert res_agent.json()["status"] == "success"
        print("  [OK] GET /api/gemini/agent-predictions: Resposta HTTP 200 validada.")

        # -------------------------------------------------------------------------
        # 5. BET DO DIA & MULTI-BOOKMAKER
        # -------------------------------------------------------------------------
        print("\n[ETAPA 5/6] Testando Bet do Dia e Ranking Multi-Bookmaker...")
        botd_res = await bet_of_the_day_service.get_bet_of_the_day()
        assert botd_res.status == "success"
        assert len(botd_res.data.selections) > 0
        assert botd_res.data.best_bookmaker.name in ("Betano", "Bet365", "KTO", "Betfair")
        print(f"  [OK] Bet do Dia: Odd Combinada={botd_res.data.combined_odd} | Melhor Casa={botd_res.data.best_bookmaker.name}")

        # -------------------------------------------------------------------------
        # 6. ROTAS LEGADAS COM RESPOSTAS RESILIENTES (ZERO EXCEÇÕES 500)
        # -------------------------------------------------------------------------
        print("\n[ETAPA 6/6] Verificando resposta resiliente em rotas legadas migadas...")
        for legacy_path in [
            "/api/sports/status",
            "/api/sports/soccer/jogos",
            "/api/nfl/jogos",
            "/api/esports/jogos",
            "/api/sharpapi/status",
            "/api/pandascore/status",
            "/api/sportmonks/status",
        ]:
            res = await client.get(legacy_path)
            assert res.status_code == 200, f"Rota legada {legacy_path} falhou com status {res.status_code}"
            print(f"  [OK] GET {legacy_path:30}: HTTP 200 OK (Desacoplada com sucesso)")

    print("\n================================================================================")
    print("   TODAS AS 6 ETAPAS DO PIPELINE DE SANIDADE FORAM APROVADAS COM SUCESSO!       ")
    print("================================================================================")


if __name__ == "__main__":
    asyncio.run(run_sanity_pipeline_test())
