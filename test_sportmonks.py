import asyncio
import sys
from httpx import AsyncClient, ASGITransport

if sys.platform == "win32":
    try:
        if sys.stdout.encoding != "utf-8":
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if sys.stderr.encoding != "utf-8":
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from main import app


async def test_sportmonks_integration():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        print("\n========================================================")
        print(" [TEST 1] GET /api/status - Provedor Sportmonks Ativo")
        print("========================================================")
        res_status = await client.get("/api/status")
        assert res_status.status_code == 200, f"Status code: {res_status.status_code}"
        data_status = res_status.json()
        assert "sportmonks" in data_status, "Chave sportmonks ausente em /api/status"
        sm_status = data_status["sportmonks"]
        assert sm_status["configured"] is True, "Sportmonks não está configurado"
        assert sm_status["mode"] == "live_api"
        print(f" -> /api/status OK: Sportmonks configurado={sm_status['configured']} | Modo={sm_status['mode']}")

        print("\n========================================================")
        print(" [TEST 2] GET /api/sportmonks/status - Conectividade & Licença")
        print("========================================================")
        res_sm_status = await client.get("/api/sportmonks/status")
        assert res_sm_status.status_code == 200, f"Status code: {res_sm_status.status_code}"
        data_sm_st = res_sm_status.json()
        assert data_sm_st["status"] == "online", f"Status Sportmonks: {data_sm_st.get('status')}"
        assert data_sm_st["tem_fixtures"] is True, "Acesso a fixtures ausente"
        assert data_sm_st["tem_odds"] is True, "Acesso a odds ausente"
        print(f" -> /api/sportmonks/status OK: {data_sm_st['provedor']} | Enriquecimentos={len(data_sm_st.get('enriquecimentos', []))}")

        print("\n========================================================")
        print(" [TEST 3] GET /api/sportmonks/jogos - Grade Oficial Normalizada")
        print("========================================================")
        res_jogos = await client.get("/api/sportmonks/jogos")
        assert res_jogos.status_code == 200, f"Status code: {res_jogos.status_code}"
        data_jogos = res_jogos.json()
        assert data_jogos["status"] == "success"
        print(f" -> /api/sportmonks/jogos OK: {data_jogos['total_jogos']} partidas retornadas.")
        if data_jogos["jogos"]:
            jogo = data_jogos["jogos"][0]
            assert "mandante" in jogo
            assert "visitante" in jogo
            assert "campeonato" in jogo
            assert "horario" in jogo
            assert "status" in jogo
            assert "placar" in jogo
            assert "linha_segura" in jogo
            assert "recomendacao" in jogo
            print(f"    Exemplo: {jogo['mandante']} vs {jogo['visitante']} ({jogo['campeonato']})")
            print(f"    Status: {jogo['status']} | Placar: {jogo['placar']}")
            print(f"    Linha Segura: {jogo['linha_segura']['selecao']} @{jogo['linha_segura']['odd']} ({jogo['linha_segura']['confianca']}%)")

        print("\n========================================================")
        print(" [TEST 4] GET /api/sportmonks/ao-vivo - Partidas em Andamento")
        print("========================================================")
        res_live = await client.get("/api/sportmonks/ao-vivo")
        assert res_live.status_code == 200, f"Status code: {res_live.status_code}"
        data_live = res_live.json()
        assert data_live["status"] == "success"
        print(f" -> /api/sportmonks/ao-vivo OK: {data_live['total_ao_vivo']} partidas ao vivo neste momento.")

        print("\n========================================================")
        print(" [TEST 5] GET /api/top5-bets - Motor Unificado Futebol + NFL")
        print("========================================================")
        res_top5 = await client.get("/api/top5-bets")
        assert res_top5.status_code == 200, f"Status code: {res_top5.status_code}"
        data_top5 = res_top5.json()
        assert data_top5["status"] == "success"
        assert "total_selecoes" in data_top5
        assert "odd_total" in data_top5
        assert "selecoes" in data_top5
        assert len(data_top5["selecoes"]) <= 5
        print(f" -> /api/top5-bets OK: Total={data_top5['total_selecoes']} seleções | Odd Composta={data_top5['odd_total']}x")
        for i, sel in enumerate(data_top5["selecoes"], 1):
            assert sel["status"] == "A_COMECAR"
            assert sel["recomendacao"]["confianca"] >= 70.0
            print(f"    {i}. [{sel['esporte'].upper()}] {sel['mandante']} vs {sel['visitante']} | {sel['recomendacao']['mercado']} @{sel['recomendacao']['odd']:.2f} ({sel['recomendacao']['confianca']}%)")

    print("\n -> TODOS OS 5 TESTES DA API SPORTMONKS E TOP 5 PASSARAM COM SUCESSO TOTAL!\n")


if __name__ == "__main__":
    asyncio.run(test_sportmonks_integration())
