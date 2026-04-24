"""
GTFS-Realtime service.
Fetches Toei Bus VehiclePosition data from ODPT and falls back to PoC mock data
when the public feed cannot be reached.
"""

import os
import math
import time
import random
from typing import Optional
from urllib.parse import urlparse

import httpx

ODPT_PUBLIC_GTFS_RT_URL = "https://api-public.odpt.org/api/v4/gtfs/realtime/ToeiBus"
ODPT_AUTH_GTFS_RT_URL = "https://api.odpt.org/api/v4/gtfs/realtime/ToeiBus"
ODPT_BUSROUTE_PATTERN_URL = "https://api-public.odpt.org/api/v4/odpt:BusroutePattern"

# Mock data delay/arrival constants
_MOCK_MIN_DELAY_SECONDS = -60
_MOCK_MAX_DELAY_SECONDS = 120
_MOCK_MIN_DEPARTURE_DELAY = 0
_MOCK_MAX_DEPARTURE_DELAY = 120
_MOCK_MIN_ARRIVAL_OFFSET = 60
_MOCK_MAX_ARRIVAL_OFFSET = 300
_ROUTE_PATTERN_CACHE: dict[str, object] = {"loaded_at": 0.0, "items": {}}
_ROUTE_PATTERN_TTL_SECONDS = 3600
_FULLWIDTH_TO_HALFWIDTH = str.maketrans(
    "０１２３４５６７８９ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ",
    "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz",
)

# ---------------------------------------------------------------------------
# Mock data helpers
# ---------------------------------------------------------------------------

_MOCK_VEHICLE_BASE: list[dict] = [
    {"trip_id": "mock-to01-shibuya", "route_id": "都01", "stop_id": "toeibus-stop-003", "current_status": "IN_TRANSIT_TO", "latitude": 35.6612, "longitude": 139.7140, "vehicle_id": "B-T01-001", "direction_id": 0},
    {"trip_id": "mock-to01-shimbashi", "route_id": "都01", "stop_id": "toeibus-stop-005", "current_status": "STOPPED_AT", "latitude": 35.6661, "longitude": 139.7585, "vehicle_id": "B-T01-014", "direction_id": 1},
    {"trip_id": "mock-gyo10-toyosu", "route_id": "業10", "stop_id": "toeibus-stop-009", "current_status": "IN_TRANSIT_TO", "latitude": 35.6625, "longitude": 139.7835, "vehicle_id": "B-G10-006", "direction_id": 0},
    {"trip_id": "mock-ka01-odaiba", "route_id": "海01", "stop_id": "toeibus-stop-010", "current_status": "IN_TRANSIT_TO", "latitude": 35.6412, "longitude": 139.7978, "vehicle_id": "B-K01-003", "direction_id": 1},
    {"trip_id": "mock-to05-ginza", "route_id": "都05-1", "stop_id": "toeibus-stop-007", "current_status": "STOPPED_AT", "latitude": 35.6721, "longitude": 139.7660, "vehicle_id": "B-T05-021", "direction_id": 0},
    {"trip_id": "mock-u23-asakusa", "route_id": "上23", "stop_id": "toeibus-stop-012", "current_status": "IN_TRANSIT_TO", "latitude": 35.7101, "longitude": 139.7974, "vehicle_id": "B-U23-010", "direction_id": 1},
    {"trip_id": "mock-n13-kinshicho", "route_id": "錦13", "stop_id": "toeibus-stop-013", "current_status": "STOPPED_AT", "latitude": 35.6968, "longitude": 139.8148, "vehicle_id": "B-N13-018", "direction_id": 0},
    {"trip_id": "mock-higashi22-tokyo", "route_id": "東22", "stop_id": "toeibus-stop-006", "current_status": "IN_TRANSIT_TO", "latitude": 35.6780, "longitude": 139.7772, "vehicle_id": "B-H22-004", "direction_id": 1},
]


def _mock_vehicles(route_ids: Optional[list[str]]) -> list[dict]:
    ts = int(time.time())
    vehicles = []
    for v in _MOCK_VEHICLE_BASE:
        if route_ids and v["route_id"] not in route_ids:
            continue
        jitter_lat = (random.random() - 0.5) * 0.002
        jitter_lon = (random.random() - 0.5) * 0.002
        vehicles.append({
            **v,
            "latitude": round(v["latitude"] + jitter_lat, 6),
            "longitude": round(v["longitude"] + jitter_lon, 6),
            "timestamp": ts,
        })
    return vehicles


def _mock_trip_updates(route_ids: Optional[list[str]]) -> list[dict]:
    updates = []
    for v in _MOCK_VEHICLE_BASE:
        if route_ids and v["route_id"] not in route_ids:
            continue
        updates.append({
            "trip_id": v["trip_id"],
            "route_id": v["route_id"],
            "stop_time_updates": [
                {
                    "stop_id": v["stop_id"],
                    "arrival_delay": random.randint(_MOCK_MIN_DELAY_SECONDS, _MOCK_MAX_DELAY_SECONDS),
                    "departure_delay": random.randint(_MOCK_MIN_DEPARTURE_DELAY, _MOCK_MAX_DEPARTURE_DELAY),
                    "arrival_time": int(time.time()) + random.randint(_MOCK_MIN_ARRIVAL_OFFSET, _MOCK_MAX_ARRIVAL_OFFSET),
                },
            ],
        })
    return updates


def _mock_alerts() -> list[dict]:
    return [
        {
            "alert_id": "mock-alert-1",
            "header_text": "都01 渋谷駅前方面に遅れ",
            "description_text": "道路混雑のため、都01 渋谷駅前方面に5分から10分程度の遅れが出ています。",
            "affected_routes": ["都01"],
            "effect": "SIGNIFICANT_DELAYS",
        },
        {
            "alert_id": "mock-alert-2",
            "header_text": "東京ビッグサイト周辺でイベント開催",
            "description_text": "東京ビッグサイト周辺でイベント開催のため、海01・都05-2で混雑が見込まれます。",
            "affected_routes": ["海01", "都05-2"],
            "effect": "MODIFIED_SERVICE",
        },
    ]


def _ssl_verify() -> bool:
    return os.getenv("ODPT_SSL_VERIFY", "true").strip().lower() not in {"0", "false", "no"}


def _odpt_feed_url(api_key: Optional[str]) -> tuple[str, dict[str, str]]:
    configured_url = os.getenv("ODPT_GTFS_RT_URL", "").strip()
    public_url = os.getenv("ODPT_PUBLIC_GTFS_RT_URL", "").strip() or ODPT_PUBLIC_GTFS_RT_URL

    if configured_url:
        url = configured_url
    elif api_key:
        url = ODPT_AUTH_GTFS_RT_URL
    else:
        url = public_url

    params: dict[str, str] = {}
    if api_key and urlparse(url).netloc == "api.odpt.org":
        params["acl:consumerKey"] = api_key
    return url, params


async def _fetch_odpt_feed(api_key: Optional[str]) -> bytes:
    url, params = _odpt_feed_url(api_key)
    async with httpx.AsyncClient(verify=_ssl_verify(), timeout=20.0) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        return response.content


def _normalize_pattern_id(value: str | None) -> str:
    if not value:
        return ""
    normalized = value.strip().lstrip("0")
    return normalized or "0"


def _normalize_route_text(value: str | None) -> str:
    return (value or "").translate(_FULLWIDTH_TO_HALFWIDTH)


def _pattern_key(pattern_id: str | None, direction_id: int | str | None = None) -> str:
    pattern = _normalize_pattern_id(pattern_id)
    direction = "" if direction_id is None else str(direction_id)
    return f"{pattern}:{direction}"


def _parse_trip_pattern_id(trip_id: str | None) -> str:
    if not trip_id:
        return ""
    return _normalize_pattern_id(trip_id.split("-", 1)[0])


def _parse_trip_direction_id(trip_id: str | None) -> str | None:
    if not trip_id:
        return None
    parts = trip_id.split("-")
    if len(parts) < 2:
        return None
    return parts[1] or None


def _route_pattern_from_item(item: dict) -> tuple[str, dict] | None:
    pattern = _normalize_pattern_id(str(item.get("odpt:pattern", "")))
    direction = str(item.get("odpt:direction", ""))
    title = _normalize_route_text(str(item.get("dc:title", "")).strip())
    note = _normalize_route_text(str(item.get("odpt:note", "")).strip())
    short_name = title.split(" ", 1)[0] if title else ""
    origin = ""
    destination = ""
    if note:
        parts = note.split(":")
        if len(parts) >= 2:
            short_name = parts[0] or short_name
            if "→" in parts[1]:
                origin, destination = parts[1].split("→", 1)
    display_name = title or short_name
    return _pattern_key(pattern, direction), {
        "pattern_id": pattern,
        "direction_id": direction,
        "route_short_name": short_name,
        "route_long_name": title,
        "route_display_name": display_name,
        "origin": origin,
        "destination": destination,
        "busroute": item.get("odpt:busroute"),
    }


async def _load_route_pattern_map(api_key: Optional[str]) -> dict[str, dict]:
    now = time.time()
    if now - float(_ROUTE_PATTERN_CACHE["loaded_at"]) < _ROUTE_PATTERN_TTL_SECONDS:
        return _ROUTE_PATTERN_CACHE["items"]  # type: ignore[return-value]

    url = os.getenv("ODPT_BUSROUTE_PATTERN_URL", "").strip() or ODPT_BUSROUTE_PATTERN_URL
    params = {"odpt:operator": "odpt.Operator:Toei"}
    if api_key and urlparse(url).netloc == "api.odpt.org":
        params["acl:consumerKey"] = api_key

    async with httpx.AsyncClient(verify=_ssl_verify(), timeout=20.0) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        data = response.json()

    items: dict[str, dict] = {}
    for item in data:
        parsed = _route_pattern_from_item(item)
        if parsed:
            key, value = parsed
            items[key] = value

    _ROUTE_PATTERN_CACHE["loaded_at"] = now
    _ROUTE_PATTERN_CACHE["items"] = items
    return items


def _metadata_for_vehicle(route_patterns: dict[str, dict], trip_id: str, direction_id: int | None) -> dict:
    pattern_id = _parse_trip_pattern_id(trip_id)
    pattern_direction = _parse_trip_direction_id(trip_id)
    metadata = route_patterns.get(_pattern_key(pattern_id, pattern_direction))
    if not metadata:
        metadata = route_patterns.get(_pattern_key(pattern_id, direction_id))
    if not metadata:
        metadata = route_patterns.get(_pattern_key(pattern_id, None))
    return metadata or {"pattern_id": pattern_id, "pattern_direction_id": pattern_direction}


def _vehicle_route_matches(vehicle: dict, query: str) -> bool:
    needle = _normalize_route_text(query).strip().lower()
    if not needle:
        return False
    haystack = " ".join(str(vehicle.get(key, "")) for key in [
        "route_id",
        "route_short_name",
        "route_long_name",
        "route_display_name",
        "destination",
        "pattern_id",
    ]).lower()
    return needle in haystack


def _distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _parse_vehicles(feed_message, route_ids: Optional[list[str]], route_patterns: dict[str, dict], feed_timestamp: int | None = None) -> list[dict]:
    try:
        from google.transit import gtfs_realtime_pb2  # type: ignore
    except ImportError:
        return []

    vehicles = []
    for entity in feed_message.entity:
        if not entity.HasField("vehicle"):
            continue
        v = entity.vehicle
        route_id = v.trip.route_id
        if route_ids and route_id not in route_ids:
            continue
        pos = v.position
        if not pos.latitude or not pos.longitude:
            continue
        trip_id = v.trip.trip_id
        direction_id = v.trip.direction_id if v.trip.HasField("direction_id") else None
        metadata = _metadata_for_vehicle(route_patterns, trip_id, direction_id)
        vehicles.append({
            "trip_id": trip_id,
            "route_id": route_id,
            "stop_id": v.stop_id,
            "current_status": gtfs_realtime_pb2.VehiclePosition.VehicleStopStatus.Name(v.current_status),
            "latitude": round(pos.latitude, 6),
            "longitude": round(pos.longitude, 6),
            "timestamp": v.timestamp,
            "feed_timestamp": feed_timestamp,
            "vehicle_id": v.vehicle.id or entity.id,
            "vehicle_label": v.vehicle.label,
            "direction_id": direction_id,
            "source": "odpt",
            **metadata,
        })
    return vehicles


async def _load_odpt_feed(api_key: Optional[str]):
    """Download and parse a single GTFS-RT feed. Returns the parsed FeedMessage."""
    from google.transit import gtfs_realtime_pb2  # type: ignore

    data = await _fetch_odpt_feed(api_key)
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(data)
    return feed


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def get_vehicle_positions(api_key: Optional[str], route_ids: Optional[list[str]] = None) -> list[dict]:
    try:
        feed = await _load_odpt_feed(api_key)
        route_patterns = await _load_route_pattern_map(api_key)
        vehicles = _parse_vehicles(feed, route_ids, route_patterns, feed.header.timestamp or None)
        return vehicles if vehicles else _mock_vehicles(route_ids)
    except Exception:
        return _mock_vehicles(route_ids)


async def search_vehicles_by_route(api_key: Optional[str], query: str, limit: int = 20) -> list[dict]:
    """Return live vehicles whose route metadata matches a user-facing route query."""
    vehicles = await get_vehicle_positions(api_key)
    matches = [v for v in vehicles if _vehicle_route_matches(v, query)]
    matches.sort(key=lambda v: str(v.get("route_display_name") or v.get("route_short_name") or v.get("route_id")))
    return matches[:limit]


async def search_nearby_vehicles(
    api_key: Optional[str],
    lat: float,
    lng: float,
    radius_m: int = 800,
    limit: int = 20,
) -> list[dict]:
    """Return live vehicles near the given point, sorted by distance."""
    vehicles = await get_vehicle_positions(api_key)
    nearby: list[dict] = []
    for vehicle in vehicles:
        try:
            distance = _distance_m(lat, lng, float(vehicle["latitude"]), float(vehicle["longitude"]))
        except (KeyError, TypeError, ValueError):
            continue
        if distance <= radius_m:
            nearby.append({**vehicle, "distance_m": round(distance)})

    nearby.sort(key=lambda v: v["distance_m"])
    return nearby[:limit]


async def get_trip_updates(api_key: Optional[str], route_ids: Optional[list[str]] = None) -> list[dict]:
    # The Toei Bus public feed used in this PoC exposes VehiclePosition. TripUpdate
    # will be wired separately if an ODPT feed/resource is selected for arrivals.
    return _mock_trip_updates(route_ids)


async def get_service_alerts(api_key: Optional[str]) -> list[dict]:
    return _mock_alerts()


async def get_station_realtime(api_key: Optional[str], stop_id: str) -> dict:
    """Return combined real-time arrivals for a single station."""
    trip_updates = await get_trip_updates(api_key)
    arrivals = []
    for tu in trip_updates:
        for stu in tu.get("stop_time_updates", []):
            if stu.get("stop_id") == stop_id:
                arrivals.append({
                    "trip_id": tu["trip_id"],
                    "route_id": tu["route_id"],
                    "arrival_time": stu.get("arrival_time"),
                    "arrival_delay": stu.get("arrival_delay"),
                    "departure_delay": stu.get("departure_delay"),
                })
    return {"stop_id": stop_id, "arrivals": arrivals}
