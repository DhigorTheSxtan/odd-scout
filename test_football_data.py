import sys
import os
import time
import asyncio
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
    import httpx
except ImportError:
    print("[ERRO FATAL] A biblioteca 'httpx' não está instalada. Execute: pip install httpx")
    sys.exit(1)

from config import (
    FOOTBALL_DATA_TOKEN,
    FOOTBALL_DATA_BASE_URL,
    REQUEST_TIMEOUT_SECONDS,
    CACHE_TTL_FOOTBALL_DATA_SECONDS,
    is_football_data_configured
)
from football_data_client import football_data_client, FootballDataAdapter, mask_key
from cache import app_cache


class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


async def run_smoke_test(target_date: str, custom_token: str = None) -> bool:
    token_to_use = (custom_token or FOOTBALL_DATA_TOKEN).strip()

    print(f"\n{Colors.CYAN}{Colors.BOLD}{'=' * 80}{Colors.RESET}")
    print(f"{Colors.CYAN}{Colors.BOLD}   DIAGNÓSTICO OFICIAL & SMOKE TEST - FOOTBALL-DATA.ORG (V4)   {Colors.RESET}")
    print(f"{Colors.CYAN}{Colors.BOLD}{'=' * 80}{Colors.RESET}")

    agora_brasilia = datetime.now(TIMEZONE_BR)
    print(f"{Colors.BOLD}Horário Atual (Brasília):{Colors.RESET} {agora_brasilia.strftime('%d/%m/%Y %H:%M:%S')} ({TIMEZONE_NAME})")
    print(f"{Colors.BOLD}Data Alvo da Consulta:{Colors.RESET}   {target_date}")
    print(f"{Colors.BOLD}Base URL:{Colors.RESET}                {FOOTBALL_DATA_BASE_URL}")
    print(f"{Colors.BOLD}Header de Autenticação:{Colors.RESET}  X-Auth-Token: {mask_key(token_to_use)}")
    print(f"{Colors.BOLD}Timeout Rígido:{Colors.RESET}          {REQUEST_TIMEOUT_SECONDS} segundos")
    print(f"{Colors.BOLD}Rate Limit Free Tier:{Colors.RESET}    10 requisições / minuto (Throttling Ativo)")
    print(f"{Colors.BOLD}TTL de Cache em Memória:{Colors.RESET} {CACHE_TTL_FOOTBALL_DATA_SECONDS}s (20 min)")
    print(f"{'-' * 80}\n")

    if not token_to_use or token_to_use in ("sua_chave_football_data_aqui", "YOUR_API_KEY"):
        print(f"{Colors.RED}[ERRO CRÍTICO] Token FOOTBALL_DATA_TOKEN não configurado no arquivo .env.{Colors.RESET}")
        return False


    print(f"{Colors.BOLD}[ETAPA 1/3] Testando conectividade e autenticação com /matches...{Colors.RESET}")
    headers = {
        "X-Auth-Token": token_to_use,
        "Accept": "application/json",
        "User-Agent": "SportsPredictorAI-SmokeTest/1.0"
    }

    start_time = time.perf_counter()
    url_teste = f"{FOOTBALL_DATA_BASE_URL.rstrip('/')}/matches"


    try:
        dt_obj = datetime.strptime(target_date, "%Y-%m-%d")
        next_day = (dt_obj + timedelta(days=1)).strftime("%Y-%m-%d")
    except Exception:
        next_day = target_date

    params = {"dateFrom": target_date, "dateTo": next_day}

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            resp = await client.get(url_teste, headers=headers, params=params)
            latency_ms = (time.perf_counter() - start_time) * 1000

            print(f" -> Status HTTP: {resp.status_code}")
            print(f" -> Latência: {latency_ms:.1f} ms")

            if resp.status_code == 401:
                print(f"{Colors.RED}[FALHA] Token rejeitado pela Football-Data.org (HTTP 401 Unauthorized).{Colors.RESET}")
                return False
            elif resp.status_code == 403:
                print(f"{Colors.YELLOW}[ALERTA] HTTP 403 Forbidden: Competição ou recurso restrito ao plano contratado.{Colors.RESET}")
            elif resp.status_code == 429:
                print(f"{Colors.YELLOW}[ALERTA] HTTP 429 Too Many Requests: Limite de taxa (10 req/min) atingido.{Colors.RESET}")
                return False
            elif resp.status_code != 200:
                print(f"{Colors.RED}[FALHA] Resposta inesperada: HTTP {resp.status_code}. Conteúdo: {resp.text[:200]}{Colors.RESET}")
                return False

            data = resp.json()
            raw_matches = data.get("matches", [])
            print(f"{Colors.GREEN} -> Conexão autenticada com sucesso! Total de partidas brutas recebidas: {len(raw_matches)}{Colors.RESET}\n")

    except Exception as exc:
        print(f"{Colors.RED}[ERRO] Falha de comunicação de rede: {exc}{Colors.RESET}")
        return False


    print(f"{Colors.BOLD}[ETAPA 2/3] Validando conversão para Schema Canônico unificado...{Colors.RESET}")
    partidas_convertidas = []
    for m in raw_matches:
        try:
            norm = FootballDataAdapter.adaptar_partida(m)
            partidas_convertidas.append(norm)
        except Exception as e:
            print(f"{Colors.YELLOW}[AVISO] Erro ao adaptar partida {m.get('id')}: {e}{Colors.RESET}")

    print(f"{Colors.GREEN} -> {len(partidas_convertidas)} partidas adaptadas com conformidade estrita ao schema.{Colors.RESET}\n")


    if partidas_convertidas:
        print(f"{Colors.CYAN}{Colors.BOLD}{'HORÁRIO':<9} | {'COMPETIÇÃO':<26} | {'CONFRONTO':<35} | {'STATUS':<12} | {'PLACAR':<8}{Colors.RESET}")
        print(f"{'-' * 98}")
        for p in partidas_convertidas[:15]:
            horario = p.get("horario", "--:--")
            comp_nome = p.get("campeonato", {}).get("nome", "Campeonato")[:25]
            casa = p.get("mandante", {}).get("nome", "Mandante")[:16]
            fora = p.get("visitante", {}).get("nome", "Visitante")[:16]
            confronto = f"{casa} x {fora}"
            status = p.get("status_descricao", "Agendado")[:11]
            placar = p.get("placar", {})
            placar_str = f"{placar.get('mandante') or '-'} x {placar.get('visitante') or '-'}"
            print(f"{horario:<9} | {comp_nome:<26} | {confronto:<35} | {status:<12} | {placar_str:<8}")
        if len(partidas_convertidas) > 15:
            print(f"... e mais {len(partidas_convertidas) - 15} partidas programadas.")
        print()
    else:
        print(f"{Colors.YELLOW}[INFO] Nenhuma partida encontrada especificamente para o filtro de data.{Colors.RESET}\n")


    print(f"{Colors.BOLD}[ETAPA 3/3] Validando proteção de Rate Limit via Cache em Memória...{Colors.RESET}")
    start_cache = time.perf_counter()
    matches_cached = await football_data_client.buscar_jogos_dia(target_date)
    duration_cache_ms = (time.perf_counter() - start_cache) * 1000

    print(f" -> Chamada 1 ao FootballDataClient: {len(matches_cached)} jogos obtidos.")


    start_hit = time.perf_counter()
    matches_hit = await football_data_client.buscar_jogos_dia(target_date)
    duration_hit_ms = (time.perf_counter() - start_hit) * 1000

    print(f" -> Chamada 2 imediata (Cache HIT): {len(matches_hit)} jogos em {duration_hit_ms:.2f} ms!")
    assert duration_hit_ms < 50.0, "Cache em memória deveria responder em < 50ms!"
    print(f"{Colors.GREEN} -> Proteção contra HTTP 429 validada com sucesso via InMemoryCache!{Colors.RESET}\n")

    print(f"{Colors.GREEN}{Colors.BOLD}{'=' * 80}{Colors.RESET}")
    print(f"{Colors.GREEN}{Colors.BOLD}   SUCESSO TOTAL: FOOTBALL-DATA.ORG INTEGRADA E OPERACIONAL!   {Colors.RESET}")
    print(f"{Colors.GREEN}{Colors.BOLD}{'=' * 80}{Colors.RESET}\n")
    return True


def main():
    parser = argparse.ArgumentParser(description="Smoke Test para Football-Data.org (v4).")
    parser.add_argument("--key", "-k", type=str, default=None, help="Token da Football-Data.org (opcional)")
    parser.add_argument("--date", "-d", type=str, default=None, help="Data no formato YYYY-MM-DD")
    args = parser.parse_args()

    data_hoje = args.date.strip() if args.date else datetime.now(TIMEZONE_BR).strftime("%Y-%m-%d")
    sucesso = asyncio.run(run_smoke_test(data_hoje, args.key))
    sys.exit(0 if sucesso else 1)


if __name__ == "__main__":
    main()
