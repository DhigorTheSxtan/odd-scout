"""
Motor de Análise Preditiva em Lote via OpenAI (ChatGPT gemini-2.0-flash).

Drop-in replacement para o gemini_analyzer.py:
  - Mesma interface pública: analisar_partida_async(), analisar_lote_partidas_async(), stream_analises_sse()
  - Mesmos Pydantic schemas (AnalisePartidaGemini, RecomendacaoGemini, PerfilRiscoGemini)
  - Mesmo contrato de SSE (event: init / match_analysis / done)
  - Fallback estatístico idêntico via herança

Provedor HTTP: httpx.AsyncClient → https://api.openai.com/v1/chat/completions
Nenhuma dependência adicional necessária (httpx já está no projeto).
"""

import asyncio
import json
import logging
import time
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx

from config import OPENAI_API_KEY, OPENAI_MODEL, is_openai_configured
from gemini_analyzer import (
    AnalisePartidaGemini,
    GeminiSportsAnalyzer,
    SYSTEM_INSTRUCTION_GEMINI,
)

logger = logging.getLogger("openai_analyzer")

OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"


class OpenAISportsAnalyzer(GeminiSportsAnalyzer):
    """
    Motor analítico consumindo OpenAI Chat Completions (gemini-2.0-flash).

    Herda de GeminiSportsAnalyzer para reutilizar:
      - formatar_prompt_partida()
      - _gerar_fallback_analitico()
    Sobrescreve apenas os métodos de inferência.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
    ):
        # Inicializa atributos do pai sem tentar instanciar o genai Client
        self.api_key = api_key or OPENAI_API_KEY
        self.model_name = model_name or OPENAI_MODEL or "gemini-2.0-flash"
        self._client: Optional[httpx.AsyncClient] = None
        self._semaphore = asyncio.Semaphore(8)
        self.timeout_seconds = 12.0
        self._rate_limit_cooldown_until = 0.0

    # ------------------------------------------------------------------
    # HTTP Client lifecycle
    # ------------------------------------------------------------------
    def _get_http_client(self) -> Optional[httpx.AsyncClient]:
        """Retorna um httpx.AsyncClient reutilizável ou None se não configurado."""
        if not is_openai_configured() and not self.api_key:
            return None

        key_to_use = self.api_key or OPENAI_API_KEY
        if not key_to_use:
            return None

        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout_seconds + 5.0, connect=5.0),
                headers={
                    "Authorization": f"Bearer {key_to_use}",
                    "Content-Type": "application/json",
                },
            )
        return self._client

    def reload_client(self, new_key: str):
        """Troca a chave e recria o cliente HTTP."""
        self.api_key = new_key.strip()
        if self._client and not self._client.is_closed:
            # Schedule close but don't await here (sync method)
            try:
                asyncio.get_event_loop().create_task(self._client.aclose())
            except RuntimeError:
                pass
        self._client = None
        return self._get_http_client()

    # ------------------------------------------------------------------
    # Inferência principal via OpenAI Chat Completions
    # ------------------------------------------------------------------
    async def analisar_partida_async(self, partida_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analisa uma partida via OpenAI Chat Completions (gemini-2.0-flash)."""

        partida_id = partida_data.get("partida", {}).get("id")
        client = self._get_http_client()

        # Sem chave → fallback estatístico imediato
        if not client:
            analise_fallback = self._gerar_fallback_analitico(
                partida_data, motivo="Chave OpenAI Pendente"
            )
            return {
                "fixture_id": partida_id,
                "gemini_analise": analise_fallback.model_dump(),
                "provedor": "motor_estatistico_fallback",
                "latencia_ms": 0,
                "status": "success",
            }

        # Rate limit cooldown ativo → fallback
        if time.time() < self._rate_limit_cooldown_until:
            tempo_restante = int(self._rate_limit_cooldown_until - time.time())
            analise_fallback = self._gerar_fallback_analitico(
                partida_data,
                motivo=f"Cooldown de Taxa OpenAI (429 - {tempo_restante}s restantes)",
            )
            return {
                "fixture_id": partida_id,
                "gemini_analise": analise_fallback.model_dump(),
                "provedor": "motor_estatistico_fallback",
                "motivo_fallback": "cooldown_429",
                "latencia_ms": 0,
                "status": "success",
            }

        # Construir prompt
        prompt_conteudo = self.formatar_prompt_partida(partida_data)
        t_inicio = time.perf_counter()

        # Schema JSON esperado (instrução extra para forçar formato)
        schema_instruction = (
            "\n\nRESPONDA EXCLUSIVAMENTE COM UM ÚNICO OBJETO JSON válido no seguinte formato "
            "(sem markdown, sem explicações, sem blocos de código):\n"
            "{\n"
            '  "partida": "Mandante vs Visitante",\n'
            '  "analise_qualitativa": "string PT-BR",\n'
            '  "analise_tática_resumida": "string PT-BR máximo 2 linhas",\n'
            '  "taxa_assertividade_global": 75.0,\n'
            '  "recomendacoes": [\n'
            "    {\n"
            '      "mercado": "Mercado: Seleção",\n'
            '      "odd_referencia": 1.75,\n'
            '      "grau_confianca_percentual": 82,\n'
            '      "taxa_assertividade_percentual": 78.5,\n'
            '      "perfil_risco": "Segura",\n'
            '      "justificativa_quantitativa": "string PT-BR com métrica exata"\n'
            "    }\n"
            "  ]\n"
            "}\n"
        )

        payload = {
            "model": self.model_name,
            "messages": [
                {
                    "role": "system",
                    "content": SYSTEM_INSTRUCTION_GEMINI + schema_instruction,
                },
                {
                    "role": "user",
                    "content": prompt_conteudo,
                },
            ],
            "temperature": 0.2,
            "max_tokens": 2048,
            "response_format": {"type": "json_object"},
        }

        async with self._semaphore:
            try:
                response = await asyncio.wait_for(
                    client.post(OPENAI_CHAT_COMPLETIONS_URL, json=payload),
                    timeout=self.timeout_seconds,
                )
                t_fim = time.perf_counter()
                latencia_ms = int((t_fim - t_inicio) * 1000)

                if response.status_code == 429:
                    self._rate_limit_cooldown_until = time.time() + 60.0
                    logger.warning(
                        "[openai_analyzer] Rate limit (429) da OpenAI. Cooldown de 60s ativado."
                    )
                    analise_fallback = self._gerar_fallback_analitico(
                        partida_data, motivo="Rate Limit OpenAI (429)"
                    )
                    return {
                        "fixture_id": partida_id,
                        "gemini_analise": analise_fallback.model_dump(),
                        "provedor": "motor_estatistico_fallback",
                        "motivo_fallback": "openai_429",
                        "latencia_ms": latencia_ms,
                        "status": "success",
                    }

                if response.status_code != 200:
                    logger.warning(
                        f"[openai_analyzer] HTTP {response.status_code} da OpenAI "
                        f"para partida {partida_id}: {response.text[:300]}"
                    )
                    analise_fallback = self._gerar_fallback_analitico(
                        partida_data, motivo=f"HTTP {response.status_code} OpenAI"
                    )
                    return {
                        "fixture_id": partida_id,
                        "gemini_analise": analise_fallback.model_dump(),
                        "provedor": "motor_estatistico_fallback",
                        "motivo_fallback": f"http_{response.status_code}",
                        "latencia_ms": latencia_ms,
                        "status": "success",
                    }

                # Parse resposta da OpenAI
                resp_json = response.json()
                raw_content = (
                    resp_json.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "{}")
                )

                # Limpar possíveis blocos markdown residuais
                clean_content = raw_content.strip()
                if clean_content.startswith("```"):
                    # Remover blocos ```json ... ```
                    lines = clean_content.split("\n")
                    if lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines and lines[-1].strip() == "```":
                        lines = lines[:-1]
                    clean_content = "\n".join(lines).strip()

                data_dict = json.loads(clean_content)
                analise_validada = AnalisePartidaGemini.model_validate(data_dict)

                logger.info(
                    f"[openai_analyzer] Análise concluída com sucesso para "
                    f"{analise_validada.partida} em {latencia_ms}ms "
                    f"(modelo: {self.model_name})"
                )

                # Extrair tokens utilizados (para monitoramento)
                usage = resp_json.get("usage", {})

                return {
                    "fixture_id": partida_id,
                    "gemini_analise": analise_validada.model_dump(),
                    "provedor": "openai_gpt4o_mini",
                    "modelo": self.model_name,
                    "latencia_ms": latencia_ms,
                    "tokens_utilizados": {
                        "prompt": usage.get("prompt_tokens", 0),
                        "completion": usage.get("completion_tokens", 0),
                        "total": usage.get("total_tokens", 0),
                    },
                    "status": "success",
                }

            except asyncio.TimeoutError:
                logger.warning(
                    f"[openai_analyzer] Timeout de {self.timeout_seconds}s excedido "
                    f"para partida {partida_id}. Aplicando fallback."
                )
                analise_fallback = self._gerar_fallback_analitico(
                    partida_data, motivo="Timeout de Inferência OpenAI"
                )
                return {
                    "fixture_id": partida_id,
                    "gemini_analise": analise_fallback.model_dump(),
                    "provedor": "motor_estatistico_fallback",
                    "motivo_fallback": "timeout_excedido",
                    "latencia_ms": int((time.perf_counter() - t_inicio) * 1000),
                    "status": "success",
                }
            except json.JSONDecodeError as jde:
                logger.warning(
                    f"[openai_analyzer] JSON inválido da OpenAI para partida {partida_id}: {jde}"
                )
                analise_fallback = self._gerar_fallback_analitico(
                    partida_data, motivo="JSON Inválido OpenAI"
                )
                return {
                    "fixture_id": partida_id,
                    "gemini_analise": analise_fallback.model_dump(),
                    "provedor": "motor_estatistico_fallback",
                    "motivo_fallback": f"json_decode_error: {str(jde)[:100]}",
                    "latencia_ms": int((time.perf_counter() - t_inicio) * 1000),
                    "status": "success",
                }
            except Exception as exc:
                err_msg = str(exc)
                if "429" in err_msg or "rate" in err_msg.lower():
                    self._rate_limit_cooldown_until = time.time() + 60.0
                    logger.warning(
                        "[openai_analyzer] Rate limit detectado via exceção. Cooldown de 60s."
                    )
                else:
                    logger.warning(
                        f"[openai_analyzer] Erro inesperado para partida {partida_id}: {exc}. "
                        "Aplicando failover estatístico."
                    )
                analise_fallback = self._gerar_fallback_analitico(
                    partida_data, motivo="Failover Resiliente OpenAI"
                )
                return {
                    "fixture_id": partida_id,
                    "gemini_analise": analise_fallback.model_dump(),
                    "provedor": "motor_estatistico_fallback",
                    "motivo_fallback": str(exc),
                    "latencia_ms": int((time.perf_counter() - t_inicio) * 1000),
                    "status": "success",
                }

    # ------------------------------------------------------------------
    # Análise em lote (sobrescreve para usar o novo analisar_partida_async)
    # ------------------------------------------------------------------
    async def analisar_lote_partidas_async(
        self, partidas: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Analisa um lote de partidas em paralelo via OpenAI."""
        if not partidas:
            return []
        tasks = [self.analisar_partida_async(p) for p in partidas]
        return await asyncio.gather(*tasks)

    # ------------------------------------------------------------------
    # Stream SSE (sobrescreve para usar o novo analisar_partida_async)
    # ------------------------------------------------------------------
    async def stream_analises_sse(
        self, partidas: List[Dict[str, Any]]
    ) -> AsyncGenerator[str, None]:
        """Stream SSE de análises via OpenAI, mesma interface do Gemini."""
        total = len(partidas)
        yield (
            f"event: init\n"
            f"data: {json.dumps({'total_partidas': total, 'mensagem': 'Iniciando pipeline analítico com OpenAI gemini-2.0-flash'})}\n\n"
        )

        if not partidas:
            yield f"event: done\ndata: {json.dumps({'concluido': True, 'processados': 0})}\n\n"
            return

        tasks = [asyncio.create_task(self.analisar_partida_async(p)) for p in partidas]

        processados = 0
        for future in asyncio.as_completed(tasks):
            res = await future
            processados += 1
            payload = {
                "progresso": {
                    "atual": processados,
                    "total": total,
                    "percentual": round((processados / total) * 100, 1),
                },
                "resultado": res,
            }
            yield f"event: match_analysis\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

        yield f"event: done\ndata: {json.dumps({'concluido': True, 'total_processados': processados})}\n\n"


# Singleton global
openai_analyzer = OpenAISportsAnalyzer()
