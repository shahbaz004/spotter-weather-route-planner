# Spotter weather route planner

React and Django compare commercial truck routes using predicted weather at the driver's arrival time. The sample trip uses simulated routes and weather and works without provider credentials.

## Run locally

Use Python 3.12 and Node 22.12 or newer.

```sh
python -m venv .venv
.venv/bin/pip install -r requirements.txt
npm install
DJANGO_DEBUG=1 .venv/bin/python manage.py runserver
```

In another terminal, run `npm run dev` and open http://localhost:5173. Select **Load sample trip** for Denver to Colorado Springs. For live planning, set `TOMTOM_API_KEY` in the Django process environment. Basemap tiles require internet access.

## How routing and weather work

- TomTom geocodes both endpoints and calculates a commercial truck route, requesting up to five alternatives and keeping the first three distinct ones. It can return fewer when it cannot find three distinct routes. The entered cargo weight affects weather rules and, added to an assumed 32,000 lb tractor-trailer tare weight, is sent as `vehicleWeight` for road restrictions. Vehicle dimensions are outside the trip form.
- The backend samples route progress at 10, 25, or 50 miles and at the destination. Location and ETA are interpolated using the route geometry and provider cumulative travel times.
- Open-Meteo hourly wind uses mph. Rain includes showers and is converted from millimeters to inches. Snow depth is converted from centimeters to inches. Wind uses the latest forecast hour at each ETA, and precipitation uses the hourly accumulation covering that ETA. Forecast requests are batched and cached for 15 minutes. Live departures are limited to the next four days to leave room for the 48-hour view within the seven-day forecast. The browser displays times in its local timezone.
- Checkpoint risk is the highest severity among wind, rain and snow after applying the load rules. Shared rain and snow thresholds enter the higher tier, with the exception of the strictly greater-than No Travel limits. Severity applies to the following segment for mileage and average risk. A No Travel checkpoint makes a route ineligible, including at the destination. If an otherwise eligible route is missing some weather, the planner withholds its recommendation.
- Eligible routes are ordered by Severe miles, High miles, distance-weighted average risk, and travel time. The heatmap visualizes relative risk intensity along the sampled corridor at departure plus the selected hour. The slider reuses the forecast data already loaded, and checkpoint details always use arrival time.

Provider references are [TomTom Routing](https://docs.tomtom.com/routing-api/documentation/tomtom-maps/v1/calculate-route), [Open-Meteo](https://open-meteo.com/en/docs), and [OpenStreetMap](https://www.openstreetmap.org/copyright).

## Test and deploy

```sh
python -m unittest spotter.test_planning
DJANGO_DEBUG=1 .venv/bin/python manage.py test spotter
npm run build
docker build -t spotter-planner .
```

Deploy the Dockerfile as a web service. Set `DJANGO_SECRET_KEY` to a long random secret, `DJANGO_ALLOWED_HOSTS` to the hosted hostname, and `TOMTOM_API_KEY` for live routing. The container serves the React build and API on the same origin. Use `GET /api/session/` for a health check. The host can supply `PORT`; it defaults to 8000.

## Walkthrough

1. Load the sample and compare the recommended detour to the quicker direct route.
2. Select route lines and checkpoints. Show the arrival time, weather readings, and load override.
3. Move the forecast slider from departure to +48 hours and explain the difference between forecast hour and checkpoint ETA.
4. Run a live trip, point out the handling of missing alternatives or forecasts, and summarize the recommendation order.
