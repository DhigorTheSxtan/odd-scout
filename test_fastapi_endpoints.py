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


async def test_endpoints():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        print("\n[FASTAPI TEST 1] GET /api/status")
        res_status = await client.get("/api/status")
        assert res_status.status_code == 200, f"Status code: {res_status.status_code}"
        data_status = res_status.json()
        assert "oddspapi" in data_status
        assert "nfl_api_sports" in data_status
        assert "modo_orquestracao" in data_status
        assert "gemini_ai" in data_status
        assert "model" in data_status["gemini_ai"]
        print(f" -> /api/status OK: {data_status['modo_orquestracao']} | gemini_ai: {data_status['gemini_ai']['mode']}")

        print("\n[FASTAPI TEST 2] GET /api/jogos-hoje")
        res_jogos = await client.get("/api/jogos-hoje")
        assert res_jogos.status_code == 200, f"Status code: {res_jogos.status_code}"
        data_jogos = res_jogos.json()
        assert data_jogos["status"] == "success"
        assert "total_partidas" in data_jogos
        assert "partidas" in data_jogos
        assert "fonte_dados" in data_jogos
        print(f" -> /api/jogos-hoje OK: {data_jogos['total_partidas']} partidas retornadas.")

        print("\n[FASTAPI TEST 3] GET /api/multipla-segura-dia")
        res_multipla = await client.get("/api/multipla-segura-dia")
        assert res_multipla.status_code == 200, f"Status code: {res_multipla.status_code}"
        data_multipla = res_multipla.json()
        assert "status" in data_multipla
        print(f" -> /api/multipla-segura-dia OK: Status={data_multipla['status']}")

        print("\n[FASTAPI TEST 4] GET /api/gemini/analise-partida/99991")
        res_gemini_partida = await client.get("/api/gemini/analise-partida/99991")
        assert res_gemini_partida.status_code == 200, f"Status code: {res_gemini_partida.status_code}"
        data_gp = res_gemini_partida.json()
        assert "gemini_analise" in data_gp
        assert "recomendacoes" in data_gp["gemini_analise"]
        print(f" -> /api/gemini/analise-partida OK: Partida={data_gp['gemini_analise'].get('partida')}")

        print("\n[FASTAPI TEST 5] GET /api/gemini/stream-analises (SSE)")
        res_sse = await client.get("/api/gemini/stream-analises")
        assert res_sse.status_code == 200, f"Status code: {res_sse.status_code}"
        assert "text/event-stream" in res_sse.headers.get("content-type", "")
        assert "event: init" in res_sse.text
        print(" -> /api/gemini/stream-analises OK: text/event-stream com evento init recebido.")

    print("\n -> Todos os endpoints FastAPI e Gemini validados com sucesso!")


if __name__ == "__main__":
    asyncio.run(test_endpoints())
