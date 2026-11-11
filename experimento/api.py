"""
experimento/api.py

API JSON do acompanhamento do experimento (prefixo /api/exp).

Leitura e publica. Escrita exige o cabecalho X-API-Key igual a variavel de
ambiente INGEST_TOKEN (sem ela, a escrita fica desativada, e nao aberta).
"""

import hmac
import os
from functools import wraps

from flask import Blueprint, Response, current_app, g, jsonify, request

from irrigation import weather as weather_api

from . import servico
from .db import GRUPOS, conectar

bp = Blueprint("experimento", __name__, url_prefix="/api/exp")


def db():
    if "exp_db" not in g:
        g.exp_db = conectar(current_app.config.get("DATABASE_PATH"))
    return g.exp_db


@bp.teardown_app_request
def _fechar_db(_exc):
    con = g.pop("exp_db", None)
    if con is not None:
        con.close()


def exige_token(funcao):
    @wraps(funcao)
    def interno(*args, **kwargs):
        esperado = os.environ.get("INGEST_TOKEN", "")
        if not esperado:
            return jsonify({"ok": False, "erro": "Escrita desativada: INGEST_TOKEN não está configurado no servidor"}), 503
        enviado = request.headers.get("X-API-Key", "")
        if not hmac.compare_digest(enviado.encode(), esperado.encode()):
            return jsonify({"ok": False, "erro": "Token inválido ou ausente (cabeçalho X-API-Key)"}), 401
        return funcao(*args, **kwargs)
    return interno


def corpo_json():
    corpo = request.get_json(silent=True)
    if not isinstance(corpo, dict):
        raise ValueError("Envie um corpo JSON (objeto)")
    return corpo


@bp.errorhandler(ValueError)
def _erro_validacao(exc):
    return jsonify({"ok": False, "erro": str(exc)}), 400


def buscar_clima():
    cfg = servico.config_obter(db())
    buscar = current_app.config.get("BUSCAR_CLIMA", weather_api.fetch_today_weather)
    return buscar(cfg["latitude"], cfg["longitude"], cfg["elevation"])


@bp.get("/metricas")
def metricas():
    return jsonify({"ok": True, **servico.metricas(db())})


@bp.get("/config")
def config_ler():
    return jsonify({"ok": True, "config": servico.config_obter(db()), "grupos": GRUPOS})


@bp.put("/config")
@exige_token
def config_gravar():
    return jsonify({"ok": True, "config": servico.config_atualizar(db(), corpo_json())})


@bp.post("/leituras")
@exige_token
def leituras():
    c = corpo_json()
    novo_id = servico.registrar_leitura(db(), c.get("grupo"), c.get("umidade_pct"), c.get("ts"), c.get("origem", "sensor"))
    return jsonify({"ok": True, "id": novo_id}), 201


@bp.post("/decidir")
@exige_token
def decidir():
    c = corpo_json()
    grupos = c.get("grupos") or ([c["grupo"]] if c.get("grupo") else list(servico.ORDEM_GRUPOS))
    for grupo in grupos:
        if grupo not in GRUPOS:
            raise ValueError(f"Grupo desconhecido: {grupo!r}")
    umidades = c.get("umidade") or {}
    try:
        clima = buscar_clima()
    except Exception as exc:  # noqa: BLE001 - resposta amigavel para a UI e para o firmware
        return jsonify({"ok": False, "erro": f"Falha ao consultar previsão do tempo: {exc}"}), 502
    resultados, erros = {}, {}
    for grupo in grupos:
        try:
            resultados[grupo] = servico.decidir(db(), grupo, clima, umidades.get(grupo))
        except ValueError as exc:
            erros[grupo] = str(exc)
    status = 200 if resultados else 400
    return jsonify({"ok": bool(resultados), "clima": clima, "resultados": resultados, "erros": erros}), status


@bp.post("/acionamentos")
@exige_token
def acionamentos():
    c = corpo_json()
    novo_id = servico.registrar_acionamento(db(), c.get("grupo"), c.get("volume_l"), c.get("duracao_min"), c.get("ts"))
    return jsonify({"ok": True, "id": novo_id}), 201


@bp.post("/medicoes")
@exige_token
def medicoes():
    c = corpo_json()
    servico.registrar_medicao(db(), c.get("grupo"), c.get("vaso"), c.get("data"), c.get("altura_cm"),
                              c.get("n_folhas"), c.get("massa_fresca_g"), c.get("massa_seca_g"))
    return jsonify({"ok": True}), 201


@bp.post("/chuva-observada/atualizar")
@exige_token
def chuva_observada():
    buscar = current_app.config.get("BUSCAR_CHUVA", servico.buscar_chuva_openmeteo)
    try:
        n = servico.atualizar_chuva_observada(db(), buscar)
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "erro": f"Falha ao consultar a chuva observada: {exc}"}), 502
    return jsonify({"ok": True, "atualizados": n})


@bp.get("/export/<tabela>.csv")
def exportar(tabela):
    texto = servico.exportar_csv(db(), tabela)
    return Response(texto, mimetype="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{tabela}.csv"'})
