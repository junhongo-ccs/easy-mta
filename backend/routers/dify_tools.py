"""
OpenAPI schema endpoint for Dify Cloud custom tool import.
"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/dify-tools-openapi.json", include_in_schema=False)
async def dify_tools_openapi():
    return {
        "openapi": "3.0.0",
        "info": {"title": "Toei Bus Tools", "version": "1.0.0"},
        "servers": [{"url": "https://easy-mta-production.up.railway.app"}],
        "paths": {
            "/api/gtfs/stops/search": {
                "get": {
                    "operationId": "search_stops",
                    "summary": "Search bus stops",
                    "parameters": [
                        {
                            "name": "q",
                            "in": "query",
                            "required": True,
                            "schema": {"type": "string"},
                            "description": "Stop name or area name.",
                        },
                        {
                            "name": "limit",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "integer", "default": 5},
                        },
                    ],
                    "responses": {
                        "200": {
                            "description": "OK",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "array",
                                        "items": {"type": "object"},
                                    }
                                }
                            },
                        }
                    },
                }
            },
            "/api/gtfs/realtime/vehicles/search": {
                "get": {
                    "operationId": "search_vehicles_by_route",
                    "summary": "Search live vehicles by route",
                    "parameters": [
                        {
                            "name": "route",
                            "in": "query",
                            "required": True,
                            "schema": {"type": "string"},
                            "description": "Route name, destination, or internal route id.",
                        },
                        {
                            "name": "limit",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "integer", "default": 5},
                        },
                    ],
                    "responses": {
                        "200": {
                            "description": "OK",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "array",
                                        "items": {"type": "object"},
                                    }
                                }
                            },
                        }
                    },
                }
            },
            "/api/gtfs/realtime/vehicles/nearby": {
                "get": {
                    "operationId": "search_nearby_vehicles",
                    "summary": "Search live vehicles near a point",
                    "parameters": [
                        {
                            "name": "lat",
                            "in": "query",
                            "required": True,
                            "schema": {"type": "number"},
                        },
                        {
                            "name": "lng",
                            "in": "query",
                            "required": True,
                            "schema": {"type": "number"},
                        },
                        {
                            "name": "radius_m",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "integer", "default": 900},
                        },
                        {
                            "name": "limit",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "integer", "default": 5},
                        },
                    ],
                    "responses": {
                        "200": {
                            "description": "OK",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "array",
                                        "items": {"type": "object"},
                                    }
                                }
                            },
                        }
                    },
                }
            },
        },
    }
