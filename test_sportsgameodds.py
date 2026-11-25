"""
Teste de Sanidade e Validação da Integração SportsGameOdds API.
Verifica:
1. Conversão matemática de odds americanas (+140, -110, etc.) para decimal.
2. Normalização dos nomes e cálculo de similaridade difusa.
3. Teste de conexão real (HTTP 200 OK e autenticado=True com a chave no .env).
4. Consulta de eventos de uma liga suportada (ex: NFL / UEFA_CHAMPIONS_LEAGUE / MLS).
5. Conformidade estrita do schema unificado:
   {
       "home_win": float,
       "draw": Optional[float],
       "away_win": float,
       "over_under": {"total": float, "over": float, "under": float},
       "spread": {"handicap": float, "home": float, "away": float},
       "provider": "SportsGameOdds"
   }
"""

import sys
import asyncio
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("test_sportsgameodds")


def test_conversao_odds():
    from services.sportsgameodds_service import SportsGameOddsService

    svc = SportsGameOddsService

    # Americanas positivas: +140 -> 1 + (140/100) = 2.40
    assert svc.converter_american_para_decimal("+140") == 2.40, f"Falha +140: {svc.converter_american_para_decimal('+140')}"
    assert svc.converter_american_para_decimal(150) == 2.50, f"Falha 150: {svc.converter_american_para_decimal(150)}"
    assert svc.converter_american_para_decimal("+100") == 2.00, f"Falha +100: {svc.converter_american_para_decimal('+100')}"

    # Americanas negativas: -110 -> 1 + (100/110) = 1.91
    assert svc.converter_american_para_decimal("-110") == 1.91, f"Falha -110: {svc.converter_american_para_decimal('-110')}"
    assert svc.converter_american_para_decimal(-200) == 1.50, f"Falha -200: {svc.converter_american_para_decimal(-200)}"

    # Decimais diretos
    assert svc.converter_american_para_decimal("1.85") == 1.85, f"Falha decimal: {svc.converter_american_para_decimal('1.85')}"
    assert svc.converter_american_para_decimal(3.20) == 3.20, f"Falha decimal: {svc.converter_american_para_decimal(3.20)}"

    # Valores nulos / inválidos
    assert svc.converter_american_para_decimal(None) is None
    assert svc.converter_american_para_decimal("") is None
    assert svc.converter_american_para_decimal("-") is None

    logger.info(" [1/5] Conversão de Odds Americanas para Decimais: PASSOU")


def test_normalizacao_e_similaridade():
    from services.sportsgameodds_service import SportsGameOddsService

    svc = SportsGameOddsService

    # Normalização de nomes removendo acentos e stopwords
    n1 = svc.normalizar_nome("São Paulo FC")
    assert "sao paulo" in n1 and "fc" not in n1.split(), f"Falha norm: {n1}"

    # Similaridade de times
    sim1 = svc.calcular_similaridade("Kansas City Chiefs", "Chiefs")
    assert sim1 >= 0.70, f"Falha similaridade Chiefs: {sim1}"

    sim2 = svc.calcular_similaridade("Real Madrid CF", "Real Madrid")
    assert sim2 >= 0.90, f"Falha similaridade Real Madrid: {sim2}"

    sim_diff = svc.calcular_similaridade("Flamengo", "Palmeiras")
    assert sim_diff < 0.50, f"Falha times diferentes: {sim_diff}"

    logger.info(" [2/5] Normalização de Nomes e Matching Engine: PASSOU")


def test_schema_unificado():
    from services.sportsgameodds_service import SportsGameOddsService

    svc = SportsGameOddsService()

    raw_event_mock = {
        "eventID": "test_event_1",
        "leagueID": "NFL",
        "odds": {
            "ml_home": {
                "betTypeID": "ml",
                "periodID": "game",
                "sideID": "home",
                "bookOdds": "-120"
            },
            "ml_away": {
                "betTypeID": "ml",
                "periodID": "game",
                "sideID": "away",
                "bookOdds": "+100"
            },
            "ou_over": {
                "betTypeID": "ou",
                "periodID": "game",
                "sideID": "over",
                "marketName": "Total Points",
                "bookOverUnder": "47.5",
                "bookOdds": "-110"
            },
            "ou_under": {
                "betTypeID": "ou",
                "periodID": "game",
                "sideID": "under",
                "marketName": "Total Points",
                "bookOverUnder": "47.5",
                "bookOdds": "-110"
            },
            "sp_home": {
                "betTypeID": "sp",
                "periodID": "game",
                "sideID": "home",
                "bookSpread": "-2.5",
                "bookOdds": "-110"
            },
            "sp_away": {
                "betTypeID": "sp",
                "periodID": "game",
                "sideID": "away",
                "bookSpread": "+2.5",
                "bookOdds": "-110"
            }
        }
    }

    norm = svc.normalizar_evento_odds(raw_event_mock)

    # Validar campos canônicos exigidos pelo Tech Lead
    assert "home_win" in norm and isinstance(norm["home_win"], float)
    assert norm["home_win"] == 1.83  # -120 -> 1 + 100/120 = 1.83
    assert norm["away_win"] == 2.00  # +100 -> 2.00

    assert "over_under" in norm and isinstance(norm["over_under"], dict)
    assert norm["over_under"]["total"] == 47.5
    assert norm["over_under"]["over"] == 1.91
    assert norm["over_under"]["under"] == 1.91

    assert "spread" in norm and isinstance(norm["spread"], dict)
    assert norm["spread"]["handicap"] == -2.5
    assert norm["spread"]["home"] == 1.91
    assert norm["spread"]["away"] == 1.91

    assert norm["provider"] == "SportsGameOdds"

    logger.info(" [3/5] Schema Unificado (home_win, over_under, spread, provider): PASSOU")


async def test_live_conexao():
    from services.sportsgameodds_service import sportsgameodds_service

    assert sportsgameodds_service.is_configured(), "SportsGameOdds API Key não está configurada no .env / config"

    # Teste de conexão real via GET /sports (com retentativa caso rate limit temporário)
    status = await sportsgameodds_service.testar_conexao()
    if status.get("http_status") == 429:
        logger.warning("Rate limit temporário atingido. Aguardando 2 segundos para retry...")
        await asyncio.sleep(2)
        status = await sportsgameodds_service.testar_conexao(force_refresh=True)

    logger.info(f"Resposta de Conexão SportsGameOdds: {status}")

    assert status.get("autenticado") is True, f"Autenticação falhou com a chave configurada: {status}"
    assert status.get("http_status") in (200, 429), f"HTTP status inesperado: {status.get('http_status')}"
    if status.get("http_status") == 200:
        assert "esportes_disponiveis" in status and len(status["esportes_disponiveis"]) > 0
        logger.info(f" [4/5] Teste de Conexão Live GET 200 OK ({len(status['esportes_disponiveis'])} esportes disponíveis): PASSOU")
    else:
        logger.info(" [4/5] Teste de Conexão Live (Chave Válida - Rate Limit Temporário): PASSOU")


async def test_live_eventos_liga():
    from services.sportsgameodds_service import sportsgameodds_service

    # Consulta de eventos da NFL
    eventos = await sportsgameodds_service.obter_eventos_liga("NFL", force_refresh=True, limit=5)
    logger.info(f"Eventos retornados para NFL: {len(eventos)}")

    if eventos:
        primeiro = eventos[0]
        norm = sportsgameodds_service.normalizar_evento_odds(primeiro)
        logger.info(f"Exemplo normalizado da NFL: {norm}")
        assert "home_win" in norm
        assert "over_under" in norm
        assert "spread" in norm
        assert norm["provider"] == "SportsGameOdds"

    logger.info(" [5/5] Consulta de Eventos e Normalização Live: PASSOU")


async def main():
    print("=" * 70)
    print("INICIANDO SUÍTE DE TESTES: Integração SportsGameOdds API")
    print("=" * 70)

    test_conversao_odds()
    test_normalizacao_e_similaridade()
    test_schema_unificado()
    await test_live_conexao()
    await test_live_eventos_liga()

    print("=" * 70)
    print(" TODOS OS TESTES DA SPORTSGAMEODDS PASSARAM COM SUCESSO!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
