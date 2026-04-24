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
