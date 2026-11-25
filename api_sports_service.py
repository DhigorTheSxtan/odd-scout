"""
Alias para importar api_sports_service na raiz do projeto.
"""
from services.api_sports_service import (
    resolver_data,
    get_relative_date_map,
    normalizar_fixture,
    format_fixtures_compact,
    fetch_apisports_by_sport,
    get_fixtures,
    fetch_fixtures_by_relative_dates,
    SPORTS_API_CONFIG,
)

__all__ = [
    "resolver_data",
    "get_relative_date_map",
    "normalizar_fixture",
    "format_fixtures_compact",
    "fetch_apisports_by_sport",
    "get_fixtures",
    "fetch_fixtures_by_relative_dates",
    "SPORTS_API_CONFIG",
]
