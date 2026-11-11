"""
experimento/servico.py

Regras de negocio do acompanhamento do experimento: registro de leituras,
decisoes, acionamentos e medicoes, e calculo das metricas do artigo
(volume por grupo, umidade, saude da planta, acionamentos evitados,
precisao da previsao e EUA).
"""

import csv
import io
import math
from datetime import date, datetime, timezone

import requests

from irrigation.decision import (
    LIMIAR_PROBABILIDADE_CHUVA,
    decidir_controle_a,
    decidir_controle_b,
    decidir_experimental,
)
from irrigation.eto import KC_RABANETE

from .db import GRUPOS

ORDEM_GRUPOS = ("controle_a", "controle_b", "experimental")

CONFIG_NUMERICA = {
    "latitude": (-90, 90),
    "longitude": (-180, 180),
    "elevation": (-500, 9000),
    "area_m2": (0.0001, 1000),
    "vazao_l_h": (0.01, 100000),
    "lamina_fixa_mm": (0.1, 100),
    "chuva_observada_limiar_mm": (0, 100),
}

TABELAS_CSV = {
    "decisoes": ("decisao", "data, grupo"),
    "leituras": ("leitura_solo", "ts, grupo"),
    "acionamentos": ("acionamento", "ts, grupo"),
    "clima": ("clima_dia", "data"),
    "medicoes": ("medicao_planta", "data, grupo, vaso"),
}


# ---------------------------------------------------------------- validacao
def agora_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _numero(valor, nome, minimo=None, maximo=None, obrigatorio=True):
    if valor is None or valor == "":
        if obrigatorio:
            raise ValueError(f"Campo obrigatório: {nome}")
        return None
    try:
        v = float(valor)
    except (TypeError, ValueError):
        raise ValueError(f"{nome} deve ser numérico") from None
    if not math.isfinite(v):
        raise ValueError(f"{nome} deve ser um número finito")
    if minimo is not None and v < minimo:
        raise ValueError(f"{nome} deve ser maior ou igual a {minimo}")
    if maximo is not None and v > maximo:
        raise ValueError(f"{nome} deve ser menor ou igual a {maximo}")
    return v


def _inteiro(valor, nome, minimo=None, maximo=None, obrigatorio=True):
    v = _numero(valor, nome, minimo, maximo, obrigatorio)
    if v is None:
        return None
    if v != int(v):
        raise ValueError(f"{nome} deve ser inteiro")
    return int(v)


def _grupo(grupo):
    if grupo not in GRUPOS:
        raise ValueError(f"Grupo desconhecido: {grupo!r}. Use: {', '.join(GRUPOS)}")
    return grupo


def _ts(ts):
    if ts in (None, ""):
        return agora_iso()
    try:
        d = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("ts deve estar em formato ISO 8601 (ex.: 2026-11-10T14:30:00Z)") from None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _data(data):
    try:
        return date.fromisoformat(str(data)).isoformat()
    except ValueError:
        raise ValueError("data deve estar no formato AAAA-MM-DD") from None


# ------------------------------------------------------------------- config
def config_obter(con):
    cfg = {}
    for linha in con.execute("SELECT chave, valor FROM config"):
        chave, valor = linha["chave"], linha["valor"]
        cfg[chave] = valor if chave == "fase_cultura" else float(valor)
    return cfg


def config_atualizar(con, valores):
    if not isinstance(valores, dict) or not valores:
        raise ValueError("Informe ao menos um parâmetro de configuração")
    for chave, valor in valores.items():
        if chave == "fase_cultura":
            if valor not in KC_RABANETE:
                raise ValueError(f"fase_cultura deve ser uma de: {', '.join(KC_RABANETE)}")
            novo = valor
        elif chave in CONFIG_NUMERICA:
            minimo, maximo = CONFIG_NUMERICA[chave]
            novo = str(_numero(valor, chave, minimo, maximo))
        else:
            raise ValueError(f"Parâmetro desconhecido: {chave}")
        con.execute("UPDATE config SET valor = ? WHERE chave = ?", (novo, chave))
    con.commit()
    return config_obter(con)


# ------------------------------------------------------------------ escrita
def registrar_leitura(con, grupo, umidade_pct, ts=None, origem="sensor"):
    _grupo(grupo)
    umidade = _numero(umidade_pct, "umidade_pct", 0, 100)
    if origem not in ("sensor", "manual"):
        raise ValueError("origem deve ser 'sensor' ou 'manual'")
    cur = con.execute(
        "INSERT INTO leitura_solo (grupo, ts, umidade_pct, origem) VALUES (?, ?, ?, ?)",
        (grupo, _ts(ts), umidade, origem),
    )
    con.commit()
    return cur.lastrowid


def ultima_umidade(con, grupo):
    linha = con.execute(
        "SELECT umidade_pct FROM leitura_solo WHERE grupo = ? ORDER BY ts DESC, id DESC LIMIT 1", (grupo,)
    ).fetchone()
    return linha["umidade_pct"] if linha else None


def decidir(con, grupo, clima, umidade_pct=None):
    """Calcula e registra a decisao do dia para um grupo (uma por grupo e data)."""
    _grupo(grupo)
    cfg = config_obter(con)
    area, vazao, lamina = cfg["area_m2"], cfg["vazao_l_h"], cfg["lamina_fixa_mm"]

    umidade = None
    if grupo == "controle_a":
        resultado = decidir_controle_a(area, vazao, lamina)
    else:
        umidade = _numero(umidade_pct, "umidade", 0, 100, obrigatorio=False)
        if umidade is None:
            umidade = ultima_umidade(con, grupo)
        if umidade is None:
            raise ValueError(f"Sem leitura de umidade do solo para {grupo}: registre uma leitura antes de decidir")
        if grupo == "controle_b":
            resultado = decidir_controle_b(umidade, area, vazao, lamina)
        else:
            resultado = decidir_experimental(umidade, clima, cfg["fase_cultura"], area, vazao)

    data = clima["date"]
    prob = clima.get("precipitation_prob_24h")
    con.execute(
        """INSERT INTO decisao (grupo, data, ts, irrigar, codigo, motivo, volume_l, duracao_min,
                                umidade_solo, eto_mm_dia, etc_mm_dia, prob_chuva)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT (grupo, data) DO UPDATE SET
               ts = excluded.ts, irrigar = excluded.irrigar, codigo = excluded.codigo,
               motivo = excluded.motivo, volume_l = excluded.volume_l, duracao_min = excluded.duracao_min,
               umidade_solo = excluded.umidade_solo, eto_mm_dia = excluded.eto_mm_dia,
               etc_mm_dia = excluded.etc_mm_dia, prob_chuva = excluded.prob_chuva""",
        (grupo, data, agora_iso(), int(resultado["irrigar"]), resultado["codigo"], resultado["motivo"],
         resultado["volume_l"], resultado["duracao_min"], umidade, resultado.get("eto_mm_dia"),
         resultado.get("etc_mm_dia"), prob),
    )
    con.execute(
        """INSERT INTO clima_dia (data, prob_chuva_prevista) VALUES (?, ?)
           ON CONFLICT (data) DO UPDATE SET prob_chuva_prevista = excluded.prob_chuva_prevista""",
        (data, prob),
    )
    con.commit()
    resultado["data"] = data
    resultado["grupo_codigo"] = grupo
    resultado["umidade_usada"] = umidade
    return resultado


def registrar_acionamento(con, grupo, volume_l, duracao_min=None, ts=None):
    _grupo(grupo)
    cur = con.execute(
        "INSERT INTO acionamento (grupo, ts, volume_l, duracao_min) VALUES (?, ?, ?, ?)",
        (grupo, _ts(ts), _numero(volume_l, "volume_l", 0), _numero(duracao_min, "duracao_min", 0, obrigatorio=False)),
    )
    con.commit()
    return cur.lastrowid


def registrar_medicao(con, grupo, vaso, data, altura_cm=None, n_folhas=None, massa_fresca_g=None, massa_seca_g=None):
    _grupo(grupo)
    n_vasos = con.execute("SELECT n_vasos FROM grupo WHERE codigo = ?", (grupo,)).fetchone()["n_vasos"]
    vaso = _inteiro(vaso, "vaso", 1, n_vasos)
    valores = (
        _numero(altura_cm, "altura_cm", 0, obrigatorio=False),
        _inteiro(n_folhas, "n_folhas", 0, obrigatorio=False),
        _numero(massa_fresca_g, "massa_fresca_g", 0, obrigatorio=False),
        _numero(massa_seca_g, "massa_seca_g", 0, obrigatorio=False),
    )
    if all(v is None for v in valores):
        raise ValueError("Informe ao menos uma medida (altura, folhas, massa fresca ou massa seca)")
    con.execute(
        """INSERT INTO medicao_planta (grupo, vaso, data, altura_cm, n_folhas, massa_fresca_g, massa_seca_g)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT (grupo, vaso, data) DO UPDATE SET
               altura_cm = COALESCE(excluded.altura_cm, altura_cm),
               n_folhas = COALESCE(excluded.n_folhas, n_folhas),
               massa_fresca_g = COALESCE(excluded.massa_fresca_g, massa_fresca_g),
               massa_seca_g = COALESCE(excluded.massa_seca_g, massa_seca_g)""",
        (grupo, vaso, _data(data)) + valores,
    )
    con.commit()


def buscar_chuva_openmeteo(latitude, longitude, inicio, fim):
    """Chuva diaria observada (mm) na API de historico da Open-Meteo: {data: mm ou None}."""
    resp = requests.get(
        "https://archive-api.open-meteo.com/v1/archive",
        params={"latitude": latitude, "longitude": longitude, "start_date": inicio, "end_date": fim,
                "daily": "precipitation_sum", "timezone": "auto"},
        timeout=15,
    )
    resp.raise_for_status()
    daily = resp.json()["daily"]
    return dict(zip(daily["time"], daily["precipitation_sum"]))


def atualizar_chuva_observada(con, buscar=buscar_chuva_openmeteo, hoje=None):
    """Preenche a chuva observada dos dias anteriores a hoje que ainda nao a tem."""
    hoje = (hoje or date.today()).isoformat()
    pendentes = [r["data"] for r in con.execute(
        "SELECT data FROM clima_dia WHERE chuva_observada_mm IS NULL AND data < ? ORDER BY data", (hoje,))]
    if not pendentes:
        return 0
    cfg = config_obter(con)
    dados = buscar(cfg["latitude"], cfg["longitude"], pendentes[0], pendentes[-1])
    atualizados = 0
    for d in pendentes:
        mm = dados.get(d)
        if mm is not None:
            con.execute("UPDATE clima_dia SET chuva_observada_mm = ?, fonte_observada = 'open-meteo-archive' WHERE data = ?", (mm, d))
            atualizados += 1
    con.commit()
    return atualizados


# ------------------------------------------------------------------ metricas
def _previsao(con, cfg):
    lim_obs = cfg["chuva_observada_limiar_mm"]
    linhas = con.execute(
        "SELECT prob_chuva_prevista p, chuva_observada_mm o FROM clima_dia "
        "WHERE prob_chuva_prevista IS NOT NULL AND chuva_observada_mm IS NOT NULL").fetchall()
    acertos = falsos = perdidos = 0
    for r in linhas:
        previsto, observado = r["p"] >= LIMIAR_PROBABILIDADE_CHUVA, r["o"] >= lim_obs
        if previsto == observado:
            acertos += 1
        elif previsto:
            falsos += 1
        else:
            perdidos += 1
    n = len(linhas)
    return {
        "n_dias": n, "acertos": acertos, "falsos_alarmes": falsos, "chuvas_nao_previstas": perdidos,
        "acuracia": (acertos / n) if n else None,
        "limiar_previsao_pct": LIMIAR_PROBABILIDADE_CHUVA, "limiar_observado_mm": lim_obs,
    }


def _saude(con, grupo):
    """Ultima medicao de cada vaso do grupo."""
    return con.execute(
        """SELECT m.* FROM medicao_planta m
           JOIN (SELECT vaso, MAX(data) d FROM medicao_planta WHERE grupo = ? GROUP BY vaso) u
             ON u.vaso = m.vaso AND u.d = m.data
           WHERE m.grupo = ? ORDER BY m.vaso""", (grupo, grupo)).fetchall()


def _media(valores):
    valores = [v for v in valores if v is not None]
    return (sum(valores) / len(valores)) if valores else None


def _serie_volume(con, grupo):
    por_dia = {}
    for r in con.execute("SELECT data, volume_l FROM decisao WHERE grupo = ? ORDER BY data", (grupo,)):
        por_dia.setdefault(r["data"], {"planejado_l": 0.0, "aplicado_l": 0.0})["planejado_l"] += r["volume_l"]
    for r in con.execute("SELECT substr(ts, 1, 10) d, SUM(volume_l) v FROM acionamento WHERE grupo = ? GROUP BY d", (grupo,)):
        por_dia.setdefault(r["d"], {"planejado_l": 0.0, "aplicado_l": 0.0})["aplicado_l"] += r["v"]
    serie, acum_p, acum_a = [], 0.0, 0.0
    for d in sorted(por_dia):
        acum_p += por_dia[d]["planejado_l"]
        acum_a += por_dia[d]["aplicado_l"]
        serie.append({"data": d, "planejado_l": round(por_dia[d]["planejado_l"], 3),
                      "aplicado_l": round(por_dia[d]["aplicado_l"], 3),
                      "acum_planejado_l": round(acum_p, 3), "acum_aplicado_l": round(acum_a, 3)})
    return serie


def metricas(con):
    cfg = config_obter(con)
    grupos = []
    for cod in ORDEM_GRUPOS:
        g = con.execute("SELECT codigo, nome, n_vasos FROM grupo WHERE codigo = ?", (cod,)).fetchone()
        dec = con.execute(
            "SELECT COUNT(*) n, COALESCE(SUM(irrigar), 0) irrigou, COALESCE(SUM(volume_l), 0) vol, "
            "COALESCE(SUM(codigo = 'chuva_prevista'), 0) evitados FROM decisao WHERE grupo = ?", (cod,)).fetchone()
        aci = con.execute("SELECT COUNT(*) n, COALESCE(SUM(volume_l), 0) vol FROM acionamento WHERE grupo = ?", (cod,)).fetchone()
        sol = con.execute(
            "SELECT COUNT(*) n, AVG(umidade_pct) media, MIN(umidade_pct) minimo, MAX(umidade_pct) maximo "
            "FROM leitura_solo WHERE grupo = ?", (cod,)).fetchone()
        medidas = _saude(con, cod)
        usa_aplicado = aci["n"] > 0
        volume_base = aci["vol"] if usa_aplicado else dec["vol"]
        massa_vaso = _media([m["massa_fresca_g"] for m in medidas])
        eua = None
        if massa_vaso is not None and volume_base > 0:
            eua = massa_vaso / (volume_base / g["n_vasos"])
        serie_solo = [{"ts": r["ts"], "umidade_pct": r["umidade_pct"]} for r in con.execute(
            "SELECT ts, umidade_pct FROM (SELECT ts, umidade_pct, id FROM leitura_solo WHERE grupo = ? "
            "ORDER BY ts DESC, id DESC LIMIT 500) ORDER BY ts, id", (cod,))]
        grupos.append({
            "codigo": cod, "nome": g["nome"], "n_vasos": g["n_vasos"],
            "n_decisoes": dec["n"], "n_dias_irrigou": dec["irrigou"],
            "acionamentos_evitados_por_chuva": dec["evitados"],
            "volume_planejado_l": round(dec["vol"], 3),
            "volume_aplicado_l": round(aci["vol"], 3) if usa_aplicado else None,
            "n_acionamentos_registrados": aci["n"],
            "volume_base": "aplicado" if usa_aplicado else "planejado",
            "umidade": {"n_leituras": sol["n"], "media": sol["media"], "minimo": sol["minimo"], "maximo": sol["maximo"]},
            "saude": {
                "n_vasos_medidos": len(medidas),
                "altura_cm_media": _media([m["altura_cm"] for m in medidas]),
                "n_folhas_media": _media([m["n_folhas"] for m in medidas]),
                "massa_fresca_g_media": massa_vaso,
                "massa_seca_g_media": _media([m["massa_seca_g"] for m in medidas]),
            },
            "eua_g_l": eua,
            "serie_volume": _serie_volume(con, cod),
            "serie_umidade": serie_solo,
        })
    recentes = [dict(r) for r in con.execute(
        "SELECT grupo, data, irrigar, codigo, motivo, volume_l, duracao_min, umidade_solo, etc_mm_dia, prob_chuva "
        "FROM decisao ORDER BY data DESC, id DESC LIMIT 20")]
    return {"config": cfg, "grupos": grupos, "previsao": _previsao(con, cfg), "decisoes_recentes": recentes}


# ---------------------------------------------------------------------- csv
def exportar_csv(con, tabela):
    if tabela not in TABELAS_CSV:
        raise ValueError(f"Tabela desconhecida: {tabela!r}. Use: {', '.join(TABELAS_CSV)}")
    nome, ordem = TABELAS_CSV[tabela]
    cur = con.execute(f"SELECT * FROM {nome} ORDER BY {ordem}")  # nome e ordem vêm da lista fixa acima
    saida = io.StringIO()
    escritor = csv.writer(saida)
    escritor.writerow([c[0] for c in cur.description])
    escritor.writerows(cur.fetchall())
    return saida.getvalue()
