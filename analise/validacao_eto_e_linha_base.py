"""
analise/validacao_eto_e_linha_base.py

Analise reproduzivel para a etapa P2 do TCC (dados reais, sem simulacao de sensores):

  1. Valida a ETo calculada por irrigation/eto.py (Penman-Monteith FAO-56)
     contra a ETo diaria (et0_fao_evapotranspiration) da API Open-Meteo,
     para Araras-SP.
  2. Mostra como a "economia" do grupo Experimental depende da linha de
     base escolhida para o Controle A (lamina fixa diaria).

Uso:
    python analise/validacao_eto_e_linha_base.py [AAAA-MM-DD inicio] [AAAA-MM-DD fim] [saida.csv]

Padrao: 2026-02-01 a 2026-04-30 (mesma epoca do experimento previsto, um ano antes).
Requer acesso a internet (archive-api.open-meteo.com) e apenas a biblioteca padrao.
"""

import csv
import json
import math
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from irrigation.eto import calculate_eto, WeatherDay, KC_RABANETE  # noqa: E402

LAT, LON, ELEV = -22.3572, -47.3823, 630.0  # Araras-SP (mesmos valores padrao do app)
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
CHUVA_PREVISTA_MM = 1.0  # proxy de "previsao de chuva": chuva observada >= 1 mm no dia
KC = KC_RABANETE["medio"]


def buscar(inicio, fim):
    params = {
        "latitude": LAT, "longitude": LON, "start_date": inicio, "end_date": fim,
        "daily": ",".join([
            "temperature_2m_max", "temperature_2m_min", "relative_humidity_2m_mean",
            "wind_speed_10m_max", "shortwave_radiation_sum", "precipitation_sum",
            "et0_fao_evapotranspiration",
        ]),
        "hourly": "wind_speed_10m",
        "wind_speed_unit": "kmh", "timezone": "auto",
    }
    url = ARCHIVE_URL + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.load(r)


def pearson(x, y):
    n = len(x)
    mx, my = sum(x) / n, sum(y) / n
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y))
    sxx = sum((a - mx) ** 2 for a in x)
    syy = sum((b - my) ** 2 for b in y)
    return sxy / math.sqrt(sxx * syy)


def percentil(valores, p):
    v = sorted(valores)
    k = (len(v) - 1) * p
    f, c = math.floor(k), math.ceil(k)
    return v[f] if f == c else v[f] + (v[c] - v[f]) * (k - f)


def eto_dia(d, i, vento_ms):
    w = WeatherDay(
        t_max=d["temperature_2m_max"][i], t_min=d["temperature_2m_min"][i],
        rh_mean=d["relative_humidity_2m_mean"][i], wind_speed_10m=vento_ms,
        solar_radiation=d["shortwave_radiation_sum"][i], elevation=ELEV, latitude=LAT,
        day_of_year=datetime.strptime(d["time"][i], "%Y-%m-%d").timetuple().tm_yday,
    )
    return calculate_eto(w)["eto_mm_dia"]


def metricas(nome, a, b):
    n = len(a)
    dif = [x - y for x, y in zip(a, b)]
    vies = sum(dif) / n
    mae = sum(abs(x) for x in dif) / n
    rmse = math.sqrt(sum(x * x for x in dif) / n)
    print(f"{nome:<34} vies={vies:+.3f}  MAE={mae:.3f}  RMSE={rmse:.3f}  r={pearson(a, b):.3f}  (mm/dia)")


def main():
    inicio = sys.argv[1] if len(sys.argv) > 1 else "2026-02-01"
    fim = sys.argv[2] if len(sys.argv) > 2 else "2026-04-30"
    saida = sys.argv[3] if len(sys.argv) > 3 else None

    dados = buscar(inicio, fim)
    d = dados["daily"]
    horas = dados["hourly"]
    vento_h = {}
    for t, v in zip(horas["time"], horas["wind_speed_10m"]):
        if v is not None:
            vento_h.setdefault(t[:10], []).append(v)

    dias = []
    for i, dia in enumerate(d["time"]):
        campos = [d[k][i] for k in ("temperature_2m_max", "temperature_2m_min", "relative_humidity_2m_mean",
                                    "wind_speed_10m_max", "shortwave_radiation_sum",
                                    "precipitation_sum", "et0_fao_evapotranspiration")]
        if any(c is None for c in campos) or dia not in vento_h:
            continue
        vento_med = sum(vento_h[dia]) / len(vento_h[dia])
        dias.append({
            "data": dia,
            "eto_app_vento_max": eto_dia(d, i, d["wind_speed_10m_max"][i] / 3.6),
            "eto_app_vento_medio": eto_dia(d, i, vento_med / 3.6),
            "eto_openmeteo": d["et0_fao_evapotranspiration"][i],
            "chuva_mm": d["precipitation_sum"][i],
        })

    n = len(dias)
    print(f"Periodo {inicio} a {fim}: {n} dias validos | Araras-SP ({LAT}, {LON}) | Kc = {KC}")
    om = [x["eto_openmeteo"] for x in dias]
    app_max = [x["eto_app_vento_max"] for x in dias]
    app_med = [x["eto_app_vento_medio"] for x in dias]

    print("\n== 1. ETo do app x ETo Open-Meteo (et0_fao_evapotranspiration) ==")
    print(f"Media Open-Meteo: {sum(om)/n:.3f} mm/dia | app (vento max, como em weather.py): {sum(app_max)/n:.3f} | app (vento medio horario): {sum(app_med)/n:.3f}")
    metricas("app com vento MAXIMO diario", app_max, om)
    metricas("app com vento MEDIO horario", app_med, om)

    print("\n== 2. Linha de base do Controle A (lamina fixa diaria) x Experimental ==")
    etc = [x["eto_app_vento_medio"] * KC for x in dias]
    chuvosos = [x["chuva_mm"] >= CHUVA_PREVISTA_MM for x in dias]
    n_chuva = sum(chuvosos)
    soma_etc = sum(etc)
    soma_exp = sum(e for e, c in zip(etc, chuvosos) if not c)
    print(f"ETc media: {soma_etc/n:.2f} mm/dia | dias com chuva >= {CHUVA_PREVISTA_MM:.0f} mm (proxy de previsao): {n_chuva} de {n}")
    print(f"Experimental sem cancelar por chuva: {soma_etc:.1f} mm no periodo | com cancelamento (previsao perfeita): {soma_exp:.1f} mm")
    print(f"{'Lamina fixa do Controle A':<34}{'mm/dia':>8}{'total (mm)':>12}{'economia do Exp.':>18}")
    for rotulo, lam in (("= ETc media (conservadora)", soma_etc / n),
                        ("= percentil 75 da ETc", percentil(etc, 0.75)),
                        ("= percentil 90 da ETc", percentil(etc, 0.90)),
                        ("= ETc maxima do periodo", max(etc))):
        total_a = lam * n
        print(f"{rotulo:<34}{lam:>8.2f}{total_a:>12.1f}{100 * (1 - soma_exp / total_a):>17.1f}%")
    ref_padrao_antigo = 15 * (120 / 60) / 0.25
    print(f"(Referencia: o padrao antigo do app, 15 min a 120 L/h em 0,25 m2, equivale a {ref_padrao_antigo:.0f} mm por acionamento.)")

    if saida:
        with open(saida, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(dias[0].keys()))
            w.writeheader()
            w.writerows(dias)
        print(f"\nCSV diario salvo em {saida}")


if __name__ == "__main__":
    main()
