"""
GTFS static data service.
Provides in-memory sample dataset of NYC subway stops and routes.
"""

from typing import Optional

# NYC Subway stops: key stations with lat/lng and route assignments
_STOPS: list[dict] = [
    {"stop_id": "127", "stop_name": "Times Sq-42 St", "stop_lat": 40.755983, "stop_lon": -73.987495, "routes": ["1", "2", "3", "7", "N", "Q", "R", "W", "S"], "wheelchair_accessible": True},
    {"stop_id": "631", "stop_name": "Grand Central-42 St", "stop_lat": 40.751776, "stop_lon": -73.976848, "routes": ["4", "5", "6", "7", "S"], "wheelchair_accessible": True},
    {"stop_id": "A27", "stop_name": "Penn Station (34 St)", "stop_lat": 40.750373, "stop_lon": -73.991057, "routes": ["A", "C", "E"], "wheelchair_accessible": True},
    {"stop_id": "120", "stop_name": "34 St-Penn Station", "stop_lat": 40.750568, "stop_lon": -73.993519, "routes": ["1", "2", "3"], "wheelchair_accessible": True},
    {"stop_id": "635", "stop_name": "Union Sq-14 St", "stop_lat": 40.735736, "stop_lon": -73.990562, "routes": ["4", "5", "6", "N", "Q", "R", "W", "L"], "wheelchair_accessible": True},
    {"stop_id": "A32", "stop_name": "Fulton St", "stop_lat": 40.709092, "stop_lon": -74.007605, "routes": ["A", "C", "J", "Z", "2", "3", "4", "5"], "wheelchair_accessible": True},
    {"stop_id": "R11", "stop_name": "Canal St", "stop_lat": 40.719527, "stop_lon": -74.000443, "routes": ["N", "Q", "R", "W", "J", "Z", "6"], "wheelchair_accessible": False},
    {"stop_id": "229", "stop_name": "72 St (Upper West Side)", "stop_lat": 40.775594, "stop_lon": -73.981963, "routes": ["1", "2", "3"], "wheelchair_accessible": True},
    {"stop_id": "621", "stop_name": "68 St-Hunter College", "stop_lat": 40.768141, "stop_lon": -73.963998, "routes": ["6"], "wheelchair_accessible": True},
    {"stop_id": "A09", "stop_name": "125 St (Harlem)", "stop_lat": 40.811109, "stop_lon": -73.952908, "routes": ["A", "B", "C", "D"], "wheelchair_accessible": True},
    {"stop_id": "D14", "stop_name": "47-50 Sts-Rockefeller Ctr", "stop_lat": 40.758663, "stop_lon": -73.981329, "routes": ["B", "D", "F", "M"], "wheelchair_accessible": True},
    {"stop_id": "A24", "stop_name": "59 St-Columbus Circle", "stop_lat": 40.768296, "stop_lon": -73.981736, "routes": ["A", "B", "C", "D", "1"], "wheelchair_accessible": True},
    {"stop_id": "G22", "stop_name": "Court Sq-23 St (Queens)", "stop_lat": 40.747023, "stop_lon": -73.945264, "routes": ["E", "G", "M", "7"], "wheelchair_accessible": True},
    {"stop_id": "702", "stop_name": "Mets-Willets Point", "stop_lat": 40.754622, "stop_lon": -73.845650, "routes": ["7"], "wheelchair_accessible": True},
    {"stop_id": "F18", "stop_name": "West 4 St-Wash Sq", "stop_lat": 40.732338, "stop_lon": -74.000495, "routes": ["A", "C", "E", "B", "D", "F", "M"], "wheelchair_accessible": False},
    {"stop_id": "L06", "stop_name": "Bedford Av", "stop_lat": 40.717304, "stop_lon": -73.956872, "routes": ["L"], "wheelchair_accessible": False},
    {"stop_id": "R20", "stop_name": "City Hall", "stop_lat": 40.713282, "stop_lon": -74.007978, "routes": ["R", "W"], "wheelchair_accessible": False},
    {"stop_id": "142", "stop_name": "South Ferry", "stop_lat": 40.702068, "stop_lon": -74.013664, "routes": ["1"], "wheelchair_accessible": True},
    {"stop_id": "A55", "stop_name": "Howard Beach-JFK Airport", "stop_lat": 40.660476, "stop_lon": -73.830301, "routes": ["A"], "wheelchair_accessible": True},
    {"stop_id": "G08", "stop_name": "Church Av (Brooklyn)", "stop_lat": 40.644041, "stop_lon": -73.979678, "routes": ["F", "G"], "wheelchair_accessible": False},
    {"stop_id": "D43", "stop_name": "Coney Island-Stillwell Av", "stop_lat": 40.577422, "stop_lon": -73.981233, "routes": ["B", "D", "F", "N", "Q"], "wheelchair_accessible": True},
    {"stop_id": "H01", "stop_name": "Broad Channel", "stop_lat": 40.608382, "stop_lon": -73.816023, "routes": ["A", "S"], "wheelchair_accessible": False},
    {"stop_id": "237", "stop_name": "Van Cortlandt Park-242 St", "stop_lat": 40.889248, "stop_lon": -73.898583, "routes": ["1"], "wheelchair_accessible": False},
    {"stop_id": "415", "stop_name": "Woodlawn", "stop_lat": 40.886037, "stop_lon": -73.878750, "routes": ["4"], "wheelchair_accessible": False},
    {"stop_id": "501", "stop_name": "Eastchester-Dyre Av", "stop_lat": 40.888241, "stop_lon": -73.830834, "routes": ["5"], "wheelchair_accessible": False},
    {"stop_id": "J27", "stop_name": "Jamaica Center-Parsons/Archer", "stop_lat": 40.702566, "stop_lon": -73.801109, "routes": ["E", "J", "Z"], "wheelchair_accessible": True},
    {"stop_id": "N02", "stop_name": "Astoria-Ditmars Blvd", "stop_lat": 40.775036, "stop_lon": -73.912034, "routes": ["N", "W"], "wheelchair_accessible": False},
    {"stop_id": "R01", "stop_name": "Forest Hills-71 Av", "stop_lat": 40.721691, "stop_lon": -73.844521, "routes": ["E", "F", "M", "R"], "wheelchair_accessible": False},
    {"stop_id": "L29", "stop_name": "Canarsie-Rockaway Pkwy", "stop_lat": 40.646654, "stop_lon": -73.901949, "routes": ["L"], "wheelchair_accessible": False},
    {"stop_id": "F01", "stop_name": "Jamaica-179 St", "stop_lat": 40.712968, "stop_lon": -73.783041, "routes": ["F"], "wheelchair_accessible": True},
]

# NYC Subway routes with official MTA colors
_ROUTES: list[dict] = [
    {"route_id": "1", "route_name": "1 Train", "route_color": "EE352E", "route_text_color": "FFFFFF"},
    {"route_id": "2", "route_name": "2 Train", "route_color": "EE352E", "route_text_color": "FFFFFF"},
    {"route_id": "3", "route_name": "3 Train", "route_color": "EE352E", "route_text_color": "FFFFFF"},
    {"route_id": "4", "route_name": "4 Train", "route_color": "00933C", "route_text_color": "FFFFFF"},
    {"route_id": "5", "route_name": "5 Train", "route_color": "00933C", "route_text_color": "FFFFFF"},
    {"route_id": "6", "route_name": "6 Train", "route_color": "00933C", "route_text_color": "FFFFFF"},
    {"route_id": "7", "route_name": "7 Train", "route_color": "B933AD", "route_text_color": "FFFFFF"},
    {"route_id": "A", "route_name": "A Train", "route_color": "0039A6", "route_text_color": "FFFFFF"},
    {"route_id": "C", "route_name": "C Train", "route_color": "0039A6", "route_text_color": "FFFFFF"},
    {"route_id": "E", "route_name": "E Train", "route_color": "0039A6", "route_text_color": "FFFFFF"},
    {"route_id": "B", "route_name": "B Train", "route_color": "FF6319", "route_text_color": "FFFFFF"},
    {"route_id": "D", "route_name": "D Train", "route_color": "FF6319", "route_text_color": "FFFFFF"},
    {"route_id": "F", "route_name": "F Train", "route_color": "FF6319", "route_text_color": "FFFFFF"},
    {"route_id": "M", "route_name": "M Train", "route_color": "FF6319", "route_text_color": "FFFFFF"},
    {"route_id": "N", "route_name": "N Train", "route_color": "FCCC0A", "route_text_color": "000000"},
    {"route_id": "Q", "route_name": "Q Train", "route_color": "FCCC0A", "route_text_color": "000000"},
    {"route_id": "R", "route_name": "R Train", "route_color": "FCCC0A", "route_text_color": "000000"},
    {"route_id": "W", "route_name": "W Train", "route_color": "FCCC0A", "route_text_color": "000000"},
    {"route_id": "L", "route_name": "L Train", "route_color": "A7A9AC", "route_text_color": "000000"},
    {"route_id": "G", "route_name": "G Train", "route_color": "6CBE45", "route_text_color": "000000"},
    {"route_id": "J", "route_name": "J Train", "route_color": "996633", "route_text_color": "FFFFFF"},
    {"route_id": "Z", "route_name": "Z Train", "route_color": "996633", "route_text_color": "FFFFFF"},
    {"route_id": "S", "route_name": "S Shuttle", "route_color": "808183", "route_text_color": "FFFFFF"},
]

_stops_by_id: dict[str, dict] = {s["stop_id"]: s for s in _STOPS}


def get_stops() -> list[dict]:
    """Return all static subway stops."""
    return list(_STOPS)


def get_routes() -> list[dict]:
    """Return all subway routes."""
    return list(_ROUTES)


def get_stop_by_id(stop_id: str) -> Optional[dict]:
    """Return a single stop by its stop_id, or None if not found."""
    return _stops_by_id.get(stop_id)
