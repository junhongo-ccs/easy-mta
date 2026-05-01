"""
FastAPI router for GTFS static and real-time endpoints.
Prefix: /api/gtfs
"""

import os
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from services import gtfs_static, gtfs_realtime

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
