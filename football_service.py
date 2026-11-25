"""
Módulo de Regras e Restrição Estrita de Campeonatos de Futebol.
Apenas partidas pertencentes à relação exata de 38 competições aprovadas são ingeridas,
processadas, sugeridas e listadas em todo o sistema. Qualquer outro torneio é sumariamente descartado.
"""

import re
import unicodedata
from typing import Dict, List, Any, Optional

# Lista dos padrões canônicos das 38 competições aprovadas
ALLOWED_LEAGUE_PATTERNS = [
    # Brasil (Nacionais e Regionais)
    "brasileiro serie a", "brasileirao serie a", "serie a brasil", "brazil serie a",
    "copa do brasil",
    "brasileiro serie b", "brasileirao serie b", "serie b brasil", "brazil serie b",
    "paulista", "paulistao",
    "carioca", "cariocao",
    "copa do nordeste",
    "mineiro",
    "gaucho", "gauchao",
    "copa verde",
    "paranaense",
    "brasileiro feminino", "brasileirao feminino", "serie a1 feminina",

    # Competições Continentais & Internacionais
    "libertadores", "copa libertadores",
    "sul-americana", "sudamericana", "copa sudamericana",
    "champions league", "uefa champions",
    "europa league", "uefa europa",
    "conference league", "uefa conference",
    "afc champions",

    # Principais Ligas e Copas Europeias
    "premier league",
    "championship",
    "fa cup",
    "efl cup", "carabao cup",
    "la liga", "laliga", "primera division",
    "copa del rey", "copa do rei",
    "serie a", "serie a tim", # validar país Itália
    "coppa italia", "copa da italia",
    "bundesliga",
    "dfb-pokal", "dfb pokal",
    "ligue 1",
    "coupe de france", "copa da franca",
    "primeira liga", "liga portugal",
    "taca de portugal",
    "eredivisie",
    "super lig", "superlig",
    "premiership", "scottish premiership",
    "jupiler", "pro league belgium",
    "super league greece", "greek super league",

    # Américas e Oriente Médio
    "major league soccer", "mls",
    "liga profesional", "primera argentina",
    "liga mx",
    "saudi pro league", "saudi league"
]

# Termos que identificam categorias de base, divisões inferiores e torneios não aprovados (com word boundaries)
DISALLOWED_TERMS = [
    # Categorias de base e juvenis
    r"\bu17\b", r"\bu18\b", r"\bu19\b", r"\bu20\b", r"\bu21\b", r"\bu23\b",
    r"\bsub-17\b", r"\bsub-18\b", r"\bsub-19\b", r"\bsub-20\b", r"\bsub-21\b", r"\bsub-23\b",
    r"\bsub 17\b", r"\bsub 18\b", r"\bsub 19\b", r"\bsub 20\b", r"\bsub 21\b", r"\bsub 23\b",
    r"\bprimavera\b", r"\byouth\b", r"\bdevelopment league\b", r"\bpremier league 2\b",

    # Divisões amadoras ou inferiores não autorizadas
    r"\bmineiro 2\b", r"\bmineiro 3\b", r"\bmineiro b\b", r"\bsegunda divisao\b", r"\bterceira divisao\b",
    r"\bpaulista a2\b", r"\bpaulista a3\b", r"\bpaulista b\b", r"\bpaulista 2\b",
    r"\bcarioca a2\b", r"\bcarioca b1\b", r"\bcarioca b2\b", r"\bcarioca c\b",
    r"\bgaucho 2\b", r"\bgaucho b\b", r"\bdivisao de acesso\b",
    r"\bserie c\b", r"\bserie d\b",
    r"\b2\. bundesliga\b", r"\b3\. liga\b", r"\b4\. liga\b", r"\bregionalliga\b", r"\boberliga\b",
    r"\bligue 2\b", r"\bnational 1\b", r"\bnational 2\b",
    r"\blaliga2\b", r"\bla liga 2\b", r"\bla liga smartbank\b", r"\bprimera rfef\b", r"\bsegunda rfef\b", r"\btercera rfef\b",
    r"\bserie b italiana\b", r"\bserie c italiana\b",
    r"\bliga de expansion\b", r"\bexpansion mx\b",
    r"\bpromocional amateur\b", r"\bprimera c\b", r"\bprimera d\b",
    r"\bsuperliga\b", r"\bsuper ligue\b",
    r"\bnfl\b", r"\bbasket\b", r"\bbasketball\b", r"\btennis\b", r"\bbaseball\b"
]

RE_DISALLOWED = [re.compile(p, re.IGNORECASE) for p in DISALLOWED_TERMS]


def _remover_acentos(texto: str) -> str:
    """Normaliza texto removendo acentos e caracteres especiais."""
    if not texto:
        return ""
    nfkd = unicodedata.normalize("NFKD", str(texto))
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()


def is_allowed_league(league_name: str, country: str = "") -> bool:
    """
    Verifica se uma liga/campeonato pertence estritamente às 38 competições autorizadas.
    Aplica desambiguação geográfica e bloqueio imediato para categorias juvenis e divisões inferiores.
    """
    if not league_name:
        return False

    raw_comb = f"{league_name} {country}"
    norm = _remover_acentos(raw_comb)

    # 1. Bloqueio imediato para categorias de base e divisões não autorizadas
    for pattern in RE_DISALLOWED:
        if pattern.search(norm):
            return False

    # 2. Bloqueio para futebol feminino genérico (a única autorizada é Brasileirão Feminino)
    if any(w in norm for w in ("women", "feminino", "fem")):
        eh_brasileirao_fem = any(
            p in norm for p in ("brasileiro feminino", "brasileirao feminino", "serie a1 feminina", "serie a1 women")
        )
        if not eh_brasileirao_fem:
            return False

    # 3. Validação geográfica estrita por competição

    # --- BRASIL ---
    if "brazil" in norm or "brasil" in norm:
        # Brasileirão Série A
        if any(p in norm for p in ("serie a", "brasileirao", "brasileiro")):
            if "serie b" not in norm and "serie c" not in norm and "serie d" not in norm:
                return True
        # Copa do Brasil
        if "copa do brasil" in norm or "brazil cup" in norm:
            return True
        # Brasileirão Série B
        if any(p in norm for p in ("serie b", "brasileiro serie b", "brasileirao serie b")):
            return True
        # Estaduais e Regionais Principais
        if "paulista" in norm or "paulistao" in norm:
            return True
        if "carioca" in norm or "cariocao" in norm:
            return True
        if "copa do nordeste" in norm or "nordeste" in norm:
            return True
        if "mineiro" in norm:
            return True
        if "gaucho" in norm or "gauchao" in norm:
            return True
        if "copa verde" in norm:
            return True
        if "paranaense" in norm:
            return True
        if "feminino" in norm or "women" in norm:
            return True
        return False

    # Estaduais mesmo sem a palavra "Brasil" explícita
    if any(p in norm for p in (
        "paulistao", "paulista", "cariocao", "carioca", "copa do nordeste", "copa verde",
        "campeonato paulista", "campeonato carioca", "campeonato mineiro", "mineiro",
        "campeonato gaucho", "campeonato paranaense", "gauchao", "gaucho", "paranaense"
    )):
        return True

    # --- CONTINENTAIS & INTERNACIONAIS ---
    if "libertadores" in norm:
        return True
    if "sul-americana" in norm or "sudamericana" in norm:
        return True
    if "champions league" in norm or "uefa champions" in norm:
        return True
    if "europa league" in norm or "uefa europa" in norm:
        return True
    if "conference league" in norm or "uefa conference" in norm:
        return True
    if "afc champions" in norm:
        return True

    # --- INGLATERRA ---
    if any(c in norm for c in ("england", "inglaterra", "britain", "reino unido")):
        if "premier league" in norm:
            return True
        if "championship" in norm:
            return True
        if "fa cup" in norm:
            return True
        if any(k in norm for k in ("carabao cup", "efl cup", "league cup")):
            return True
        return False

    # --- ESPANHA ---
    if any(c in norm for c in ("spain", "espanha")) or "laliga" in norm or "la liga" in norm:
        if any(p in norm for p in ("la liga", "laliga", "primera division")):
            return True
        if any(p in norm for p in ("copa del rey", "copa do rei", "king cup")):
            return True
        return False

    # --- ITÁLIA ---
    if any(c in norm for c in ("italy", "italia")):
        if "serie a" in norm and "serie b" not in norm and "serie c" not in norm:
            return True
        if any(p in norm for p in ("coppa italia", "copa da italia", "italy cup")):
            return True
        return False

    # --- ALEMANHA ---
    if any(c in norm for c in ("germany", "alemanha")):
        if "bundesliga" in norm and "2. bundesliga" not in norm:
            return True
        if any(p in norm for p in ("dfb-pokal", "dfb pokal", "german cup")):
            return True
        return False

    # --- FRANÇA ---
    if any(c in norm for c in ("france", "franca")):
        if "ligue 1" in norm and "ligue 2" not in norm:
            return True
        if any(p in norm for p in ("coupe de france", "copa da franca", "french cup")):
            return True
        return False

    # --- PORTUGAL ---
    if "portugal" in norm:
        if any(p in norm for p in ("liga portugal", "primeira liga")):
            return True
        if any(p in norm for p in ("taca de portugal", "copa de portugal", "portuguese cup")):
            return True
        return False

    # --- HOLANDA ---
    if any(c in norm for c in ("netherlands", "holanda", "holland")) or "eredivisie" in norm:
        if "eredivisie" in norm:
            return True

    # --- TURQUIA ---
    if any(c in norm for c in ("turkey", "turquia")) or re.search(r"\b(super\s*lig|superlig)\b", norm):
        if re.search(r"\b(super\s*lig|superlig)\b", norm):
            return True

    # --- ESCÓCIA ---
    if any(c in norm for c in ("scotland", "escocia")):
        if any(p in norm for p in ("premiership", "scottish premiership")) and "championship" not in norm:
            return True

    # --- BÉLGICA ---
    if "jupiler" in norm:
        return True
    if any(c in norm for c in ("belgium", "belgica")):
        if "jupiler" in norm or ("pro league" in norm and "challenger" not in norm):
            return True

    # --- GRÉCIA ---
    if any(c in norm for c in ("greece", "grecia")) or "super league greece" in norm or "greek super league" in norm:
        if "super league" in norm:
            return True

    # --- ESTADOS UNIDOS (MLS) ---
    if any(c in norm for c in ("usa", "united states", "estados unidos", "north america")) or "major league soccer" in norm:
        if any(p in norm for p in ("mls", "major league soccer")):
            return True

    # --- ARGENTINA ---
    if "argentina" in norm or "liga profesional" in norm or "primera argentina" in norm:
        if any(p in norm for p in ("liga profesional", "primera division", "primera argentina")):
            if not any(d in norm for d in ("primera b", "primera c", "primera d", "torneo promocional")):
                return True

    # --- MÉXICO ---
    if any(c in norm for c in ("mexico", "mexicana")) or "liga mx" in norm:
        if "liga mx" in norm and "expansion" not in norm and "u21" not in norm and "u20" not in norm and "femenil" not in norm:
            return True

    # --- ARÁBIA SAUDITA ---
    if any(c in norm for c in ("saudi", "arabia saudita", "saudi pro league", "saudi league")):
        if any(p in norm for p in ("saudi pro league", "saudi league", "pro league")) and "division 1" not in norm:
            return True

    # 4. Caso não tenha casado com as regras restritas acima, descarta por padrão
    return False


def filter_allowed_matches(matches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Filtra uma lista de partidas, mantendo exclusivamente aquelas cujo campeonato
    pertence à relação exata das 38 competições autorizadas.
    """
    clean_matches = []
    for m in matches:
        lg_obj = m.get("campeonato") or m.get("league") or {}
        if isinstance(lg_obj, dict):
            lg_name = lg_obj.get("name") or lg_obj.get("nome") or ""
            country = lg_obj.get("country") or lg_obj.get("pais") or ""
        else:
            lg_name = str(lg_obj)
            country = ""

        if is_allowed_league(lg_name, country):
            clean_matches.append(m)

    return clean_matches
