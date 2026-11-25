import sys
import asyncio
from datetime import datetime
from httpx import AsyncClient, ASGITransport

if sys.platform == "win32":
    try:
        if sys.stdout.encoding != 'utf-8':
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        if sys.stderr.encoding != 'utf-8':
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

from config import (
    APISPORTS_SPORTS_CONFIG,
    is_apisports_configured,
    get_apisports_config
)
from apisports_service import apisports_service
from main import app


async def test_config_and_catalog():
    print("\n[TEST 1] Validação do Catálogo Multi-Esportes e Configurações...")
    assert len(APISPORTS_SPORTS_CONFIG) == 11, f"Esperado 11 esportes, encontrado {len(APISPORTS_SPORTS_CONFIG)}"
    
    esportes_esperados = [
        "football", "afl", "baseball", "basketball",
        "handball", "hockey", "mma", "nba", "rugby", "volleyball", "american-football"
    ]
    for sp in esportes_esperados:
        assert sp in APISPORTS_SPORTS_CONFIG, f"Esporte '{sp}' ausente no catálogo!"
        cfg = get_apisports_config(sp)
        assert cfg.get("url"), f"Esporte '{sp}' sem URL configurada!"
        assert cfg.get("key"), f"Esporte '{sp}' sem Key configurada!"
        assert cfg.get("name"), f"Esporte '{sp}' sem nome amigável!"
        assert cfg.get("route_type"), f"Esporte '{sp}' sem route_type!"

    assert is_apisports_configured(), "API-Sports deve reportar configurada com a chave fornecida."
    print(f" -> Catálogo validado com 100% de sucesso! 11 esportes registrados.")


async def test_normalization_engine():
    print("\n[TEST 2] Validação do Motor Polimórfico de Normalização de Eventos...")
    
    # 1. Futebol
    raw_football = {
        "fixture": {"id": 12345, "date": "2026-09-15T20:00:00Z", "status": {"short": "1H", "long": "Primeiro Tempo"}},
        "teams": {"home": {"id": 1, "name": "Arsenal", "logo": "ars.png"}, "away": {"id": 2, "name": "Chelsea", "logo": "che.png"}},
        "goals": {"home": 1, "away": 0},
        "league": {"id": 39, "name": "Premier League", "country": "England", "logo": "pl.png", "round": "Rodada 5"}
    }
    norm_foot = apisports_service.normalizar_evento("football", raw_football, "Futebol")
    assert norm_foot["id"] == 12345
    assert norm_foot["mandante"]["nome"] == "Arsenal"
    assert norm_foot["visitante"]["nome"] == "Chelsea"
    assert norm_foot["placar"]["mandante"] == 1
    assert norm_foot["esporte"] == "football"

    # 2. MMA
    raw_mma = {
        "id": 888,
        "date": "2026-09-15T23:00:00Z",
        "fighters": {"first": {"name": "Alex Poatan"}, "second": {"name": "Israel Adesanya"}},
        "slug": "UFC 300"
    }
    norm_mma = apisports_service.normalizar_evento("mma", raw_mma, "MMA / UFC")
    assert norm_mma["id"] == 888
    assert norm_mma["mandante"]["nome"] == "Alex Poatan"
    assert norm_mma["visitante"]["nome"] == "Israel Adesanya"

    # 3. NBA / Basquete
    raw_nba = {
        "id": 777,
        "date": "2026-09-15T21:30:00Z",
        "teams": {"home": {"id": 10, "name": "Los Angeles Lakers"}, "away": {"id": 11, "name": "Golden State Warriors"}},
        "scores": {"home": {"total": 112}, "away": {"total": 108}},
        "league": {"name": "NBA"}
    }
    norm_nba = apisports_service.normalizar_evento("nba", raw_nba, "NBA")
    assert norm_nba["id"] == 777
    assert norm_nba["placar"]["mandante"] == 112
    assert norm_nba["placar"]["visitante"] == 108

    print(" -> Normalização polimórfica aprovada para Futebol, MMA e Esportes Coletivos!")


async def test_service_status_and_resilience():
    print("\n[TEST 3] Testando Comunicação Real com APIs e Resiliência a Status...")
    res_status = await apisports_service.obter_status_geral()
    assert res_status["status"] == "success"
    assert "esportes" in res_status
    assert len(res_status["esportes"]) == 11
    print(f" -> Status geral executado com sucesso: {res_status['total_esportes']} modalidades consultadas.")

    # Consulta esporte individual (Futebol)
    st_foot = await apisports_service.obter_status_esporte("football")
    assert st_foot["esporte"] == "football"
    assert "status" in st_foot
    print(f" -> Status Futebol: {st_foot['status']} | Configurado: {st_foot.get('configurado')}")

    # Consulta jogos do esporte (Futebol)
    res_jogos = await apisports_service.buscar_jogos(sport="football", data="2026-09-15")
    assert "status" in res_jogos
    assert "jogos" in res_jogos
    print(f" -> Busca de jogos de futebol concluída sem falha fatal: Status={res_jogos['status']}, Total={res_jogos['total']}")


async def test_fastapi_endpoints():
    print("\n[TEST 4] Testando Endpoints FastAPI da Suíte Multi-Esportes...")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. /api/status contém apisports
        res_sys = await client.get("/api/status")
        assert res_sys.status_code == 200
        data_sys = res_sys.json()
        assert "apisports" in data_sys
        assert data_sys["apisports"]["configured"] is True
        assert data_sys["apisports"]["total_sports"] == 11
        print(f" -> /api/status OK: {data_sys['apisports']['total_sports']} esportes reportados.")

        # 2. GET /api/sports/status
        res_sports = await client.get("/api/sports/status")
        assert res_sports.status_code == 200
        data_sports = res_sports.json()
        assert data_sports["status"] == "success"
        assert "esportes" in data_sports
        print(f" -> GET /api/sports/status OK: {len(data_sports['esportes'])} esportes no payload.")

        # 3. GET /api/sports/nba/status
        res_nba = await client.get("/api/sports/nba/status")
        assert res_nba.status_code == 200
        data_nba = res_nba.json()
        assert data_nba["esporte"] == "nba"
        print(" -> GET /api/sports/nba/status OK.")

        # 4. GET /api/sports/basketball/jogos
        res_bball = await client.get("/api/sports/basketball/jogos?data=2026-09-15")
        assert res_bball.status_code == 200
        data_bball = res_bball.json()
        assert "jogos" in data_bball
        print(f" -> GET /api/sports/basketball/jogos OK: Total={data_bball.get('total')}")

        # 5. POST /api/config/apisports-key
        res_post_key = await client.post(
            "/api/config/apisports-key",
            json={"api_key": "6663cf644fc7f534acff36d5dc033458", "sport": "volleyball"}
        )
        assert res_post_key.status_code == 200
        data_post = res_post_key.json()
        assert data_post["status"] == "success"
        print(f" -> POST /api/config/apisports-key OK: {data_post['message']}")


async def run_suite():
    print("=" * 70)
    print("  SUÍTE DE INTEGRAÇÃO: API-SPORTS MULTI-ESPORTES (11 MODALIDADES) ")
    print("=" * 70)
    await test_config_and_catalog()
    await test_normalization_engine()
    await test_service_status_and_resilience()
    await test_fastapi_endpoints()
    print("\n" + "=" * 70)
    print("  TODOS OS TESTES MULTI-ESPORTES FORAM APROVADOS COM SUCESSO!     ")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    asyncio.run(run_suite())
