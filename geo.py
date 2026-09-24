"""
Geocoding and nearby-place lookup for Navjeevan.

    GOOGLE_MAPS_API_KEY set  ->  Google Places API (New)
    otherwise                ->  OpenStreetMap / Nominatim (free, no key)

Both paths return the same shape, so the pipeline never learns which one ran:

    {"name": str, "detail": str, "phone": str | None, "source": str, "distance_km": float}

`phone` is whatever the provider actually holds — an OSM `phone`/`contact:phone`
tag, or a Google `nationalPhoneNumber`. Most mapped facilities have none, so it
is frequently None and never guessed or completed.

Note on scope: map POI data covers *facilities* — hospitals, fire stations,
police stations. It does not contain mobile assets like NDRF/SDRF rescue teams,
because those are dispatched rather than located. Those come from the web
search in navjeevan.py.
"""

from __future__ import annotations

import math
import os
import re
import threading
import time

import requests

USER_AGENT = "navjeevan/1.0 (disaster triage)"
TIMEOUT = 30

# Our categories -> the POI types each provider understands.
POI_TYPES: dict[str, list[str]] = {
    "medical": ["hospital", "clinic", "pharmacy"],
    "rescue": ["fire_station", "police"],
    "supplies": [],  # relief camps aren't stable POIs — web search only
}

# Nominatim search term and Google place type per POI type.
OSM_TERM = {
    "hospital": "hospital",
    "clinic": "clinic",
    "fire_station": "fire station",
    "police": "police station",
    "pharmacy": "pharmacy",
}
GOOGLE_TYPE = {
    "hospital": "hospital",
    "clinic": "clinic",
    "fire_station": "fire_station",
    "police": "police_station",
    "pharmacy": "pharmacy",
}

# What Nominatim's `type` field must be for a hit to count as a real facility.
# Nominatim search is a *text* match, so a hospital query also returns bus stops
# and a fire-station query returns police posts; without this check those land in
# the resource list as if they were the thing we asked for.
ALLOWED_TYPES: dict[str, set[str]] = {
    "hospital": {"hospital", "clinic"},
    "clinic": {"hospital", "clinic"},
    "fire_station": {"fire_station", "police"},
    "police": {"police", "fire_station"},
    "pharmacy": {"pharmacy", "chemist"},
}

# Facilities OSM holds no name for are labelled by type rather than by their
# street, which is how a road name ended up presented as a rescue resource.
TYPE_LABEL = {
    "hospital": "hospital",
    "clinic": "clinic",
    "fire_station": "fire station",
    "police": "police station",
    "pharmacy": "pharmacy",
}

# A name matching one of these is a road, gate or other passage, not a facility.
NOT_A_FACILITY = (
    "gate", "road", "marg", "street", "flyover", "underpass", "chowk", "crossing",
)

# Real medical facilities that cannot respond to an emergency. OSM files these
# under type=hospital or clinic, but a skin clinic or a homoeopathic college
# cannot triage trauma. Matched as a *prefix*, so "Diagnostics" and
# "Homoeopathic" are caught by "diagnostic" and "homoeo". British and misspelt
# variants are listed separately because OSM contains both.
NOT_EMERGENCY = (
    "diagnostic", "patholog", "laborator", "medical room",
    "homeo", "homoeo", "ayurved", "unani", "siddha", "naturopath", "veterinar",
    "dental", "orthodont", "derma", "skin", "cosmetic", "laser",
    "eye", "ophthalm", "opthalm", "optical", "fertility", "ivf",
)

# Capability order within a category: a hospital outranks a clinic, a fire
# station outranks a police post. Distance decides inside each rank.
TYPE_RANK = {"hospital": 0, "fire_station": 0, "clinic": 1, "police": 1, "pharmacy": 2}

_NOT_A_FACILITY_RE = re.compile(r"\b(" + "|".join(NOT_A_FACILITY) + r")\b", re.IGNORECASE)
_NOT_EMERGENCY_RE = re.compile(r"\b(" + "|".join(NOT_EMERGENCY) + r")", re.IGNORECASE)


def has_google() -> bool:
    return bool(os.environ.get("GOOGLE_MAPS_API_KEY"))


def provider_name() -> str:
    return "Google Places" if has_google() else "OpenStreetMap"


# --------------------------------------------------------------------------- #
# Distance
# --------------------------------------------------------------------------- #

def _distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km."""
    radius = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    return round(2 * radius * math.asin(math.sqrt(a)), 2)


# --------------------------------------------------------------------------- #
# Geocoding:  "Saket, Delhi" -> coordinates
# --------------------------------------------------------------------------- #

def geocode(location: str) -> dict | None:
    """Resolve a place name to {"lat", "lon", "label"}, or None."""
    if not location or location == "Unknown":
        return None
    try:
        return _google_geocode(location) if has_google() else _osm_geocode(location)
    except Exception:
        return None


def _google_geocode(location: str) -> dict | None:
    response = requests.get(
        "https://maps.googleapis.com/maps/api/geocode/json",
        params={"address": location, "key": os.environ["GOOGLE_MAPS_API_KEY"]},
        timeout=TIMEOUT,
    )
    payload = response.json()
    if payload.get("status") != "OK" or not payload.get("results"):
        return None
    hit = payload["results"][0]
    return {
        "lat": hit["geometry"]["location"]["lat"],
        "lon": hit["geometry"]["location"]["lng"],
        "label": hit["formatted_address"],
    }


def _osm_geocode(location: str) -> dict | None:
    data = _nominatim("search", {"q": location, "format": "json", "limit": 1})
    if not data:
        return None
    return {"lat": float(data[0]["lat"]), "lon": float(data[0]["lon"]), "label": data[0]["display_name"]}


# --------------------------------------------------------------------------- #
# Reverse geocoding & address resolution
# --------------------------------------------------------------------------- #

def reverse_geocode(lat: float, lon: float) -> dict | None:
    """Resolve coordinates to district/state context: {district, state, country, label}."""
    try:
        if has_google():
            return _google_reverse(lat, lon)
        return _osm_reverse(lat, lon)
    except Exception:
        return None


def _google_reverse(lat: float, lon: float) -> dict | None:
    response = requests.get(
        "https://maps.googleapis.com/maps/api/geocode/json",
        params={"latlng": f"{lat},{lon}", "key": os.environ["GOOGLE_MAPS_API_KEY"]},
        timeout=TIMEOUT,
    )
    payload = response.json()
    if payload.get("status") != "OK" or not payload.get("results"):
        return None
    components = payload["results"][0].get("address_components", [])
    info: dict[str, str] = {}
    for comp in components:
        types = comp.get("types", [])
        if "administrative_area_level_2" in types:
            info["district"] = comp["long_name"]
        elif "administrative_area_level_1" in types:
            info["state"] = comp["long_name"]
        elif "country" in types:
            info["country"] = comp["long_name"]
    info["label"] = payload["results"][0].get("formatted_address", "")
    return info


def _osm_reverse(lat: float, lon: float) -> dict | None:
    data = _nominatim("reverse", {"lat": lat, "lon": lon, "format": "json", "zoom": 10})
    if not data or "error" in data:
        return None
    address = data.get("address", {})
    return {
        "district": address.get("county") or address.get("state_district") or "",
        "state": address.get("state", ""),
        "country": address.get("country", ""),
        "label": data.get("display_name", ""),
    }


def geocode_address(address: str) -> tuple[float, float] | None:
    """Attempt to resolve a textual address to (lat, lon). Returns None on failure."""
    result = geocode(address)
    if result:
        return (result["lat"], result["lon"])
    return None


# Public distance helper
haversine_km = _distance_km


# --------------------------------------------------------------------------- #
# Nearby search
# --------------------------------------------------------------------------- #

def nearby(lat: float, lon: float, poi_types: list[str], radius_m: int = 5000, limit: int = 8) -> list[dict]:
    """Facilities of the given types within `radius_m`, nearest first."""
    if not poi_types:
        return []
    try:
        if has_google():
            return _google_nearby(lat, lon, poi_types, radius_m, limit)
        return _osm_nearby(lat, lon, poi_types, radius_m, limit)
    except Exception:
        return []


def _phone_from_tags(tags: dict) -> str | None:
    """OSM files numbers under several keys, sometimes several per tag."""
    for key in ("phone", "contact:phone", "emergency:phone"):
        value = (tags or {}).get(key)
        if value:
            # "011-22344470;23404040;23365525" — the first is the primary line.
            return value.split(";")[0].strip() or None
    return None


def _google_nearby(lat, lon, poi_types, radius_m, limit) -> list[dict]:
    """Places API (New) searchNearby."""
    response = requests.post(
        "https://places.googleapis.com/v1/places:searchNearby",
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": os.environ["GOOGLE_MAPS_API_KEY"],
            "X-Goog-FieldMask": (
                "places.displayName,places.formattedAddress,places.location,"
                "places.googleMapsUri,places.nationalPhoneNumber"
            ),
        },
        json={
            "includedTypes": [GOOGLE_TYPE.get(t, t) for t in poi_types],
            "maxResultCount": min(limit, 20),
            "locationRestriction": {
                "circle": {
                    "center": {"latitude": lat, "longitude": lon},
                    "radius": float(radius_m),
                }
            },
        },
        timeout=TIMEOUT,
    )
    response.raise_for_status()

    found = []
    for place in response.json().get("places", []):
        point = place.get("location", {})
        plat = point.get("latitude")
        plon = point.get("longitude")
        found.append(
            {
                "name": place.get("displayName", {}).get("text", "").strip(),
                "detail": place.get("formattedAddress", ""),
                "phone": place.get("nationalPhoneNumber") or None,
                "source": place.get("googleMapsUri", ""),
                "distance_km": _distance_km(lat, lon, plat, plon),
                "lat": plat,
                "lon": plon,
            }
        )
    found.sort(key=lambda item: item["distance_km"])
    return [item for item in found if item["name"]][:limit]


def _osm_nearby(lat, lon, poi_types, radius_m, limit) -> list[dict]:
    """Nominatim bounded search — a separate call per POI type."""
    dlat = radius_m / 111_320
    dlon = radius_m / (111_320 * max(math.cos(math.radians(lat)), 0.01))
    viewbox = f"{lon - dlon},{lat + dlat},{lon + dlon},{lat - dlat}"  # left,top,right,bottom

    seen: set[str] = set()
    found = []
    for poi in poi_types:
        results = _nominatim(
            "search",
            {
                "q": OSM_TERM.get(poi, poi),
                "format": "json",
                "limit": 20,
                "bounded": 1,
                "viewbox": viewbox,
                "extratags": 1,  # carries `phone` / `contact:phone` where mapped
            },
        )
        allowed = ALLOWED_TYPES.get(poi, {poi})
        for place in results:
            otype = (place.get("type") or "").lower()
            if otype not in allowed:
                continue  # a bus stop is not a hospital, however it was matched

            raw_name = (place.get("name") or "").strip()
            if raw_name and _NOT_A_FACILITY_RE.search(raw_name):
                continue
            if poi in ("hospital", "clinic") and raw_name and _NOT_EMERGENCY_RE.search(raw_name):
                continue

            # Unnamed in OSM: say so rather than borrowing the street name.
            name = raw_name or f"Unnamed {TYPE_LABEL.get(otype, otype)}"
            key = raw_name.lower() if raw_name else f"@{place['lat']},{place['lon']}"
            if key in seen:
                continue
            seen.add(key)

            plat, plon = float(place["lat"]), float(place["lon"])
            distance = _distance_km(lat, lon, plat, plon)
            if distance > radius_m / 1000:
                continue  # a bounded box is a square; the radius is still a circle

            address = ", ".join(part.strip() for part in place.get("display_name", "").split(",")[1:4])
            label = TYPE_LABEL.get(otype, otype).title()
            found.append(
                {
                    "name": name,
                    # Naming the facility type lets the planner tell a trauma
                    # hospital from a dispensary when it picks where to send people.
                    "detail": f"{label} · {address}" if address else label,
                    "phone": _phone_from_tags(place.get("extratags") or {}),
                    "source": (
                        f"https://www.openstreetmap.org/?mlat={plat}&mlon={plon}"
                        f"#map=17/{plat}/{plon}"
                    ),
                    "distance_km": distance,
                    "lat": plat,
                    "lon": plon,
                    "_type": otype,
                }
            )

    # Most capable first, nearest first within each capability rank.
    found.sort(key=lambda item: (TYPE_RANK.get(item["_type"], 9), item["distance_km"]))
    return [{k: v for k, v in item.items() if k != "_type"} for item in found[:limit]]


# --------------------------------------------------------------------------- #
# Nominatim is rate-limited to 1 request/second and the three resource branches
# run in parallel, so calls are serialised here behind a lock.
# --------------------------------------------------------------------------- #

_nominatim_lock = threading.Lock()
_last_call = 0.0


def _nominatim(path: str, params: dict) -> list | dict:
    global _last_call
    with _nominatim_lock:
        gap = 1.1 - (time.monotonic() - _last_call)
        if gap > 0:
            time.sleep(gap)
        response = requests.get(
            f"https://nominatim.openstreetmap.org/{path}",
            params=params,
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT,
        )
        _last_call = time.monotonic()

    response.raise_for_status()
    return response.json()
