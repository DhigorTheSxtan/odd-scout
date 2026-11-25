"""
Testes Unitários: Validação Rígida das 38 Competições Permitidas
"""

import unittest
from football_service import is_allowed_league

class TestAllowedLeagues(unittest.TestCase):

    def test_casos_positivos_todas_as_38_competicoes(self):
        # 1. Brasileirão Série A
        self.assertTrue(is_allowed_league("Brasileirão Série A", "Brazil"))
        self.assertTrue(is_allowed_league("Serie A", "Brazil"))
        self.assertTrue(is_allowed_league("BRAZIL: Serie A"))

        # 2. Copa do Brasil
        self.assertTrue(is_allowed_league("Copa do Brasil", "Brasil"))

        # 3. Brasileirão Série B
        self.assertTrue(is_allowed_league("Brasileirão Série B", "Brazil"))
        self.assertTrue(is_allowed_league("BRAZIL: Serie B"))

        # 4. Campeonato Paulista (Paulistão)
        self.assertTrue(is_allowed_league("Campeonato Paulista", "Brasil"))
        self.assertTrue(is_allowed_league("Paulistão", "Brasil"))

        # 5. Campeonato Carioca (Cariocão)
        self.assertTrue(is_allowed_league("Campeonato Carioca", "Brasil"))
        self.assertTrue(is_allowed_league("Cariocão"))

        # 6. Copa do Nordeste
        self.assertTrue(is_allowed_league("Copa do Nordeste", "Brasil"))

        # 7. Campeonato Mineiro
        self.assertTrue(is_allowed_league("Campeonato Mineiro", "Brasil"))

        # 8. Campeonato Gaúcho (Gauchão)
        self.assertTrue(is_allowed_league("Campeonato Gaúcho", "Brasil"))
        self.assertTrue(is_allowed_league("Gauchão"))

        # 9. Copa Verde
        self.assertTrue(is_allowed_league("Copa Verde", "Brasil"))

        # 10. Campeonato Paranaense
        self.assertTrue(is_allowed_league("Campeonato Paranaense", "Brasil"))

        # 11. Brasileirão Feminino
        self.assertTrue(is_allowed_league("Brasileirão Feminino", "Brasil"))
        self.assertTrue(is_allowed_league("Serie A1 Feminina", "Brasil"))

        # 12. Copa Libertadores da América
        self.assertTrue(is_allowed_league("Copa Libertadores", "South America"))
        self.assertTrue(is_allowed_league("SOUTH AMERICA: Copa Libertadores - Play Offs"))

        # 13. Copa Sul-Americana
        self.assertTrue(is_allowed_league("Copa Sudamericana", "South America"))
        self.assertTrue(is_allowed_league("SOUTH AMERICA: Copa Sudamericana - Play Offs"))

        # 14. UEFA Champions League
        self.assertTrue(is_allowed_league("UEFA Champions League", "Europe"))

        # 15. UEFA Europa League
        self.assertTrue(is_allowed_league("UEFA Europa League", "Europe"))

        # 16. UEFA Conference League
        self.assertTrue(is_allowed_league("UEFA Conference League", "Europe"))

        # 17. AFC Champions League
        self.assertTrue(is_allowed_league("AFC Champions League", "Asia"))

        # 18. Premier League (Inglaterra)
        self.assertTrue(is_allowed_league("Premier League", "England"))
        self.assertTrue(is_allowed_league("ENGLAND: Premier League"))

        # 19. Championship (2ª divisão inglesa)
        self.assertTrue(is_allowed_league("Championship", "England"))
        self.assertTrue(is_allowed_league("ENGLAND: Championship"))

        # 20. Copa da Inglaterra (FA Cup)
        self.assertTrue(is_allowed_league("FA Cup", "England"))
        self.assertTrue(is_allowed_league("ENGLAND: FA Cup - Qualification"))

        # 21. Copa da Liga Inglesa (Carabao Cup)
        self.assertTrue(is_allowed_league("Carabao Cup", "England"))
        self.assertTrue(is_allowed_league("EFL Cup", "England"))

        # 22. La Liga (Espanha)
        self.assertTrue(is_allowed_league("La Liga", "Spain"))
        self.assertTrue(is_allowed_league("SPAIN: LaLiga"))

        # 23. Copa do Rei (Copa del Rey)
        self.assertTrue(is_allowed_league("Copa del Rey", "Spain"))

        # 24. Serie A (Itália)
        self.assertTrue(is_allowed_league("Serie A", "Italy"))
        self.assertTrue(is_allowed_league("ITALY: Serie A"))

        # 25. Copa da Itália (Coppa Italia)
        self.assertTrue(is_allowed_league("Coppa Italia", "Italy"))

        # 26. Bundesliga (Alemanha)
        self.assertTrue(is_allowed_league("Bundesliga", "Germany"))
        self.assertTrue(is_allowed_league("GERMANY: Bundesliga"))

        # 27. Copa da Alemanha (DFB-Pokal)
        self.assertTrue(is_allowed_league("DFB-Pokal", "Germany"))

        # 28. Ligue 1 (França)
        self.assertTrue(is_allowed_league("Ligue 1", "France"))
        self.assertTrue(is_allowed_league("FRANCE: Ligue 1"))

        # 29. Copa da França (Coupe de France)
        self.assertTrue(is_allowed_league("Coupe de France", "France"))

        # 30. Liga Portugal (Primeira Liga)
        self.assertTrue(is_allowed_league("Liga Portugal", "Portugal"))
        self.assertTrue(is_allowed_league("Primeira Liga", "Portugal"))

        # 31. Taça de Portugal
        self.assertTrue(is_allowed_league("Taça de Portugal", "Portugal"))

        # 32. Eredivisie (Holanda)
        self.assertTrue(is_allowed_league("Eredivisie", "Netherlands"))
        self.assertTrue(is_allowed_league("NETHERLANDS: Eredivisie"))

        # 33. Süper Lig (Turquia)
        self.assertTrue(is_allowed_league("Süper Lig", "Turkey"))

        # 34. Scottish Premiership (Escócia)
        self.assertTrue(is_allowed_league("Premiership", "Scotland"))
        self.assertTrue(is_allowed_league("Scottish Premiership", "Scotland"))

        # 35. Jupiler Pro League (Bélgica)
        self.assertTrue(is_allowed_league("Jupiler Pro League", "Belgium"))

        # 36. Greek Super League (Grécia)
        self.assertTrue(is_allowed_league("Super League", "Greece"))
        self.assertTrue(is_allowed_league("Greek Super League", "Greece"))

        # 37. MLS (Estados Unidos)
        self.assertTrue(is_allowed_league("Major League Soccer", "USA"))
        self.assertTrue(is_allowed_league("MLS", "USA"))

        # 38. Liga Profesional (Argentina)
        self.assertTrue(is_allowed_league("Liga Profesional", "Argentina"))
        self.assertTrue(is_allowed_league("ARGENTINA: Liga Profesional - Clausura"))

        # 39. Liga MX (México)
        self.assertTrue(is_allowed_league("Liga MX", "Mexico"))

        # 40. Saudi Pro League (Arábia Saudita)
        self.assertTrue(is_allowed_league("Saudi Pro League", "Saudi Arabia"))


    def test_casos_negativos_bloqueio_rigido(self):
        # Países não permitidos usando mesmo nome
        self.assertFalse(is_allowed_league("Premier League", "Armenia"))
        self.assertFalse(is_allowed_league("ARMENIA: Premier League"))
        self.assertFalse(is_allowed_league("FAROE ISLANDS: Premier League"))
        self.assertFalse(is_allowed_league("Bundesliga", "Austria"))
        self.assertFalse(is_allowed_league("AUSTRIA: Bundesliga"))
        self.assertFalse(is_allowed_league("Ligue 1", "Algeria"))
        self.assertFalse(is_allowed_league("ALGERIA: Ligue 1"))
        self.assertFalse(is_allowed_league("Serie A", "Ecuador"))
        self.assertFalse(is_allowed_league("Championship", "Scotland"))
        self.assertFalse(is_allowed_league("Superliga", "Denmark"))
        self.assertFalse(is_allowed_league("Superliga", "Romania"))
        self.assertFalse(is_allowed_league("Veikkausliiga", "Finland"))
        self.assertFalse(is_allowed_league("Abissnet Superiore", "Albania"))

        # Categorias de Base / Juvenis (U20, U19, Sub-20, etc.)
        self.assertFalse(is_allowed_league("Paulista U20", "Brazil"))
        self.assertFalse(is_allowed_league("BRAZIL: Paulista U20 - Play Offs"))
        self.assertFalse(is_allowed_league("COSAFA Championship U20", "Africa"))
        self.assertFalse(is_allowed_league("Pernambucano U20", "Brazil"))
        self.assertFalse(is_allowed_league("Sul-Matogrossense U20", "Brazil"))
        self.assertFalse(is_allowed_league("ENGLAND: Premier League 2"))
        self.assertFalse(is_allowed_league("GERMANY: DFB Youth League - Preliminary"))
        self.assertFalse(is_allowed_league("ITALY: Primavera 1"))
        self.assertFalse(is_allowed_league("MEXICO: Liga MX U21 - Apertura"))

        # Divisões amadoras ou inferiores não autorizadas
        self.assertFalse(is_allowed_league("BRAZIL: Mineiro 3"))
        self.assertFalse(is_allowed_league("BRAZIL: Paraibano 2"))
        self.assertFalse(is_allowed_league("SPAIN: LaLiga2"))
        self.assertFalse(is_allowed_league("SPAIN: Tercera RFEF - Group 11"))
        self.assertFalse(is_allowed_league("GERMANY: 2. Bundesliga"))
        self.assertFalse(is_allowed_league("GERMANY: Oberliga Bayern"))
        self.assertFalse(is_allowed_league("FRANCE: Ligue 2"))
        self.assertFalse(is_allowed_league("ITALY: Serie B"))
        self.assertFalse(is_allowed_league("ARGENTINA: Primera B"))
        self.assertFalse(is_allowed_league("ARGENTINA: Primera C"))
        self.assertFalse(is_allowed_league("ARGENTINA: Torneo Promocional Amateur"))
        self.assertFalse(is_allowed_league("MEXICO: Liga de Expansion MX - Apertura"))

        # Femininos não autorizados (só Brasileirão Feminino é permitido)
        self.assertFalse(is_allowed_league("AUSTRIA: Bundesliga Women"))
        self.assertFalse(is_allowed_league("ENGLAND: WSL"))
        self.assertFalse(is_allowed_league("FRANCE: Premiere Ligue Women"))
        self.assertFalse(is_allowed_league("GERMANY: Bundesliga Women"))
        self.assertFalse(is_allowed_league("ARGENTINA: Primera A Women - Clausura"))


if __name__ == "__main__":
    unittest.main()
