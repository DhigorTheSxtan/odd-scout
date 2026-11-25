import asyncio
import sys
from datetime import datetime
from zoneinfo import ZoneInfo
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


async def run_tests():
    print("=================================================================")
    print("  SUÍTE DE AUDITORIA: INTEGRAÇÃO REAL DA API DE JOGOS & ZERO MOCKS")
    print("=================================================================")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:

        # Teste 1: Consumo da rota oficial /api/games para data atual
        hoje = datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%Y-%m-%d")
        print(f"\n[TESTE 1] GET /api/games?date={hoje}")
        res = await client.get(f"/api/games?date={hoje}")
        assert res.status_code == 200, f"Status code inesperado: {res.status_code}"
        games = res.json()
        assert isinstance(games, list), "A resposta deve ser uma lista JSON."
        print(f" -> Sucesso: {len(games)} jogos retornados para {hoje} (HTTP 200).")

        # Validação estrita do contrato de dados para cada item
        for idx, g in enumerate(games[:10]):
            assert "id" in g, f"Item {idx} sem campo 'id'"
            assert isinstance(g["id"], (int, str)), f"ID deve ser int ou str: {type(g['id'])}"

            assert "league" in g and isinstance(g["league"], dict), f"Item {idx} league inválido"
            assert "name" in g["league"] and "logo" in g["league"]

            assert "home_team" in g and isinstance(g["home_team"], dict), f"Item {idx} home_team inválido"
            assert "name" in g["home_team"] and "logo" in g["home_team"]

            assert "away_team" in g and isinstance(g["away_team"], dict), f"Item {idx} away_team inválido"
            assert "name" in g["away_team"] and "logo" in g["away_team"]

            assert "status" in g, f"Item {idx} sem 'status'"
            assert g["status"] in ("SCHEDULED", "LIVE", "FINISHED"), f"Status inválido: {g['status']}"

            assert "score" in g and isinstance(g["score"], dict), f"Item {idx} score inválido"
            assert "home" in g["score"] and isinstance(g["score"]["home"], int)
            assert "away" in g["score"] and isinstance(g["score"]["away"], int)

            assert "start_time" in g and isinstance(g["start_time"], str), f"Item {idx} start_time inválido"
            # Valida parsing ISO8601 e fuso horário
            dt = datetime.fromisoformat(g["start_time"].replace("Z", "+00:00"))
            assert dt is not None
        print(" -> Contrato do schema JSON 100% validado para todas as partidas amostradas.")

        # Teste 2: Alias /api/football/matches
        print("\n[TESTE 2] GET /api/football/matches")
        res_alias = await client.get("/api/football/matches")
        assert res_alias.status_code == 200
        games_alias = res_alias.json()
        assert isinstance(games_alias, list)
        print(f" -> Alias /api/football/matches OK: {len(games_alias)} jogos.")

        # Teste 3: Tolerância Zero a Mocks para data futura sem partidas
        print("\n[TESTE 3] GET /api/games?date=2045-06-15 (Tolerância Zero a Mocks)")
        res_future = await client.get("/api/games?date=2045-06-15")
        assert res_future.status_code == 200, f"Status code inesperado: {res_future.status_code}"
        future_games = res_future.json()
        assert future_games == [], f"Esperado [], mas recebeu: {future_games}"
        print(" -> Sucesso: Retornou lista vazia [] com status HTTP 200 legítimo sem nenhum mock.")

        # Teste 4: Filtro por status
        print("\n[TESTE 4] GET /api/games?status=LIVE")
        res_live = await client.get("/api/games?status=LIVE")
        assert res_live.status_code == 200
        live_games = res_live.json()
        for g in live_games:
            assert g["status"] == "LIVE"
        print(f" -> Filtro de status LIVE OK: {len(live_games)} partidas em andamento.")

        # Teste 5: Filtro por status SCHEDULED
        print("\n[TESTE 5] GET /api/games?status=SCHEDULED")
        res_sched = await client.get("/api/games?status=SCHEDULED")
        assert res_sched.status_code == 200
        sched_games = res_sched.json()
        for g in sched_games:
            assert g["status"] == "SCHEDULED"
        print(f" -> Filtro de status SCHEDULED OK: {len(sched_games)} partidas agendadas.")

    print("\n=================================================================")
    print("  TODOS OS 5 TESTES DE AUDITORIA FORAM APROVADOS COM SUCESSO!")
    print("=================================================================")


if __name__ == "__main__":
    asyncio.run(run_tests())
