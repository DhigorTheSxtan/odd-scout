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
from config import is_sharpapi_configured, SHARPAPI_KEY, SHARPAPI_BASE_URL
from sharpapi_service import sharpapi_service


async def run_sharpapi_tests():
    print("================================================================================")
    print("   TESTE DE INTEGRAÇÃO OFICIAL: SHARPAPI (SPORTS BETTING ODDS API)              ")
    print("================================================================================")

    print("\n[TEST 1/5] Validando Chave e Configuração de Ambiente (.env)...")
    assert is_sharpapi_configured(), "SharpAPI deve estar configurada no .env"
    assert SHARPAPI_KEY.startswith("sk_live_"), "Chave deve ser o token oficial sk_live_..."
    print(f"  [OK] Chave ativa detectada: {SHARPAPI_KEY[:7]}...{SHARPAPI_KEY[-4:]}")
    print(f"  [OK] Base URL oficial: {SHARPAPI_BASE_URL}")

    print("\n[TEST 2/5] Testando Conectividade Direta e Health Check (/odds?limit=1)...")
    status_conexao = await sharpapi_service.obter_status_conexao()
    assert status_conexao.get("status") == "online", f"Status esperado: online. Recebido: {status_conexao}"
    assert status_conexao.get("status_code") == 200
    assert "DraftKings" in status_conexao.get("casas_suportadas", [])
    assert "FanDuel" in status_conexao.get("casas_suportadas", [])
    print(f"  [OK] Conectado com sucesso à SharpAPI! Latência: {status_conexao.get('latencia_ms')}ms")
    print(f"  [OK] Bookmakers suportados: {status_conexao.get('casas_suportadas')}")

    print("\n[TEST 3/5] Testando Obtenção de Cotações da NFL (DraftKings & FanDuel)...")
    odds_nfl = await sharpapi_service.buscar_odds_nfl()
    assert odds_nfl.get("status") == "success"
    assert odds_nfl.get("raw_items_count", 0) > 0, "Deve retornar cotações para a NFL"
    print(f"  [OK] Total de cotações da NFL retornadas: {odds_nfl.get('raw_items_count')}")
    print(f"  [OK] Total de confrontos mapeados: {odds_nfl.get('total_confrontos')}")
    for match, m_data in list(odds_nfl.get("confrontos", {}).items())[:2]:
        print(f"       -> {match} | Bookmakers: {list(m_data.get('bookmakers', {}).keys())}")

    print("\n[TEST 4/5] Testando Obtenção de Esportes e Ligas...")
    esportes = await sharpapi_service.obter_esportes()
    assert len(esportes) > 0, "Deve retornar lista de esportes"
    ligas = await sharpapi_service.obter_ligas()
    assert len(ligas) > 0, "Deve retornar lista de ligas"
    print(f"  [OK] Total de esportes disponíveis na SharpAPI: {len(esportes)}")
    print(f"  [OK] Total de ligas disponíveis na SharpAPI: {len(ligas)}")

    print("\n[TEST 5/5] Testando Endpoints REST do FastAPI (/api/sharpapi/*)...")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # GET /api/status
        res_sys = await client.get("/api/status")
        assert res_sys.status_code == 200
        data_sys = res_sys.json()
        assert "sharpapi" in data_sys
        assert data_sys["sharpapi"]["configured"] is True
        print(f"  [OK] GET /api/status: Bloco 'sharpapi' verificado com sucesso!")

        # GET /api/sharpapi/status
        res_stat = await client.get("/api/sharpapi/status")
        assert res_stat.status_code == 200
        assert res_stat.json().get("status") == "online"
        print(f"  [OK] GET /api/sharpapi/status: HTTP 200 (Online)")

        # GET /api/sharpapi/odds?league=nfl
        res_odds = await client.get("/api/sharpapi/odds?league=nfl")
        assert res_odds.status_code == 200
        assert len(res_odds.json().get("odds", [])) > 0
        print(f"  [OK] GET /api/sharpapi/odds?league=nfl: HTTP 200 ({len(res_odds.json().get('odds', []))} cotações)")

        # GET /api/sharpapi/sports
        res_sports = await client.get("/api/sharpapi/sports")
        assert res_sports.status_code == 200
        print(f"  [OK] GET /api/sharpapi/sports: HTTP 200 ({len(res_sports.json())} esportes)")

    print("\n================================================================================")
    print("      TODOS OS TESTES DA SHARPAPI FORAM APROVADOS COM SUCESSO!                 ")
    print("================================================================================")
    return True

if __name__ == "__main__":
    asyncio.run(run_sharpapi_tests())
