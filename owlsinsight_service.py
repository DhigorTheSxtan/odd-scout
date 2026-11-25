"""
Alias na raiz para exportar funções de owlsinsight_service.
"""
from services.owlsinsight_service import (
    fetch_soccer_fixtures,
    fetch_soccer_fixtures_by_date,
    normalizar_partida_owls,
    resolver_data_futebol
)

__all__ = [
    "fetch_soccer_fixtures",
    "fetch_soccer_fixtures_by_date",
    "normalizar_partida_owls",
    "resolver_data_futebol"
]
