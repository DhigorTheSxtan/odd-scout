import asyncio
import json
from httpx import AsyncClient, ASGITransport
from main import app
from models.bet_of_the_day import BetOfTheDayResponse, BetOfTheDayData, SelectionItem
from services.bet_of_the_day_service import bet_of_the_day_service


async def test_bet_of_the_day_full_flow():
    print("\n================================================================================")
    print("   TESTE DE INTEGRAÇÃO OFICIAL: BET DO DIA (ENGINE, MULTI-BOOKMAKER & REST)     ")
    print("================================================================================")

    # 1. Teste Direto do Serviço
    print("\n[TEST 1] Invocando bet_of_the_day_service.get_bet_of_the_day()...")
    res = await bet_of_the_day_service.get_bet_of_the_day(force_refresh=True)

    assert isinstance(res, BetOfTheDayResponse)
    assert res.status == "success"
    assert res.data is not None
    assert isinstance(res.data, BetOfTheDayData)

    print(f"  [OK] Status: {res.status}")
    print(f"  [OK] Badge Odd: {res.badge_odd}")
    print(f"  [OK] Odd Combinada: {res.data.combined_odd}")
    print(f"  [OK] Confiança: {res.data.confidence_score * 100:.0f}%")

    # 2. Validação das 4 Seleções
    print("\n[TEST 2] Verificando composição da múltipla (exatamente 4 seleções analíticas)...")
    assert len(res.data.selections) == 4, f"Esperado 4 seleções, recebido {len(res.data.selections)}"
    for idx, sel in enumerate(res.data.selections, 1):
        assert isinstance(sel, SelectionItem)
        assert sel.fixture_id
        assert sel.match
        assert sel.market
        assert sel.pick
        assert sel.odd > 1.0
        assert sel.best_bookmaker == "Betano"
        assert len(sel.justification) > 10
        print(f"  [{idx}/4] {sel.match:32} | {sel.market:15} | Pick: {sel.pick:25} | Odd: @{sel.odd:.2f}")

    # 3. Validação do Ranking Multi-Bookmaker
    print("\n[TEST 3] Auditando Ranking Multi-Bookmaker (Betano, Bet365, KTO, Betfair)...")
    comp = res.data.bookmaker_comparison
    assert len(comp) == 4, f"Esperado 4 bookmakers, recebido {len(comp)}"

    bookmaker_names = [b.name for b in comp]
    assert "Betano" in bookmaker_names
    assert "Bet365" in bookmaker_names
    assert "KTO" in bookmaker_names
    assert "Betfair" in bookmaker_names

    best = res.data.best_bookmaker
    assert best.name == "Betano"
    assert best.is_best_choice is True
    assert best.badge == "Maior Retorno"
    assert best.total_odd == res.data.combined_odd

    for b in comp:
        is_best_str = " [MELHOR RETORNO]" if b.is_best_choice else ""
        print(f"  - {b.name:10}: @{b.total_odd:.2f} (Melhor: {b.is_best_choice}){is_best_str}")
        if b.name != "Betano":
            assert b.is_best_choice is False

    # 4. Teste de Resiliência de Cache (Segundo Acesso sem force_refresh)
    print("\n[TEST 4] Testando resiliência de cache de dois níveis (memória & disco)...")
    cached_res = await bet_of_the_day_service.get_bet_of_the_day(force_refresh=False)
    assert cached_res.data.combined_odd == res.data.combined_odd
    assert len(cached_res.data.selections) == 4
    print("  [OK] Cache retornou o mesmo payload consistente.")

    # 5. Teste dos Endpoints REST FastAPI
    print("\n[TEST 5] Testando endpoint canônico GET /api/v1/bets/bet-of-the-day...")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        http_res = await client.get("/api/v1/bets/bet-of-the-day")
        assert http_res.status_code == 200
        http_data = http_res.json()
        assert http_data["status"] == "success"
        assert http_data["badge_odd"] == res.badge_odd
        assert len(http_data["data"]["selections"]) == 4
        print(f"  [OK] GET /api/v1/bets/bet-of-the-day: HTTP 200 OK | Badge: {http_data['badge_odd']}")

        # Teste do alias /api/bet-of-the-day
        alias_res = await client.get("/api/bet-of-the-day")
        assert alias_res.status_code == 200
        print(f"  [OK] GET /api/bet-of-the-day (alias): HTTP 200 OK")

    print("\n================================================================================")
    print("   TODOS OS 5 TESTES DA BET DO DIA FORAM APROVADOS COM SUCESSO!                 ")
    print("================================================================================\n")


if __name__ == "__main__":
    asyncio.run(test_bet_of_the_day_full_flow())
