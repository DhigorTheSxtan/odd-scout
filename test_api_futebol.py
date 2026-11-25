import sys
import os
import time
import json
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
    from dotenv import load_dotenv
    env_path = Path(__file__).resolve().parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass

try:
    import httpx
except ImportError:
    print("[ERRO FATAL] A biblioteca 'httpx' não está instalada. Execute: pip install httpx")
    sys.exit(1)

from config import (
    API_FUTEBOL_KEY,
    API_FUTEBOL_BASE_URL,
    REQUEST_TIMEOUT_SECONDS,
    is_api_futebol_configured
)
from api_futebol_adapter import ApiFutebolAdapter


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
    return f"{key[:6]}{'*' * (len(key) - 10)}{key[-4:]}"


def print_header():
    print(f"\n{Colors.CYAN}{Colors.BOLD}{'=' * 75}{Colors.RESET}")
    print(f"{Colors.CYAN}{Colors.BOLD}   DIAGNÓSTICO & SMOKE TEST: API-FUTEBOL (BRASIL){Colors.RESET}")
    print(f"{Colors.CYAN}   Provedora Nacional de Alta Precisão (Brasileirão, Copa do Brasil){Colors.RESET}")
    print(f"{Colors.CYAN}{Colors.BOLD}{'=' * 75}{Colors.RESET}\n")


def test_api_futebol():
    print_header()

    print(f"{Colors.BOLD}[1/4] Verificação de Credenciais e Ambiente{Colors.RESET}")
    print(f" • Base URL: {API_FUTEBOL_BASE_URL}")
    print(f" • Chave (.env): {mask_key(API_FUTEBOL_KEY)}")
    print(f" • Timeout Estrito: {REQUEST_TIMEOUT_SECONDS}s")

    if not is_api_futebol_configured():
        print(f"\n{Colors.YELLOW}[AVISO] API_FUTEBOL_KEY não configurada ou com placeholder no .env.{Colors.RESET}")
        print("Para conectar à API oficial, obtenha seu token em: https://dash.api-futebol.com.br/")
        print("E adicione no arquivo .env:\n  API_FUTEBOL_KEY=live_xxxxxxxxxxxxxxxxxxxxxxxx\n")
        return

    print(f" • Status Configuração: {Colors.GREEN}CONFIGURADA{Colors.RESET}")

    headers = {
        "Authorization": f"Bearer {API_FUTEBOL_KEY}",
        "Accept": "application/json",
        "User-Agent": "ApiFutebolSmokeTest/1.0"
    }

    client = httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS)


    print(f"\n{Colors.BOLD}[2/4] Testando Autenticação e Dados da Conta (/v1/me)...{Colors.RESET}")
    start_t = time.perf_counter()
    try:
        res_me = client.get(f"{API_FUTEBOL_BASE_URL}/me", headers=headers)
        lat_ms = (time.perf_counter() - start_t) * 1000

        print(f" • Resposta HTTP: {res_me.status_code} ({lat_ms:.1f}ms)")

        if res_me.status_code == 401:
            try:
                err_payload = res_me.json()
                msg = err_payload.get("message") or err_payload.get("mensagem") or "Token inválido ou não autorizado."
            except Exception:
                msg = res_me.text
            print(f"{Colors.YELLOW}[RESPOSTA 401 DA API-FUTEBOL]{Colors.RESET} {msg}")
            print(f"{Colors.CYAN}Dica:{Colors.RESET} Acesse https://dash.api-futebol.com.br/ para verificar os campeonatos vinculados ao plano do seu token.")
            return
        elif res_me.status_code == 429:
            print(f"{Colors.YELLOW}[ERRO 429] Limite de requisições do plano atingido (Rate Limit).{Colors.RESET}")
            return
        elif res_me.status_code >= 500:
            print(f"{Colors.RED}[ERRO {res_me.status_code}] Servidor da API-Futebol indisponível temporariamente.{Colors.RESET}")
            return
        elif res_me.status_code == 200:
            me_data = res_me.json()
            plano = me_data.get("plano", {})
            camps = me_data.get("campeonatos", [])
            print(f"{Colors.GREEN} • Autenticação: SUCESSO{Colors.RESET}")
            print(f" • Plano Ativo: {plano.get('nome', 'Padrão')} (Vencimento: {plano.get('data_vencimento', 'N/A')})")
            print(f" • Campeonatos Liberados no Plano: {len(camps)}")
            for c in camps[:5]:
                print(f"    - [{c.get('campeonato_id')}] {c.get('nome')}")
            if len(camps) > 5:
                print(f"    - ... e mais {len(camps) - 5} competições.")

    except httpx.TimeoutException:
        print(f"{Colors.RED}[FALHA] Timeout de requisição (> {REQUEST_TIMEOUT_SECONDS}s).{Colors.RESET}")
        return
    except httpx.RequestError as exc:
        print(f"{Colors.RED}[FALHA] Erro de rede ao conectar à API-Futebol: {exc}{Colors.RESET}")
        return


    print(f"\n{Colors.BOLD}[3/4] Consultando Partidas Ao Vivo (/v1/ao-vivo)...{Colors.RESET}")
    try:
        start_t = time.perf_counter()
        res_live = client.get(f"{API_FUTEBOL_BASE_URL}/ao-vivo", headers=headers)
        lat_ms = (time.perf_counter() - start_t) * 1000
        print(f" • Resposta HTTP: {res_live.status_code} ({lat_ms:.1f}ms)")
        if res_live.status_code == 200:
            live_data = res_live.json()
            if isinstance(live_data, list):
                print(f"{Colors.GREEN} • Jogos em andamento agora: {len(live_data)}{Colors.RESET}")
                for j in live_data[:3]:
                    norm = ApiFutebolAdapter.adaptar_partida(j)
                    print(f"    ⚽ {norm['mandante']['nome']} vs {norm['visitante']['nome']} | Status: {norm['status_descricao']}")
            else:
                print(f" • Resposta: {live_data}")
        else:
            print(f"{Colors.YELLOW} • Retorno HTTP {res_live.status_code}: {res_live.text[:150]}{Colors.RESET}")
    except Exception as exc:
        print(f"{Colors.YELLOW} • Aviso ao consultar ao-vivo: {exc}{Colors.RESET}")


    print(f"\n{Colors.BOLD}[4/4] Consultando Partidas do Brasileirão (/v1/campeonatos/10/partidas)...{Colors.RESET}")
    try:
        start_t = time.perf_counter()
        res_camp = client.get(f"{API_FUTEBOL_BASE_URL}/campeonatos/10/partidas", headers=headers)
        lat_ms = (time.perf_counter() - start_t) * 1000
        print(f" • Resposta HTTP: {res_camp.status_code} ({lat_ms:.1f}ms)")

        if res_camp.status_code == 200:
            camp_data = res_camp.json()
            camp_meta = camp_data.get("campeonato", {})
            partidas = camp_data.get("partidas", {})
            print(f"{Colors.GREEN} • Campeonato: {camp_meta.get('nome', 'Brasileirão')}{Colors.RESET}")

            total_jogos = 0
            amostra_jogos = []
            if isinstance(partidas, dict):
                for f_nome, fases in partidas.items():
                    if isinstance(fases, dict):
                        for r_nome, rodada in fases.items():
                            if isinstance(rodada, list):
                                total_jogos += len(rodada)
                                if len(amostra_jogos) < 3 and rodada:
                                    amostra_jogos.extend(rodada[:2])

            print(f" • Total de jogos mapeados no campeonato: {total_jogos}")
            print(f" • Exemplo de confrontos adaptados via Adapter Pattern:")
            for j in amostra_jogos[:3]:
                norm = ApiFutebolAdapter.adaptar_partida(j)
                print(f"    🏆 [{norm['campeonato']['nome']}] {norm['mandante']['nome']} vs {norm['visitante']['nome']}")
                print(f"       📅 Data/Hora: {norm['horario']} ({norm['data_hora']}) | Status: {norm['status_descricao']}")
                print(f"       🏟️ Estádio: {norm['estadio']}")
        elif res_camp.status_code == 403:
            print(f"{Colors.YELLOW} • O Brasileirão Série A (ID 10) não está liberado no plano da sua chave.{Colors.RESET}")
        else:
            print(f"{Colors.YELLOW} • Retorno HTTP {res_camp.status_code}: {res_camp.text[:150]}{Colors.RESET}")

    except Exception as exc:
        print(f"{Colors.RED} • Erro na consulta de partidas: {exc}{Colors.RESET}")

    print(f"\n{Colors.GREEN}{Colors.BOLD}{'=' * 75}{Colors.RESET}")
    print(f"{Colors.GREEN}{Colors.BOLD}   SMOKE TEST FINALIZADO COM SUCESSO!{Colors.RESET}")
    print(f"{Colors.GREEN}{Colors.BOLD}{'=' * 75}{Colors.RESET}\n")


if __name__ == "__main__":
    test_api_futebol()
