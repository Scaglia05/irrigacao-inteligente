"""
app.py

Servidor web do protótipo do Sistema de Irrigação Inteligente (TCC).

Expõe:
  GET  /                    -> painel (dashboard) principal
  GET  /api/localizacao     -> geocodifica uma cidade (nome -> lat/lon)
  POST /api/calcular        -> calcula a decisão de irrigação para o
                                aspersor/grupo selecionado
  GET  /experimento         -> acompanhamento do experimento (3 grupos)
  /api/exp/...              -> leituras, decisões, medições e métricas
                                (ver experimento/api.py)

Autor: Guilherme Augusto Scaglia — Engenharia de Computação (FHO)
Orientador: Prof. Pedro Luís Antonelli
"""

import os
from flask import Flask, jsonify, render_template, request

from experimento.api import bp as experimento_bp
from irrigation import weather as weather_api
from irrigation.decision import (
    decidir_controle_a,
    decidir_controle_b,
    decidir_experimental,
    LAMINA_FIXA_PADRAO_MM,
)

app = Flask(__name__)
app.register_blueprint(experimento_bp)

# Cidade padrão usada quando o usuário ainda não digitou nada
CIDADE_PADRAO = "Araras, SP"


@app.route("/")
def index():
    return render_template("index.html", cidade_padrao=CIDADE_PADRAO)


@app.route("/apresentacao")
def apresentacao():
    return render_template("apresentacao.html")


@app.route("/experimento")
def experimento():
    return render_template("experimento.html")


@app.route("/api/localizacao")
def api_localizacao():
    cidade = request.args.get("cidade", CIDADE_PADRAO)
    try:
        local = weather_api.geocode_city(cidade)
        return jsonify({"ok": True, "local": local})
    except Exception as exc:  # noqa: BLE001 - resposta amigável para a UI
        return jsonify({"ok": False, "erro": str(exc)}), 400


@app.route("/api/calcular", methods=["POST"])
def api_calcular():
    payload = request.get_json(force=True) or {}

    grupo = payload.get("grupo", "experimental")
    latitude = float(payload.get("latitude", -22.3572))
    longitude = float(payload.get("longitude", -47.3823))
    elevation = float(payload.get("elevation", 630))
    area_m2 = float(payload.get("area_m2", 1.0))
    vazao_l_h = float(payload.get("vazao_l_h", 120))
    umidade_solo = float(payload.get("umidade_solo", 40))
    fase_cultura = payload.get("fase_cultura", "medio")
    lamina_fixa_mm = float(payload.get("lamina_fixa_mm", LAMINA_FIXA_PADRAO_MM))

    try:
        clima = weather_api.fetch_today_weather(latitude, longitude, elevation)
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "erro": f"Falha ao consultar previsão do tempo: {exc}"}), 502

    if grupo == "controle_a":
        resultado = decidir_controle_a(area_m2, vazao_l_h, lamina_fixa_mm)
    elif grupo == "controle_b":
        resultado = decidir_controle_b(umidade_solo, area_m2, vazao_l_h, lamina_fixa_mm)
    elif grupo == "experimental":
        resultado = decidir_experimental(umidade_solo, clima, fase_cultura, area_m2, vazao_l_h)
    else:
        return jsonify({"ok": False, "erro": f"Grupo desconhecido: {grupo}"}), 400

    return jsonify({"ok": True, "clima": clima, "resultado": resultado})


@app.route("/api/comparar", methods=["POST"])
def api_comparar():
    """Calcula os três grupos de uma só vez, para a visão comparativa."""
    payload = request.get_json(force=True) or {}

    latitude = float(payload.get("latitude", -22.3572))
    longitude = float(payload.get("longitude", -47.3823))
    elevation = float(payload.get("elevation", 630))
    area_m2 = float(payload.get("area_m2", 1.0))
    vazao_l_h = float(payload.get("vazao_l_h", 120))
    umidade_solo = float(payload.get("umidade_solo", 40))
    fase_cultura = payload.get("fase_cultura", "medio")
    lamina_fixa_mm = float(payload.get("lamina_fixa_mm", LAMINA_FIXA_PADRAO_MM))

    try:
        clima = weather_api.fetch_today_weather(latitude, longitude, elevation)
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "erro": f"Falha ao consultar previsão do tempo: {exc}"}), 502

    resultados = {
        "controle_a": decidir_controle_a(area_m2, vazao_l_h, lamina_fixa_mm),
        "controle_b": decidir_controle_b(umidade_solo, area_m2, vazao_l_h, lamina_fixa_mm),
        "experimental": decidir_experimental(umidade_solo, clima, fase_cultura, area_m2, vazao_l_h),
    }
    return jsonify({"ok": True, "clima": clima, "resultados": resultados})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
