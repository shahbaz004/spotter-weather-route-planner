import json
from datetime import datetime, timezone
from math import isfinite

from django.http import JsonResponse
from django.urls import path
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from .planning import assess, checkpoints, grid_key, rank, summarize, weather_at
from .providers import ProviderError, live_forecast, live_routes, sample_forecast, sample_routes


@require_GET
@ensure_csrf_cookie
def session(request):
    return JsonResponse({"ready": True})


@require_POST
def trip(request):
    try:
        payload = json.loads(request.body)
        if not isinstance(payload, dict):
            raise ValueError("Provide trip details as a JSON object.")
        departure = datetime.fromisoformat(payload.get("departure", ""))
        if departure.tzinfo is None:
            raise ValueError("Include a timezone with departure.")
        departure = round(departure.timestamp())
        now = datetime.now(timezone.utc).timestamp()
        demo = payload.get("demo") is True
        if not demo and not now - 120 <= departure <= now + 4 * 86400:
            raise ValueError("Choose a departure from now through the next four days.")
        load = float(payload.get("load", -1))
        spacing = payload.get("spacing")
        if not isfinite(load) or load < 0 or spacing not in (10, 25, 50):
            raise ValueError("Enter a nonnegative load and choose a checkpoint interval.")
        origin, destination = (payload.get(field, "") for field in ("origin", "destination"))
        if not all(isinstance(value, str) and 0 < len(value.strip()) <= 160 for value in (origin, destination)):
            raise ValueError("Enter an origin and destination of up to 160 characters each.")
        routes, origin, destination = (sample_routes() if demo else
                                       live_routes(origin.strip(), destination.strip(), departure, load))
        sampled = [checkpoints(route, spacing, departure) for route in routes]
        corridor = [checkpoints(route, max(10, min(25, spacing)), departure) for route in routes]
        heat_points = list(dict.fromkeys(grid_key(s["point"]) for samples in corridor for s in samples))
        points = list(dict.fromkeys([*heat_points, *(grid_key(s["point"]) for samples in sampled for s in samples)]))
        forecasts = sample_forecast(points, departure) if demo else live_forecast(points)
        scored = [summarize(route, samples, forecasts, load) for route, samples in zip(routes, sampled)]
        ranked = rank(scored)
        for route in scored:
            del route["progress"]
        return JsonResponse({
            "routes": scored, "recommended": ranked[0]["id"] if ranked else None,
            "departure": departure, "origin": origin, "destination": destination, "demo": demo,
            "heat": [{"point": point, "levels": [
                assess(weather_at(forecasts.get(point, {}), departure + hour * 3600), load)[0]
                for hour in range(49)
            ]} for point in heat_points],
        })
    except (TypeError, ValueError) as exc:
        return JsonResponse({"error": str(exc) or "Invalid trip details."}, status=400)
    except ProviderError as exc:
        return JsonResponse({"error": str(exc)}, status=502)
    except (KeyError, IndexError):
        return JsonResponse({"error": "A provider returned incomplete data. Please try again."}, status=502)


urlpatterns = [path("api/session/", session), path("api/trip/", trip)]
