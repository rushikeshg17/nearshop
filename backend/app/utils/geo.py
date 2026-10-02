"""Distance helpers. MongoDB's 2dsphere index finds the candidates inside a circle; the exact
distance shown to customers is computed here with Haversine so it is the same number everywhere."""
import math

EARTH_RADIUS_KM = 6371.0088


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def within_km(lat: float, lng: float, radius_km: float) -> dict:
    """MongoDB filter for a GeoJSON field: points within `radius_km` of (lat, lng). Uses the 2dsphere index.
    Padded by 1% so rounding at the edge is decided by the exact Haversine check, not the index."""
    return {"$geoWithin": {"$centerSphere": [[lng, lat], (radius_km * 1.01 + 0.02) / EARTH_RADIUS_KM]}}


def bounding_box(lat: float, lng: float, radius_km: float) -> tuple[float, float, float, float]:
    """(min_lat, max_lat, min_lng, max_lng) that fully contains the radius circle."""
    dlat = math.degrees(radius_km / EARTH_RADIUS_KM)
    dlng = math.degrees(radius_km / (EARTH_RADIUS_KM * max(math.cos(math.radians(lat)), 1e-6)))
    return lat - dlat, lat + dlat, lng - dlng, lng + dlng
