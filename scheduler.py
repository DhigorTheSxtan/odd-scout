import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncGenerator, Dict, List, Optional, Set
import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

try:
    from zoneinfo import ZoneInfo
    TIMEZONE_BR = ZoneInfo("America/Sao_Paulo")
except Exception:
    TIMEZONE_BR = timezone(timedelta(hours=-3))

from pathlib import Path
from cache import app_cache
from daily_pipeline import daily_pipeline
from config import DATA_REFERENCIA_HOJE
from services.gemini_analyzer import CACHE_FILE, is_cache_valid_for_today

logger = logging.getLogger("scheduler")


class SSEBroadcastHub:


    def __init__(self):
        self._clients: Set[asyncio.Queue] = set()
        self._lock = asyncio.Lock()

    async def subscribe(self) -> asyncio.Queue:

        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        async with self._lock:
            self._clients.add(q)
        logger.info(f"[SSE Hub] Novo cliente conectado. Total ativos: {len(self._clients)}")
        return q

    async def unsubscribe(self, q: asyncio.Queue) -> None:

        async with self._lock:
            self._clients.discard(q)
        logger.info(f"[SSE Hub] Cliente desconectado. Total ativos: {len(self._clients)}")

    async def broadcast(self, event: str, data: Dict[str, Any]) -> int:

        msg = f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
        enviados = 0
        async with self._lock:
            clientes_copia = list(self._clients)

        for q in clientes_copia:
            try:

                if q.full():
                    try:
                        q.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                await q.put(msg)
                enviados += 1
            except Exception as exc:
                logger.warning(f"[SSE Hub] Falha ao enviar para cliente: {exc}")
                async with self._lock:
                    self._clients.discard(q)

        return enviados

    async def stream_client(self, q: asyncio.Queue, request: Optional[Any] = None) -> AsyncGenerator[str, None]:
        # Handshake de conexão
        init_payload = {
            "status": "connected",
            "timestamp": datetime.now(TIMEZONE_BR).isoformat(),
            "fuso": "America/Sao_Paulo"
        }
        yield f"event: connected\ndata: {json.dumps(init_payload)}\n\n"

        # Apenas lê o cache salvo em disco e faz streaming para o front
        if CACHE_FILE.exists():
            try:
                data = CACHE_FILE.read_text(encoding="utf-8")
                yield f"data: {data}\n\n"
            except Exception as exc:
                logger.warning(f"[SSE Hub] Erro ao ler cache para streaming: {exc}")

        # Mantém conexão viva com heartbeat sem processar IA
        try:
            while True:
                if request is not None and hasattr(request, "is_disconnected") and await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=15.0)
                    yield msg
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            await self.unsubscribe(q)

    @property
    def total_clientes_conectados(self) -> int:
        return len(self._clients)


sse_broadcast_hub = SSEBroadcastHub()


class JobSchedulerService:


    MAX_RETRIES = 3
    BACKOFF_DELAYS = [30, 60, 120]

    def __init__(self):
        self.timezone_sp = pytz.timezone("America/Sao_Paulo")
        self.scheduler = AsyncIOScheduler(timezone=self.timezone_sp)
        self.hub = sse_broadcast_hub
        self._is_running = False
        self._executando_agora = False
        self._executando_atualizacao_jogos = False
        self.ultimo_resultado: Optional[Dict[str, Any]] = None
        self.ultima_execucao_timestamp: Optional[str] = None
        self.ultima_atualizacao_jogos: Optional[Dict[str, Any]] = None
        self.total_execucoes_sucesso: int = 0
        self.total_execucoes_falha: int = 0
        self.total_atualizacoes_horarias_sucesso: int = 0

    async def executar_rotina_diaria_00h(self, data_alvo: Optional[str] = None, origem: str = "CRON_00H") -> Dict[str, Any]:

        if self._executando_agora:
            logger.warning("[scheduler] Rotina diária já se encontra em execução simultânea. Ignorando chamada duplicada.")
            return {"status": "busy", "mensagem": "Rotina diária já em execução."}

        self._executando_agora = True
        alvo = data_alvo or DATA_REFERENCIA_HOJE
        logger.info(f"[scheduler] Iniciando execução da rotina diária para {alvo} (Origem: {origem})...")

        for tentativa in range(1, self.MAX_RETRIES + 1):
            try:
                resultado = await daily_pipeline.executar_pipeline_completo(
                    data_alvo=alvo,
                    broadcaster_fn=self.hub.broadcast
                )

                self.ultimo_resultado = resultado
                self.ultima_execucao_timestamp = datetime.now(TIMEZONE_BR).isoformat()
                self.total_execucoes_sucesso += 1
                self._executando_agora = False
                logger.info(f"[scheduler] Rotina diária de {alvo} executada COM SUCESSO na tentativa {tentativa}/{self.MAX_RETRIES}!")
                return resultado

            except Exception as exc:
                logger.error(f"[scheduler] ERRO na tentativa {tentativa}/{self.MAX_RETRIES} da rotina diária: {exc}")
                if tentativa < self.MAX_RETRIES:
                    delay = self.BACKOFF_DELAYS[tentativa - 1]
                    logger.info(f"[scheduler] Aplicando Exponential Backoff: aguardando {delay}s antes da tentativa {tentativa + 1}...")
                    await asyncio.sleep(delay)
                else:
                    self.total_execucoes_falha += 1
                    self.ultimo_resultado = {"status": "error", "detalhes": str(exc), "tentativas": tentativa}
                    self.ultima_execucao_timestamp = datetime.now(TIMEZONE_BR).isoformat()
                    self._executando_agora = False
                    logger.critical(f"[scheduler] FALHA CRÍTICA: Todas as {self.MAX_RETRIES} tentativas da rotina diária falharam.")
                    return {"status": "error", "erro": str(exc), "data": alvo}

        self._executando_agora = False
        return {"status": "error", "mensagem": "Fluxo inesperado"}

    async def atualizar_todos_jogos_dia(
        self,
        target_date: Optional[str] = None,
        force_refresh: bool = True,
        origem: str = "ROTINA_HORARIA"
    ) -> Dict[str, Any]:
        """
        Rotina de automação periódica (executada a cada 1 hora):
        Sincroniza e renova a grade de jogos do dia de forma unificada e resiliente:
        - Futebol (Orquestrador Oficial: OddsPapi + API-Sports)
        - Futebol Americano / NFL (american_football_service)
        - eSports Pro (pandascore_service)
        - 12 modalidades da API-Sports (apisports_service)
        - Motor Preditivo Top 5 Bets & Múltiplas do Dia
        - Notificação SSE em tempo real para os clientes conectados
        """
        if self._executando_atualizacao_jogos:
            logger.warning("[scheduler] Atualização de jogos já em andamento. Ignorando chamada concorrente.")
            return {"status": "busy", "mensagem": "Atualização horária já em execução."}

        self._executando_atualizacao_jogos = True
        alvo = target_date or DATA_REFERENCIA_HOJE
        logger.info(f"[scheduler] Iniciando sincronização de TODOS os jogos para {alvo} (Origem: {origem})...")
        t_inicio = datetime.now()

        try:
            # 1. Agente Central Híbrido com Trava Anti-Alucinação para esportes suportados
            from routers.sports import obter_jogos_por_modalidade
            esportes_suportados = ["futebol", "basquete", "nfl", "nba", "mma", "esports"]
            total_geral_jogos = 0
            for esp in esportes_suportados:
                try:
                    res_esp_dict = await obter_jogos_por_modalidade(sport=esp, date_param=alvo, force_refresh=force_refresh)
                    jogos_esp = res_esp_dict.get("data") or res_esp_dict.get("jogos") or []
                    total_geral_jogos += len(jogos_esp)
                except Exception as e_esp:
                    logger.warning(f"[scheduler] Erro ao sincronizar partidas ({esp}): {e_esp}")

            # 2. Motor Preditivo: Top 5 Bets do Dia
            try:
                from app import obter_top5_bets_dia
                res_top5 = await obter_top5_bets_dia(data=alvo, force_refresh=force_refresh)
                total_top5 = res_top5.get("total_selecoes", 0)
            except Exception as e_top5:
                logger.warning(f"[scheduler] Erro ao atualizar Top 5 Bets: {e_top5}")
                res_top5 = {"status": "error", "erro": str(e_top5)}
                total_top5 = 0

            # 3. Bet do Dia Oficial
            try:
                from services.bet_of_the_day_service import bet_of_the_day_service
                await bet_of_the_day_service.get_bet_of_the_day(target_date=alvo, force_refresh=force_refresh)
            except Exception as e_botd:
                logger.warning(f"[scheduler] Erro ao atualizar Bet do Dia: {e_botd}")

            duracao_segundos = round((datetime.now() - t_inicio).total_seconds(), 2)

            resultado_sincronizacao = {
                "status": "success",
                "data": alvo,
                "origem": origem,
                "duracao_segundos": duracao_segundos,
                "timestamp": datetime.now(TIMEZONE_BR).isoformat(),
                "agente_ia": "gemini-2.0-flash",
                "totais": {
                    "total_geral_jogos": total_geral_jogos,
                    "partidas_analisadas": total_geral_jogos,
                    "top5_bets": total_top5
                },
                "top5_bets": res_top5
            }

            self.ultima_atualizacao_jogos = resultado_sincronizacao
            self.total_atualizacoes_horarias_sucesso += 1

            # 6. Notificação em tempo real para todos os clientes conectados via SSE
            await self.hub.broadcast("ATUALIZACAO_TODOS_JOGOS_HORARIA", {
                "evento": "ATUALIZACAO_TODOS_JOGOS_HORARIA",
                "mensagem": f"Grade de jogos atualizada com sucesso! ({total_geral_jogos} eventos disponíveis)",
                "data": alvo,
                "totais": resultado_sincronizacao["totais"],
                "timestamp": resultado_sincronizacao["timestamp"]
            })

            logger.info(f"[scheduler] Sincronização de TODOS os jogos concluída em {duracao_segundos}s! Total de eventos: {total_geral_jogos}")
            return resultado_sincronizacao

        except Exception as exc:
            logger.error(f"[scheduler] Erro crítico na atualização de jogos: {exc}", exc_info=True)
            return {"status": "error", "erro": str(exc), "data": alvo}
        finally:
            self._executando_atualizacao_jogos = False

    async def checar_e_executar_bootstrap(self) -> None:

        hoje = DATA_REFERENCIA_HOJE
        if is_cache_valid_for_today():
            logger.info(f"[scheduler] [BOOTSTRAP] Cache diário para {hoje} já validado em disco. Standby até 00:00 (0 tokens consumidos).")
            return

        cache_key = f"unified_orchestrated_{hoje}_all"
        dados_cache = await app_cache.get(cache_key)

        if not dados_cache or not dados_cache.get("partidas"):
            logger.info(f"[scheduler] [BOOTSTRAP] Cache do dia {hoje} está vazio. Disparando rotina inicial de aquecimento...")

            asyncio.create_task(self.executar_rotina_diaria_00h(data_alvo=hoje, origem="BOOTSTRAP_COLD_START"))
        else:
            total_jogos = len(dados_cache.get("partidas", []))
            logger.info(f"[scheduler] [BOOTSTRAP] Grade de {hoje} já aquecida no cache com {total_jogos} partidas. Standby até 00:00.")

    async def iniciar(self, executar_bootstrap: bool = True) -> None:

        if self._is_running:
            return

        trigger = CronTrigger(hour=0, minute=0, timezone=self.timezone_sp)
        self.scheduler.add_job(
            self.executar_rotina_diaria_00h,
            trigger=trigger,
            id="rotina_diaria_00h_sp",
            name="Rotina Noturna de Ingestão e Análise Gemini Flash",
            replace_existing=True,
            misfire_grace_time=3600
        )

        trigger_horario = IntervalTrigger(hours=1, timezone=self.timezone_sp)
        self.scheduler.add_job(
            self.atualizar_todos_jogos_dia,
            trigger=trigger_horario,
            id="rotina_horaria_atualizar_jogos",
            name="Atualização Automática de Todos os Jogos (1 em 1 hora)",
            replace_existing=True,
            misfire_grace_time=600
        )

        self.scheduler.start()
        self._is_running = True
        logger.info("[scheduler] APScheduler iniciado com sucesso! Agendamentos: 00:00 (Diário) e 1 em 1 hora (Recorrente).")

        if executar_bootstrap:
            await self.checar_e_executar_bootstrap()

    async def parar(self) -> None:

        if self._is_running:
            self.scheduler.shutdown(wait=False)
            self._is_running = False
            logger.info("[scheduler] APScheduler encerrado com sucesso.")

    def obter_status(self) -> Dict[str, Any]:

        job_00h = self.scheduler.get_job("rotina_diaria_00h_sp")
        proximo_00h = job_00h.next_run_time.isoformat() if job_00h and job_00h.next_run_time else None

        job_horario = self.scheduler.get_job("rotina_horaria_atualizar_jogos")
        proximo_horario = job_horario.next_run_time.isoformat() if job_horario and job_horario.next_run_time else None

        return {
            "status": "ativo" if self._is_running else "parado",
            "hora_agendada": "00:00",
            "proxima_execucao": proximo_00h,
            "proximo_disparo_brasilia": proximo_00h,
            "total_execucoes": self.total_execucoes_sucesso,
            "executando_agora_00h": self._executando_agora,
            "executando_agora_horario": self._executando_atualizacao_jogos,
            "fuso_horario": "America/Sao_Paulo",
            "rotinas": {
                "rotina_diaria_00h": {
                    "id": "rotina_diaria_00h_sp",
                    "frequencia": "Diariamente às 00:00 (America/Sao_Paulo)",
                    "proximo_disparo": proximo_00h,
                    "total_sucessos": self.total_execucoes_sucesso,
                    "total_falhas": self.total_execucoes_falha,
                    "ultima_execucao": self.ultima_execucao_timestamp,
                    "ultimo_resumo": self.ultimo_resultado
                },
                "rotina_horaria_1h": {
                    "id": "rotina_horaria_atualizar_jogos",
                    "frequencia": "A cada 1 hora (Intervalo: 3600s)",
                    "proximo_disparo": proximo_horario,
                    "total_sucessos": self.total_atualizacoes_horarias_sucesso,
                    "ultima_atualizacao": self.ultima_atualizacao_jogos
                }
            },
            "clientes_sse_conectados": self.hub.total_clientes_conectados
        }


job_scheduler = JobSchedulerService()

async def iniciar_agendador():
    await job_scheduler.iniciar()

async def parar_agendador():
    await job_scheduler.parar()
