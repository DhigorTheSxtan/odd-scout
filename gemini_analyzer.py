"""
Módulo Centralizado Gemini Analyzer com Travas Anti-Vazamento de Tokens e Cache Diário Unificado.
Re-exporta e sincroniza com services/gemini_analyzer.py.
"""

from services.gemini_analyzer import (
    CACHE_FILE,
    INVALID_NAMES,
    is_cache_valid_for_today,
    is_valid_match,
    PerfilRiscoGemini,
    RecomendacaoGemini,
    AnalisePartidaGemini,
    GeminiAnalyzer,
    GeminiSportsAnalyzer,
    gemini_analyzer,
)

__all__ = [
    "CACHE_FILE",
    "INVALID_NAMES",
    "is_cache_valid_for_today",
    "is_valid_match",
    "PerfilRiscoGemini",
    "RecomendacaoGemini",
    "AnalisePartidaGemini",
    "GeminiAnalyzer",
    "GeminiSportsAnalyzer",
    "gemini_analyzer",
]
