import sys
import os
import time
import argparse
from pathlib import Path
from typing import Dict, Any, Optional


if sys.platform == "win32":
    try:
        if sys.stdout.encoding != 'utf-8':
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        if sys.stderr.encoding != 'utf-8':
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

try:
    import requests
except ImportError:
    print("[ERRO FATAL] A biblioteca 'requests' não está instalada.")
    print("Execute: pip install requests")
    sys.exit(1)


try:
    from dotenv import load_dotenv
    env_path = Path(__file__).resolve().parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass


STATUS_ENDPOINT = "https://v3.football.api-sports.io/status"
REQUEST_TIMEOUT = 8.0


class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


def mask_key(key: str) -> str:

    if not key or len(key) < 8:
        return "****"
    return f"{key[:4]}{'*' * (len(key) - 8)}{key[-4:]}"


def print_banner():
    print(f"\n{Colors.CYAN}{Colors.BOLD}==============================================================={Colors.RESET}")
    print(f"{Colors.CYAN}{Colors.BOLD}       API-FOOTBALL (API-SPORTS) - SMOKE TEST & DIAGNÓSTICO   {Colors.RESET}")
    print(f"{Colors.CYAN}{Colors.BOLD}==============================================================={Colors.RESET}")


def run_smoke_test(api_key: str) -> bool:

    headers = {
        "x-apisports-key": api_key,
        "Accept": "application/json",
        "User-Agent": "SportsPredictorDiagnostic/1.0"
    }

    print(f"\n{Colors.BOLD}[1/3] Parâmetros de Teste:{Colors.RESET}")
    print(f"  • Endpoint: {STATUS_ENDPOINT}")
    print(f"  • Timeout configurado: {REQUEST_TIMEOUT}s")
    print(f"  • Chave em teste: {Colors.CYAN}{mask_key(api_key)}{Colors.RESET}")

    print(f"\n{Colors.BOLD}[2/3] Conectando ao host remoto...{Colors.RESET}")

    start_time = time.perf_counter()
    try:
        response = requests.get(STATUS_ENDPOINT, headers=headers, timeout=REQUEST_TIMEOUT)
        latency_ms = (time.perf_counter() - start_time) * 1000
    except requests.exceptions.Timeout:
        latency_ms = (time.perf_counter() - start_time) * 1000
        print(f"\n{Colors.RED}{Colors.BOLD}[FALHA CRÍTICA - TIMEOUT]{Colors.RESET}")
        print(f"  • Status: Requisição excedeu o limite máximo estrito de {REQUEST_TIMEOUT} segundos.")
        print(f"  • Latência registrada: {latency_ms:.1f} ms")
        print(f"  • Ação Recomendada: Verifique sua conexão com a internet ou se há bloqueio/firewall na rede.")
        return False
    except requests.exceptions.ConnectionError as e:
        print(f"\n{Colors.RED}{Colors.BOLD}[FALHA CRÍTICA - CONEXÃO / DNS]{Colors.RESET}")
        print(f"  • Status: Falha ao resolver DNS ou indisponibilidade do host https://v3.football.api-sports.io")
        print(f"  • Detalhes técnicos: {str(e)}")
        print(f"  • Ação Recomendada: Verifique conexão, servidores DNS ou status global em https://status.api-sports.io")
        return False
    except requests.exceptions.RequestException as e:
        print(f"\n{Colors.RED}{Colors.BOLD}[FALHA CRÍTICA - REQUISIÇÃO HTTP]{Colors.RESET}")
        print(f"  • Erro inesperado: {str(e)}")
        return False

    print(f"\n{Colors.BOLD}[3/3] Analisando Resposta HTTP & Payload:{Colors.RESET}")
    status_code = response.status_code
    print(f"  • Código HTTP retornado: {status_code}")
    print(f"  • Latência da requisição: {latency_ms:.1f} ms")


    if status_code in (401, 403):
        print(f"\n{Colors.RED}{Colors.BOLD}[REPROVADO] AUTENTICAÇÃO RECUSADA (HTTP {status_code}){Colors.RESET}")
        print(f"  • Causa: A chave informada '{mask_key(api_key)}' foi rejeitada pela API-Sports.")
        print(f"  • Ação Recomendada: Acesse https://dashboard.api-football.com/, copie sua chave válida e configure-a no arquivo .env.")
        return False


    if status_code == 429:
        print(f"\n{Colors.RED}{Colors.BOLD}[REPROVADO] COTA EXCEDIDA (HTTP 429 - TOO MANY REQUESTS){Colors.RESET}")
        print(f"  • Causa: A cota diária ou limite por minuto do seu plano foi atingida.")
        print(f"  • Ação Recomendada: Aguarde a virada do dia (00:00 UTC) para renovação da cota ou faça upgrade do plano.")
        return False


    if status_code >= 500:
        print(f"\n{Colors.RED}{Colors.BOLD}[REPROVADO] ERRO NOS SERVIDORES DA API-SPORTS (HTTP {status_code}){Colors.RESET}")
        print(f"  • Causa: Instabilidade temporária nos servidores remotos.")
        print(f"  • Ação Recomendada: Consulte https://status.api-sports.io e tente novamente em instantes.")
        return False


    try:
        data = response.json()
    except Exception:
        print(f"\n{Colors.RED}{Colors.BOLD}[REPROVADO] RESPOSTA NÃO É UM JSON VÁLIDO{Colors.RESET}")
        print(f"  • Conteúdo bruto: {response.text[:300]}")
        return False


    errors = data.get("errors", {})
    if errors and (isinstance(errors, dict) and len(errors) > 0 or isinstance(errors, list) and len(errors) > 0):
        error_str = str(errors)
        print(f"\n{Colors.RED}{Colors.BOLD}[REPROVADO] ERRO IDENTIFICADO NO CORPO DA RESPOSTA{Colors.RESET}")
        print(f"  • Detalhes do erro: {Colors.YELLOW}{errors}{Colors.RESET}")

        if "token" in error_str:
            print(f"  • Causa: Token de autenticação inválido ou expirado.")
            print(f"  • Ação: Verifique sua chave no dashboard da API-Football.")
        elif "rateLimit" in error_str or "requests" in error_str:
            print(f"  • Causa: Limite de requisições excedido.")
            print(f"  • Ação: Aguarde a redefinição de cota diária (00:00 UTC).")
        else:
            print(f"  • Ação: Verifique a documentação oficial da API-Sports.")
        return False


    account_info = data.get("response", {}).get("account", {})
    subscription_info = data.get("response", {}).get("subscription", {})
    requests_info = data.get("response", {}).get("requests", {})

    firstname = account_info.get("firstname", "N/A")
    lastname = account_info.get("lastname", "")
    full_name = f"{firstname} {lastname}".strip()
    email = account_info.get("email", "N/A")

    plan_name = subscription_info.get("plan", "N/A")
    plan_active = subscription_info.get("active", False)
    plan_end = subscription_info.get("end", "N/A")

    current_requests = requests_info.get("current", 0)
    limit_day = requests_info.get("limit_day", 0)
    remaining_requests = max(0, limit_day - current_requests)
    usage_percent = (current_requests / limit_day * 100) if limit_day > 0 else 0.0


    if latency_ms < 350:
        latency_badge = f"{Colors.GREEN}Excelente ({latency_ms:.1f} ms){Colors.RESET}"
    elif latency_ms < 800:
        latency_badge = f"{Colors.YELLOW}Normal ({latency_ms:.1f} ms){Colors.RESET}"
    else:
        latency_badge = f"{Colors.RED}Alta ({latency_ms:.1f} ms){Colors.RESET}"


    bar_length = 25
    filled = int(bar_length * (current_requests / limit_day)) if limit_day > 0 else 0
    quota_bar = "#" * filled + "-" * (bar_length - filled)


    print(f"\n{Colors.GREEN}{Colors.BOLD}==============================================================={Colors.RESET}")
    print(f"{Colors.GREEN}{Colors.BOLD}           DIAGNÓSTICO APROVADO - TUDO FUNCIONANDO 100%       {Colors.RESET}")
    print(f"{Colors.GREEN}{Colors.BOLD}==============================================================={Colors.RESET}")
    print(f"  {Colors.BOLD}Titular da Conta:{Colors.RESET}     {full_name} ({email})")
    print(f"  {Colors.BOLD}Plano Ativo:{Colors.RESET}          {Colors.CYAN}{plan_name}{Colors.RESET} (Status: {'Ativo' if plan_active else 'Inativo'}, Expira: {plan_end})")
    print(f"  {Colors.BOLD}Latência de Rede:{Colors.RESET}     {latency_badge}")
    print(f"  {Colors.BOLD}Requisições Hoje:{Colors.RESET}     {current_requests} / {limit_day} ({usage_percent:.1f}% consumidos)")
    print(f"  {Colors.BOLD}Uso da Cota:{Colors.RESET}          [{Colors.YELLOW}{quota_bar}{Colors.RESET}]")
    print(f"  {Colors.BOLD}Requisições Restantes:{Colors.RESET} {Colors.GREEN}{Colors.BOLD}{remaining_requests}{Colors.RESET} chamadas disponíveis hoje")
    print(f"{Colors.GREEN}{Colors.BOLD}==============================================================={Colors.RESET}\n")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Smoke Test de Conectividade e Validação de Chave da API-Football."
    )
    parser.add_argument(
        "--key", "-k",
        type=str,
        default=None,
        help="Chave da API-Football (se omitido, lê do arquivo .env ou variável API_FOOTBALL_KEY)"
    )
    args = parser.parse_args()

    print_banner()


    api_key = args.key or os.getenv("API_FOOTBALL_KEY", "").strip()


    if not api_key or api_key in ("sua_chave_aqui", "YOUR_API_KEY", ""):
        print(f"{Colors.YELLOW}[AVISO DE CONFIGURAÇÃO]{Colors.RESET}")
        print("  • Nenhuma chave válida foi encontrada no .env ou via argumento --key.")
        print("  • Você pode passar a chave agora para testar de forma segura:")
        try:
            prompted_key = input(f"\n  Digite ou cole sua chave API-Football: ").strip()
            if prompted_key:
                api_key = prompted_key
            else:
                print(f"\n{Colors.RED}[ERRO] Nenhuma chave fornecida. Teste abortado.{Colors.RESET}")
                print("Exemplo de uso: python check_api.py --key SUA_CHAVE_AQUI\n")
                sys.exit(1)
        except (KeyboardInterrupt, EOFError):
            print("\nOperação cancelada pelo usuário.")
            sys.exit(1)

    success = run_smoke_test(api_key)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
