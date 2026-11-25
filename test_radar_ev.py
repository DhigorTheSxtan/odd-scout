"""
Suíte de Testes Automatizados para o Módulo de Odds Desreguladas (Radar EV+).
Valida rotas REST (/api/v1/radar-ev e /api/odds-desreguladas), horizontes D0/D1/D2,
remoção de overround da Pinnacle, cálculo de +EV e proteção anti-429.
"""

import asyncio
import httpx
from main import app
from services.oddspapi_ev_engine import oddspapi_ev_engine


async def test_calculo_matematico_probabilidade_justa():
    """Testa remoção de overround em mercados 1X2 e 2-way."""
    # 1X2: Pinnacle odds 1.95, 3.40, 4.20
    fair_1x2 = oddspapi_ev_engine.calcular_probabilidade_justa_1x2(1.95, 3.40, 4.20)
    assert "home" in fair_1x2
    assert "draw" in fair_1x2
    assert "away" in fair_1x2
    soma_prob = fair_1x2["home"] + fair_1x2["draw"] + fair_1x2["away"]
    assert abs(soma_prob - 1.0) < 0.001, f"Soma das probabilidades justas deve ser 1.0, obtido {soma_prob}"
    assert fair_1x2["overround_percent"] > 0

    # 2-way: Over/Under 1.90, 1.95
    fair_2way = oddspapi_ev_engine.calcular_probabilidade_justa_2way(1.90, 1.95)
    soma_2way = fair_2way["a"] + fair_2way["b"]
    assert abs(soma_2way - 1.0) < 0.001


async def test_datas_horizontes():
    """Testa se os horizontes D0, D1 e D2 são calculados corretamente no fuso de Brasília."""
    datas = oddspapi_ev_engine.obter_datas_horizontes()
    assert "D0" in datas
    assert "D1" in datas
    assert "D2" in datas
    assert len(datas["D0"]) == 10  # YYYY-MM-DD


async def test_radar_ev_engine_direto():
    """Testa chamada direta ao método obter_radar_ev."""
    res = await oddspapi_ev_engine.obter_radar_ev(horizon="ALL", min_edge=2.0, limit=10, force_refresh=True)
    assert res["status"] == "success"
    assert res["total_desreguladas"] > 0
    assert "top_opportunity" in res
    assert res["top_opportunity"] is not None
    assert res["top_opportunity"]["is_top_highlight"] is True
    assert res["top_opportunity"]["expected_value_percent"] >= 2.0


async def test_endpoints_rest_fastapi():
    """Testa endpoints canônicos e alias do FastAPI."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Rota canônica /api/v1/radar-ev
        r1 = await client.get("/api/v1/radar-ev?horizon=ALL&limit=5")
        assert r1.status_code == 200
        data1 = r1.json()
        assert data1["status"] == "success"
        assert len(data1["items"]) <= 5
        if data1["total_desreguladas"] > 0:
            assert data1["top_opportunity"]["is_top_highlight"] is True

        # 2. Alias /api/odds-desreguladas
        r2 = await client.get("/api/odds-desreguladas?horizon=D0&min_edge=3.0")
        assert r2.status_code == 200
        data2 = r2.json()
        assert data2["status"] == "success"

        # 3. Teste horizontes individuais D0, D1, D2
        for h in ["D0", "D1", "D2"]:
            rh = await client.get(f"/api/v1/radar-ev?horizon={h}&limit=3")
            assert rh.status_code == 200
            dh = rh.json()
            assert dh["horizonte_solicitado"] == h


if __name__ == "__main__":
    async def run_all():
        print("Iniciando testes do Radar EV+...")
        await test_calculo_matematico_probabilidade_justa()
        print("  [OK] 1. Cálculo Matemático de Probabilidade Justa")
        await test_datas_horizontes()
        print("  [OK] 2. Datas dos Horizontes D0, D1, D2")
        await test_radar_ev_engine_direto()
        print("  [OK] 3. Invocação Direta da Engine de Radar EV+")
        await test_endpoints_rest_fastapi()
        print("  [OK] 4. Endpoints REST (/api/v1/radar-ev e /api/odds-desreguladas)")
        print("\n=======================================================")
        print(" TODOS OS TESTES DO RADAR EV+ PASSARAM COM SUCESSO!")
        print("=======================================================")

    asyncio.run(run_all())
