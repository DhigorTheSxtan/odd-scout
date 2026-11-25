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
from config import is_pandascore_configured, PANDASCORE_TOKEN, PANDASCORE_BASE_URL
from pandascore_service import pandascore_service


async def run_pandascore_tests():
    print("=" * 80)
    print("   TESTE DE INTEGRAÇÃO OFICIAL: PANDASCORE (ESPORTS & SPORTS DATA API)        ")
    print("=" * 80)

    # 1. Configuração e Token
    print("\n[TEST 1/5] Verificando Variáveis de Ambiente e Configuração...")
    assert is_pandascore_configured(), "PandaScore deve estar configurado no .env"
    assert len(PANDASCORE_TOKEN) > 20, "Token deve ser uma chave Bearer válida do PandaScore"
    print(f"  [OK] Token ativo detectado: {PANDASCORE_TOKEN[:6]}...{PANDASCORE_TOKEN[-4:]}")
    print(f"  [OK] Base URL oficial: {PANDASCORE_BASE_URL}")

    # 2. Conectividade e Status da API
    print("\n[TEST 2/5] Testando Conectividade Direta e Status com api.pandascore.co...")
    status_conexao = await pandascore_service.obter_status_conexao()
    assert status_conexao.get("status") in ("online", "chave_invalida"), f"Status inesperado: {status_conexao}"
    assert status_conexao.get("provedor") == "PandaScore Official (https://api.pandascore.co)"
    print(f"  [OK] Conectado à PandaScore! Status: {status_conexao.get('status')}, Latência: {status_conexao.get('latencia_ms')}ms")
    print(f"  [OK] Videogames suportados reportados: {status_conexao.get('videogames_suportados')}")

    # 3. Videogames e Ligas
    print("\n[TEST 3/5] Consultando Lista de Videogames e Torneios...")
    videogames = await pandascore_service.obter_videogames()
    assert len(videogames) > 0, "Deve retornar lista de videogames suportados"
    print(f"  [OK] Total de videogames retornados: {len(videogames)}")
    slugs = [vg.get("slug") for vg in videogames[:5]]
    print(f"  [OK] Exemplos de jogos: {', '.join(slugs)}")

    ligas = await pandascore_service.obter_ligas(videogame_slug="cs-go")
    print(f"  [OK] Torneios/Ligas CS2 retornados: {len(ligas)}")

    # 4. Partidas Ao Vivo e Consolidadas
    print("\n[TEST 4/5] Coletando Partidas Ao Vivo e Próximas...")
    partidas_res = await pandascore_service.buscar_todas_partidas(limite=10)
    assert "partidas" in partidas_res, "Dicionário de resposta deve conter chave 'partidas'"
    assert "total" in partidas_res, "Dicionário de resposta deve conter chave 'total'"
    print(f"  [OK] Partidas recuperadas: {partidas_res.get('total')} (Ao vivo: {partidas_res.get('total_ao_vivo')})")

    # 5. Endpoints REST do FastAPI (/api/pandascore/* e /api/status)
    print("\n[TEST 5/5] Testando Endpoints REST do FastAPI (/api/pandascore/*)...")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # GET /api/status
        res_sys = await client.get("/api/status")
        assert res_sys.status_code == 200, f"GET /api/status falhou com HTTP {res_sys.status_code}"
        data_sys = res_sys.json()
        assert "pandascore" in data_sys, "Bloco 'pandascore' deve constar em /api/status"
        assert data_sys["pandascore"]["configured"] is True
        print(f"  [OK] GET /api/status: Bloco 'pandascore' verificado com sucesso!")

        # GET /api/pandascore/status
        res_stat = await client.get("/api/pandascore/status")
        assert res_stat.status_code == 200
        assert res_stat.json().get("status") == "online"
        print(f"  [OK] GET /api/pandascore/status: HTTP 200 (Online)")

        # GET /api/pandascore/videogames
        res_vg = await client.get("/api/pandascore/videogames")
        assert res_vg.status_code == 200
        assert len(res_vg.json()) > 0
        print(f"  [OK] GET /api/pandascore/videogames: HTTP 200 ({len(res_vg.json())} jogos)")

        # GET /api/pandascore/partidas
        res_part = await client.get("/api/pandascore/partidas?limite=5")
        assert res_part.status_code == 200
        data_part = res_part.json()
        assert "partidas" in data_part
        print(f"  [OK] GET /api/pandascore/partidas: HTTP 200 ({len(data_part['partidas'])} partidas)")

        # GET /api/pandascore/ao-vivo
        res_live = await client.get("/api/pandascore/ao-vivo")
        assert res_live.status_code == 200
        print(f"  [OK] GET /api/pandascore/ao-vivo: HTTP 200 ({res_live.json().get('total_ao_vivo')} ao vivo)")

        # GET /api/pandascore/ligas
        res_ligas = await client.get("/api/pandascore/ligas")
        assert res_ligas.status_code == 200
        print(f"  [OK] GET /api/pandascore/ligas: HTTP 200 ({len(res_ligas.json())} ligas)")

    print("\n" + "=" * 80)
    print("      TODOS OS TESTES DO PANDASCORE FORAM APROVADOS COM SUCESSO!        ")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(run_pandascore_tests())
