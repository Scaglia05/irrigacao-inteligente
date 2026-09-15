"""
irrigation/weather.py

Integracao com a API de previsao climatica (Open-Meteo).

Open-Meteo foi escolhida por ser gratuita e nao exigir chave de API,
o que facilita a hospedagem do prototipo (nenhum segredo precisa ser
configurado no Render para a demonstracao funcionar).

Documentacao: https://open-meteo.com/en/docs
"""

from datetime import datetime, date
import requests

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

DAILY_VARS = [
    "temperature_2m_max",
    "temperature_2m_min",
    "relative_humidity_2m_mean",
    "wind_speed_10m_max",
    "shortwave_radiation_sum",
    "precipitation_sum",
    "precipitation_probability_max",
]


def geocode_city(city_name: str) -> dict:
    """Converte um nome de cidade em latitude/longitude/altitude,
    usando a API de geocodificacao do Open-Meteo."""
    resp = requests.get(
        GEOCODING_URL,
        params={"name": city_name, "count": 1, "language": "pt", "format": "json"},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    results = data.get("results")
    if not results:
        raise ValueError(f"Cidade não encontrada: {city_name}")
    r = results[0]
    return {
        "name": r["name"],
        "admin1": r.get("admin1", ""),
        "country": r.get("country", ""),
        "latitude": r["latitude"],
        "longitude": r["longitude"],
        "elevation": r.get("elevation", 0.0),
    }


def fetch_today_weather(latitude: float, longitude: float, elevation: float) -> dict:
    """Busca os dados meteorologicos do dia atual necessarios para o
    calculo de ETo, alem da probabilidade de chuva nas proximas 24h."""
    resp = requests.get(
        FORECAST_URL,
        params={
            "latitude": latitude,
            "longitude": longitude,
            "daily": ",".join(DAILY_VARS),
            "hourly": "precipitation_probability",
            "forecast_days": 2,
            "timezone": "auto",
        },
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()

    daily = data["daily"]
    today_idx = 0

    # Probabilidade maxima de chuva nas proximas 24 horas (dado horario)
    hourly_probs = data.get("hourly", {}).get("precipitation_probability", [])
    next_24h_probs = hourly_probs[:24] if hourly_probs else [0]
    rain_prob_24h = max(next_24h_probs) if next_24h_probs else 0.0

    day_of_year = datetime.strptime(daily["time"][today_idx], "%Y-%m-%d").timetuple().tm_yday

    return {
        "date": daily["time"][today_idx],
        "t_max": daily["temperature_2m_max"][today_idx],
        "t_min": daily["temperature_2m_min"][today_idx],
        "rh_mean": daily["relative_humidity_2m_mean"][today_idx],
        "wind_speed_10m": daily["wind_speed_10m_max"][today_idx] / 3.6,  # km/h -> m/s
        "solar_radiation": daily["shortwave_radiation_sum"][today_idx],
        "precipitation": daily["precipitation_sum"][today_idx],
        "precipitation_prob_24h": rain_prob_24h,
        "elevation": elevation,
        "latitude": latitude,
        "day_of_year": day_of_year,
    }
