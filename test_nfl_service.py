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


async def test_nfl_integration():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        print("\n========================================================")
        print(" [TEST 1] GET /api/status - Integração Big Balls Data")
        print("========================================================")
        res_status = await client.get("/api/status")
        assert res_status.status_code == 200, f"Status code: {res_status.status_code}"
        data_status = res_status.json()
        assert "nfl_bigballsdata" in data_status, "Chave nfl_bigballsdata não encontrada em /api/status"
        print(f" -> /api/status OK: NFL configurada={data_status['nfl_bigballsdata']['configured']} | Mode={data_status['nfl_bigballsdata']['mode']}")

        print("\n========================================================")
        print(" [TEST 2] GET /api/nfl/status - Saúde do Serviço NFL")
        print("========================================================")
        res_nfl_status = await client.get("/api/nfl/status")
        assert res_nfl_status.status_code == 200, f"Status code: {res_nfl_status.status_code}"
        data_nfl_st = res_nfl_status.json()
        assert data_nfl_st["status"] == "online"
        assert "total_partidas" in data_nfl_st
        assert "semanas_disponiveis" in data_nfl_st
        print(f" -> /api/nfl/status OK: {data_nfl_st['total_partidas']} partidas | Semanas={list(data_nfl_st['semanas_disponiveis'].keys())}")

        print("\n========================================================")
        print(" [TEST 3] GET /api/nfl/jogos - Grade Completa e Schema PT-BR")
        print("========================================================")
        res_jogos = await client.get("/api/nfl/jogos")
        assert res_jogos.status_code == 200, f"Status code: {res_jogos.status_code}"
        data_jogos = res_jogos.json()
        assert data_jogos["status"] == "success"
        assert data_jogos["total_jogos"] > 0
        assert len(data_jogos["jogos"]) > 0

        primeiro_jogo = data_jogos["jogos"][0]
        # Validação rígida do schema exigido pelo usuário
        assert "time_casa" in primeiro_jogo, "time_casa ausente"
        assert "time_fora" in primeiro_jogo, "time_fora ausente"
        assert "data_hora" in primeiro_jogo, "data_hora ausente"
        assert "status" in primeiro_jogo, "status ausente"
        assert "placar" in primeiro_jogo, "placar ausente"
        assert "mercados" in primeiro_jogo, "mercados ausente"
        assert "linha_segura" in primeiro_jogo, "linha_segura ausente"

        # Validar conteúdo em PT-BR
        assert "nome" in primeiro_jogo["time_casa"]
        assert "sigla" in primeiro_jogo["time_casa"]
        assert "nome" in primeiro_jogo["time_fora"]
        assert "sigla" in primeiro_jogo["time_fora"]
        assert "horario" in primeiro_jogo
        assert "data_formatada" in primeiro_jogo
        assert "tempo_restante_texto" in primeiro_jogo

        # Validar mercados da NFL (Moneyline, Spread, Total de Pontos)
        tipos_mercados = [m.get("tipo", "") for m in primeiro_jogo["mercados"]]
        assert any("Moneyline" in t for t in tipos_mercados), "Mercado Moneyline ausente"
        assert any("Handicap" in t or "Spread" in t for t in tipos_mercados), "Mercado Handicap ausente"
        assert any("Total" in t for t in tipos_mercados), "Mercado Total de Pontos ausente"

        # Validar Linha Segura
        ls = primeiro_jogo["linha_segura"]
        assert "selecao" in ls
        assert "odd" in ls
        assert "confianca" in ls
        assert "justificativa_tatica" in ls
        assert ls["confianca"] >= 70.0

        print(f" -> /api/nfl/jogos OK: {data_jogos['total_jogos']} jogos retornados.")
        print(f"    Exemplo: {primeiro_jogo['time_casa']['nome']} ({primeiro_jogo['time_casa']['sigla']}) vs {primeiro_jogo['time_fora']['nome']} ({primeiro_jogo['time_fora']['sigla']})")
        print(f"    Data/Hora BRT: {primeiro_jogo['data_formatada']} às {primeiro_jogo['horario']}")
        print(f"    Linha Segura: {ls['selecao']} @{ls['odd']:.2f} ({ls['confianca']}% conf.)")

        print("\n========================================================")
        print(" [TEST 4] GET /api/nfl/jogos?semana=2 - Filtro por Semana")
        print("========================================================")
        res_sem2 = await client.get("/api/nfl/jogos?semana=2")
        assert res_sem2.status_code == 200
        data_sem2 = res_sem2.json()
        assert data_sem2["total_jogos"] > 0
        for j in data_sem2["jogos"]:
            assert j["semana_id"] == 2 or "2" in j["semana"]
        print(f" -> Filtro de Semana OK: {data_sem2['total_jogos']} jogos na Semana 2.")

        print("\n========================================================")
        print(" [TEST 5] GET /api/nfl/jogos?status=pre_jogo - Filtro por Status")
        print("========================================================")
        res_pre = await client.get("/api/nfl/jogos?status=pre_jogo")
        assert res_pre.status_code == 200
        data_pre = res_pre.json()
        for j in data_pre["jogos"]:
            assert j["status"]["tipo"] == "pre_jogo"
        print(f" -> Filtro de Status OK: {data_pre['total_jogos']} jogos pré-jogo.")

        print("\n========================================================")
        print(" [TEST 6] GET /api/jogos-hoje - Não-Regressão do Futebol Tradicional")
        print("========================================================")
        res_soccer = await client.get("/api/jogos-hoje")
        assert res_soccer.status_code == 200
        data_soccer = res_soccer.json()
        assert data_soccer["status"] == "success"
        print(f" -> /api/jogos-hoje OK: Futebol tradicional funcionando perfeitamente ({data_soccer['total_partidas']} partidas).")

    print("\n -> TODOS OS 6 TESTES DE INTEGRAÇÃO DA NFL PASSARAM COM SUCESSO!")


if __name__ == "__main__":
    asyncio.run(test_nfl_integration())
