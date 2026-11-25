"""
Suite de Testes Unitários e de Integração para a Migração do Agente Gemini 2.0 Flash.
Valida:
1. Exclusividade do Gemini 2.0 Flash no pool MODEL_TRACKERS.
2. Controle estrito de taxa RPM (max_rpm=15) e cooldown em StrictModelTracker.
3. Função _call_interactions_api com ativação da ferramenta googleSearch e regras de transformação.
4. Endpoints FastAPI (/api/status, /api/jogos-hoje, /api/gemini/agent-predictions).
5. Ausência de dependências das APIs legadas (sportsgameodds, oddspedia, owlsinsight).
"""

import asyncio
import sys
import unittest
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient, ASGITransport, Response

if sys.platform == "win32":
    try:
        if sys.stdout.encoding != 'utf-8':
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        if sys.stderr.encoding != 'utf-8':
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

from services.ai_analytics_service import (
    StrictModelTracker,
    MODEL_TRACKERS,
    _call_interactions_api,
    _extrair_json_da_resposta,
    obter_jogos_e_palpites_gemini,
    calculate_batch_probabilities
)
from main import app


async def run_all_checks():
    print("\n" + "=" * 70)
    print("AUDITORIA E VALIDAÇÃO: AGENTE GEMINI 2.0 FLASH & REMOÇÃO DE APIS EXTERNAS")
    print("=" * 70)

    # -------------------------------------------------------------------------
    # TESTE 1: MODEL_TRACKERS e StrictModelTracker
    # -------------------------------------------------------------------------
    print("\n[CHECK 1/5] Verificando Exclusividade do Gemini 2.0 Flash no Pool...")
    assert len(MODEL_TRACKERS) == 1, f"Esperado 1 modelo no pool, encontrado {len(MODEL_TRACKERS)}"
    tracker = MODEL_TRACKERS[0]
    assert tracker.model_name == "gemini-2.0-flash", f"Modelo incorreto: {tracker.model_name}"
    assert tracker.max_rpm == 15, f"max_rpm incorreto: {tracker.max_rpm}"
    print(f"  [OK] Pool fixado exclusivamente em: {tracker.model_name} (max_rpm={tracker.max_rpm})")

    # Testando controle de slots e cooldown
    tracker_test = StrictModelTracker("gemini-2.0-flash", max_rpm=2)
    s1 = await tracker_test.acquire_slot()
    s2 = await tracker_test.acquire_slot()
    assert s1 is True and s2 is True, "Falha ao adquirir slots válidos"
    tracker_test.set_cooldown(60.0)
    assert tracker_test.is_in_cooldown() is True
    s3 = await tracker_test.acquire_slot()
    assert s3 is False, "Slot não deveria ser concedido durante cooldown"
    print("  [OK] StrictModelTracker: Janela deslizante, cooldown e bloqueio validados.")

    # -------------------------------------------------------------------------
    # TESTE 2: Parser JSON da IA e Robustez de Extração
    # -------------------------------------------------------------------------
    print("\n[CHECK 2/5] Testando Parser de Extração JSON com Regras de Transformação...")
    mock_markdown = """Aqui está a análise:
    ```json
    [
      {"match_id": "Flamengo_Fluminense", "best_market": "Over 1.5 Gols", "market_prob": 82, "reasoning": "Clássico com alto índice de finalizações."}
    ]
    ```
    """
    extraidos = _extrair_json_da_resposta(mock_markdown)
    assert len(extraidos) == 1
    assert extraidos[0]["match_id"] == "Flamengo_Fluminense"
    assert extraidos[0]["market_prob"] == 82
    print(f"  [OK] Extração de JSON via Markdown: {extraidos[0]['match_id']} -> {extraidos[0]['best_market']}")

    # -------------------------------------------------------------------------
    # TESTE 3: _call_interactions_api com googleSearch Grounding & 429
    # -------------------------------------------------------------------------
    print("\n[CHECK 3/5] Testando _call_interactions_api com Grounding e Tratamento 429...")

    # Mock de resposta HTTP simulando o retorno da API Gemini com Grounding
    mock_gemini_response = {
        "candidates": [{
            "content": {
                "parts": [{
                    "text": '[{"match_id": "Arsenal_Chelsea", "best_market": "Over 2.5 Golos", "market_prob": 85, "reasoning": "Histórico de 5 partidas com média superior a 2.5 gols."}]'
                }]
            }
        }]
    }

    MODEL_TRACKERS[0]._cooldown_until = 0.0
    with patch("services.ai_analytics_service.GEMINI_API_KEY", "mock_gemini_key_123"), \
         patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = Response(200, json=mock_gemini_response)

        res = await _call_interactions_api("gemini-2.0-flash", {"data": "2026-09-22"})
        assert len(res) >= 1
        assert res[0]["match_id"] == "Arsenal_Chelsea"
        assert res[0]["grounding"] is True
        print(f"  [OK] _call_interactions_api retornou: {res[0]['match_id']} (Grounding={res[0]['grounding']})")

        # Inspecionar payload enviado
        called_args, called_kwargs = mock_post.call_args
        sent_payload = called_kwargs.get("json", {})
        assert "tools" in sent_payload, "Ferramenta 'tools' ausente no payload"
        assert sent_payload["tools"] == [{"googleSearch": {}}], f"Tool googleSearch incorreta: {sent_payload['tools']}"
        prompt_enviado = sent_payload["contents"][0]["parts"][0]["text"]
        assert "REGRAS DE TRANSFORMAÇÃO" in prompt_enviado
        assert "Role Assignment" in prompt_enviado
        assert "Chain-of-Thought" in prompt_enviado
        assert "Output Schema" in prompt_enviado
        print("  [OK] Payload inspecionado: 'tools': [{'googleSearch': {}}] e Regras de Transformação presentes.")

    # Testando reação ao HTTP 429
    MODEL_TRACKERS[0]._cooldown_until = 0.0
    with patch("services.ai_analytics_service.GEMINI_API_KEY", "mock_gemini_key_123"), \
         patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post_429:
        mock_post_429.return_value = Response(429, text="Resource Exhausted")
        res_429 = await _call_interactions_api("gemini-2.0-flash", {"data": "2026-09-22"})
        # Deve retornar fallback resiliente sem quebrar e ativar cooldown
        assert len(res_429) > 0
        assert MODEL_TRACKERS[0].is_in_cooldown() is True
        print(f"  [OK] Tratamento 429: Ativou cooldown={MODEL_TRACKERS[0].is_in_cooldown()} e retornou {len(res_429)} palpites resilientes.")
    MODEL_TRACKERS[0]._cooldown_until = 0.0

    # -------------------------------------------------------------------------
    # TESTE 4: Endpoints FastAPI (/api/status, /api/jogos-hoje, /api/gemini/agent-predictions)
    # -------------------------------------------------------------------------
    print("\n[CHECK 4/5] Auditando Endpoints FastAPI com o Agente Gemini Integrado...")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. /api/status
        res_status = await client.get("/api/status")
        assert res_status.status_code == 200
        st = res_status.json()
        assert "gemini_agent" in st, "Chave gemini_agent ausente em /api/status"
        assert st["gemini_agent"]["model"] == "gemini-2.0-flash"
        assert st["gemini_agent"]["grounding"] is True
        assert st["gemini_agent"]["tool"] == "googleSearch"
        # Garantir que APIs legadas não constam em /api/status
        assert "oddspedia" not in st, "Alerta: oddspedia ainda presente em /api/status"
        assert "owlsinsight" not in st, "Alerta: owlsinsight ainda presente em /api/status"
        assert "sportsgameodds" not in st, "Alerta: sportsgameodds ainda presente em /api/status"
        print(f"  [OK] GET /api/status: Gemini Agent {st['gemini_agent']['model']} (Grounding={st['gemini_agent']['tool']})")

        # 2. /api/jogos-hoje
        res_jogos = await client.get("/api/jogos-hoje")
        assert res_jogos.status_code == 200
        dj = res_jogos.json()
        assert dj["status"] == "success"
        assert "partidas" in dj and len(dj["partidas"]) > 0
        print(f"  [OK] GET /api/jogos-hoje: {dj['total_partidas']} partidas (Fonte: {dj.get('fonte_dados')})")

        # 3. /api/gemini/agent-predictions
        res_agent = await client.get("/api/gemini/agent-predictions")
        assert res_agent.status_code == 200
        da = res_agent.json()
        assert da["status"] == "success"
        assert da["provedor"] == "gemini-2.0-flash"
        assert len(da["data"]) > 0
        print(f"  [OK] GET /api/gemini/agent-predictions: {da['total']} palpites diretos do Agente Gemini.")

        # 4. Rotas legadas devem retornar 404 (removidas)
        for rota_legada in ("/api/oddspedia/status", "/api/sportsgameodds/status", "/api/owlsinsight/status"):
            res_legada = await client.get(rota_legada)
            assert res_legada.status_code == 404, f"Rota {rota_legada} deveria retornar 404, retornou {res_legada.status_code}"
        print("  [OK] Confirmação de 404 Not Found para rotas legadas removidas.")

    # -------------------------------------------------------------------------
    # TESTE 5: calculate_batch_probabilities e compatibilidade
    # -------------------------------------------------------------------------
    print("\n[CHECK 5/5] Testando calculate_batch_probabilities retrocompatível...")
    matches_mock = [
        {"id": "m1", "home": "Arsenal", "away": "Chelsea", "league": "Premier League"},
        {"id": "m2", "home": "Real Madrid", "away": "Barcelona", "league": "La Liga"}
    ]
    preds = await calculate_batch_probabilities(matches_mock)
    assert len(preds) == 2
    assert preds[0]["match_id"] == "m1"
    assert "best_market" in preds[0]
    assert "market_prob" in preds[0]
    print(f"  [OK] Batch Probabilities geradas com sucesso para {len(preds)} confrontos.")

    print("\n" + "=" * 70)
    print("TODAS AS 5 ETAPAS FORAM APROVADAS COM SUCESSO!")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    asyncio.run(run_all_checks())
