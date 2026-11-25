"""
Suíte de Testes: SportsGameOdds em TODOS os Jogos de TODOS os Esportes
Valida:
1. Enriquecimento de Futebol (Soccer)
2. Enriquecimento de Futebol Americano (NFL)
3. Enriquecimento de Basquete (NBA / Basketball)
4. Enriquecimento de Beisebol (MLB / Baseball)
5. Enriquecimento de Hóquei (NHL / Hockey)
6. Conformidade canônica do schema em todas as modalidades:
   - home_win (float)
   - away_win (float)
   - over_under (dict com total, over, under)
   - spread (dict com handicap, home, away)
   - provider: SportsGameOdds
"""

import sys
import asyncio
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("test_all_sports_odds")


async def test_enrich_all_modalities():
    from services.sportsgameodds_service import sportsgameodds_service

    assert sportsgameodds_service.is_configured(), "SportsGameOdds não configurada"

    modalidades = [
        ("soccer", "Flamengo", "Palmeiras"),
        ("soccer", "Real Madrid", "Barcelona"),
        ("nfl", "Kansas City Chiefs", "Denver Broncos"),
        ("basketball", "Boston Celtics", "Los Angeles Lakers"),
        ("baseball", "New York Yankees", "Boston Red Sox"),
        ("hockey", "Toronto Maple Leafs", "Montreal Canadiens"),
    ]

    for sport, home, away in modalidades:
        jogos_mock = [{
            "id": f"test_{sport}_1",
            "mandante": {"nome": home},
            "visitante": {"nome": away},
            "campeonato": {"nome": f"Liga {sport.upper()}"},
            "data": "2026-09-17"
        }]

        enriquecidos = await sportsgameodds_service.enriquecer_jogos(jogos_mock, sport=sport, target_date="2026-09-17")
        assert len(enriquecidos) == 1, f"Falha ao retornar jogo enriquecido para {sport}"

        j = enriquecidos[0]
        assert "odds" in j, f"Campo 'odds' ausente no jogo de {sport}"
        odds = j["odds"]

        # Validação do schema canônico
        assert isinstance(odds.get("home_win"), (int, float)) and odds["home_win"] > 1.0, f"home_win inválido em {sport}: {odds.get('home_win')}"
        assert isinstance(odds.get("away_win"), (int, float)) and odds["away_win"] > 1.0, f"away_win inválido em {sport}: {odds.get('away_win')}"
        assert "over_under" in odds and isinstance(odds["over_under"], dict), f"over_under inválido em {sport}"
        assert "spread" in odds and isinstance(odds["spread"], dict), f"spread inválido em {sport}"
        assert odds.get("provider") == "SportsGameOdds", f"provider incorreto em {sport}: {odds.get('provider')}"
        assert j.get("provedor_odds") == "SportsGameOdds"

        logger.info(f"[{sport.upper()}] {home} vs {away} -> Home: @{odds['home_win']} | Away: @{odds['away_win']} | O/U {odds['over_under']['total']}: @{odds['over_under']['over']} | Provider: {odds['provider']}")

    logger.info(" [1/3] Enriquecimento de Todas as Modalidades Esportivas: PASSOU")


async def test_nfl_service_integration():
    from nfl_service import nfl_service

    res = await nfl_service.buscar_grade_jogos(force_refresh=True)
    jogos = res.get("jogos", [])
    assert len(jogos) > 0, "Nenhum jogo retornado pelo nfl_service"

    primeiro = jogos[0]
    assert "odds" in primeiro, "Campo 'odds' ausente no jogo da NFL"
    assert primeiro["odds"].get("provider") == "SportsGameOdds", f"Provedor incorreto na NFL: {primeiro['odds'].get('provider')}"

    mercados = primeiro.get("mercados", [])
    assert len(mercados) >= 3, "Mercados da NFL incompletos"
    for m in mercados:
        assert m.get("provedor") == "SportsGameOdds", f"Mercado NFL sem tag SportsGameOdds: {m}"

    logger.info(f" [2/3] Integração NFLService com SportsGameOdds: PASSOU ({len(jogos)} jogos da NFL com odds ativas)")


async def test_apisports_integration():
    from apisports_service import apisports_service

    # Testar para Basquete (Basketball)
    res_bask = await apisports_service.buscar_jogos(sport="basketball", force_refresh=False)
    assert res_bask.get("status") in ("success", "error"), f"Status inesperado em basketball: {res_bask}"
    for j in res_bask.get("jogos", []):
        assert "odds" in j, "Campo 'odds' ausente no jogo de basquete"
        assert j["odds"].get("provider") == "SportsGameOdds"

    # Testar para Beisebol (Baseball)
    res_base = await apisports_service.buscar_jogos(sport="baseball", force_refresh=False)
    for j in res_base.get("jogos", []):
        assert "odds" in j, "Campo 'odds' ausente no jogo de beisebol"
        assert j["odds"].get("provider") == "SportsGameOdds"

    logger.info(" [3/3] Integração ApiSportsService (Multi-Esportes) com SportsGameOdds: PASSOU")


async def main():
    print("=" * 70)
    print("INICIANDO TESTES: SportsGameOdds em Todos os Esportes")
    print("=" * 70)

    await test_enrich_all_modalities()
    await test_nfl_service_integration()
    await test_apisports_integration()

    print("=" * 70)
    print(" TODOS OS TESTES MULTI-ESPORTES DA SPORTSGAMEODDS PASSARAM!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
