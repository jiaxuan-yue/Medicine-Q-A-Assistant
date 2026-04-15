"""自动化环境感知服务：时间、节气、定位、天气。"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime
from threading import RLock
from typing import Any

import requests

from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)

_SOLAR_TERM_BOUNDARIES: list[tuple[tuple[int, int], str]] = [
    ((1, 5), "小寒"),
    ((1, 20), "大寒"),
    ((2, 4), "立春"),
    ((2, 19), "雨水"),
    ((3, 5), "惊蛰"),
    ((3, 20), "春分"),
    ((4, 4), "清明"),
    ((4, 20), "谷雨"),
    ((5, 5), "立夏"),
    ((5, 21), "小满"),
    ((6, 5), "芒种"),
    ((6, 21), "夏至"),
    ((7, 7), "小暑"),
    ((7, 22), "大暑"),
    ((8, 7), "立秋"),
    ((8, 23), "处暑"),
    ((9, 7), "白露"),
    ((9, 23), "秋分"),
    ((10, 8), "寒露"),
    ((10, 23), "霜降"),
    ((11, 7), "立冬"),
    ((11, 22), "小雪"),
    ((12, 7), "大雪"),
    ((12, 21), "冬至"),
]

_CACHE_LOCK = RLock()
_CACHE: dict[str, Any] = {"expires_at": 0.0, "value": None}


def get_current_solar_term(now: datetime | None = None) -> str:
    """Approximate current solar term using fixed date boundaries."""
    current = now or datetime.now()
    marker = (current.month, current.day)
    current_term = "冬至"
    for boundary, term in _SOLAR_TERM_BOUNDARIES:
        if marker >= boundary:
            current_term = term
        else:
            break
    return current_term


def _safe_request_json(
    session: requests.Session,
    method: str,
    url: str,
    *,
    timeout: float,
    **kwargs,
) -> dict[str, Any]:
    response = session.request(method, url, timeout=timeout, **kwargs)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError(f"Unexpected payload from {url}")
    return payload


def _normalize_preferred_location(preferred_location: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(preferred_location, dict):
        return {}
    normalized: dict[str, Any] = {}
    for key in ("latitude", "longitude", "accuracy_m", "source", "label", "city", "province"):
        if preferred_location.get(key) is not None:
            normalized[key] = preferred_location.get(key)
    return normalized


def _get_system_location(session: requests.Session) -> dict[str, str]:
    payload = _safe_request_json(
        session,
        "GET",
        settings.IP_GEO_API_URL,
        timeout=settings.LIVE_CONTEXT_TIMEOUT_SECONDS,
    )
    if payload.get("status") != "success":
        raise RuntimeError(payload.get("message") or "IP geolocation failed")
    return {
        "city": (payload.get("city") or "").strip(),
        "province": (payload.get("regionName") or "").strip(),
        "country": (payload.get("country") or "").strip(),
    }


def _get_qweather_headers() -> dict[str, str]:
    token = (settings.QWEATHER_API_TOKEN or settings.QWEATHER_API_KEY or "").strip()
    if not token:
        raise RuntimeError("QWeather token is missing")
    return {"Authorization": f"Bearer {token}"}


def _lookup_qweather_location_id(
    session: requests.Session,
    *,
    city: str,
    province: str,
    coordinates: tuple[float, float] | None = None,
) -> tuple[str, str, str]:
    params = {"range": "cn", "number": 5}
    if coordinates:
        longitude, latitude = coordinates
        params["location"] = f"{longitude:.6f},{latitude:.6f}"
    else:
        params["location"] = city or province
    if province and not coordinates:
        params["adm"] = province
    payload = _safe_request_json(
        session,
        "GET",
        f"{settings.QWEATHER_API_HOST.rstrip('/')}/geo/v2/city/lookup",
        params=params,
        headers=_get_qweather_headers(),
        timeout=settings.LIVE_CONTEXT_TIMEOUT_SECONDS,
    )
    if payload.get("code") != "200" or not payload.get("location"):
        raise RuntimeError(f"QWeather city lookup failed: {payload}")
    first = payload["location"][0]
    return first["id"], first.get("name", city), first.get("adm1", province)


def _get_qweather_now(
    session: requests.Session,
    *,
    location_id: str,
) -> dict[str, str]:
    payload = _safe_request_json(
        session,
        "GET",
        f"{settings.QWEATHER_API_HOST.rstrip('/')}/v7/weather/now",
        params={"location": location_id},
        headers=_get_qweather_headers(),
        timeout=settings.LIVE_CONTEXT_TIMEOUT_SECONDS,
    )
    if payload.get("code") != "200":
        raise RuntimeError(f"QWeather now weather failed: {payload}")
    now_payload = payload.get("now") or {}
    return {
        "temperature": str(now_payload.get("temp", "")).strip(),
        "humidity": str(now_payload.get("humidity", "")).strip(),
        "condition": str(now_payload.get("text", "")).strip(),
        "source": "qweather",
    }


def _lookup_amap_adcode(
    session: requests.Session,
    *,
    city: str,
    province: str,
    coordinates: tuple[float, float] | None = None,
) -> tuple[str, str, str]:
    api_key = (settings.AMAP_API_KEY or "").strip()
    if not api_key:
        raise RuntimeError("AMap key is missing")
    if coordinates:
        longitude, latitude = coordinates
        payload = _safe_request_json(
            session,
            "GET",
            f"{settings.AMAP_API_HOST.rstrip('/')}/v3/geocode/regeo",
            params={"location": f"{longitude:.6f},{latitude:.6f}", "key": api_key, "extensions": "base"},
            timeout=settings.LIVE_CONTEXT_TIMEOUT_SECONDS,
        )
        regeocode = payload.get("regeocode") or {}
        address = regeocode.get("addressComponent") or {}
        if payload.get("status") != "1" or not address:
            raise RuntimeError(f"AMap regeo failed: {payload}")
        city_name = address.get("city") or address.get("district") or city
        if isinstance(city_name, list):
            city_name = city_name[0] if city_name else city
        province_name = address.get("province") or province
        adcode = address.get("adcode", "")
        return adcode, str(city_name or city), str(province_name or province)

    address = f"{province}{city}".strip() or city or province
    payload = _safe_request_json(
        session,
        "GET",
        f"{settings.AMAP_API_HOST.rstrip('/')}/v3/geocode/geo",
        params={"address": address, "key": api_key},
        timeout=settings.LIVE_CONTEXT_TIMEOUT_SECONDS,
    )
    if payload.get("status") != "1" or not payload.get("geocodes"):
        raise RuntimeError(f"AMap geocode failed: {payload}")
    first = payload["geocodes"][0]
    return first.get("adcode", ""), city, province


def _get_amap_now(
    session: requests.Session,
    *,
    adcode: str,
) -> dict[str, str]:
    api_key = (settings.AMAP_API_KEY or "").strip()
    if not api_key:
        raise RuntimeError("AMap key is missing")
    payload = _safe_request_json(
        session,
        "GET",
        f"{settings.AMAP_API_HOST.rstrip('/')}/v3/weather/weatherInfo",
        params={"city": adcode, "key": api_key, "extensions": "base", "output": "json"},
        timeout=settings.LIVE_CONTEXT_TIMEOUT_SECONDS,
    )
    lives = payload.get("lives") or []
    if payload.get("status") != "1" or not lives:
        raise RuntimeError(f"AMap weather failed: {payload}")
    first = lives[0]
    return {
        "temperature": str(first.get("temperature", "")).strip(),
        "humidity": str(first.get("humidity", "")).strip(),
        "condition": str(first.get("weather", "")).strip(),
        "source": "amap",
    }


def _get_live_weather(
    session: requests.Session,
    *,
    city: str,
    province: str,
    coordinates: tuple[float, float] | None = None,
) -> dict[str, str]:
    provider = (settings.WEATHER_PROVIDER or "qweather").strip().lower()
    if provider == "amap":
        adcode, resolved_city, resolved_province = _lookup_amap_adcode(
            session,
            city=city,
            province=province,
            coordinates=coordinates,
        )
        weather = _get_amap_now(session, adcode=adcode)
        weather["city"] = resolved_city
        weather["province"] = resolved_province
        return weather

    location_id, resolved_city, resolved_province = _lookup_qweather_location_id(
        session,
        city=city,
        province=province,
        coordinates=coordinates,
    )
    weather = _get_qweather_now(session, location_id=location_id)
    weather["city"] = resolved_city
    weather["province"] = resolved_province
    return weather


def _format_environmental_context(
    *,
    current_date: str,
    solar_term: str,
    province: str,
    city: str,
    temperature: str | None,
    humidity: str | None,
    fallback_label: str | None = None,
) -> str:
    location = f"{province}{city}".strip() or fallback_label or "未知位置"
    if temperature and humidity:
        weather_text = f"{temperature}°C，湿度 {humidity}%"
    elif temperature:
        weather_text = f"{temperature}°C"
    else:
        weather_text = "未获取"
    return f"时间：{current_date} ({solar_term}) | 位置：{location} | 天气：{weather_text}"


def _build_live_context_uncached(preferred_location: dict[str, Any] | None = None) -> dict[str, Any]:
    now = datetime.now()
    current_date = now.strftime("%Y-%m-%d")
    solar_term = get_current_solar_term(now)

    province = ""
    city = ""
    label = ""
    temperature = ""
    humidity = ""
    condition = ""
    source = "unavailable"
    latitude: float | None = None
    longitude: float | None = None
    preferred_location = _normalize_preferred_location(preferred_location)
    if preferred_location:
        latitude = float(preferred_location["latitude"])
        longitude = float(preferred_location["longitude"])
        city = str(preferred_location.get("city") or "").strip()
        province = str(preferred_location.get("province") or "").strip()
        label = str(preferred_location.get("label") or "").strip()
        source = str(preferred_location.get("source") or "browser-geolocation")

    with requests.Session() as session:
        coordinates = (longitude, latitude) if longitude is not None and latitude is not None else None
        if not coordinates:
            try:
                location = _get_system_location(session)
                province = location.get("province", "")
                city = location.get("city", "")
            except Exception as exc:
                logger.warning("live_context location lookup failed: %s", exc)

        if city or province or coordinates:
            try:
                weather = _get_live_weather(
                    session,
                    city=city,
                    province=province,
                    coordinates=coordinates,
                )
                province = weather.get("province", province)
                city = weather.get("city", city)
                temperature = weather.get("temperature", "")
                humidity = weather.get("humidity", "")
                condition = weather.get("condition", "")
                source = weather.get("source", source)
            except Exception as exc:
                logger.warning("live_context weather lookup failed: %s", exc)

    environmental_context = _format_environmental_context(
        current_date=current_date,
        solar_term=solar_term,
        province=province,
        city=city,
        temperature=temperature or None,
        humidity=humidity or None,
        fallback_label=label,
    )
    return {
        "date": current_date,
        "solar_term": solar_term,
        "province": province,
        "city": city,
        "label": label,
        "latitude": latitude,
        "longitude": longitude,
        "temperature": temperature,
        "humidity": humidity,
        "condition": condition,
        "source": source,
        "environmental_context": environmental_context,
    }


def get_live_context(preferred_location: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return cached live context string and structured fields."""
    preferred_location = _normalize_preferred_location(preferred_location)
    if preferred_location:
        return _build_live_context_uncached(preferred_location=preferred_location)

    now_ts = time.time()
    ttl_seconds = max(0, int(settings.LIVE_CONTEXT_TTL_SECONDS))
    if ttl_seconds > 0:
        with _CACHE_LOCK:
            cached = _CACHE.get("value")
            expires_at = float(_CACHE.get("expires_at") or 0.0)
            if cached and expires_at > now_ts:
                return cached

    context = _build_live_context_uncached()

    if ttl_seconds > 0:
        with _CACHE_LOCK:
            _CACHE["value"] = context
            _CACHE["expires_at"] = now_ts + ttl_seconds

    return context


async def get_live_context_async(preferred_location: dict[str, Any] | None = None) -> dict[str, Any]:
    return await asyncio.to_thread(get_live_context, preferred_location)
