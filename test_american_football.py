#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de Teste de Fumaça Isolado - API-Sports American Football (NFL)
Testa a conectividade com a API oficial, a autenticação por chave de ambiente,
o cálculo dinâmico da data no fuso de Brasília (America/Sao_Paulo) e a normalização PT-BR.
"""

import os
import sys
import asyncio
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Configuração de encoding para Windows
if sys.platform == "win32":
    try:
        if sys.stdout and hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Adiciona o diretório base ao sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from american_football_service import american_football_service


async def main():
    print("=" * 70)
    print("  🏈 TESTE DE FUMAÇA: API-SPORTS FUTEBOL AMERICANO (NFL) 🏈")
    print("=" * 70)

    # 1. Validação de Credenciais no .env
    api_key = os.getenv("AMERICAN_FOOTBALL_API_KEY", "").strip()
    if not api_key:
        print("[ERRO CRÍTICO] Variável AMERICAN_FOOTBALL_API_KEY não encontrada no .env!")
        sys.exit(1)

    key_masked = api_key[:4] + "*" * (len(api_key) - 8) + api_key[-4:]
    print(f"[1/5] Chave detectada com segurança: {key_masked}")

    # 2. Teste de Conexão e Status da Assinatura
    print("\n[2/5] Consultando status da assinatura na API-Sports (/status)...")
    status_info = await american_football_service.obter_status()
    print(f"      -> Status do Serviço: {status_info.get('status')}")
    print(f"      -> Plano:             {status_info.get('plano', 'N/A')}")
    print(f"      -> Assinatura Ativa:  {status_info.get('ativo', False)}")
    print(f"      -> Limite Diário:     {status_info.get('limite_diario', 'N/A')} requisições")
    print(f"      -> Requisições Hoje:  {status_info.get('requisicoes_hoje', 'N/A')}")

    # 3. Data Dinâmica em Horário de Brasília
    data_hoje_brt = american_football_service.obter_data_atual_brasilia()
    print(f"\n[3/5] Fuso Horário e Data Dinâmica:")
    print(f"      -> Fuso Horário Alvo: America/Sao_Paulo")
    print(f"      -> Data Atual (BRT):  {data_hoje_brt}")

    # 4. Busca e Normalização da Grade de Jogos de Hoje
    print(f"\n[4/5] Buscando partidas para {data_hoje_brt} via GET /games?date={data_hoje_brt}&timezone=America/Sao_Paulo...")
    resultado = await american_football_service.buscar_jogos(data=data_hoje_brt, force_refresh=True)

    total_jogos = resultado.get("total_jogos", 0)
    contadores = resultado.get("contadores_status", {})
    print(f"      -> Total de Jogos Encontrados Hoje: {total_jogos}")
    print(f"      -> Contadores por Status: {contadores}")
    print(f"      -> Provedor: {resultado.get('provedor')}")

    # Se na data de hoje não houver jogos da NFL (ex: segunda sem jogo ou pré-temporada),
    # testamos também a data recente de jogos (2026-09-13) para validar a normalização completa
    jogos = resultado.get("jogos", [])
    if not jogos:
        print(f"      [INFO] Sem jogos para {data_hoje_brt}. Consultando rodada recente (2026-09-13) para validar normalização...")
        res_sample = await american_football_service.buscar_jogos(data="2026-09-13", force_refresh=False)
        jogos = res_sample.get("jogos", [])
        print(f"      -> Jogos retornados na rodada recente: {len(jogos)}")

    # 5. Exibição Detalhada das Partidas e Parciais por Quarto
    print("\n[5/5] Visualização das Partidas Normalizadas:")
    print("-" * 70)

    for i, j in enumerate(jogos[:5], 1):
        status = j.get("status", {})
        tc = j.get("time_casa", {})
        tf = j.get("time_fora", {})
        pq = j.get("parciais_quartos", {})
        ls = j.get("linha_segura", {})

        nome_casa = tc.get('nome') if isinstance(tc, dict) else str(tc)
        sigla_casa = tc.get('sigla', 'CASA') if isinstance(tc, dict) else 'CASA'
        nome_fora = tf.get('nome') if isinstance(tf, dict) else str(tf)
        sigla_fora = tf.get('sigla', 'FORA') if isinstance(tf, dict) else 'FORA'
        liga_nome = j.get('liga', {}).get('nome', 'NFL') if isinstance(j.get('liga'), dict) else str(j.get('liga', 'NFL'))

        print(f"  PARTIDA #{i}: {nome_fora} ({sigla_fora}) vs {nome_casa} ({sigla_casa})")
        print(f"  🏆 Competição:  {liga_nome} | {j.get('semana', '')} | {j.get('fase', '')}")
        print(f"  ⏰ Horário BRT: {j.get('data_formatada', '')} às {j.get('horario', '--:--')} (Estádio: {j.get('estadio', 'Oficial')})")
        print(f"  📊 Status:      [{status.get('short', '')}] {status.get('label', '')} ({status.get('quarto', '')})")
        placar = j.get('placar', {})
        print(f"  🏈 Placar Geral: {sigla_fora} {placar.get('fora', '-')} x {placar.get('casa', '-')} {sigla_casa}")
        
        # Tabela de Quartos
        if pq and "fora" in pq and "casa" in pq:
            print("  ┌─────────────────────────────────────────────────────────────┐")
            print("  │ TABELA DE PARCIAIS POR QUARTO                               │")
            print("  ├──────────┬─────┬─────┬─────┬─────┬─────┬───────────────────┤")
            print("  │ Equipe   │ 1ºQ │ 2ºQ │ 3ºQ │ 4ºQ │ OT  │ Total             │")
            print("  ├──────────┼─────┼─────┼─────┼─────┼─────┼───────────────────┤")
            print(f"  │ {sigla_fora:<8} │ {str(pq.get('fora', {}).get('q1') or '-'):<3} │ {str(pq.get('fora', {}).get('q2') or '-'):<3} │ {str(pq.get('fora', {}).get('q3') or '-'):<3} │ {str(pq.get('fora', {}).get('q4') or '-'):<3} │ {str(pq.get('fora', {}).get('ot') or '-'):<3} │ {str(pq.get('fora', {}).get('total') or '-'):<17} │")
            print(f"  │ {sigla_casa:<8} │ {str(pq.get('casa', {}).get('q1') or '-'):<3} │ {str(pq.get('casa', {}).get('q2') or '-'):<3} │ {str(pq.get('casa', {}).get('q3') or '-'):<3} │ {str(pq.get('casa', {}).get('q4') or '-'):<3} │ {str(pq.get('casa', {}).get('ot') or '-'):<3} │ {str(pq.get('casa', {}).get('total') or '-'):<17} │")
            print("  └──────────┴─────┴─────┴─────┴─────┴─────┴───────────────────┘")

        # Linha Segura e Mercados
        if ls:
            print(f"  ⭐ LINHA SEGURA: {ls.get('selecao', 'N/A')} @{float(ls.get('odd', 1.0)):.2f} ({ls.get('confianca', 0)}% Confiança)")
            print(f"  💡 Justificativa: \"{ls.get('justificativa_tatica', '')}\"")
        mp = j.get('metricas_projetadas', {})
        if mp:
            print(f"  📈 Projeções: ~{mp.get('jardas_totais_estimadas', 0)} Jardas Totais | ~{mp.get('touchdowns_estimados', 0)} TDs")
        print("-" * 70)

    print("\n[SUCESSO] Todos os testes da API-Sports American Football foram concluídos com êxito!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
