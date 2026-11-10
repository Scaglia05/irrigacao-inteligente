"""
irrigation/decision.py

Logica de decisao de irrigacao para os tres grupos experimentais do
TCC, cada um representando um "aspersor" configurado com uma
estrategia diferente:

  - Controle A: irrigacao por tempo fixo (metodo tradicional)
  - Controle B: irrigacao por limiar simples de umidade do solo
  - Experimental: sistema completo (umidade + ETc + previsao climatica)

Cada estrategia retorna um resultado no mesmo formato, para que a
interface possa comparar os tres lado a lado.
"""

from .eto import calculate_eto, WeatherDay, KC_RABANETE

# Limiar de umidade do solo abaixo do qual a irrigacao e necessaria
# (Grupo Controle B), em % de capacidade de campo.
UMIDADE_LIMIAR = 35.0

# Lamina fixa por acionamento (mm) dos Grupos Controle A e B, configuravel na UI.
# Valor padrao = ETc media diaria do rabanete (Kc medio 0,90) em Araras-SP entre
# 01/02 e 30/04/2026 (3,64 mm/dia), calculada com a serie da Open-Meteo por
# analise/validacao_eto_e_linha_base.py. E uma linha de base conservadora: o
# tempo fixo repoe, em media, o que a planta consome. Um valor muito acima da
# demanda faria a "economia" do sistema experimental ser artefato do controle.
LAMINA_FIXA_PADRAO_MM = 3.6

# Probabilidade de chuva (%) acima da qual o sistema Experimental
# cancela a irrigacao programada.
LIMIAR_PROBABILIDADE_CHUVA = 60.0


def _litros_por_minuto(vazao_l_h: float) -> float:
    return vazao_l_h / 60.0


def calcular_volume_e_duracao(etc_mm: float, area_m2: float, vazao_l_h: float) -> dict:
    """Converte a necessidade hidrica (ETc, em mm) em volume de agua
    (litros) e tempo de irrigacao (minutos), dada a area da cultura e
    a vazao do aspersor/gotejador.

    1 mm de lamina de agua sobre 1 m2 equivale a 1 litro de agua,
    portanto: volume (L) = ETc (mm) x area (m2).
    """
    volume_l = etc_mm * area_m2
    vazao_l_min = _litros_por_minuto(vazao_l_h)
    duracao_min = volume_l / vazao_l_min if vazao_l_min > 0 else 0.0
    return {
        "volume_l": round(volume_l, 2),
        "duracao_min": round(duracao_min, 1),
        "vazao_l_min": round(vazao_l_min, 3),
    }


def decidir_controle_a(area_m2: float, vazao_l_h: float, lamina_fixa_mm: float) -> dict:
    """Controle A: irrigacao programada (lamina fixa por dia), sem considerar clima ou solo."""
    calc = calcular_volume_e_duracao(lamina_fixa_mm, area_m2, vazao_l_h)
    return {
        "grupo": "Controle A",
        "estrategia": "Tempo fixo",
        "irrigar": True,
        "motivo": (f"Acionamento programado de {lamina_fixa_mm:.1f} mm ({calc['duracao_min']:.1f} min), "
                   "independente do clima ou da umidade do solo."),
        "duracao_min": calc["duracao_min"],
        "volume_l": calc["volume_l"],
        "usa_clima": False,
        "usa_umidade": False,
        "usa_etc": False,
    }


def decidir_controle_b(umidade_solo: float, area_m2: float, vazao_l_h: float,
                        lamina_fixa_mm: float) -> dict:
    """Controle B: irrigacao por limiar simples de umidade do solo (mesma lamina do Controle A)."""
    irrigar = umidade_solo < UMIDADE_LIMIAR
    calc = calcular_volume_e_duracao(lamina_fixa_mm if irrigar else 0.0, area_m2, vazao_l_h)
    duracao = calc["duracao_min"]
    volume_l = calc["volume_l"]

    if irrigar:
        motivo = f"Umidade do solo ({umidade_solo:.0f}%) abaixo do limiar de {UMIDADE_LIMIAR:.0f}%."
    else:
        motivo = f"Umidade do solo ({umidade_solo:.0f}%) acima do limiar de {UMIDADE_LIMIAR:.0f}% — irrigação não acionada."

    return {
        "grupo": "Controle B",
        "estrategia": "Limiar de umidade",
        "irrigar": irrigar,
        "motivo": motivo,
        "duracao_min": round(duracao, 1),
        "volume_l": round(volume_l, 2),
        "usa_clima": False,
        "usa_umidade": True,
        "usa_etc": False,
    }


def decidir_experimental(umidade_solo: float, weather: dict, fase_cultura: str,
                          area_m2: float, vazao_l_h: float) -> dict:
    """Grupo Experimental: sistema completo proposto no TCC.

    Combina umidade do solo, calculo de evapotranspiracao da cultura
    (ETc = ETo x Kc, metodo Penman-Monteith FAO-56) e previsao
    climatica para decidir se e quanto irrigar.
    """
    w = WeatherDay(
        t_max=weather["t_max"],
        t_min=weather["t_min"],
        rh_mean=weather["rh_mean"],
        wind_speed_10m=weather["wind_speed_10m"],
        solar_radiation=weather["solar_radiation"],
        elevation=weather["elevation"],
        latitude=weather["latitude"],
        day_of_year=weather["day_of_year"],
        precipitation=weather.get("precipitation", 0.0),
        precipitation_prob_24h=weather.get("precipitation_prob_24h", 0.0),
    )
    eto_result = calculate_eto(w)
    eto = eto_result["eto_mm_dia"]
    kc = KC_RABANETE[fase_cultura]
    etc = round(eto * kc, 3)

    calc = calcular_volume_e_duracao(etc, area_m2, vazao_l_h)

    vai_chover = w.precipitation_prob_24h >= LIMIAR_PROBABILIDADE_CHUVA
    solo_ja_umido = umidade_solo >= UMIDADE_LIMIAR + 15  # margem de seguranca maior

    if vai_chover:
        irrigar = False
        motivo = (f"Previsão de chuva de {w.precipitation_prob_24h:.0f}% nas próximas 24h "
                  f"(acima do limiar de {LIMIAR_PROBABILIDADE_CHUVA:.0f}%) — irrigação suspensa.")
        duracao, volume = 0.0, 0.0
    elif solo_ja_umido:
        irrigar = False
        motivo = f"Umidade do solo já elevada ({umidade_solo:.0f}%) — irrigação não é necessária hoje."
        duracao, volume = 0.0, 0.0
    else:
        irrigar = True
        motivo = (f"ETc calculada em {etc:.2f} mm/dia (ETo {eto:.2f} × Kc {kc:.2f}); "
                  f"solo em {umidade_solo:.0f}% e sem previsão relevante de chuva.")
        duracao, volume = calc["duracao_min"], calc["volume_l"]

    return {
        "grupo": "Experimental",
        "estrategia": "Sistema completo (ETc + clima + solo)",
        "irrigar": irrigar,
        "motivo": motivo,
        "duracao_min": round(duracao, 1),
        "volume_l": round(volume, 2),
        "usa_clima": True,
        "usa_umidade": True,
        "usa_etc": True,
        "eto_mm_dia": eto,
        "kc": kc,
        "etc_mm_dia": etc,
        "eto_detalhes": eto_result,
        "precipitacao_prob_24h": w.precipitation_prob_24h,
        "vazao_l_min": calc["vazao_l_min"],
    }
