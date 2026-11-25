"""
Suíte de Testes Automatizados: Comparador de Odds Entre 6 Casas Específicas e Destaque do Top 3
"""
import json
import inspect
import asyncio
from services.ai_analytics_service import (
    CASAS_ALVO,
    _sanitizar_top_3_bookmakers,
    analyze_fixtures_with_gemini,
    _gerar_predicoes_compact_fallback,
    carregar_cache_diario,
    _get_cache_filepath
)

def test_1_casas_alvo_estritas():
    print("\n[TESTE 1] Verificando lista restrita de CASAS_ALVO...")
    casas_esperadas = ["Betano", "Bet365", "Superbet", "Betfair", "Sportingbet", "Esportes da Sorte"]
    assert CASAS_ALVO == casas_esperadas, f"CASAS_ALVO inválidas: {CASAS_ALVO}"
    print(f"  [OK] CASAS_ALVO contém exatamente as 6 casas autorizadas: {CASAS_ALVO}")


def test_2_sanitizacao_e_ordenacao_decrescente():
    print("\n[TESTE 2] Verificando função _sanitizar_top_3_bookmakers...")
    
    # 2.1 Rejeição de casas não autorizadas (ex: Pinnacle, KTO, Betfair permitida, Pinnacle proibida)
    raw = [
        {"bookmaker": "Pinnacle", "odd": 2.10},
        {"bookmaker": "Betano", "odd": 1.95},
        {"bookmaker": "Novibet", "odd": 2.05},
        {"bookmaker": "Bet365", "odd": 1.90}
    ]
    sanitized = _sanitizar_top_3_bookmakers(raw)
    assert len(sanitized) == 3, f"Esperado 3 casas, obtido {len(sanitized)}"
    for c in sanitized:
        assert c["bookmaker"] in CASAS_ALVO, f"Casa não autorizada passou: {c['bookmaker']}"
    assert "Pinnacle" not in [c["bookmaker"] for c in sanitized]
    assert "Novibet" not in [c["bookmaker"] for c in sanitized]
    
    # Ordenação decrescente: maior odd primeiro
    odds = [c["odd"] for c in sanitized]
    assert odds == sorted(odds, reverse=True), f"Odds não estão em ordem decrescente: {odds}"
    print("  [OK] Casas proibidas descartadas e Top 3 ordenado decrescentemente.")

    # 2.2 Normalização de aliases e preenchimento de fallback
    raw_aliases = [
        {"bookmaker": "esportes da sorte", "odd": 1.88},
        {"bookmaker": "SUPERBET", "odd": 1.92}
    ]
    res_aliases = _sanitizar_top_3_bookmakers(raw_aliases)
    assert len(res_aliases) == 3
    nomes = [c["bookmaker"] for c in res_aliases]
    assert "Esportes da Sorte" in nomes
    assert "Superbet" in nomes
    assert len(set(nomes)) == 3, "Casas não são distintas"
    odds_al = [c["odd"] for c in res_aliases]
    assert odds_al == sorted(odds_al, reverse=True)
    print("  [OK] Normalização de nomes e preenchimento automático para 3 casas distintas.")


def test_3_prompt_e_schema_gemini():
    print("\n[TESTE 3] Inspecionando código e prompt do analyze_fixtures_with_gemini...")
    fonte = inspect.getsource(analyze_fixtures_with_gemini)
    
    # Valida presença das 6 casas no prompt
    assert "Betano" in fonte
    assert "Bet365" in fonte
    assert "Superbet" in fonte
    assert "Betfair" in fonte
    assert "Sportingbet" in fonte
    assert "Esportes da Sorte" in fonte
    
    # Valida cláusulas do prompt
    assert "top_3_bookmakers" in fonte
    assert "recommended_market" in fonte
    assert "probability_pct" in fonte
    assert "SELECIONE AS 3 CASAS COM AS MAIORES ODDS" in fonte
    
    # Valida anti-alucinação preservada
    assert "REGRA DE SEGURANÇA E INTEGRIDADE" in fonte
    assert "retorne uma lista JSON vazia: []" in fonte
    print("  [OK] Prompt do Gemini contém todas as diretrizes das 6 casas e o schema exigido.")


def test_4_execucao_anti_alucinacao_e_fallback():
    print("\n[TESTE 4] Testando analyze_fixtures_with_gemini com lista vazia e fallback...")
    
    # Lista vazia não aciona IA e retorna []
    res_vazia = asyncio.run(analyze_fixtures_with_gemini([]))
    assert res_vazia == [], "Lista vazia não retornou []"
    print("  [OK] analyze_fixtures_with_gemini([]) retornou [] imediatamente.")

    # Fallback determinístico
    jogo_mock = ["ID: FIXTURE_100 | Modalidade: futebol | C: Arsenal | F: Chelsea | Data: 2026-09-23"]
    fb = _gerar_predicoes_compact_fallback(jogo_mock, sport="futebol")
    assert len(fb) == 1
    item = fb[0]
    assert "top_3_bookmakers" in item
    assert len(item["top_3_bookmakers"]) == 3
    for b in item["top_3_bookmakers"]:
        assert b["bookmaker"] in CASAS_ALVO
    assert "recommended_market" in item
    assert "probability_pct" in item
    assert "reasoning" in item
    print("  [OK] Fallback determinístico gera exatamente o schema com Top 3 das casas autorizadas.")


def test_5_cache_diario_ia_persistente():
    print("\n[TESTE 5] Validando estrutura persistida em cache_diario_ia.json...")
    cache_path = _get_cache_filepath()
    with open(cache_path, "r", encoding="utf-8") as f:
        dados = json.load(f)
    
    palpites = dados.get("palpites", {})
    assert len(palpites) > 0, "Cache está vazio"
    
    for match_id, p in palpites.items():
        assert "top_3_bookmakers" in p, f"{match_id} não possui 'top_3_bookmakers'"
        top3 = p["top_3_bookmakers"]
        assert isinstance(top3, list) and len(top3) == 3, f"{match_id} não possui 3 bookmakers"
        
        casas_no_jogo = set()
        for idx, b in enumerate(top3):
            assert "bookmaker" in b and "odd" in b, f"Formato inválido em {match_id}: {b}"
            assert b["bookmaker"] in CASAS_ALVO, f"Casa proibida '{b['bookmaker']}' encontrada em {match_id}"
            casas_no_jogo.add(b["bookmaker"])
        assert len(casas_no_jogo) == 3, f"Casas duplicadas em {match_id}: {top3}"
        
        # Odds decrescentes
        odds = [float(b["odd"]) for b in top3]
        assert odds == sorted(odds, reverse=True), f"Odds fora de ordem decrescente em {match_id}: {odds}"
    
    print(f"  [OK] Todos os {len(palpites)} palpites do cache_diario_ia.json estão 100% em conformidade com as 6 casas e Top 3!")


def test_6_frontend_renderizacao_e_badges():
    print("\n[TESTE 6] Validando renderização e estilos no frontend (index.html)...")
    with open("index.html", "r", encoding="utf-8") as f:
        html = f.read()
    
    # 1. Função renderizarCardJogo presente
    assert "function renderizarCardJogo(jogo, predicao)" in html, "renderizarCardJogo não encontrada"
    assert "window.renderizarCardJogo = renderizarCardJogo" in html, "window.renderizarCardJogo não exportada"
    
    # 2. Estilos dos badges (1º destacado em âmbar, 2º e 3º em azul)
    assert "bg-amber-500/20 text-amber-300 border-amber-500/40 font-semibold" in html, "Estilo do 1º colocado não encontrado"
    assert "bg-blue-950/60 text-blue-200 border-blue-800/40" in html, "Estilo do 2º e 3º colocado não encontrado"
    
    # 3. Textos do card
    assert "Top 3 Melhores Odds" in html
    assert "card-jogo bg-[#162032] border border-blue-900/40 rounded-xl" in html
    
    # 4. Sem Pinnacle na lista padrão de Top 3
    assert '{ bookmaker: "Pinnacle"' not in html, "Pinnacle ainda presente em index.html"
    print("  [OK] index.html contém renderizarCardJogo, estilos e badges dos crachás exatamente conforme a especificação.")


if __name__ == "__main__":
    print("=" * 70)
    print(" SUÍTE DE TESTES: TOP 3 MELHORES ODDS ENTRE 6 CASAS ESPECÍFICAS")
    print("=" * 70)
    
    test_1_casas_alvo_estritas()
    test_2_sanitizacao_e_ordenacao_decrescente()
    test_3_prompt_e_schema_gemini()
    test_4_execucao_anti_alucinacao_e_fallback()
    test_5_cache_diario_ia_persistente()
    test_6_frontend_renderizacao_e_badges()
    
    print("\n" + "=" * 70)
    print(" TODOS OS 6 TESTES DA SUÍTE FORAM APROVADOS COM SUCESSO!")
    print("=" * 70)
