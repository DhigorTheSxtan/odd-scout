import os
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# ==============================================================================
# CONFIGURAÇÃO CENTRAL: GOOGLE GEMINI 2.0 FLASH (AGENTE COM SEARCH GROUNDING)
# ==============================================================================
GOOGLE_API_KEY = (os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY", "")).strip()
GEMINI_API_KEY = (os.getenv("GEMINI_API_KEY") or GOOGLE_API_KEY).strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash").strip()
GEMINI_AUTO_ENABLED = os.getenv("GEMINI_AUTO_ENABLED", "True").lower() in ("true", "1", "yes")

# Servidor e Desempenho Local
PORT = int(os.getenv("PORT", "8000"))
HOST = os.getenv("HOST", "127.0.0.1")
DEBUG = os.getenv("DEBUG", "True").lower() in ("true", "1", "yes")
REQUEST_TIMEOUT_SECONDS = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "8.0"))
CACHE_TTL_FIXTURES_SECONDS = int(os.getenv("CACHE_TTL_FIXTURES_SECONDS", "600"))
CACHE_TTL_STATS_SECONDS = int(os.getenv("CACHE_TTL_STATS_SECONDS", "14400"))


# ==============================================================================
# DATAS DE REFERÊNCIA DINÂMICAS (AMERICA/SAO_PAULO)
# ==============================================================================
def _data_brasilia_offset(offset_dias: int = 0) -> str:
    """Retorna a data no fuso America/Sao_Paulo com offset em dias (formato YYYY-MM-DD)."""
    try:
        from zoneinfo import ZoneInfo
        tz_br = ZoneInfo("America/Sao_Paulo")
    except Exception:
        tz_br = timezone(timedelta(hours=-3))
    agora = datetime.now(tz_br)
    alvo = agora + timedelta(days=offset_dias)
    return alvo.strftime("%Y-%m-%d")


_DATA_REFERENCIA_OVERRIDE_HOJE = os.getenv("DATA_REFERENCIA_HOJE", "").strip()
_DATA_REFERENCIA_OVERRIDE_AMANHA = os.getenv("DATA_REFERENCIA_AMANHA", "").strip()
_DATA_REFERENCIA_OVERRIDE_ONTEM = os.getenv("DATA_REFERENCIA_ONTEM", "").strip()

DATA_REFERENCIA_HOJE = _DATA_REFERENCIA_OVERRIDE_HOJE or _data_brasilia_offset(0)
DATA_REFERENCIA_AMANHA = _DATA_REFERENCIA_OVERRIDE_AMANHA or _data_brasilia_offset(1)
DATA_REFERENCIA_ONTEM = _DATA_REFERENCIA_OVERRIDE_ONTEM or _data_brasilia_offset(-1)


# Ligas Autorizadas Canônicas
TARGET_LEAGUES = {
    39: "Premier League (Inglaterra)",
    140: "La Liga (Espanha)",
    135: "Serie A (Itália)",
    78: "Bundesliga (Alemanha)",
    61: "Ligue 1 (França)",
    71: "Brasileirão Série A",
    72: "Brasileirão Série B",
    73: "Copa do Brasil",
    2: "UEFA Champions League",
    3: "UEFA Europa League",
    13: "Copa Libertadores",
    11: "Copa Sul-Americana",
    253: "Major League Soccer (MLS)",
    94: "Liga Portugal"
}


# ==============================================================================
# FUNÇÕES DE GERENCIAMENTO DA CHAVE GEMINI
# ==============================================================================
def is_gemini_configured() -> bool:
    """Verifica se a credencial do Google Gemini está configurada."""
    key = GEMINI_API_KEY or GOOGLE_API_KEY or os.getenv("GOOGLE_API_KEY", "") or os.getenv("GEMINI_API_KEY", "")
    return bool(key and key.strip() not in ("sua_chave_gemini_aqui", "YOUR_GEMINI_KEY", "YOUR_API_KEY", "sua_chave_aqui", ""))


def set_gemini_api_key(new_key: str) -> None:
    """Atualiza a chave do Gemini em memória, variáveis de ambiente e arquivo .env."""
    global GEMINI_API_KEY, GOOGLE_API_KEY
    clean_key = new_key.strip()
    GEMINI_API_KEY = clean_key
    GOOGLE_API_KEY = clean_key
    os.environ["GEMINI_API_KEY"] = clean_key
    os.environ["GOOGLE_API_KEY"] = clean_key
    _update_env_var("GEMINI_API_KEY", clean_key)
    _update_env_var("GOOGLE_API_KEY", clean_key)


def _update_env_var(var_name: str, val: str) -> None:
    """Grava com segurança uma variável no arquivo .env."""
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        env_file.write_text(f"{var_name}={val}\n", encoding="utf-8")
        return

    try:
        content = env_file.read_text(encoding="utf-8")
        lines = content.splitlines()
        found = False
        new_lines = []
        for line in lines:
            if line.startswith(f"{var_name}="):
                new_lines.append(f"{var_name}={val}")
                found = True
            else:
                new_lines.append(line)
        if not found:
            new_lines.append(f"{var_name}={val}")
        env_file.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    except Exception as e:
        print(f"[config] Erro ao gravar .env ({var_name}): {e}")


# ==============================================================================
# STUBS RETROCOMPATÍVEIS (APIs DE TERCEIROS DESATIVADAS / MIGRADO PARA GEMINI)
# ==============================================================================
OWLSINSIGHT_API_KEY = os.getenv("OWLSINSIGHT_API_KEY", os.getenv("OWLSINSIGHT_KEY", "")).strip()
OWLSINSIGHT_KEY = OWLSINSIGHT_API_KEY
OWLS_INSIGHT_KEY = OWLSINSIGHT_API_KEY
OWLSINSIGHT_BASE_URL = os.getenv("OWLSINSIGHT_BASE_URL", "https://api.owlsinsight.com/api/v1/soccer").strip()
CACHE_TTL_OWLSINSIGHT_SECONDS = int(os.getenv("CACHE_TTL_OWLSINSIGHT_SECONDS", 3600))

ODDSPEDIA_KEY = ""
ODDSPEDIA_BASE_URL = ""
CACHE_TTL_ODDSPEDIA_SECONDS = 0
CACHE_TTL_ODDS_SECONDS = 0
ODDSPAPI_KEY = ""
ODDSPAPI_BASE_URL = ""

SPORTSGAMEODDS_API_KEY = ""
SPORTSGAMEODDS_BASE_URL = ""
CACHE_TTL_SPORTSGAMEODDS_SECONDS = 0

OPENAI_API_KEY = ""
OPENAI_MODEL = "gemini-2.0-flash"

BIGBALLS_KEY = ""
BIGBALLSDATA_TOKEN = ""
BIGBALLSDATA_BASE_URL = ""
CACHE_TTL_NFL_PRE_SECONDS = 0
CACHE_TTL_NFL_LIVE_SECONDS = 0

AMERICAN_FOOTBALL_API_KEY = ""
AMERICAN_FOOTBALL_BASE_URL = ""

APISPORTS_KEY = os.getenv("APISPORTS_KEY", os.getenv("API_SPORTS_KEY", os.getenv("API_FOOTBALL_KEY", ""))).strip()
CACHE_TTL_APISPORTS_SECONDS = int(os.getenv("CACHE_TTL_APISPORTS_SECONDS", 3600))
APISPORTS_SPORTS_CONFIG: dict[str, dict] = {}

SHARPAPI_KEY = (os.getenv("SHARPAPI_KEY") or "sk_live_2wqgQogHtVyhHANQCmvqy5").strip()
SHARPAPI_BASE_URL = os.getenv("SHARPAPI_BASE_URL", "https://api.sharpapi.io/api/v1").strip()
CACHE_TTL_SHARPAPI_SECONDS = int(os.getenv("CACHE_TTL_SHARPAPI_SECONDS", "300"))

PANDASCORE_TOKEN = os.getenv("PANDASCORE_API_KEY", os.getenv("PANDASCORE_TOKEN", os.getenv("PANDASCORE_KEY", ""))).strip()
PANDASCORE_KEY = PANDASCORE_TOKEN
PANDASCORE_API_KEY = PANDASCORE_TOKEN
PANDASCORE_BASE_URL = os.getenv("PANDASCORE_BASE_URL", "https://api.pandascore.co").strip()
CACHE_TTL_PANDASCORE_SECONDS = int(os.getenv("CACHE_TTL_PANDASCORE_SECONDS", 180))

SPORTMONKS_API_TOKEN = ""
SPORTMONKS_KEY = ""
SPORTMONKS_BASE_URL = ""
CACHE_TTL_SPORTMONKS_SECONDS = 0

FOOTBALL_DATA_TOKEN = ""
FOOTBALL_DATA_ORG_KEY = ""
FOOTBALL_DATA_BASE_URL = ""
CACHE_TTL_FOOTBALL_DATA_SECONDS = 0
FOOTBALL_DATA_COMPETICOES: dict[str, int] = {}

API_FUTEBOL_KEY = ""
API_FUTEBOL_BASE_URL = ""
API_FUTEBOL_CAMPEONATOS_PADRAO: dict[int, str] = {}
API_FOOTBALL_KEY = ""
API_BASE_URL = ""


def is_oddspapi_configured() -> bool:
    return False

def set_oddspapi_key(k: str) -> None:
    pass

def is_oddspedia_configured() -> bool:
    return False

def set_oddspedia_key(k: str) -> None:
    pass

def is_bigballsdata_configured() -> bool:
    return False

def set_bigballsdata_token(t: str) -> None:
    pass

is_bigballs_configured = is_bigballsdata_configured
set_bigballs_key = set_bigballsdata_token

def is_american_football_configured() -> bool:
    return False

def set_american_football_key(k: str) -> None:
    pass

def is_sharpapi_configured() -> bool:
    global SHARPAPI_KEY
    key = SHARPAPI_KEY or os.getenv("SHARPAPI_KEY", "")
    return bool(key and key.strip().startswith("sk_live_"))

def set_sharpapi_key(k: str) -> None:
    global SHARPAPI_KEY
    clean_k = (k or "").strip()
    SHARPAPI_KEY = clean_k
    os.environ["SHARPAPI_KEY"] = clean_k
    _update_env_var("SHARPAPI_KEY", clean_k)

def is_pandascore_configured() -> bool:
    global PANDASCORE_TOKEN
    return bool(PANDASCORE_TOKEN)

def set_pandascore_token(t: str) -> None:
    global PANDASCORE_TOKEN, PANDASCORE_KEY
    PANDASCORE_TOKEN = (t or "").strip()
    PANDASCORE_KEY = PANDASCORE_TOKEN
    os.environ["PANDASCORE_TOKEN"] = PANDASCORE_TOKEN
    os.environ["PANDASCORE_KEY"] = PANDASCORE_KEY

def is_apisports_configured(sport: str = None) -> bool:
    global APISPORTS_KEY
    return bool(APISPORTS_KEY)

def get_apisports_config(sport: str) -> dict:
    global APISPORTS_KEY
    return {"key": APISPORTS_KEY, "url": "https://v3.football.api-sports.io", "name": "API-Sports"}

def set_apisports_key(sport: str, k: str) -> None:
    global APISPORTS_KEY
    APISPORTS_KEY = (k or "").strip()
    os.environ["APISPORTS_KEY"] = APISPORTS_KEY

def is_sportmonks_configured() -> bool:
    return False

def set_sportmonks_token(t: str) -> None:
    pass

def is_football_data_configured() -> bool:
    return False

def set_football_data_token(t: str) -> None:
    pass

def is_api_futebol_configured() -> bool:
    return False

def set_api_futebol_key(k: str) -> None:
    pass

def is_owlsinsight_configured() -> bool:
    global OWLSINSIGHT_API_KEY
    return bool(OWLSINSIGHT_API_KEY)

def set_owlsinsight_key(k: str) -> None:
    global OWLSINSIGHT_API_KEY, OWLSINSIGHT_KEY, OWLS_INSIGHT_KEY
    OWLSINSIGHT_API_KEY = (k or "").strip()
    OWLSINSIGHT_KEY = OWLSINSIGHT_API_KEY
    OWLS_INSIGHT_KEY = OWLSINSIGHT_API_KEY
    os.environ["OWLSINSIGHT_API_KEY"] = OWLSINSIGHT_API_KEY

def is_api_key_valid() -> bool:
    return False

def is_sportsgameodds_configured() -> bool:
    return False

def set_sportsgameodds_key(k: str) -> None:
    pass

def is_openai_configured() -> bool:
    return False

def set_openai_api_key(k: str) -> None:
    pass
