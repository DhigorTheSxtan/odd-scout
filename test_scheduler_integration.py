import asyncio
import json
import sys
from httpx import AsyncClient, ASGITransport
import pytz

if sys.platform == "win32":
    try:
        if sys.stdout.encoding != 'utf-8':
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        if sys.stderr.encoding != 'utf-8':
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

from main import app
from scheduler import job_scheduler, sse_broadcast_hub
from daily_pipeline import daily_pipeline

async def test_scheduler_suite():
    print("================================================================================")
    print("   TESTE DE INTEGRAÇÃO DO AGENDADOR AUTOMATIZADO (00:00 AMERICA/SAO_PAULO)     ")
    print("================================================================================")


    print("\n[TEST 1/5] Validando CronTrigger e Fuso Horário America/Sao_Paulo...")
    await job_scheduler.iniciar(executar_bootstrap=False)
    status = job_scheduler.obter_status()
    assert status["fuso_horario"] == "America/Sao_Paulo"
    assert status["hora_agendada"] == "00:00"
    assert status["status"] == "ativo"
    assert status["proximo_disparo_brasilia"] is not None
    print(f"  [OK] Scheduler ativo!")
    print(f"  [OK] Próximo disparo programado: {status['proximo_disparo_brasilia']}")


    print("\n[TEST 2/5] Testando SSEBroadcastHub (Assinatura e Broadcast)...")
    queue = await sse_broadcast_hub.subscribe()
    assert sse_broadcast_hub.total_clientes_conectados >= 1

    test_payload = {
        "evento": "TESTE_BROADCAST",
        "mensagem": "Verificando entrega em tempo real",
        "partidas": 10
    }
    enviados = await sse_broadcast_hub.broadcast("NOVA_RODADA_DIARIA", test_payload)
    assert enviados >= 1

    msg_recebida = await asyncio.wait_for(queue.get(), timeout=2.0)
    assert "event: NOVA_RODADA_DIARIA" in msg_recebida
    assert "TESTE_BROADCAST" in msg_recebida
    await sse_broadcast_hub.unsubscribe(queue)
    print(f"  [OK] Mensagem SSE entregue com sucesso: {msg_recebida.strip()[:60]}...")


    print("\n[TEST 3/5] Testando Exponential Backoff e Resiliência...")
    tentativas_executadas = 0

    class MockPipelineComFalha:
        async def executar_pipeline_completo(self, data_alvo, broadcaster_fn):
            nonlocal tentativas_executadas
            tentativas_executadas += 1
            if tentativas_executadas < 2:
                raise ConnectionError("Falha de rede simulada para testar backoff")
            return {"status": "success", "recuperado": True, "tentativas": tentativas_executadas}


    job_scheduler.BACKOFF_DELAYS = [0.05, 0.1, 0.15]
    job_scheduler._executando_agora = False
    import scheduler
    old_pipeline = scheduler.daily_pipeline
    scheduler.daily_pipeline = MockPipelineComFalha()

    res_retry = await job_scheduler.executar_rotina_diaria_00h(origem="TEST_RETRY")
    assert res_retry.get("status") == "success"
    assert tentativas_executadas == 2
    scheduler.daily_pipeline = old_pipeline
    job_scheduler.BACKOFF_DELAYS = [30, 60, 120]
    print(f"  [OK] Retry automático com recuo exponencial executou e recuperou na tentativa {tentativas_executadas}!")


    print("\n[TEST 4/5] Auditando Endpoints FastAPI (/api/scheduler e /api/stream/eventos)...")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:

        res_sched = await client.get("/api/scheduler/status")
        assert res_sched.status_code == 200
        st_data = res_sched.json()
        assert st_data["fuso_horario"] == "America/Sao_Paulo"
        print(f"  [OK] GET /api/scheduler/status: {st_data['status']} | Fuso: {st_data['fuso_horario']}")


        res_sys = await client.get("/api/status")
        assert res_sys.status_code == 200
        sys_data = res_sys.json()
        assert "scheduler" in sys_data
        print(f"  [OK] GET /api/status: Contém objeto scheduler operacional.")


    stream_q = await sse_broadcast_hub.subscribe()
    generator = sse_broadcast_hub.stream_client(stream_q)
    initial_event = await anext(generator)
    assert "event: connected" in initial_event
    assert "America/Sao_Paulo" in initial_event
    await generator.aclose()
    print(f"  [OK] SSE Stream Client Generator: Emite handshake inicial com sucesso: {initial_event.strip()[:60]}...")


    print("\n[TEST 5/5] Encerrando Scheduler...")
    await job_scheduler.parar()
    assert not job_scheduler._is_running
    print("  [OK] Scheduler encerrado com sucesso!")

    print("\n================================================================================")
    print("      TODOS OS TESTES DO JOB SCHEDULER FORAM APROVADOS COM SUCESSO!            ")
    print("================================================================================")
    return True

if __name__ == "__main__":
    asyncio.run(test_scheduler_suite())
