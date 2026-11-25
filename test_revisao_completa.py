import asyncio
import json
import os
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
from gemini_analyzer import (
    gemini_analyzer,
    PerfilRiscoGemini,
    RecomendacaoGemini,
    AnalisePartidaGemini
)
from config import is_gemini_configured, GEMINI_MODEL

async def executar_revisao_completa():
    print("================================================================================")
    print("      REVISÃO GERAL E AUDITORIA DO PIPELINE FOOTBALL ANALYTICS & GEMINI FLASH    ")
    print("================================================================================")


    print("\n[CHECK 1/6] Verificando Schemas Pydantic e Structured Output...")
    try:
        rec = RecomendacaoGemini(
            mercado="Mais de 8.5 Escanteios",
            odd_referencia=1.78,
            grau_confianca_percentual=85,
            perfil_risco=PerfilRiscoGemini.SEGURA,
            justificativa_quantitativa="Ambos os times somam média de 11.2 cantos/jogo"
        )
        analise = AnalisePartidaGemini(
            partida="Flamengo vs Palmeiras",
            analise_tática_resumida="Confronto de alto volume ofensivo pelas alas e transições verticais rápidas.",
            recomendacoes=[rec]
        )
        d = analise.model_dump()
        assert d["partida"] == "Flamengo vs Palmeiras"
        assert d["recomendacoes"][0]["perfil_risco"] == "Segura"
        assert d["recomendacoes"][0]["grau_confianca_percentual"] == 85
        print("  [OK] Schemas Pydantic validados com sucesso!")
    except Exception as e:
        print(f"  [FALHA] Erro no teste de schema: {e}")
        return False


    print("\n[CHECK 2/6] Testando GeminiSportsAnalyzer (Inferência e Fallback Resiliente)...")
    partida_teste = {
        "partida": {
            "id": 101010,
            "data_hora": "2026-09-14T21:30:00-03:00",
            "mandante": {"id": 1, "nome": "Corinthians"},
            "visitante": {"id": 2, "nome": "São Paulo"},
            "estadio": "Neo Química Arena",
            "status_descricao": "Agendado"
        },
        "campeonato": {"id": 71, "nome": "Brasileirão Série A", "rodada": "Rodada 26"},
        "metricas_chave": {
            "gols_esperados": {"home": 1.25, "away": 1.05, "total": 2.30},
            "mercados_poisson": {
                "over_1_5": 76.5,
                "over_2_5": 48.0,
                "under_2_5": 52.0,
                "btts_yes": 54.0,
                "home_win": 42.0,
                "draw": 30.0,
                "away_win": 28.0
            },
            "escanteios": {"disponivel": True, "esperado_mandante": 6.0, "esperado_visitante": 4.5, "esperado_total": 10.5},
            "finalizacoes": {"disponivel": True, "total_esperado": 27.0, "no_alvo_esperado": 9.5},
            "laterais": {"disponivel": True, "esperado_total": 38.0}
        },
        "recomendacoes": [
            {
                "mercado": "Gols",
                "selecao": "Mais de 1.5 Gols",
                "grau_confianca": 76.5,
                "odd_referencia": 1.40,
                "perfil_risco": "seguro",
                "justificativa": "Poisson projeta 76.5% para over 1.5 gols."
            }
        ]
    }
    try:
        resultado = await gemini_analyzer.analisar_partida_async(partida_teste)
        assert resultado["status"] == "success"
        assert "gemini_analise" in resultado
        analise_out = resultado["gemini_analise"]
        assert "partida" in analise_out
        assert "analise_tática_resumida" in analise_out
        assert len(analise_out["recomendacoes"]) > 0
        print(f"  [OK] Provedor ativo: {resultado.get('provedor')} | Confronto: {analise_out['partida']}")
        print(f"  [OK] Análise tática: \"{analise_out['analise_tática_resumida']}\"")
        print(f"  [OK] Recomendações emitidas: {len(analise_out['recomendacoes'])}")
    except Exception as e:
        print(f"  [FALHA] Erro no analisador: {e}")
        return False


    print("\n[CHECK 3/6] Testando Streaming SSE (Server-Sent Events)...")
    try:
        chunks = []
        async for chunk in gemini_analyzer.stream_analises_sse([partida_teste]):
            chunks.append(chunk)

        texto_stream = "".join(chunks)
        assert "event: init" in texto_stream
        assert "event: match_analysis" in texto_stream
        assert "event: done" in texto_stream
        print(f"  [OK] Stream SSE gerou {len(chunks)} eventos conformes com a especificação!")
    except Exception as e:
        print(f"  [FALHA] Erro no stream SSE: {e}")
        return False


    print("\n[CHECK 4/6] Auditando todos os Endpoints da API FastAPI...")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:

        res = await client.get("/api/status")
        assert res.status_code == 200
        st = res.json()
        assert "gemini_ai" in st
        print(f"  [OK] GET /api/status: online | Gemini AI mode: {st['gemini_ai']['mode']} | Modelo: {st['gemini_ai']['model']}")


        res = await client.get("/api/gemini/analise-partida/101010")
        assert res.status_code == 200
        gp = res.json()
        assert gp["status"] == "success"
        print(f"  [OK] GET /api/gemini/analise-partida/101010: Retornou análise com status={gp['status']}")


        res = await client.get("/api/gemini/stream-analises")
        assert res.status_code == 200
        assert "text/event-stream" in res.headers.get("content-type", "")
        print(f"  [OK] GET /api/gemini/stream-analises: Header Content-Type={res.headers.get('content-type')}")


        res = await client.get("/api/multipla-segura-dia")
        assert res.status_code == 200
        ms = res.json()
        print(f"  [OK] GET /api/multipla-segura-dia: Status={ms.get('status')} | Total Seleções={ms.get('total_selecoes')}")


    print("\n[CHECK 5/6] Auditando Sintaxe e Integridade do Frontend (index.html)...")
    with open("index.html", "r", encoding="utf-8") as f:
        html = f.read()


    assert "gemini-status-badge" in html, "Falta badge do Gemini no cabeçalho"
    assert "modal-gemini-section" in html, "Falta seção do Gemini no modal de inspeção"
    assert "iniciarStreamGeminiFlash" in html, "Falta função de streaming SSE no frontend"
    assert "gerarHtmlGeminiCard" in html, "Falta gerador do card Gemini"
    assert "atualizarCardComGemini" in html, "Falta função reativa de atualização do card"
    assert "/api/gemini/stream-analises" in html, "Falta URL do endpoint SSE no EventSource"


    s_start = html.rfind("<script>")
    s_end = html.rfind("</script>")
    js = html[s_start+8:s_end]
    assert js.count("{") == js.count("}"), "Chaves desbalanceadas no JavaScript"
    assert js.count("(") == js.count(")"), "Parênteses desbalanceados no JavaScript"
    assert js.count(chr(96)) % 2 == 0, "Template strings (backticks) desbalanceados"
    print("  [OK] Frontend index.html com sintaxe 100% balanceada e componentes integrados!")


    print("\n[CHECK 6/6] Auditoria de Segurança e Isolamento de Chaves de API...")
    assert "AIza" not in html, "Alerta: Possível chave de API do Google exposta no frontend!"
    assert "GEMINI_API_KEY" not in html, "Alerta: Variável de chave exposta no código cliente!"

    with open(".gitignore", "r", encoding="utf-8") as f:
        git_ignore = f.read()
    assert ".env" in git_ignore, "Alerta: .env não está no .gitignore!"
    print("  [OK] Segurança aprovada: nenhuma credencial exposta no cliente e .env devidamente ignorado no git.")

    print("\n================================================================================")
    print("   TODAS AS 6 ETAPAS DE REVISÃO E TESTES FORAM APROVADAS COM SUCESSO TOTAL!    ")
    print("================================================================================")
    return True

if __name__ == "__main__":
    asyncio.run(executar_revisao_completa())
