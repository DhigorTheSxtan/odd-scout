from fastapi.testclient import TestClient
from main import app
from oddscout_service import oddscout_service

client = TestClient(app)

def test_status_endpoint():
    response = client.get("/api/oddscout/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert data["casas_conectadas"] >= 5
    assert "Betano" in data["casas_lista"]

def test_banca_endpoint():
    response = client.get("/api/oddscout/banca")
    assert response.status_code == 200
    data = response.json()
    assert "saldo_atual" in data
    assert data["saldo_atual"] > 0
    assert "analise_formatos" in data

def test_ligas_contadores():
    response = client.get("/api/oddscout/ligas-contadores")
    assert response.status_code == 200
    data = response.json()
    assert len(data["ligas"]) > 0
    assert len(data["datas"]) > 0

def test_bet_do_dia():
    response = client.get("/api/oddscout/bet-do-dia")
    assert response.status_code == 200
    data = response.json()
    assert "odd_acumulada" in data
    assert data["odd_acumulada"] > 1.0

def test_radar_oportunidades():
    response = client.get("/api/oddscout/radar-oportunidades")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert len(data["oportunidades"]) >= 2
    for item in data["oportunidades"]:
        assert "valor_esperado" in item
        assert "casa_atrasada" in item
        assert item["odd_atual"] > 1.0

def test_gerar_multipla_post():
    payload = {
        "num_jogos": 5,
        "perfil_risco": "alto_retorno",
        "valor_aposta": 100.0
    }
    response = client.post("/api/oddscout/gerar-multipla", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert len(data["selecoes"]) == 5
    assert "odds_totais_casas" in data
    assert "Betano" in data["odds_totais_casas"]
    assert "Bet365" in data["odds_totais_casas"]
    assert "KTO" in data["odds_totais_casas"]
    assert "Sportingbet" in data["odds_totais_casas"]
    assert data["odds_totais_casas"]["Betano"] >= data["odds_totais_casas"]["Sportingbet"]
    assert "simulacao_bolso" in data
    assert len(data["simulacao_bolso"]["cards"]) == 4

def test_simular_retorno_custom_stake():
    payload = {
        "valor_aposta": 250.0,
        "odds_casas": {
            "Betano": 38.50,
            "Bet365": 34.20,
            "KTO": 31.80,
            "Sportingbet": 29.20
        },
        "melhor_casa": "Betano"
    }
    response = client.post("/api/oddscout/simular-retorno", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["retorno_maximo"] == round(250.0 * 38.50, 2)
    assert len(data["cards"]) == 4
    betano_card = [c for c in data["cards"] if c["nome_casa"] == "Betano"][0]
    assert betano_card["valor_recebe"] == 9625.00
    assert betano_card["lucro_limpo"] == 9375.00
    sportingbet_card = [c for c in data["cards"] if c["nome_casa"] == "Sportingbet"][0]
    assert sportingbet_card["valor_recebe"] == 7300.00
    assert sportingbet_card["deixa_de_ganhar"] == round(9625.00 - 7300.00, 2)

def test_post_nova_aposta():
    payload = {
        "valor": 50.0,
        "casa": "Betano",
        "odd_total": 15.20,
        "jogos_count": 4
    }
    response = client.post("/api/oddscout/banca/aposta", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["aposta"]["valor_apostado"] == 50.0

def test_banca_ajustar():
    response = client.post("/api/oddscout/banca/ajustar", json={"novo_saldo": 16500.0})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["banca"]["saldo_atual"] == 16500.0
    # Restaura saldo padrão
    client.post("/api/oddscout/banca/ajustar", json={"novo_saldo": 12450.0})

def test_historico_apostas():
    response = client.get("/api/oddscout/historico-apostas")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "apostas" in data
    assert len(data["apostas"]) > 0

def test_jogos_ao_vivo():
    response = client.get("/api/oddscout/ao-vivo")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "total_ao_vivo" in data
    assert isinstance(data.get("jogos"), list)
    assert data["total_ao_vivo"] == len(data["jogos"])

if __name__ == "__main__":
    test_status_endpoint()
    test_banca_endpoint()
    test_ligas_contadores()
    test_bet_do_dia()
    test_radar_oportunidades()
    test_gerar_multipla_post()
    test_simular_retorno_custom_stake()
    test_post_nova_aposta()
    test_banca_ajustar()
    test_historico_apostas()
    test_jogos_ao_vivo()
    print("ALL TESTS PASSED SUCCESSFULLY!")
