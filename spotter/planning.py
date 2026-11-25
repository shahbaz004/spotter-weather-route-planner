from bisect import bisect_left, bisect_right
from itertools import accumulate
from math import asin, ceil, cos, radians, sin, sqrt

METERS_PER_MILE = 1609.344
RISK_NAMES = ["Low", "Moderate", "High", "Severe", "No Travel"]


def assess(weather, load):
    if weather is None:
        return None, None
    wind, rain, snow = (weather[key] for key in ("wind", "rain", "snow"))
    wind_risk = bisect_right([25, 35, 45, 55], wind)
    reason = None
    if wind_risk == 3 and load > 30_000:
        wind_risk, reason = 4, "Wind of at least 45 mph with a load over 30,000 lb"
    elif wind_risk == 2 and load > 40_000:
        wind_risk, reason = 3, "Wind of at least 35 mph with a load over 40,000 lb"
    rain_risk = 4 if rain > 1 else bisect_right([0.1, 0.25, 0.5], rain)
    snow_risk = 4 if snow > 3 else bisect_right([0.5, 1, 2], snow)
    return max(wind_risk, rain_risk, snow_risk), reason


def distance(a, b):
    lat, other_lat = radians(a[0]), radians(b[0])
    delta_lon = radians(b[1] - a[1])
    h = sin((other_lat - lat) / 2)**2 + cos(lat) * cos(other_lat) * sin(delta_lon / 2)**2
    return 12_742_000 * asin(sqrt(min(1, h)))


def checkpoints(route, spacing, departure):
    points, progress = route["geometry"], route["progress"]
    distances = [entry[1] for entry in progress]
    end = distances[-1]
    interval = spacing * METERS_PER_MILE
    targets = [index * interval for index in range(ceil(end / interval))] + [end]
    cumulative = list(accumulate((distance(a, b) for a, b in zip(points, points[1:])), initial=0))
    result = []
    for target in targets:
        upper = min(max(1, bisect_left(distances, target)), len(progress) - 1)
        start_idx, start_m, start_time = progress[upper - 1]
        end_idx, end_m, end_time = progress[upper]
        ratio = (target - start_m) / (end_m - start_m) if end_m > start_m else 0
        position = cumulative[start_idx] + ratio * (cumulative[end_idx] - cumulative[start_idx])
        right = min(max(1, bisect_left(cumulative, position)), len(points) - 1)
        length = cumulative[right] - cumulative[right - 1]
        fraction = (position - cumulative[right - 1]) / length if length else 0
        lat = points[right - 1][0] + fraction * (points[right][0] - points[right - 1][0])
        lon_delta = (points[right][1] - points[right - 1][1] + 180) % 360 - 180
        lon = (points[right - 1][1] + fraction * lon_delta + 180) % 360 - 180
        result.append({"point": [lat, lon], "mile": target / METERS_PER_MILE,
                       "eta": round(departure + start_time + ratio * (end_time - start_time))})
    return result


def summarize(route, samples, forecast, load):
    miles = [0.0] * len(RISK_NAMES)
    for sample in samples:
        sample["weather"] = weather_at(forecast.get(grid_key(sample["point"]), {}), sample["eta"])
        sample["risk"], sample["reason"] = assess(sample["weather"], load)
    for current, following in zip(samples, samples[1:]):
        if current["risk"] is not None:
            miles[current["risk"]] += following["mile"] - current["mile"]
    complete = all(sample["risk"] is not None for sample in samples)
    blocked = any(sample["risk"] == 4 for sample in samples)
    length = samples[-1]["mile"]
    return {**route, "checkpoints": samples, "riskMiles": miles, "miles": length, "complete": complete,
            "blocked": blocked, "averageRisk": sum(i * mi for i, mi in enumerate(miles)) / length if complete else None,
            "eta": samples[-1]["eta"], "worstRisk": max((s["risk"] for s in samples if s["risk"] is not None), default=None)}


def rank(routes):
    candidates = [route for route in routes if not route["blocked"]]
    if any(not route["complete"] for route in candidates):
        return []
    return sorted(candidates, key=lambda route: (round(route["riskMiles"][3], 6),
                  round(route["riskMiles"][2], 6), round(route["averageRisk"], 8), route["seconds"]))


def grid_key(point):
    return tuple(round(value, 3) for value in point)


def weather_at(forecast, timestamp):
    hour = timestamp // 3600 * 3600
    wind = forecast.get(hour)
    precipitation = forecast.get(hour if timestamp == hour else hour + 3600)
    if wind is None or precipitation is None:
        return None
    return {"wind": wind[0], "rain": precipitation[1], "snow": precipitation[2]}
