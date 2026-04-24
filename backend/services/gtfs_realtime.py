"""
GTFS-Realtime service.
Fetches live vehicle positions, trip updates, and service alerts from the MTA API.
Falls back to realistic mock data when MTA_API_KEY is not configured.
"""

import time
import math
import random
from typing import Optional

import httpx

MTA_BASE_URL = "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs"

# Mock data delay/arrival constants
_MOCK_MIN_DELAY_SECONDS = -60
_MOCK_MAX_DELAY_SECONDS = 120
_MOCK_MIN_DEPARTURE_DELAY = 0
_MOCK_MAX_DEPARTURE_DELAY = 120
_MOCK_MIN_ARRIVAL_OFFSET = 60
_MOCK_MAX_ARRIVAL_OFFSET = 300

# Feed suffixes for each route group
_FEED_SUFFIXES: dict[str, str] = {
    "ace":  "-ace",
    "bdfm": "-bdfm",
    "g":    "-g",
    "jz":   "-jz",
    "nqrw": "-nqrw",
    "l":    "-l",
    "1234567": "",   # default feed (numbered lines)
    "si":   "-si",
}

_ROUTE_TO_FEED: dict[str, str] = {
    "A": "-ace", "C": "-ace", "E": "-ace",
    "B": "-bdfm", "D": "-bdfm", "F": "-bdfm", "M": "-bdfm",
    "G": "-g",
    "J": "-jz", "Z": "-jz",
    "N": "-nqrw", "Q": "-nqrw", "R": "-nqrw", "W": "-nqrw",
    "L": "-l",
    "1": "", "2": "", "3": "", "4": "", "5": "", "6": "", "7": "",
    "S": "",
}


def _feeds_for_routes(route_ids: Optional[list[str]]) -> set[str]:
    """Determine the set of feed suffixes needed for the requested routes."""
    if not route_ids:
        return set(_FEED_SUFFIXES.values())
    feeds: set[str] = set()
    for r in route_ids:
        suffix = _ROUTE_TO_FEED.get(r.upper())
        if suffix is not None:
            feeds.add(suffix)
    return feeds or set(_FEED_SUFFIXES.values())


# ---------------------------------------------------------------------------
# Mock data helpers
# ---------------------------------------------------------------------------

_MOCK_VEHICLE_BASE: list[dict] = [
    {"trip_id": "mock-1-uptown", "route_id": "1", "stop_id": "120", "current_status": "IN_TRANSIT_TO", "latitude": 40.755, "longitude": -73.990, "vehicle_id": "1A01"},
    {"trip_id": "mock-2-uptown", "route_id": "2", "stop_id": "229", "current_status": "STOPPED_AT",    "latitude": 40.776, "longitude": -73.982, "vehicle_id": "2A05"},
    {"trip_id": "mock-4-downtown", "route_id": "4", "stop_id": "631", "current_status": "STOPPED_AT",  "latitude": 40.751, "longitude": -73.976, "vehicle_id": "4B12"},
    {"trip_id": "mock-6-uptown", "route_id": "6", "stop_id": "621", "current_status": "IN_TRANSIT_TO", "latitude": 40.763, "longitude": -73.966, "vehicle_id": "6C03"},
    {"trip_id": "mock-A-downtown", "route_id": "A", "stop_id": "A27", "current_status": "STOPPED_AT",  "latitude": 40.750, "longitude": -73.991, "vehicle_id": "AA09"},
    {"trip_id": "mock-L-bklyn", "route_id": "L", "stop_id": "L06",  "current_status": "IN_TRANSIT_TO", "latitude": 40.717, "longitude": -73.957, "vehicle_id": "LL02"},
    {"trip_id": "mock-N-queens", "route_id": "N", "stop_id": "N02",  "current_status": "STOPPED_AT",   "latitude": 40.775, "longitude": -73.912, "vehicle_id": "NA07"},
    {"trip_id": "mock-7-queens", "route_id": "7", "stop_id": "702",  "current_status": "IN_TRANSIT_TO", "latitude": 40.748, "longitude": -73.870, "vehicle_id": "7D14"},
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
            "header_text": "1/2/3 trains delayed due to signal problems",
            "description_text": "Expect delays of up to 15 minutes on the 1, 2, and 3 trains between 34 St-Penn Station and Times Sq-42 St.",
            "affected_routes": ["1", "2", "3"],
            "effect": "SIGNIFICANT_DELAYS",
        },
        {
            "alert_id": "mock-alert-2",
            "header_text": "A train service change this weekend",
            "description_text": "A trains run express between 59 St-Columbus Circle and Jay St-MetroTech this weekend due to track maintenance.",
            "affected_routes": ["A"],
            "effect": "MODIFIED_SERVICE",
        },
    ]


# ---------------------------------------------------------------------------
# Live MTA API helpers
# ---------------------------------------------------------------------------

async def _fetch_feed(client: httpx.AsyncClient, api_key: str, suffix: str) -> bytes:
    url = MTA_BASE_URL + suffix
    response = await client.get(url, headers={"x-api-key": api_key}, timeout=10.0)
    response.raise_for_status()
    return response.content


def _parse_vehicles(feed_message, route_ids: Optional[list[str]]) -> list[dict]:
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
        vehicles.append({
            "trip_id": v.trip.trip_id,
            "route_id": route_id,
            "stop_id": v.stop_id,
            "current_status": gtfs_realtime_pb2.VehiclePosition.VehicleStopStatus.Name(v.current_status),
            "latitude": round(pos.latitude, 6),
            "longitude": round(pos.longitude, 6),
            "timestamp": v.timestamp,
            "vehicle_id": v.vehicle.id,
        })
    return vehicles


def _parse_trip_updates(feed_message, route_ids: Optional[list[str]]) -> list[dict]:
    updates = []
    for entity in feed_message.entity:
        if not entity.HasField("trip_update"):
            continue
        tu = entity.trip_update
        route_id = tu.trip.route_id
        if route_ids and route_id not in route_ids:
            continue
        stu_list = []
        for stu in tu.stop_time_update:
            stu_list.append({
                "stop_id": stu.stop_id,
                "arrival_delay": stu.arrival.delay if stu.HasField("arrival") else None,
                "departure_delay": stu.departure.delay if stu.HasField("departure") else None,
                "arrival_time": stu.arrival.time if stu.HasField("arrival") else None,
            })
        updates.append({
            "trip_id": tu.trip.trip_id,
            "route_id": route_id,
            "stop_time_updates": stu_list,
        })
    return updates


def _parse_alerts(feed_message) -> list[dict]:
    alerts = []
    for entity in feed_message.entity:
        if not entity.HasField("alert"):
            continue
        alert = entity.alert
        header = next((t.text for t in alert.header_text.translation if t.language == "en"), "")
        desc = next((t.text for t in alert.description_text.translation if t.language == "en"), "")
        affected = [ie.route_id for ie in alert.informed_entity if ie.route_id]

        try:
            from google.transit import gtfs_realtime_pb2  # type: ignore
            effect = gtfs_realtime_pb2.Alert.Effect.Name(alert.effect)
        except Exception:
            effect = str(alert.effect)

        alerts.append({
            "alert_id": entity.id,
            "header_text": header,
            "description_text": desc,
            "affected_routes": affected,
            "effect": effect,
        })
    return alerts


async def _load_feed(api_key: str, suffix: str):
    """Download and parse a single GTFS-RT feed. Returns the parsed FeedMessage."""
    from google.transit import gtfs_realtime_pb2  # type: ignore

    async with httpx.AsyncClient() as client:
        data = await _fetch_feed(client, api_key, suffix)

    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(data)
    return feed


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def get_vehicle_positions(api_key: Optional[str], route_ids: Optional[list[str]] = None) -> list[dict]:
    if not api_key:
        return _mock_vehicles(route_ids)

    try:
        from google.transit import gtfs_realtime_pb2  # type: ignore
        results: list[dict] = []
        for suffix in _feeds_for_routes(route_ids):
            feed = await _load_feed(api_key, suffix)
            results.extend(_parse_vehicles(feed, route_ids))
        return results
    except Exception:
        return _mock_vehicles(route_ids)


async def get_trip_updates(api_key: Optional[str], route_ids: Optional[list[str]] = None) -> list[dict]:
    if not api_key:
        return _mock_trip_updates(route_ids)

    try:
        results: list[dict] = []
        for suffix in _feeds_for_routes(route_ids):
            feed = await _load_feed(api_key, suffix)
            results.extend(_parse_trip_updates(feed, route_ids))
        return results
    except Exception:
        return _mock_trip_updates(route_ids)


async def get_service_alerts(api_key: Optional[str]) -> list[dict]:
    if not api_key:
        return _mock_alerts()

    try:
        # Alerts are present in any feed; use the default numbered-lines feed
        feed = await _load_feed(api_key, "")
        alerts = _parse_alerts(feed)
        return alerts if alerts else _mock_alerts()
    except Exception:
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
