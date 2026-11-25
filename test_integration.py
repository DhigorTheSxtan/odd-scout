import sys
import asyncio
import json
from unittest.mock import patch, AsyncMock
from datetime import datetime

if sys.platform == "win32":
    try:
        if sys.stdout.encoding != 'utf-8':
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        if sys.stderr.encoding != 'utf-8':
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

from football_orchestrator import football_orchestrator
from football_games_service import football_games_service, normalizar_status
from engine import PredictiveEngine


def test_status_normalization():
    print("\n[TEST 1] Validação de Normalização Canônica de Status (SCHEDULED | LIVE | FINISHED)...")
    casos = [
        ("IN_PLAY", "LIVE"),
        ("1H", "LIVE"),
        ("HT", "LIVE"),
        ("FT", "FINISHED"),
        ("FINISHED", "FINISHED"),
        ("SCHEDULED", "SCHEDULED"),
        ("NS", "SCHEDULED"),
        (None, "SCHEDULED")
    ]
    for status_raw, esperado in casos:
        res = normalizar_status(status_raw)
        assert res == esperado, f"Falha normalizar_status para '{status_raw}': esperado {esperado}, obteve {res}"
    print(" -> Normalização canônica de status validada com sucesso!")


def test_deduplicacao_fuzzy():
    print("\n[TEST 2] Validação de Deduplicação Inteligente (Fuzzy Matching)...")

    assert football_orchestrator.sao_mesmo_confronto(
        "Como 1907", "Parma Calcio 1913",
        "Como", "Parma"
    ), "Falha ao identificar Como vs Parma com sufixos"

    assert football_orchestrator.sao_mesmo_confronto(
        "Chelsea FC", "Arsenal FC",
        "Chelsea", "Arsenal"
    ), "Falha ao identificar Chelsea vs Arsenal"

    assert football_orchestrator.sao_mesmo_confronto(
        "Real Madrid CF", "FC Barcelona",
        "Real Madrid", "Barcelona"
    ), "Falha ao identificar El Clásico"

    assert not football_orchestrator.sao_mesmo_confronto(
        "Chelsea", "Arsenal",
        "Liverpool", "Everton"
    ), "Identificou erroneamente confrontos diferentes como iguais"

    print(" -> Algoritmo de desduplicação fuzzy validado com sucesso!")


async def test_orquestrador_execucao():
    print("\n[TEST 3] Testando Execução Assíncrona do Orquestrador de Dados...")
    hoje = datetime.now().strftime("%Y-%m-%d")
    res = await football_orchestrator.obter_jogos_unificados(hoje, force_refresh=True)

    assert res["status"] == "success"
    assert "data_consulta" in res
    assert "total_partidas" in res
    assert "partidas" in res
    assert "fonte_dados" in res
    print(f" -> Orquestrador executou com sucesso! Total de partidas: {res['total_partidas']}")
    print(f" -> Provedores reportados: {list(res['fonte_dados']['provedores'].keys())}")
    print(f" -> Origem predominante: {res['fonte_dados']['origem_predominante']}")

    if res["partidas"]:
        p0 = res["partidas"][0]
        assert "partida" in p0
        assert "mandante" in p0
        assert "visitante" in p0
        assert "campeonato" in p0
        assert "horario" in p0
        assert "metricas_chave" in p0
        assert "recomendacoes" in p0
        assert "odds" in p0
        print(f" -> Partida 1: {p0['mandante']['nome']} vs {p0['visitante']['nome']} (Provedor: {p0.get('provedor')})")


async def test_football_games_service():
    print("\n[TEST 4] Testando FootballGamesService (Schema canônico)...")
    hoje = datetime.now().strftime("%Y-%m-%d")
    games = await football_games_service.get_games(date=hoje)
    assert isinstance(games, list)
    print(f" -> FootballGamesService retornou {len(games)} partidas para {hoje}.")
    for g in games[:5]:
        assert "id" in g
        assert "league" in g
        assert "home_team" in g
        assert "away_team" in g
        assert "status" in g
        assert g["status"] in ("SCHEDULED", "LIVE", "FINISHED")
        assert "score" in g
        assert "start_time" in g
    print(" -> Schema canônico 100% validado!")


def run_all():
    print("=" * 70)
    print("   SUÍTE DE INTEGRAÇÃO OFICIAL: ORQUESTRADOR & SERVIÇOS")
    print("=" * 70)
    test_status_normalization()
    test_deduplicacao_fuzzy()
    asyncio.run(test_orquestrador_execucao())
    asyncio.run(test_football_games_service())
    print("\n" + "=" * 70)
    print("   TODOS OS TESTES DE INTEGRAÇÃO PASSARAM COM SUCESSO!")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    run_all()
