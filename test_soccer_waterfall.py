import asyncio
import unittest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from main import app
from soccer_fallback_service import (
    SoccerWaterfallService,
    QuotaExceededException,
    GeminiSoccerAdapter,
    PROVIDERS_CHAIN,
    soccer_fallback_service
)
from schemas import MatchSchema, TeamSchema, LeagueSchema, ScoreSchema

client = TestClient(app)


class TestSoccerWaterfall(unittest.TestCase):

    def test_normal_waterfall_matches(self):
        """Testa se o fluxo normal de partidas consome com sucesso o agente central Gemini."""
        soccer_fallback_service.providers = list(PROVIDERS_CHAIN)
        soccer_fallback_service.reset_exhausted()

        response = client.get("/api/matches?sport=soccer&data=2026-09-17")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)

    def test_sport_games_waterfall_dispatcher(self):
        """Testa o endpoint /api/sports/soccer/jogos utilizando a integração Gemini 2.0 Flash."""
        soccer_fallback_service.providers = list(PROVIDERS_CHAIN)
        soccer_fallback_service.reset_exhausted()

        with patch("routers.sports.fetch_soccer_fixtures_by_date", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = [
                {
                    "id": 123,
                    "fixture_id": 123,
                    "home_team": "Arsenal",
                    "away_team": "Chelsea",
                    "mandante": {"nome": "Arsenal"},
                    "visitante": {"nome": "Chelsea"},
                    "campeonato": {"nome": "Premier League"},
                    "date": "2026-09-17T16:00:00-03:00",
                    "status": "SCHEDULED",
                    "odds": {"1": 1.95, "X": 3.40, "2": 3.80}
                }
            ]
            response = client.get("/api/sports/soccer/jogos?data=2026-09-17")
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertTrue(data.get("sucesso"))
            self.assertEqual(data.get("esporte"), "soccer")
            self.assertIn("Gemini", data.get("provedor", ""))

    def test_cascade_failover_on_quota_exhausted(self):
        """
        Simula esgotamento de cota (HTTP 429) no provedor primário e valida se
        o mecanismo comuta automaticamente para o próximo fallback resiliente.
        """
        class MockExhaustedPrimary(GeminiSoccerAdapter):
            async def get_matches(self, *args, **kwargs):
                raise QuotaExceededException("mock_primary", "Simulated 429 Quota Exceeded", 429)

        class MockFallback(GeminiSoccerAdapter):
            name = "mock_fallback"
            async def get_matches(self, *args, **kwargs):
                return [
                    MatchSchema(
                        id=123,
                        data="2026-09-17",
                        data_hora="2026-09-17T16:00:00-03:00",
                        mandante=TeamSchema(id=1, nome="Arsenal"),
                        visitante=TeamSchema(id=2, nome="Chelsea"),
                        campeonato=LeagueSchema(id=39, nome="Premier League", pais="Inglaterra")
                    )
                ]

        test_chain = [
            ("mock_primary", MockExhaustedPrimary()),
            ("mock_fallback", MockFallback()),
        ]

        custom_service = SoccerWaterfallService(chain=test_chain)
        matches = asyncio.run(custom_service.fetch_soccer_matches(date="2026-09-17"))

        self.assertIn("mock_primary", custom_service.exhausted_providers)
        self.assertEqual(custom_service.last_used_provider, "mock_fallback")
        self.assertIsInstance(matches, list)
        self.assertEqual(len(matches), 1)


if __name__ == "__main__":
    unittest.main()
