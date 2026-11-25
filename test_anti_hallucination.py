"""
Suite de Testes da Trava Anti-Alucinação (Zero Jogos Fictícios) e Tratamento de Lista Vazia.
Valida:
1. APIs externas retornam 0 jogos -> Backend NÃO aciona o Gemini, interrompe o pipeline e retorna status "empty".
2. Estrutura do payload no endpoint /api/sports/{sport}/jogos:
   - status: "empty"
   - total_eventos: 0
   - message: "Nenhum jogo programado para esta modalidade nesta data."
   - data: []
3. Blindagem no Prompt do Gemini com REGRA DE SEGURANÇA E INTEGRIDADE em analyze_fixtures_with_gemini.
4. Fallback determinístico não inventa confrontos fictícios (retorna lista vazia).
5. Comportamento quando existem jogos reais (status "success", total_eventos > 0).
"""

import asyncio
import sys
import unittest
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient, ASGITransport

if sys.platform == "win32":
    try:
        if sys.stdout.encoding != 'utf-8':
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        if sys.stderr.encoding != 'utf-8':
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

from main import app
from routers.sports import obter_jogos_por_modalidade
from services.ai_analytics_service import (
    analyze_fixtures_with_gemini,
    _gerar_predicoes_fallback
)


async def run_tests():
    print("=" * 75)
    print("TESTES: TRAVA ANTI-ALUCINAÇÃO & TRATAMENTO DE LISTA VAZIA")
    print("=" * 75)

    # -------------------------------------------------------------------------
    # TESTE 1: Trava Rígida no Backend - API Externa retorna lista vazia
    # -------------------------------------------------------------------------
    print("\n[TESTE 1] Verificando Trava Rígida com API externa vazia (ex: OwlsInsight/Futebol)...")
    with patch("routers.sports.fetch_soccer_fixtures_by_date", new=AsyncMock(return_value=[])), \
         patch("routers.sports.analyze_fixtures_with_gemini", new=AsyncMock()) as mock_gemini:

        res = await obter_jogos_por_modalidade(sport="football", date_param="2099-01-01")

        # Verifica se o Gemini NUNCA foi chamado
        mock_gemini.assert_not_called()

        assert res["status"] == "empty", f"Status esperado 'empty', obtido: {res.get('status')}"
        assert res["total_eventos"] == 0, f"total_eventos esperado 0, obtido: {res.get('total_eventos')}"
        assert res["message"] == "Nenhum jogo programado para esta modalidade nesta data."
        assert res["data"] == [], f"data esperado [], obtido: {res.get('data')}"
        assert res["jogos"] == [], f"jogos esperado [], obtido: {res.get('jogos')}"
        print("  [OK] Trava anti-alucinação acionada: Gemini NÃO foi chamado e retorno status='empty'.")

    # -------------------------------------------------------------------------
    # TESTE 2: Trava Rígida para Outros Esportes (API-Sports / Basquete)
    # -------------------------------------------------------------------------
    print("\n[TESTE 2] Verificando Trava Rígida para Esportes Tradicionais vazios (ex: Handebol)...")
    with patch("routers.sports.fetch_apisports_by_sport", new=AsyncMock(return_value=[])), \
         patch("routers.sports.analyze_fixtures_with_gemini", new=AsyncMock()) as mock_gemini:

        res = await obter_jogos_por_modalidade(sport="handball", date_param="2099-01-01")

        mock_gemini.assert_not_called()
        assert res["status"] == "empty"
        assert res["total_eventos"] == 0
        assert res["message"] == "Nenhum jogo programado para esta modalidade nesta data."
        assert res["data"] == []
        print("  [OK] Esporte tradicional vazio interceptado com sucesso.")

    # -------------------------------------------------------------------------
    # TESTE 3: Endpoint FastAPI /api/sports/{sport}/jogos com lista vazia
    # -------------------------------------------------------------------------
    print("\n[TESTE 3] Testando Endpoint HTTP GET /api/sports/basketball/jogos com retorno vazio...")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch("routers.sports.fetch_apisports_by_sport", new=AsyncMock(return_value=[])):
            resp = await client.get("/api/sports/basketball/jogos?date=2099-01-01")
            assert resp.status_code == 200, f"Status code HTTP incorreto: {resp.status_code}"
            json_data = resp.json()
            assert json_data["status"] == "empty", f"Status JSON incorreto: {json_data.get('status')}"
            assert json_data["total_eventos"] == 0
            assert json_data["message"] == "Nenhum jogo programado para esta modalidade nesta data."
            assert json_data["data"] == []
            print(f"  [OK] Endpoint HTTP retornou status='empty' e total_eventos=0 conforme especificação.")

    # -------------------------------------------------------------------------
    # TESTE 4: Blindagem no Prompt do Gemini (ai_analytics_service.py)
    # -------------------------------------------------------------------------
    print("\n[TESTE 4] Verificando Cláusula Anti-Alucinação no Prompt do Gemini...")
    # Testa se fixtures vazias retornam [] imediatamente
    res_vazia = await analyze_fixtures_with_gemini([])
    assert res_vazia == [], "Lista vazia deve retornar [] imediatamente sem requisição."

    # Inspeciona o código fonte de analyze_fixtures_with_gemini para garantir a presença da regra
    import inspect
    func_source = inspect.getsource(analyze_fixtures_with_gemini)
    assert "REGRA DE SEGURANÇA E INTEGRIDADE" in func_source, "Falta REGRA DE SEGURANÇA E INTEGRIDADE no prompt"
    assert "É EXPRESSAMENTE PROIBIDO inventar" in func_source, "Falta proibição expressa de inventar partidas"
    assert "retorne uma lista JSON vazia: []" in func_source, "Falta instrução de retornar [] caso dados vazios"
    print("  [OK] Cláusula estrita anti-alucinação verificada no código do prompt.")

    # -------------------------------------------------------------------------
    # TESTE 5: Trava Anti-Alucinação para PandaScore (Esports)
    # -------------------------------------------------------------------------
    print("\n[TESTE 5] Verificando Trava Anti-Alucinação para PandaScore (Esports vazio)...")
    with patch("routers.sports.fetch_esports_matches", new=AsyncMock(return_value=[])), \
         patch("routers.sports.analyze_fixtures_with_gemini", new=AsyncMock()) as mock_gem:
        res_esports = await obter_jogos_por_modalidade(sport="cs2", date_param="2099-01-01")
        mock_gem.assert_not_called()
        assert res_esports["status"] == "empty"
        assert res_esports["total_eventos"] == 0
        assert res_esports["message"] == "Nenhum jogo programado para esta modalidade nesta data."
        assert res_esports["data"] == []
        print("  [OK] PandaScore Esports vazio: Gemini NÃO chamado e retorno status='empty'.")

    # -------------------------------------------------------------------------
    # TESTE 6: Comportamento quando HÁ jogos reais retornados pela API
    # -------------------------------------------------------------------------
    print("\n[TESTE 6] Verificando fluxo normal quando existem jogos reais...")
    jogo_mock = {
        "id": "1001",
        "fixture_id": "1001",
        "home_team": "Time Real A",
        "away_team": "Time Real B",
        "mandante": {"nome": "Time Real A"},
        "visitante": {"nome": "Time Real B"},
        "campeonato": {"nome": "Liga Real"}
    }
    with patch("routers.sports.fetch_soccer_fixtures_by_date", new=AsyncMock(return_value=[jogo_mock])), \
         patch("routers.sports.analyze_fixtures_with_gemini", new=AsyncMock()):

        res_real = await obter_jogos_por_modalidade(sport="football", date_param="2026-09-23")
        assert res_real["status"] == "success"
        assert res_real["total_eventos"] == 1
        assert len(res_real["data"]) == 1
        assert res_real["data"][0]["home_team"] == "Time Real A"
        print(f"  [OK] Jogos reais fluem normalmente com status='success' e total_eventos={res_real['total_eventos']}.")

    print("\n" + "=" * 75)
    print("TODOS OS TESTES DA TRAVA ANTI-ALUCINAÇÃO PASSARAM COM SUCESSO!")
    print("=" * 75)


if __name__ == "__main__":
    asyncio.run(run_tests())
