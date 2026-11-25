import sys
import os
import time
import argparse
from pathlib import Path
from datetime import datetime, timezone, timedelta


if sys.platform == "win32":
    try:
        if sys.stdout.encoding != 'utf-8':
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        if sys.stderr.encoding != 'utf-8':
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

try:
    from zoneinfo import ZoneInfo
    TIMEZONE_BR = ZoneInfo("America/Sao_Paulo")
except Exception:
    TIMEZONE_BR = timezone(timedelta(hours=-3))

TIMEZONE_NAME = "America/Sao_Paulo"


try:
    from dotenv import load_dotenv
    env_path = Path(__file__).resolve().parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass

try:
    import requests
except ImportError:
    print("[ERRO FATAL] Pacote 'requests' não encontrado. Execute: pip install requests")
    sys.exit(1)


class TermColors:
    HEADER = "\033[95m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


def mask_key(key: str) -> str:

    if not key or len(key) < 8:
        return "****"
    return f"{key[:4]}{'*' * (len(key) - 8)}{key[-4:]}"


def main():
    parser = argparse.ArgumentParser(
        description="Diagnóstico Dinâmico de Partidas Reais na API-Football (Zero Mock)."
    )
    parser.add_argument(
        "--key", "-k",
        type=str,
        default=None,
        help="Chave da API-Football (opcional, lê do .env se omitido)"
    )
    parser.add_argument(
        "--date", "-d",
        type=str,
        default=None,
        help="Data no formato YYYY-MM-DD (padrão: data atual em Brasília)"
    )
    args = parser.parse_args()


    agora_brasilia = datetime.now(TIMEZONE_BR)
    data_hoje = args.date.strip() if (args.date and args.date.strip()) else agora_brasilia.strftime("%Y-%m-%d")


    api_key = (args.key or os.getenv("API_FOOTBALL_KEY", "")).strip()

    print(f"\n{TermColors.CYAN}{TermColors.BOLD}{'=' * 75}{TermColors.RESET}")
    print(f"{TermColors.CYAN}{TermColors.BOLD}   DIAGNÓSTICO OFICIAL DE PARTIDAS EM TEMPO REAL (API-FOOTBALL)   {TermColors.RESET}")
    print(f"{TermColors.CYAN}{TermColors.BOLD}{'=' * 75}{TermColors.RESET}")

    print(f"{TermColors.BOLD}Data Local Atual (Brasília):{TermColors.RESET} {agora_brasilia.strftime('%d/%m/%Y %H:%M:%S')} ({TIMEZONE_NAME})")
    print(f"{TermColors.BOLD}Data da Consulta:{TermColors.RESET}           {data_hoje}")
    print(f"{TermColors.BOLD}Chave API-Football:{TermColors.RESET}         {mask_key(api_key)}")

    if not api_key or api_key in ("sua_chave_aqui", "YOUR_API_KEY", ""):
        print(f"\n{TermColors.RED}{TermColors.BOLD}[ALERTA DE CHAVE]{TermColors.RESET}")
        print(f"  • Nenhuma chave válida foi configurada no arquivo .env nem passada via flag --key.")
        print(f"  • O sistema operará em modo estrito (sem mocks) retornando 0 jogos.")
        print(f"  • Para testar com sua chave agora, execute:")
        print(f"    {TermColors.YELLOW}python verificar_jogos_hoje.py --key SUA_CHAVE_AQUI{TermColors.RESET}\n")
        sys.exit(0)


    endpoint_url = "https://v3.football.api-sports.io/fixtures"
    params = {
        "date": data_hoje,
        "timezone": TIMEZONE_NAME
    }
    headers = {
        "x-apisports-key": api_key,
        "Accept": "application/json",
        "User-Agent": "SportsPredictorDiagnostic/1.0"
    }

    url_completa = f"{endpoint_url}?date={data_hoje}&timezone={TIMEZONE_NAME}"

    print(f"\n{TermColors.BOLD}[LOG ESTRUTURADO DE REQUISIÇÃO]{TermColors.RESET}")
    print(f"  • URL Exata:   {TermColors.CYAN}{url_completa}{TermColors.RESET}")
    print(f"  • Parâmetros:  date={data_hoje} | timezone={TIMEZONE_NAME}")
    print(f"  • Timeout:     8.0 segundos")

    start_time = time.perf_counter()
    try:
        response = requests.get(endpoint_url, params=params, headers=headers, timeout=8.0)
        latency_ms = (time.perf_counter() - start_time) * 1000
    except requests.exceptions.Timeout:
        print(f"\n{TermColors.RED}[ERRO] Timeout excedido (> 8.0s) ao conectar a {endpoint_url}{TermColors.RESET}")
        sys.exit(1)
    except requests.exceptions.RequestException as exc:
        print(f"\n{TermColors.RED}[ERRO] Falha de conexão: {exc}{TermColors.RESET}")
        sys.exit(1)

    print(f"\n{TermColors.BOLD}[LOG ESTRUTURADO DE RESPOSTA]{TermColors.RESET}")
    print(f"  • Status HTTP: {response.status_code}")
    print(f"  • Latência:    {latency_ms:.1f} ms")

    if response.status_code == 401:
        print(f"\n{TermColors.RED}{TermColors.BOLD}[FALHA 401] Chave de API inválida ou não autorizada pela API-Sports.{TermColors.RESET}")
        print("  • Verifique sua chave em https://dashboard.api-football.com/")
        sys.exit(1)
    elif response.status_code == 429:
        print(f"\n{TermColors.RED}{TermColors.BOLD}[FALHA 429] Cota diária ou limite por minuto excedido na API-Football.{TermColors.RESET}")
        sys.exit(1)

    try:
        data = response.json()
    except Exception:
        print(f"\n{TermColors.RED}[ERRO] A resposta da API não é um JSON válido: {response.text[:300]}{TermColors.RESET}")
        sys.exit(1)

    errors = data.get("errors", {})
    if errors and (isinstance(errors, dict) and len(errors) > 0 or isinstance(errors, list) and len(errors) > 0):
        print(f"\n{TermColors.YELLOW}[AVISO DE ERROS NO PAYLOAD]: {errors}{TermColors.RESET}")

    results_count = data.get("results", 0)
    fixtures_list = data.get("response", [])
    print(f"  • results:     {results_count} jogos retornados oficialmente pela API")

    if results_count == 0 or len(fixtures_list) == 0:
        print(f"\n{TermColors.YELLOW}{TermColors.BOLD}---------------------------------------------------------------------------{TermColors.RESET}")
        print(f"{TermColors.YELLOW}{TermColors.BOLD}RESULTADO: Nenhum jogo oficial encontrado para a data de hoje ({data_hoje}) no fuso {TIMEZONE_NAME}.{TermColors.RESET}")
        print(f"O backend retornará estritamente [] (lista vazia) sem criar jogos simulados.")
        print(f"{TermColors.YELLOW}{TermColors.BOLD}---------------------------------------------------------------------------{TermColors.RESET}\n")
        sys.exit(0)


    STATUS_PROGRAMADOS = {"NS", "1H", "HT", "2H"}
    STATUS_ENCERRADOS = {"FT", "AET", "PEN"}
    STATUS_CANCELADOS = {"CANC", "PST", "INT", "ABD", "SUSP"}

    programados = []
    encerrados = []
    cancelados = []

    for f in fixtures_list:
        status_short = f.get("fixture", {}).get("status", {}).get("short", "")
        if status_short in STATUS_PROGRAMADOS:
            programados.append(f)
        elif status_short in STATUS_ENCERRADOS:
            encerrados.append(f)
        elif status_short in STATUS_CANCELADOS:
            cancelados.append(f)
        else:
            programados.append(f)

    print(f"\n{TermColors.BOLD}[AUDITORIA DE STATUS DAS PARTIDAS DE HOJE]{TermColors.RESET}")
    print(f"  • Programadas / Ao Vivo (NS, 1H, HT, 2H): {TermColors.GREEN}{len(programados)}{TermColors.RESET}")
    print(f"  • Já Encerradas (FT, AET, PEN):          {TermColors.YELLOW}{len(encerrados)}{TermColors.RESET}")
    print(f"  • Canceladas / Adiada (CANC, PST):       {TermColors.RED}{len(cancelados)}{TermColors.RESET}")


    print(f"\n{TermColors.GREEN}{TermColors.BOLD}{'=' * 95}{TermColors.RESET}")
    print(f"{TermColors.GREEN}{TermColors.BOLD}{'PARTIDAS REAIS DE HOJE (FUSO HORÁRIO: AMÉRICA/SÃO PAULO)':^95}{TermColors.RESET}")
    print(f"{TermColors.GREEN}{TermColors.BOLD}{'=' * 95}{TermColors.RESET}")
    print(f"{'ID':<10} | {'HORA (BRT)':<10} | {'STATUS':<8} | {'CAMPEONATO':<25} | {'CONFRONTO':<35}")
    print("-" * 95)

    exibir_jogos = programados if programados else fixtures_list[:25]
    for f in exibir_jogos[:35]:
        fix_id = str(f.get("fixture", {}).get("id", "N/A"))
        raw_date = f.get("fixture", {}).get("date", "")
        status_s = f.get("fixture", {}).get("status", {}).get("short", "NS")
        league_name = (f.get("league", {}).get("name", "N/A"))[:24]
        home_name = f.get("teams", {}).get("home", {}).get("name", "Mandante")
        away_name = f.get("teams", {}).get("away", {}).get("name", "Visitante")
        confronto = f"{home_name} vs {away_name}"[:34]

        hora_str = "--:--"
        if raw_date:
            try:
                dt_obj = datetime.fromisoformat(raw_date.replace("Z", "+00:00")).astimezone(TIMEZONE_BR)
                hora_str = dt_obj.strftime("%H:%M")
            except Exception:
                hora_str = raw_date[11:16]

        print(f"{fix_id:<10} | {hora_str:<10} | {status_s:<8} | {league_name:<25} | {confronto:<35}")

    total_mostrados = min(len(exibir_jogos), 35)
    print("-" * 95)
    print(f"Mostrando {total_mostrados} de {len(fixtures_list)} jogos oficiais retornados pela API-Football.")
    print(f"{TermColors.GREEN}{TermColors.BOLD}Diagnóstico concluído com sucesso: ZERO DADOS MOCADOS.{TermColors.RESET}\n")


if __name__ == "__main__":
    main()
