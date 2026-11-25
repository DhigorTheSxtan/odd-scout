from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timezone, timedelta

try:
    from zoneinfo import ZoneInfo
    TIMEZONE_BR = ZoneInfo("America/Sao_Paulo")
except Exception:
    TIMEZONE_BR = timezone(timedelta(hours=-3))


class ApiFutebolAdapter:


    STATUS_MAP = {

        "nao-iniciado": ("NS", "Não Iniciado"),
        "agendada": ("NS", "Não Iniciado"),
        "a-iniciar": ("NS", "Não Iniciado"),
        "programado": ("NS", "Não Iniciado"),


        "em-andamento": ("LIVE", "Ao Vivo"),
        "ao-vivo": ("LIVE", "Ao Vivo"),
        "1-tempo": ("1H", "1º Tempo"),
        "intervalo": ("HT", "Intervalo"),
        "2-tempo": ("2H", "2º Tempo"),
        "prorrogacao": ("ET", "Prorrogação"),
        "penaltis": ("PEN", "Pênaltis"),


        "finalizado": ("FT", "Finalizado"),
        "encerrado": ("FT", "Finalizado"),
        "pos-jogo": ("FT", "Finalizado"),


        "cancelado": ("CANC", "Cancelado"),
        "adiado": ("PST", "Adiado"),
        "suspenso": ("SUSP", "Suspenso"),
        "interrompido": ("INT", "Interrompido")
    }

    @classmethod
    def normalizar_status(cls, status_raw: Optional[str]) -> Tuple[str, str]:

        if not status_raw:
            return ("NS", "Não Iniciado")

        clean = str(status_raw).strip().lower().replace(" ", "-")
        return cls.STATUS_MAP.get(clean, ("NS", status_raw.capitalize()))

    @classmethod
    def formatar_data_hora(cls, data_iso: Optional[str], data_br: Optional[str] = None, hora: Optional[str] = None) -> Tuple[str, str]:

        horario_str = hora.strip() if (hora and isinstance(hora, str)) else "--:--"
        iso_str = ""

        if data_iso and isinstance(data_iso, str):
            try:

                raw = data_iso.strip()
                if len(raw) >= 5 and (raw[-5] in ('+', '-') and raw[-3] != ':'):
                    raw = f"{raw[:-2]}:{raw[-2:]}"
                dt = datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(TIMEZONE_BR)
                iso_str = dt.isoformat()
                horario_str = dt.strftime("%H:%M")
                return (iso_str, horario_str)
            except Exception:
                pass

        if data_br and hora:
            try:
                dt = datetime.strptime(f"{data_br.strip()} {hora.strip()}", "%d/%m/%Y %H:%M").replace(tzinfo=TIMEZONE_BR)
                iso_str = dt.isoformat()
                horario_str = dt.strftime("%H:%M")
                return (iso_str, horario_str)
            except Exception:
                pass

        return (iso_str or datetime.now(TIMEZONE_BR).isoformat(), horario_str)

    @classmethod
    def normalizar_estatisticas(cls, stats_raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:

        parsed = {
            "corners": {"home": 0, "away": 0},
            "shots_total": {"home": 0, "away": 0},
            "shots_on_target": {"home": 0, "away": 0},
            "throw_ins": {"home": None, "away": None},
            "possession": {"home": "50%", "away": "50%"}
        }

        if not stats_raw or not isinstance(stats_raw, dict):
            return parsed

        mandante_st = stats_raw.get("mandante", {}) or {}
        visitante_st = stats_raw.get("visitante", {}) or {}


        c_home = mandante_st.get("escanteios")
        c_away = visitante_st.get("escanteios")
        if c_home is not None:
            parsed["corners"]["home"] = int(c_home) if str(c_home).isdigit() else 0
        if c_away is not None:
            parsed["corners"]["away"] = int(c_away) if str(c_away).isdigit() else 0


        pos_home = mandante_st.get("posse_de_bola")
        pos_away = visitante_st.get("posse_de_bola")
        if pos_home:
            parsed["possession"]["home"] = str(pos_home).strip()
        if pos_away:
            parsed["possession"]["away"] = str(pos_away).strip()


        fin_home = mandante_st.get("finalizacao", {}) or {}
        fin_away = visitante_st.get("finalizacao", {}) or {}

        if isinstance(fin_home, dict):
            t_h = fin_home.get("total")
            g_h = fin_home.get("no_gol")
            if t_h is not None:
                parsed["shots_total"]["home"] = int(t_h) if str(t_h).isdigit() else 0
            if g_h is not None:
                parsed["shots_on_target"]["home"] = int(g_h) if str(g_h).isdigit() else 0

        if isinstance(fin_away, dict):
            t_a = fin_away.get("total")
            g_a = fin_away.get("no_gol")
            if t_a is not None:
                parsed["shots_total"]["away"] = int(t_a) if str(t_a).isdigit() else 0
            if g_a is not None:
                parsed["shots_on_target"]["away"] = int(g_a) if str(g_a).isdigit() else 0


        lat_home = mandante_st.get("laterais")
        lat_away = visitante_st.get("laterais")
        if lat_home is not None and str(lat_home).isdigit():
            parsed["throw_ins"]["home"] = int(lat_home)
        if lat_away is not None and str(lat_away).isdigit():
            parsed["throw_ins"]["away"] = int(lat_away)

        return parsed

    @classmethod
    def normalizar_time(cls, time_raw: Optional[Dict[str, Any]], lado: str = "time") -> Dict[str, Any]:

        if not time_raw or not isinstance(time_raw, dict):
            return {"id": 0, "nome": f"Time {lado}", "logo": "", "sigla": ""}

        t_id = time_raw.get("time_id") or time_raw.get("id") or 0
        nome = (
            time_raw.get("nome_popular")
            or time_raw.get("nome")
            or time_raw.get("sigla")
            or f"Time {lado}"
        )
        logo = time_raw.get("escudo") or time_raw.get("logo") or ""
        sigla = time_raw.get("sigla") or ""

        return {
            "id": int(t_id) if str(t_id).isdigit() else 0,
            "nome": str(nome).strip(),
            "logo": str(logo).strip(),
            "sigla": str(sigla).strip()
        }

    @classmethod
    def normalizar_campeonato(cls, camp_raw: Optional[Dict[str, Any]], rodada_str: Optional[str] = None) -> Dict[str, Any]:

        if not camp_raw or not isinstance(camp_raw, dict):
            return {
                "id": 10,
                "nome": "Brasileirão",
                "pais": "Brasil",
                "logo": "",
                "rodada": rodada_str or "Rodada Atual"
            }

        c_id = camp_raw.get("campeonato_id") or camp_raw.get("id") or 10
        nome = camp_raw.get("nome_popular") or camp_raw.get("nome") or "Campeonato Brasileiro"
        logo = camp_raw.get("logo") or "https://cdn.api-futebol.com.br/campeonatos/logos/campeonato-brasileiro-serie-a-2024.png"

        return {
            "id": int(c_id) if str(c_id).isdigit() else 10,
            "nome": str(nome).strip(),
            "pais": "Brasil",
            "logo": str(logo).strip(),
            "rodada": rodada_str or camp_raw.get("rodada_atual", {}).get("nome") if isinstance(camp_raw.get("rodada_atual"), dict) else (rodada_str or "Rodada Atual")
        }

    @classmethod
    def adaptar_partida(cls, partida_raw: Dict[str, Any]) -> Dict[str, Any]:

        partida_id = partida_raw.get("partida_id") or partida_raw.get("id") or 0
        time_m = cls.normalizar_time(partida_raw.get("time_mandante"), "Mandante")
        time_v = cls.normalizar_time(partida_raw.get("time_visitante"), "Visitante")

        rodada_nome = partida_raw.get("rodada")
        if isinstance(rodada_nome, dict):
            rodada_nome = rodada_nome.get("nome")

        campeonato = cls.normalizar_campeonato(partida_raw.get("campeonato"), rodada_str=str(rodada_nome) if rodada_nome else None)

        status_short, status_desc = cls.normalizar_status(partida_raw.get("status"))

        data_iso = partida_raw.get("data_realizacao_iso")
        data_br = partida_raw.get("data_realizacao")
        hora = partida_raw.get("hora_realizacao")
        data_hora_iso, horario_formatado = cls.formatar_data_hora(data_iso, data_br, hora)


        estadio_obj = partida_raw.get("estadio")
        estadio_nome = "Estádio"
        cidade_nome = ""
        if isinstance(estadio_obj, dict):
            estadio_nome = estadio_obj.get("nome_popular") or estadio_obj.get("nome") or "Estádio"
            cidade_nome = estadio_obj.get("cidade", "")
        elif isinstance(estadio_obj, str):
            estadio_nome = estadio_obj


        p_m = partida_raw.get("placar_mandante")
        p_v = partida_raw.get("placar_visitante")


        estatisticas_norm = cls.normalizar_estatisticas(partida_raw.get("estatisticas"))

        return {
            "id": int(partida_id) if str(partida_id).isdigit() else 0,
            "mandante": time_m,
            "visitante": time_v,
            "campeonato": campeonato,
            "horario": horario_formatado,
            "data_hora": data_hora_iso,
            "status": status_short,
            "status_descricao": status_desc,
            "estadio": estadio_nome,
            "cidade": cidade_nome,
            "placar": {
                "mandante": int(p_m) if p_m is not None and str(p_m).isdigit() else None,
                "visitante": int(p_v) if p_v is not None and str(p_v).isdigit() else None
            },
            "estatisticas": estatisticas_norm,
            "provedor": "api_futebol",
            "raw_data": partida_raw
        }

    @classmethod
    def adaptar_historico_time(cls, partidas_anteriores: List[Dict[str, Any]], team_id: int) -> List[Dict[str, Any]]:

        jogos_adaptados = []
        for p in partidas_anteriores:
            if not isinstance(p, dict):
                continue

            time_m = p.get("time_mandante") or {}
            time_v = p.get("time_visitante") or {}

            m_id = time_m.get("time_id") or time_m.get("id") or 0
            v_id = time_v.get("time_id") or time_v.get("id") or 0

            p_m = p.get("placar_mandante")
            p_v = p.get("placar_visitante")

            goals_h = int(p_m) if (p_m is not None and str(p_m).isdigit()) else 0
            goals_a = int(p_v) if (p_v is not None and str(p_v).isdigit()) else 0

            stats_norm = cls.normalizar_estatisticas(p.get("estatisticas"))

            jogos_adaptados.append({
                "fixture": {
                    "id": p.get("partida_id") or p.get("id") or 0,
                    "date": p.get("data_realizacao_iso") or ""
                },
                "teams": {
                    "home": {"id": int(m_id) if str(m_id).isdigit() else 0, "name": time_m.get("nome_popular", "Mandante")},
                    "away": {"id": int(v_id) if str(v_id).isdigit() else 0, "name": time_v.get("nome_popular", "Visitante")}
                },
                "goals": {
                    "home": goals_h,
                    "away": goals_a
                },
                "stats": stats_norm
            })

        return jogos_adaptados
