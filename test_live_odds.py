import asyncio
import sys
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
from models.live_odds import LiveOddsResponse


async def test_live_odds_endpoints():
    print("\n[TEST LIVE ODDS 1] Testing GET /api/v1/live/odds...")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/live/odds")
        assert res.status_code == 200, f"Status code: {res.status_code}"
        data = res.json()
        print(f" -> Status: {data.get('status')}, Total: {data.get('total')}")
        parsed = LiveOddsResponse(**data)
        assert parsed.status == "success"
        assert parsed.total == len(parsed.data)

        # Se houver jogos, validar integridade dos campos reais
        for game in parsed.data:
            assert game.fixture_id
            assert game.minute
            assert game.period
            assert game.home_team
            assert game.away_team
            assert game.active_market
            assert game.best_bookmaker.odd > 1.0
            print(f"    * {game.home_team} {game.home_score}x{game.away_score} {game.away_team} [{game.minute}] - {game.active_market} @{game.best_bookmaker.odd} ({game.best_bookmaker.name})")

        print("\n[TEST LIVE ODDS 2] Testing GET /api/v1/live/jogos-ao-vivo (alias)...")
        res_alias = await client.get("/api/v1/live/jogos-ao-vivo")
        assert res_alias.status_code == 200, f"Status code: {res_alias.status_code}"
        data_alias = res_alias.json()
        assert data_alias["status"] == "success"
        assert "data" in data_alias

    print("\n[SUCCESS] Todos os testes de Live Odds foram aprovados com sucesso!")


if __name__ == "__main__":
    asyncio.run(test_live_odds_endpoints())
