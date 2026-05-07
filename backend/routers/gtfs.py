"""
FastAPI router for GTFS static and real-time endpoints.
Prefix: /api/gtfs
"""

import os
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from services import gtfs_static, gtfs_realtime, gtfs_shapes

router = APIRouter()


def _api_key() -> Optional[str]:
    return os.getenv("ODPT_API_KEY") or None


def _vehicle_feature(vehicle: dict) -> Optional[dict]:
    try:
        lat = float(vehicle["latitude"])
        lng = float(vehicle["longitude"])
    except (KeyError, TypeError, ValueError):
        return None

    if abs(lat) > 90 or abs(lng) > 180:
        return None

    vehicle_id = vehicle.get("vehicle_id") or vehicle.get("id")
    route_label = (
        vehicle.get("route_short_name")
        or vehicle.get("route_display_name")
        or vehicle.get("route_id")
    )

    return {
        "type": "Feature",
        "id": vehicle_id,
        "geometry": {
            "type": "Point",
            "coordinates": [lng, lat],
        },
        "properties": {
            "vehicle_id": vehicle_id,
            "route_id": vehicle.get("route_id"),
            "route_short_name": vehicle.get("route_short_name"),
            "route_display_name": vehicle.get("route_display_name"),
            "route_label": route_label,
            "destination": vehicle.get("destination"),
            "trip_id": vehicle.get("trip_id"),
            "pattern_id": vehicle.get("pattern_id"),
            "stop_id": vehicle.get("stop_id"),
            "stop_name": vehicle.get("stop_name"),
            "next_stop_name": vehicle.get("next_stop_name"),
            "current_stop_name": vehicle.get("current_stop_name"),
            "current_status": vehicle.get("current_status"),
            "timestamp": vehicle.get("timestamp"),
            "feed_timestamp": vehicle.get("feed_timestamp"),
            "source": vehicle.get("source"),
        },
    }


def _vehicle_feature_collection(vehicles: list[dict]) -> dict:
    features = [_vehicle_feature(vehicle) for vehicle in vehicles]
    return {
        "type": "FeatureCollection",
        "features": [feature for feature in features if feature is not None],
    }


def _parse_routes_param(routes: Optional[str]) -> Optional[set[str]]:
    if not routes:
        return None
    items = {item.strip() for item in routes.split(",") if item.strip()}
    return items or None


def _normalize_stop_name(name: str) -> str:
    text = str(name or "").strip().replace("　", " ")
    for suffix in ["駅前", "駅", "停留所", "バス停"]:
        text = text.replace(suffix, "")
    return text.replace(" ", "")


def _stops_by_normalized_name(stops: list[dict]) -> dict[str, dict]:
    mapping: dict[str, dict] = {}
    for stop in stops:
        normalized = _normalize_stop_name(str(stop.get("stop_name", "")))
        if normalized and normalized not in mapping:
            mapping[normalized] = stop
    return mapping


def _resolve_terminal_stops(route: dict, stop_map: dict[str, dict]) -> tuple[Optional[dict], Optional[dict]]:
    route_name = str(route.get("route_name") or "")
    core = route_name.split(" ", 1)[1] if " " in route_name else route_name
    if " - " not in core:
        return None, None
    origin_raw, destination_raw = core.split(" - ", 1)
    origin = stop_map.get(_normalize_stop_name(origin_raw))
    destination = stop_map.get(_normalize_stop_name(destination_raw))
    return origin, destination


def _route_stops(route_id: str, stops: list[dict]) -> list[dict]:
    return [stop for stop in stops if route_id in stop.get("routes", [])]


def _farthest_stop_pair(stops: list[dict]) -> tuple[Optional[dict], Optional[dict]]:
    if len(stops) < 2:
        return None, None
    best_pair: tuple[Optional[dict], Optional[dict]] = (None, None)
    best_dist = -1.0
    for i, a in enumerate(stops):
        for b in stops[i + 1:]:
            dx = float(a["stop_lon"]) - float(b["stop_lon"])
            dy = float(a["stop_lat"]) - float(b["stop_lat"])
            dist = dx * dx + dy * dy
            if dist > best_dist:
                best_dist = dist
                best_pair = (a, b)
    return best_pair


def _ordered_route_path_stops(route_id: str, origin: Optional[dict], destination: Optional[dict], stops: list[dict]) -> list[dict]:
    candidates = _route_stops(route_id, stops)
    if not candidates:
        return []

    if not origin or not destination:
        fallback_origin, fallback_destination = _farthest_stop_pair(candidates)
        origin = origin or fallback_origin
        destination = destination or fallback_destination
    if not origin or not destination:
        return candidates

    origin_id = str(origin.get("stop_id", ""))
    destination_id = str(destination.get("stop_id", ""))
    origin_lon = float(origin["stop_lon"])
    origin_lat = float(origin["stop_lat"])
    destination_lon = float(destination["stop_lon"])
    destination_lat = float(destination["stop_lat"])
    vx = destination_lon - origin_lon
    vy = destination_lat - origin_lat
    norm = vx * vx + vy * vy
    if norm <= 1e-12:
        return [origin, destination] if origin_id != destination_id else [origin]

    waypoints = []
    seen = set()
    for stop in candidates:
        stop_id = str(stop.get("stop_id", ""))
        if not stop_id or stop_id in seen:
            continue
        seen.add(stop_id)
        if stop_id in {origin_id, destination_id}:
            continue
        px = float(stop["stop_lon"]) - origin_lon
        py = float(stop["stop_lat"]) - origin_lat
        t = (px * vx + py * vy) / norm
        # Perpendicular distance from baseline for tie-breaking.
        cross = abs(px * vy - py * vx)
        waypoints.append((t, cross, stop))

    waypoints.sort(key=lambda item: (item[0], item[1]))
    ordered = [origin] + [item[2] for item in waypoints] + [destination]
    deduped: list[dict] = []
    seen_ids: set[str] = set()
    for stop in ordered:
        stop_id = str(stop.get("stop_id", ""))
        if stop_id and stop_id not in seen_ids:
            deduped.append(stop)
            seen_ids.add(stop_id)
    return deduped


def _route_lines_feature_collection(route_filter: Optional[set[str]]) -> dict:
    stops = gtfs_static.get_stops()
    routes = gtfs_static.get_routes()
    stop_map = _stops_by_normalized_name(stops)
    features: list[dict] = []
    for route in routes:
        route_id = str(route.get("route_id", ""))
        if route_filter and route_id not in route_filter:
            continue
        origin, destination = _resolve_terminal_stops(route, stop_map)
        path_stops = _ordered_route_path_stops(route_id, origin, destination, stops)
        if len(path_stops) < 2:
            continue
        features.append({
            "type": "Feature",
            "id": f"line-{route_id}",
            "geometry": {
                "type": "LineString",
                "coordinates": [[float(stop["stop_lon"]), float(stop["stop_lat"])] for stop in path_stops],
            },
            "properties": {
                "route_id": route_id,
                "route_name": route.get("route_name"),
                "route_color": route.get("route_color"),
                "origin_stop_name": path_stops[0].get("stop_name"),
                "destination_stop_name": path_stops[-1].get("stop_name"),
                "stop_count": len(path_stops),
                "path_type": "stop-sequence-polyline",
            },
        })
    return {"type": "FeatureCollection", "features": features}


def _route_terminals_feature_collection(route_filter: Optional[set[str]]) -> dict:
    stops = gtfs_static.get_stops()
    routes = gtfs_static.get_routes()
    stop_map = _stops_by_normalized_name(stops)
    features_by_id: dict[str, dict] = {}
    for route in routes:
        route_id = str(route.get("route_id", ""))
        if route_filter and route_id not in route_filter:
            continue
        origin, destination = _resolve_terminal_stops(route, stop_map)
        for role, stop in [("origin", origin), ("destination", destination)]:
            if not stop:
                continue
            stop_id = str(stop.get("stop_id", ""))
            if not stop_id:
                continue
            if stop_id not in features_by_id:
                features_by_id[stop_id] = {
                    "type": "Feature",
                    "id": stop_id,
                    "geometry": {
                        "type": "Point",
                        "coordinates": [float(stop["stop_lon"]), float(stop["stop_lat"])],
                    },
                    "properties": {
                        "stop_id": stop_id,
                        "stop_name": stop.get("stop_name"),
                        "terminal_roles": [],
                        "routes": [],
                    },
                }
            feature = features_by_id[stop_id]
            if role not in feature["properties"]["terminal_roles"]:
                feature["properties"]["terminal_roles"].append(role)
            if route_id not in feature["properties"]["routes"]:
                feature["properties"]["routes"].append(route_id)

    return {"type": "FeatureCollection", "features": list(features_by_id.values())}


# ---------------------------------------------------------------------------
# Static endpoints
# ---------------------------------------------------------------------------

@router.get("/stops")
async def list_stops():
    """Return all bus stops."""
    return gtfs_static.get_stops()


@router.get("/stops/search")
async def search_stops(q: str = Query(description="停留所名、エリア、系統名で検索"), limit: int = Query(default=10, ge=1, le=50)):
    """Search stops by name, area, or route labels."""
    return gtfs_static.search_stops(q, limit)


@router.get("/routes")
async def list_routes():
    """Return all bus routes."""
    return gtfs_static.get_routes()


@router.get("/routes/lines.geojson")
async def routes_lines_geojson(routes: Optional[str] = Query(default=None, description="Comma-separated route IDs, e.g. 都01,業10")):
    """Return PoC route lines (origin->destination, stop-sequence polyline) as GeoJSON FeatureCollection."""
    route_filter = _parse_routes_param(routes)
    return _route_lines_feature_collection(route_filter)


@router.get("/routes/shapes.geojson")
async def routes_shapes_geojson(routes: Optional[str] = Query(default=None, description="Comma-separated route IDs, e.g. 都01,業10")):
    """Return shape-like route lines from ODPT busstop order as GeoJSON FeatureCollection."""
    route_list = [r.strip() for r in routes.split(",")] if routes else None
    try:
        return await gtfs_realtime.get_route_shapes_geojson(_api_key(), route_list)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"GeoJSON系統shapeを取得できませんでした: {exc}") from exc


@router.get("/routes/snapped.geojson")
async def routes_snapped_geojson(
    routes: Optional[str] = Query(default=None, description="Comma-separated route IDs, e.g. 都01,業10"),
    max_stops: int = Query(default=50, ge=2, le=150, description="Max via stops per route for ArcGIS solve"),
):
    """Return road-snapped route lines using ArcGIS Route API (fallback to shapes when unavailable)."""
    route_list = [r.strip() for r in routes.split(",")] if routes else None
    try:
        return await gtfs_realtime.get_route_snapped_geojson(_api_key(), route_list, max_stops=max_stops)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"GeoJSON道路スナップ系統を取得できませんでした: {exc}") from exc


@router.get("/routes/shapes-exact.geojson")
async def routes_shapes_exact_geojson(routes: Optional[str] = Query(default=None, description="Comma-separated route IDs or short names, e.g. 都01,業10")):
    """Return exact GTFS shapes.txt polylines as GeoJSON FeatureCollection."""
    route_list = [r.strip() for r in routes.split(",")] if routes else None
    try:
        return gtfs_shapes.get_exact_route_shapes_geojson(route_list)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=f"GTFS静的ファイル不足: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"GeoJSON厳密shapeを取得できませんでした: {exc}") from exc


@router.get("/stops/terminals.geojson")
async def terminal_stops_geojson(routes: Optional[str] = Query(default=None, description="Comma-separated route IDs, e.g. 都01,業10")):
    """Return terminal stops (origin/destination only) as GeoJSON FeatureCollection."""
    route_filter = _parse_routes_param(routes)
    return _route_terminals_feature_collection(route_filter)


@router.get("/stops/{stop_id}")
async def get_stop(stop_id: str):
    """Return a single stop with its real-time arrivals."""
    stop = gtfs_static.get_stop_by_id(stop_id)
    if stop is None:
        raise HTTPException(status_code=404, detail=f"停留所 '{stop_id}' が見つかりません。")

    realtime = await gtfs_realtime.get_station_realtime(_api_key(), stop_id)
    return {**stop, "realtime": realtime}


# ---------------------------------------------------------------------------
# Real-time endpoints
# ---------------------------------------------------------------------------

@router.get("/realtime/vehicles")
async def realtime_vehicles(routes: Optional[str] = Query(default=None, description="Comma-separated route IDs, e.g. 1,A,L")):
    """Return current vehicle positions."""
    route_list = [r.strip() for r in routes.split(",")] if routes else None
    try:
        return await gtfs_realtime.get_vehicle_positions(_api_key(), route_list)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"リアルタイムデータを取得できませんでした: {exc}") from exc


@router.get("/realtime/vehicles.geojson")
async def realtime_vehicles_geojson(routes: Optional[str] = Query(default=None, description="Comma-separated route IDs, e.g. 1,A,L")):
    """Return current vehicle positions as GeoJSON FeatureCollection."""
    route_list = [r.strip() for r in routes.split(",")] if routes else None
    try:
        vehicles = await gtfs_realtime.get_vehicle_positions(_api_key(), route_list)
        return _vehicle_feature_collection(vehicles)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"GeoJSON車両データを取得できませんでした: {exc}") from exc


@router.get("/realtime/vehicles/search")
async def search_realtime_vehicles_by_route(
    route: str = Query(description="利用者向け系統名またはGTFS route_id。例: 都01, 早77, 147"),
    limit: int = Query(default=20, ge=1, le=100),
):
    """Search current vehicle positions by user-facing route labels."""
    try:
        return await gtfs_realtime.search_vehicles_by_route(_api_key(), route, limit)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"系統別車両検索に失敗しました: {exc}") from exc


@router.get("/realtime/vehicles/nearby")
async def search_nearby_realtime_vehicles(
    lat: float = Query(description="検索中心の緯度"),
    lng: float = Query(description="検索中心の経度"),
    radius_m: int = Query(default=800, ge=50, le=5000, description="検索半径メートル"),
    limit: int = Query(default=20, ge=1, le=100),
):
    """Search current vehicle positions near a point."""
    try:
        return await gtfs_realtime.search_nearby_vehicles(_api_key(), lat, lng, radius_m, limit)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"周辺車両検索に失敗しました: {exc}") from exc


@router.get("/realtime/trip-updates")
async def realtime_trip_updates(routes: Optional[str] = Query(default=None, description="Comma-separated route IDs")):
    """Return upcoming arrival/departure predictions."""
    route_list = [r.strip() for r in routes.split(",")] if routes else None
    try:
        return await gtfs_realtime.get_trip_updates(_api_key(), route_list)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"運行更新情報を取得できませんでした: {exc}") from exc


@router.get("/realtime/alerts")
async def realtime_alerts():
    """Return active service alerts."""
    try:
        return await gtfs_realtime.get_service_alerts(_api_key())
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"運行アラートを取得できませんでした: {exc}") from exc
