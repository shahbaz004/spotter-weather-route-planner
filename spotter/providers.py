import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import urlopen

from .planning import distance


class ProviderError(Exception):
    pass


def request_json(url, parameters, service):
    try:
        with urlopen(f"{url}?{urlencode(parameters, doseq=True)}", timeout=24) as response:
            return json.load(response)
    except (HTTPError, URLError, TimeoutError, ValueError):
        raise ProviderError(f"{service} is unavailable. Please try again.") from None


def geocode(query, key):
    response = request_json(
        f"https://api.tomtom.com/search/2/geocode/{quote(query, safe='')}.json",
        {"key": key, "limit": 1}, "Geocoding")
    if not response["results"]:
        raise ValueError(f"No location found for {query}.")
    result = response["results"][0]
    point = result["position"]
    return f'{point["lat"]},{point["lon"]}', result["address"]["freeformAddress"]


TRACTOR_TRAILER_TARE_LB = 32_000
LB_TO_KG = 0.45359237


def live_routes(origin, destination, departure, load=0):
    key = os.getenv("TOMTOM_API_KEY")
    if not key:
        raise ProviderError("Live routing requires a TomTom API key. Use the sample trip to explore the planner.")
    with ThreadPoolExecutor(max_workers=2) as pool:
        start = pool.submit(geocode, origin, key)
        finish = pool.submit(geocode, destination, key)
        a, origin_label = start.result()
        b, destination_label = finish.result()
    if a == b:
        raise ValueError("Choose different origin and destination locations.")
    result = request_json(f"https://api.tomtom.com/routing/1/calculateRoute/{a}:{b}/json", {
        "key": key, "maxAlternatives": 5, "travelMode": "truck", "vehicleCommercial": "true",
        "vehicleWeight": round((TRACTOR_TRAILER_TARE_LB + load) * LB_TO_KG),
        "departAt": datetime.fromtimestamp(departure, timezone.utc).isoformat(),
        "extendedRouteRepresentation": ["distance", "travelTime"],
    }, "Truck routing")
    routes = []
    seen = set()
    for item in result.get("routes", []):
        points = [[point["latitude"], point["longitude"]] for point in item["legs"][0]["points"]]
        signature = tuple(tuple(point) for point in points)
        if signature in seen or len(points) < 2 or item["summary"]["lengthInMeters"] <= 0:
            continue
        seen.add(signature)
        if len(routes) == 3:
            break
        routes.append({"id": len(routes) + 1, "geometry": points, "seconds": item["summary"]["travelTimeInSeconds"],
                       "progress": [(p["pointIndex"], p["distanceInMeters"], p["travelTimeInSeconds"])
                                    for p in item["progress"]]})
    if not routes:
        raise ValueError("No truck routes were found for this trip.")
    return routes, origin_label, destination_label


def forecast_batch(points):
    data = request_json("https://api.open-meteo.com/v1/forecast", {
        "latitude": ",".join(str(p[0]) for p in points),
        "longitude": ",".join(str(p[1]) for p in points),
        "hourly": "wind_speed_10m,rain,showers,snowfall",
        "wind_speed_unit": "mph", "timeformat": "unixtime", "forecast_days": 7,
    }, "Weather forecast")
    locations = data if isinstance(data, list) else [data]
    result = {}
    for point, location in zip(points, locations):
        hour = location["hourly"]
        result[point] = {
            t: (wind, (rain + showers) / 25.4, snow / 2.54)
            for t, wind, rain, showers, snow in zip(hour["time"], hour["wind_speed_10m"], hour["rain"],
                                                 hour["showers"], hour["snowfall"])
            if None not in (wind, rain, showers, snow)
        }
    return result


def live_forecast(points):
    from django.core.cache import cache

    keys = {point: f"forecast:{point[0]}:{point[1]}" for point in points}
    cached = cache.get_many(keys.values())
    result = {point: cached[key] for point, key in keys.items() if key in cached}
    missing = [point for point in points if point not in result]
    with ThreadPoolExecutor(max_workers=4) as pool:
        batches = [missing[i:i + 60] for i in range(0, len(missing), 60)]
        for batch in pool.map(forecast_batch, batches):
            result.update(batch)
            cache.set_many({keys[point]: data for point, data in batch.items()}, timeout=900)
    return result


def sample_routes():
    start, end = [39.739, -104.99], [38.833, -104.821]
    paths = [
        [start, [39.612, -104.902], [39.372, -104.859], [39.073, -104.86], end],
        [start, [39.654, -105.18], [39.384, -105.348], [39.093, -105.125], [38.94, -105.016], end],
        [start, [39.72, -104.655], [39.354, -104.665], [39.219, -104.537], [38.961, -104.604], end],
    ]
    routes = []
    for index, (path, minutes) in enumerate(zip(paths, [69, 97, 88]), 1):
        meters = 0
        progress = [(0, 0, 0)]
        for point_index, (a, b) in enumerate(zip(path, path[1:]), 1):
            meters += distance(a, b)
            progress.append((point_index, meters, 0))
        routes.append({"id": index, "geometry": path, "seconds": minutes * 60,
                       "progress": [(i, m, m / meters * minutes * 60) for i, m, _ in progress]})
    return routes, "Denver, CO", "Colorado Springs, CO"


def sample_forecast(points, departure):
    from math import exp, sin

    start = int(departure) // 3600 * 3600
    return {point: {
        start + h * 3600: (
            14 + 36 * exp(-((point[1] + 104.84 - 0.05 * sin(h / 7)) / 0.125)**2)
            * exp(-((point[0] - 39.33) / 0.48)**2),
            0.42 * exp(-((point[1] + 104.57 + 0.075 * sin(h / 5)) / 0.14)**2),
            0.0,
        ) for h in range(51)
    } for point in points}
