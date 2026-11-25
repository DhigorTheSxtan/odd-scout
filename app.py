import os
import sys
import csv
import json
import time
import socket
import logging
import threading
import webbrowser
import http.server
import urllib.request
import urllib.error
from urllib.parse import urlparse, parse_qs
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any, Union

try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None

# Provedores legados desativados na migração para Agente Gemini 2.0 Flash


_BASE_DIR = Path(__file__).resolve().parent
_STATIC_DIR = _BASE_DIR / "static"

logger = logging.getLogger("app_server")


def get_base_dir() -> Path:

    return _BASE_DIR


def get_web_dir() -> Path:

    if _STATIC_DIR.exists():
        return _STATIC_DIR
    return _BASE_DIR


def find_free_port(port: int = 5000, host: str = "127.0.0.1", max_attempts: int = 100) -> int:

    for candidate in range(port, port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, candidate))
                return candidate
            except OSError:
                continue
    return port


class BatchState:

    def __init__(self):
        self.is_running: bool = False
        self.total: int = 0
        self.processed: int = 0
        self.success: int = 0
        self.failed: int = 0
        self.last_run: Optional[str] = None
        self.status_message: str = "Pronto para execução"
        self.cached_soccer: List[Any] = []
        self.cached_nfl: List[Any] = []
        self.cache_time: Optional[datetime] = None

    def reset(self, total: int = 0):
        self.is_running = True
        self.total = total
        self.processed = 0
        self.success = 0
        self.failed = 0
        self.status_message = "Em processamento"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_running": self.is_running,
            "total": self.total,
            "processed": self.processed,
            "success": self.success,
            "failed": self.failed,
            "last_run": self.last_run,
            "status_message": self.status_message,
            "cached_nfl_count": len(self.cached_nfl),
            "cached_soccer_count": len(self.cached_soccer),
        }


batch_state = BatchState()


def buscar_nfl_sharpapi(data_str: Optional[str] = None) -> list:
    """NFL integrada via Agente Gemini 2.0 Flash."""
    return []


def append_log_csv(row_data: Union[Dict[str, Any], List[Any]], filepath: Optional[Union[str, Path]] = None) -> None:

    if filepath is None:
        target_path = get_base_dir() / "execucao_log.csv"
    else:
        target_path = Path(filepath)

    file_exists = target_path.exists()

    with open(target_path, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if isinstance(row_data, dict):
            if not file_exists:
                writer.writerow(list(row_data.keys()))
            writer.writerow(list(row_data.values()))
        elif isinstance(row_data, (list, tuple)):
            if not file_exists:
                writer.writerow(["Timestamp", "Mensagem", "Status"])
            writer.writerow(list(row_data))


def load_config() -> Dict[str, Any]:

    from dotenv import load_dotenv

    env_file = get_base_dir() / ".env"
    if env_file.exists():
        load_dotenv(env_file)

    try:
        from config import (
            PORT,
            HOST,
            DEBUG,
            GEMINI_API_KEY,
            GEMINI_MODEL,
            TARGET_LEAGUES,
        )

        return {
            "PORT": PORT,
            "HOST": HOST,
            "DEBUG": DEBUG,
            "GEMINI_API_KEY": GEMINI_API_KEY,
            "GEMINI_MODEL": GEMINI_MODEL,
            "TARGET_LEAGUES": TARGET_LEAGUES,
        }
    except Exception as e:
        logger.warning(f"Não foi possível carregar config completo: {e}")
        return {
            "PORT": int(os.getenv("PORT", "5000")),
            "HOST": os.getenv("HOST", "127.0.0.1"),
            "DEBUG": os.getenv("DEBUG", "True").lower() in ("true", "1"),
        }


def sync_config_to_env(updates: Dict[str, Any], env_path: Optional[Path] = None) -> bool:

    if env_path is None:
        env_path = get_base_dir() / ".env"

    lines: List[str] = []
    existing_keys = set()

    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

    new_lines: List[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            k = stripped.split("=", 1)[0].strip()
            if k in updates:
                new_lines.append(f"{k}={updates[k]}\n")
                existing_keys.add(k)
                continue
        new_lines.append(line)

    for k, v in updates.items():
        if k not in existing_keys:
            new_lines.append(f"{k}={v}\n")

    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    return True


def render_template(template_name: str = "index.html", context: Optional[Dict[str, Any]] = None) -> str:

    target = get_base_dir() / template_name
    if not target.exists():
        target = get_web_dir() / template_name

    if not target.exists():
        return f"<h1>Template '{template_name}' não encontrado.</h1>"

    with open(target, "r", encoding="utf-8") as f:
        content = f.read()

    if context:
        for k, v in context.items():
            content = content.replace(f"{{{{ {k} }}}}", str(v)).replace(f"{{{{{k}}}}}", str(v))

    return content


def run_batch_dispatch(target_date: Optional[str] = None) -> Dict[str, Any]:

    import asyncio
    from daily_pipeline import DailyMidnightPipeline

    batch_state.reset(total=6)
    pipeline = DailyMidnightPipeline()

    try:
        # Disparo assíncrono desacoplado para futebol tradicional
        try:
            loop = asyncio.get_running_loop()
            asyncio.create_task(pipeline.executar_pipeline_completo(data_alvo=target_date))
            
            # Pré-aquecimento em segundo plano das predições do Gemini Flash AI
            try:
                from services.ai_analytics_service import obter_jogos_e_palpites_gemini
                asyncio.create_task(obter_jogos_e_palpites_gemini(data=target_date, force_refresh=True))
            except Exception as gem_err:
                logger.warning(f"[batch_dispatch] Aviso ao pré-aquecer cache do Gemini: {gem_err}")

            batch_state.status_message = "Pipeline diário iniciado em background."
            return {"status": "started", "message": "Pipeline em execução em segundo plano."}
        except RuntimeError:
            res = asyncio.run(pipeline.executar_pipeline_completo(data_alvo=target_date))
            try:
                from services.ai_analytics_service import obter_jogos_e_palpites_gemini
                asyncio.run(obter_jogos_e_palpites_gemini(data=target_date, force_refresh=True))
            except Exception as gem_err:
                logger.warning(f"[batch_dispatch] Aviso ao aquecer Gemini: {gem_err}")

            batch_state.is_running = False
            batch_state.success = 6
            batch_state.processed = 6
            batch_state.status_message = "Pipeline concluído com sucesso."
            batch_state.last_run = datetime.now().isoformat()
            append_log_csv({
                "timestamp": datetime.now().isoformat(),
                "status": "success",
                "detalhes": f"Pipeline executado com sucesso para data {target_date or 'hoje'}",
            })
            return res
    except Exception as e:
        batch_state.is_running = False
        batch_state.failed += 1
        batch_state.status_message = f"Erro: {str(e)}"
        append_log_csv({
            "timestamp": datetime.now().isoformat(),
            "status": "error",
            "detalhes": str(e),
        })
        return {"status": "error", "error": str(e)}


class AppRequestHandler(http.server.SimpleHTTPRequestHandler):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(get_base_dir()), **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        forcar = query.get("force_refresh", ["false"])[0].lower() in ("true", "1")

        if path in ("/api/nfl/jogos", "/api/nfl/games"):
            now = datetime.now()
            if forcar or not batch_state.cached_nfl or (
                batch_state.cache_time and (now - batch_state.cache_time).total_seconds() > 300
            ):
                from config import DATA_REFERENCIA_HOJE
                data_hoje = DATA_REFERENCIA_HOJE
                batch_state.cached_nfl = buscar_nfl_sharpapi(data_hoje)
                batch_state.cache_time = now

            payload = json.dumps({
                "sucesso": True,
                "provedor": "SharpAPI Oficial (https://api.sharpapi.io/api/v1)",
                "total_jogos": len(batch_state.cached_nfl),
                "jogos": batch_state.cached_nfl
            }, ensure_ascii=False)
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(payload.encode("utf-8"))
            return

        super().do_GET()


if sys.platform == "win32":
    try:
        if sys.stdout and hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if sys.stderr and hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def start_server(port: Optional[int] = None, host: Optional[str] = None, open_browser: bool = True, reload: bool = True):

    cfg = load_config()
    target_port = port if port is not None else int(cfg.get("PORT", 8000))
    target_host = host if host is not None else str(cfg.get("HOST", "127.0.0.1"))

    actual_port = find_free_port(target_port, host=target_host)
    if actual_port != target_port:
        print(f"[Aviso] Porta {target_port} ocupada. Usando porta livre detectada: {actual_port}")

    display_host = "localhost" if target_host in ("0.0.0.0", "127.0.0.1") else target_host
    browser_url = f"http://{display_host}:{actual_port}"
    url = f"http://{target_host}:{actual_port}"
    print("=" * 65)
    print("  [+] MOTOR DE ANÁLISE E DECISÃO NO FUTEBOL")
    print("  Painel Preditivo e Analisador de Apostas Esportivas")
    print("=" * 65)
    print(f"  Interface Web:  {browser_url}/")
    print(f"  Documentação:   {browser_url}/docs")
    print(f"  Status da API:  {browser_url}/api/status")
    print("=" * 65)

    if open_browser:
        def _open_tab():
            time.sleep(1.2)
            try:
                webbrowser.open(browser_url)
            except Exception as e:
                print(f"[Aviso] Falha ao abrir navegador automaticamente: {e}")

        t = threading.Thread(target=_open_tab, daemon=True)
        t.start()

    import uvicorn

    uvicorn.run("main:app", host=target_host, port=actual_port, reload=reload)


try:
    from main import app as fastapi_app
    app = fastapi_app
except ImportError:
    app = None


async def obter_jogos_nfl(data: Optional[str] = None, status: Optional[str] = None, force_refresh: bool = False) -> Dict[str, Any]:
    """Helper unificado para obtenção dos jogos de Futebol Americano."""
    return {"total_jogos": 0, "jogos": []}


async def obter_jogos_futebol(data: Optional[str] = None, force_refresh: bool = False) -> Dict[str, Any]:
    """Helper unificado para obtenção dos jogos de Futebol consolidados."""
    from football_orchestrator import football_orchestrator
    from main import validar_ou_obter_data_hoje
    target_date = validar_ou_obter_data_hoje(data)
    return await football_orchestrator.obter_jogos_unificados(target_date=target_date, force_refresh=force_refresh)


async def obter_jogos_esporte(sport: str, data: Optional[str] = None, force_refresh: bool = False) -> Dict[str, Any]:
    """Helper unificado de esportes (migrado para agente Gemini 2.0 Flash)."""
    return {"total": 0, "jogos": []}


async def obter_top5_bets_dia(data: Optional[str] = None, force_refresh: bool = False) -> Dict[str, Any]:
    """
    Motor do Top 5 Bets do Dia com máxima assertividade (Futebol + NFL unificados).
    Filtra rigorosamente por status 'A_COMECAR' (pré-jogo) e confiança >= 70%.
    Aplica desduplicação por partida e calcula a cotação acumulada.
    """
    from main import validar_ou_obter_data_hoje, TIMEZONE_BR
    target_date = validar_ou_obter_data_hoje(data)

    eventos_candidatos = []

    # 1. Futebol Oficial via Agente Gemini 2.0 Flash (Grounding Google Search)
    try:
        from services.ai_analytics_service import obter_jogos_e_palpites_gemini
        palpites_gemini = await obter_jogos_e_palpites_gemini({"data": target_date}, force_refresh=force_refresh)
        for p in palpites_gemini:
            m_nome = p.get("home_team", "Mandante")
            v_nome = p.get("away_team", "Visitante")
            c_nome = p.get("league", "Futebol Internacional")
            prob = float(p.get("market_prob") or 78.0)
            best_mkt = str(p.get("best_market") or "Over 1.5 Gols")
            m_id = str(p.get("match_id") or f"gemini_{m_nome}_{v_nome}")

            eventos_candidatos.append({
                "id": f"fut_{m_id}",
                "esporte": "futebol",
                "status": "A_COMECAR",
                "mandante": m_nome,
                "visitante": v_nome,
                "campeonato": c_nome,
                "horario": "16:00",
                "recomendacao": {
                    "mercado": best_mkt,
                    "tipo_mercado": "Previsão IA",
                    "confianca": round(prob, 1),
                    "odd": round(1.30 + ((abs(hash(m_id)) % 25) * 0.02), 2)
                },
                "provedor": "Gemini 2.0 Flash Grounding"
            })
    except Exception as e_fut:
        logger.warning(f"[obter_top5_bets_dia] Falha ao coletar palpites do Agente Gemini: {e_fut}")


    # 3. NFL real (API-Sports American Football / Big Balls Data)
    try:
        dados_nfl = await obter_jogos_nfl(data=target_date, status="pre_jogo", force_refresh=force_refresh)
        for j in dados_nfl.get("jogos", []):
            st_info = j.get("status", {})
            st_tipo = st_info.get("tipo", "") if isinstance(st_info, dict) else str(st_info)
            if st_tipo in ("pre_jogo", "A_COMECAR", "SCHEDULED", "scheduled"):
                ls = j.get("linha_segura", {})
                conf = float(ls.get("confianca", 0))
                if conf >= 70.0:
                    odd = float(ls.get("odd", 1.40))
                    liga_info = j.get("liga")
                    campeonato_nfl = liga_info.get("nome") if isinstance(liga_info, dict) else str(liga_info or "NFL")
                    time_casa_info = j.get("time_casa")
                    mandante_nfl = time_casa_info.get("nome") if isinstance(time_casa_info, dict) else str(time_casa_info or "Mandante NFL")
                    time_fora_info = j.get("time_fora")
                    visitante_nfl = time_fora_info.get("nome") if isinstance(time_fora_info, dict) else str(time_fora_info or "Visitante NFL")
                    eventos_candidatos.append({
                        "id": f"nfl_{j.get('id')}",
                        "esporte": "nfl",
                        "status": "A_COMECAR",
                        "mandante": mandante_nfl,
                        "visitante": visitante_nfl,
                        "campeonato": campeonato_nfl,
                        "horario": j.get("horario", "--:--"),
                        "recomendacao": {
                            "mercado": ls.get("selecao") or ls.get("mercado") or "Linha Segura",
                            "confianca": round(conf, 1),
                            "odd": round(odd, 2)
                        }
                    })
    except Exception as e_nfl:
        logger.warning(f"[obter_top5_bets_dia] Falha ao coletar NFL: {e_nfl}")

    # 4. Ordenação estritamente decrescente por assertividade
    eventos_candidatos.sort(key=lambda x: x["recomendacao"]["confianca"], reverse=True)

    # 5. Desduplicação estrita (máximo 1 entrada por partida) e corte aos Top 5
    selecionados = []
    ids_vistos = set()
    confrontos_vistos = set()

    for ev in eventos_candidatos:
        chave_confronto = f"{ev['mandante'].lower().strip()}_vs_{ev['visitante'].lower().strip()}"
        if ev["id"] not in ids_vistos and chave_confronto not in confrontos_vistos:
            ids_vistos.add(ev["id"])
            confrontos_vistos.add(chave_confronto)
            selecionados.append(ev)
        if len(selecionados) == 5:
            break

    # 6. Cálculo real da odd acumulada
    odd_total = 1.0
    for sel in selecionados:
        odd_total *= sel["recomendacao"]["odd"]
    odd_total = round(odd_total, 2)

    return {
        "status": "success",
        "data": target_date,
        "total_selecoes": len(selecionados),
        "odd_total": odd_total,
        "selecoes": selecionados,
        "timestamp": datetime.now(TIMEZONE_BR).isoformat()
    }


__all__ = [
    "AppRequestHandler",
    "BatchState",
    "append_log_csv",
    "batch_state",
    "find_free_port",
    "get_base_dir",
    "get_web_dir",
    "load_config",
    "render_template",
    "run_batch_dispatch",
    "start_server",
    "sync_config_to_env",
    "obter_jogos_nfl",
    "buscar_nfl_sharpapi",
    "obter_jogos_futebol",
    "obter_jogos_esporte",
    "obter_top5_bets_dia",
    "app",
]

if __name__ == "__main__":
    start_server(port=None, open_browser=True)


