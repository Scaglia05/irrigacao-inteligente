"""
irrigation/eto.py

Calculo da Evapotranspiracao de Referencia (ETo) pelo metodo
Penman-Monteith, parametrizado pelo boletim FAO-56.

Referencia: ALLEN, R. G.; PEREIRA, L. S.; RAES, D.; SMITH, M.
Crop evapotranspiration: guidelines for computing crop water
requirements. FAO Irrigation and Drainage Paper 56. Rome: FAO, 1998.

Todas as formulas seguem literalmente o Capitulo 3 do FAO-56, para
que o calculo seja auditavel e explicavel na defesa do TCC.
"""

import math
from dataclasses import dataclass


@dataclass
class WeatherDay:
    """Dados meteorologicos diarios necessarios para o calculo de ETo."""
    t_max: float           # temperatura maxima do ar (C)
    t_min: float           # temperatura minima do ar (C)
    rh_mean: float         # umidade relativa media (%)
    wind_speed_10m: float  # velocidade do vento a 10m (m/s)
    solar_radiation: float  # radiacao solar incidente (MJ/m2/dia)
    elevation: float       # altitude do local (m)
    latitude: float        # latitude do local (graus, negativo = sul)
    day_of_year: int       # dia juliano (1-366)
    precipitation: float = 0.0            # chuva do dia (mm) - informativo
    precipitation_prob_24h: float = 0.0   # probabilidade de chuva nas proximas 24h (%)


def _wind_speed_2m(u10: float) -> float:
    """Converte velocidade do vento medida a 10m para a altura padrao
    de 2m, usando o perfil logaritmico de vento (FAO-56, Eq. 47)."""
    return u10 * (4.87 / math.log(67.8 * 10 - 5.42))


def _saturation_vapor_pressure(t: float) -> float:
    """Pressao de saturacao de vapor (kPa) para uma temperatura (C).
    FAO-56, Eq. 11."""
    return 0.6108 * math.exp((17.27 * t) / (t + 237.3))


def _slope_svp_curve(t_mean: float) -> float:
    """Declividade da curva de pressao de saturacao de vapor (kPa/C),
    calculada na temperatura media. FAO-56, Eq. 13."""
    es = _saturation_vapor_pressure(t_mean)
    return (4098 * es) / ((t_mean + 237.3) ** 2)


def _atmospheric_pressure(elevation: float) -> float:
    """Pressao atmosferica (kPa) em funcao da altitude. FAO-56, Eq. 7."""
    return 101.3 * ((293 - 0.0065 * elevation) / 293) ** 5.26


def _psychrometric_constant(pressure: float) -> float:
    """Constante psicrometrica (kPa/C). FAO-56, Eq. 8."""
    return 0.000665 * pressure


def _extraterrestrial_radiation(latitude_deg: float, day_of_year: int) -> float:
    """Radiacao extraterrestre diaria (Ra, MJ/m2/dia). FAO-56, Eq. 21-25."""
    lat_rad = math.radians(latitude_deg)
    dr = 1 + 0.033 * math.cos((2 * math.pi / 365) * day_of_year)
    delta = 0.409 * math.sin((2 * math.pi / 365) * day_of_year - 1.39)
    ws = math.acos(max(-1.0, min(1.0, -math.tan(lat_rad) * math.tan(delta))))
    gsc = 0.0820  # constante solar, MJ/m2/min
    ra = (24 * 60 / math.pi) * gsc * dr * (
        ws * math.sin(lat_rad) * math.sin(delta)
        + math.cos(lat_rad) * math.cos(delta) * math.sin(ws)
    )
    return ra


def _net_radiation(rs: float, ra: float, t_max: float, t_min: float,
                    ea: float, elevation: float) -> float:
    """Radiacao liquida (Rn, MJ/m2/dia). FAO-56, Eq. 38-40."""
    albedo = 0.23  # albedo de referencia (grama)
    rns = (1 - albedo) * rs  # radiacao de onda curta liquida

    rso = (0.75 + 2e-5 * elevation) * ra  # radiacao de ceu limpo
    rso = max(rso, 0.01)
    rs_rso = min(rs / rso, 1.0) if rso > 0 else 0.0

    sigma = 4.903e-9  # constante de Stefan-Boltzmann (MJ K^-4 m^-2 dia^-1)
    t_max_k = t_max + 273.16
    t_min_k = t_min + 273.16
    rnl = sigma * ((t_max_k ** 4 + t_min_k ** 4) / 2) * \
        (0.34 - 0.14 * math.sqrt(max(ea, 0))) * (1.35 * rs_rso - 0.35)

    return rns - rnl


def calculate_eto(w: WeatherDay) -> dict:
    """Calcula ETo (mm/dia) pelo metodo Penman-Monteith FAO-56.

    Retorna um dicionario com o resultado final e todas as variaveis
    intermediarias, para que a interface possa exibir o passo a passo
    do calculo (transparencia cientifica na apresentacao).
    """
    t_mean = (w.t_max + w.t_min) / 2
    u2 = _wind_speed_2m(w.wind_speed_10m)

    delta = _slope_svp_curve(t_mean)
    p = _atmospheric_pressure(w.elevation)
    gamma = _psychrometric_constant(p)

    es_tmax = _saturation_vapor_pressure(w.t_max)
    es_tmin = _saturation_vapor_pressure(w.t_min)
    es = (es_tmax + es_tmin) / 2
    ea = es * (w.rh_mean / 100)
    vpd = max(es - ea, 0)

    ra = _extraterrestrial_radiation(w.latitude, w.day_of_year)
    rn = _net_radiation(w.solar_radiation, ra, w.t_max, w.t_min, ea, w.elevation)
    g = 0.0  # fluxo de calor no solo, desprezivel em escala diaria (FAO-56)

    numerator = 0.408 * delta * (rn - g) + gamma * (900 / (t_mean + 273)) * u2 * vpd
    denominator = delta + gamma * (1 + 0.34 * u2)
    eto = max(numerator / denominator, 0.0)

    return {
        "eto_mm_dia": round(eto, 3),
        "t_mean": round(t_mean, 2),
        "u2": round(u2, 3),
        "delta": round(delta, 4),
        "gamma": round(gamma, 4),
        "es_kpa": round(es, 4),
        "ea_kpa": round(ea, 4),
        "vpd_kpa": round(vpd, 4),
        "ra_mj": round(ra, 3),
        "rn_mj": round(rn, 3),
        "pressure_kpa": round(p, 2),
    }


# ---------------------------------------------------------------------
# Coeficientes de cultura (Kc) - rabanete (Raphanus sativus)
# Fonte: ALLEN et al., 1998 (FAO-56), tabela de hortalicas de raiz de
# ciclo curto, valores adotados no projeto de pesquisa do TCC.
# ---------------------------------------------------------------------
KC_RABANETE = {
    "inicial": 0.70,
    "medio": 0.90,
    "final": 0.85,
}
