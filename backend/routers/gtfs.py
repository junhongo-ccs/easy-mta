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
    return os.getenv("MTA_API_KEY") or None


# ---------------------------------------------------------------------------
# Static endpoints
# ---------------------------------------------------------------------------

@router.get("/stops")
async def list_stops():
    """Return all subway stops."""
    return gtfs_static.get_stops()


@router.get("/routes")
async def list_routes():
    """Return all subway routes."""
    return gtfs_static.get_routes()


@router.get("/stops/{stop_id}")
async def get_stop(stop_id: str):
    """Return a single stop with its real-time arrivals."""
    stop = gtfs_static.get_stop_by_id(stop_id)
    if stop is None:
        raise HTTPException(status_code=404, detail=f"Stop '{stop_id}' が見つかりません。")

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
        raise HTTPException(status_code=503, detail=f"MTAリアルタイムデータを取得できませんでした: {exc}") from exc


@router.get("/realtime/trip-updates")
async def realtime_trip_updates(routes: Optional[str] = Query(default=None, description="Comma-separated route IDs")):
    """Return upcoming arrival/departure predictions."""
    route_list = [r.strip() for r in routes.split(",")] if routes else None
    try:
        return await gtfs_realtime.get_trip_updates(_api_key(), route_list)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"MTAトリップ更新を取得できませんでした: {exc}") from exc


@router.get("/realtime/alerts")
async def realtime_alerts():
    """Return active service alerts."""
    try:
        return await gtfs_realtime.get_service_alerts(_api_key())
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"MTAサービスアラートを取得できませんでした: {exc}") from exc
