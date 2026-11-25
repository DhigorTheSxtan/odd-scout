import asyncio
import json
from gemini_analyzer import (
    gemini_analyzer,
    PerfilRiscoGemini,
    RecomendacaoGemini,
    AnalisePartidaGemini
)

async def test_gemini_schemas_and_fallback():
    print("--- TESTE 1: Schema Pydantic ---")
    rec = RecomendacaoGemini(
        mercado="Mais de 8.5 Escanteios",
        odd_referencia=1.75,
        grau_confianca_percentual=82,
        perfil_risco=PerfilRiscoGemini.SEGURA,
        justificativa_quantitativa="Ambos os times somam média de 11.2 cantos/jogo"
    )
    analise = AnalisePartidaGemini(
        partida="Flamengo vs Palmeiras",
        analise_tática_resumida="Duelo equilibrado com alta intensidade pelas alas e volume ofensivo superior nas transições.",
        recomendacoes=[rec]
    )
    serialized = analise.model_dump()
    print("Schema serializado com sucesso:")
    print(json.dumps(serialized, indent=2, ensure_ascii=False))

    assert serialized["partida"] == "Flamengo vs Palmeiras"
    assert serialized["recomendacoes"][0]["perfil_risco"] in ("Segura", "Moderada", "Alto Risco")
    print("[OK] TESTE 1 PASSOU!")

    print("\n--- TESTE 2: Fallback Resiliente (sem chave ou em timeout) ---")
    mock_match = {
        "partida": {
            "id": 99991,
            "data_hora": "2026-09-14T20:00:00-03:00",
            "mandante": {"id": 1, "nome": "Flamengo"},
            "visitante": {"id": 2, "nome": "Palmeiras"},
            "estadio": "Maracana",
            "status_descricao": "Agendado"
        },
        "campeonato": {
            "id": 71,
            "nome": "Brasileirao Serie A",
            "rodada": "Rodada 26"
        },
        "metricas_chave": {
            "gols_esperados": {"home": 1.45, "away": 1.15, "total": 2.60},
            "mercados_poisson": {
                "over_1_5": 79.2,
                "over_2_5": 54.1,
                "under_2_5": 45.9,
                "btts_yes": 56.4,
                "home_win": 44.0,
                "draw": 28.0,
                "away_win": 28.0
            },
            "escanteios": {
                "disponivel": True,
                "esperado_mandante": 5.8,
                "esperado_visitante": 5.4,
                "esperado_total": 11.2
            },
            "finalizacoes": {
                "disponivel": True,
                "total_esperado": 28.5,
                "no_alvo_esperado": 10.2
            },
            "laterais": {
                "disponivel": True,
                "esperado_total": 42.0
            }
        },
        "recomendacoes": [
            {
                "mercado": "Escanteios",
                "selecao": "Mais de 8.5 Escanteios",
                "grau_confianca": 84.0,
                "odd_referencia": 1.75,
                "perfil_risco": "seguro",
                "justificativa_estatistica": "Ambos os times somam media de 11.2 cantos/jogo nas ultimas 8 partidas."
            },
            {
                "mercado": "Gols",
                "selecao": "Mais de 1.5 Gols",
                "grau_confianca": 78.0,
                "odd_referencia": 1.38,
                "perfil_risco": "seguro",
                "justificativa_estatistica": "Poisson projeta 79.2% de probabilidade empirica para over 1.5 gols."
            }
        ]
    }

    resultado = await gemini_analyzer.analisar_partida_async(mock_match)
    print("Resultado da inferencia/fallback:")
    print(json.dumps(resultado, indent=2, ensure_ascii=True))

    assert "gemini_analise" in resultado
    assert resultado["status"] == "success"
    assert "partida" in resultado["gemini_analise"]
    assert len(resultado["gemini_analise"]["recomendacoes"]) > 0
    print("[OK] TESTE 2 PASSOU!")

    print("\n--- TESTE 3: Server-Sent Events (SSE) Stream ---")
    events = []
    async for sse_chunk in gemini_analyzer.stream_analises_sse([mock_match]):
        events.append(sse_chunk)
        if len(events) <= 3:
            print("SSE Chunk recebido:\n", sse_chunk.strip().encode("ascii", "replace").decode("ascii"))

    assert len(events) >= 3
    assert "event: match_analysis" in "".join(events)
    assert "event: done" in "".join(events)
    print("[OK] TESTE 3 PASSOU!")

if __name__ == "__main__":
    asyncio.run(test_gemini_schemas_and_fallback())
