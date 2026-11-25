import unittest

from spotter.planning import METERS_PER_MILE, assess, checkpoints, grid_key, rank, summarize, weather_at
from spotter.providers import sample_forecast, sample_routes


class PlanningTests(unittest.TestCase):
    def test_shared_thresholds_and_strict_stops(self):
        for rain, snow, expected in [(0.10, 0, 1), (0.25, 0, 2), (0.50, 0, 3), (1, 0, 3),
                                     (1.001, 0, 4), (0, 0.5, 1), (0, 1, 2), (0, 2, 3),
                                     (0, 3, 3), (0, 3.001, 4)]:
            with self.subTest(rain=rain, snow=snow):
                self.assertEqual(assess({"wind": 0, "rain": rain, "snow": snow}, 0)[0], expected)

    def test_load_boundaries(self):
        for wind, load, expected in [(25, 0, 1), (35, 40_000, 2), (35, 40_001, 3),
                                     (45, 30_000, 3), (45, 30_001, 4), (55, 0, 4)]:
            with self.subTest(wind=wind, load=load):
                self.assertEqual(assess({"wind": wind, "rain": 0, "snow": 0}, load)[0], expected)

    def test_checkpoints_follow_provider_timing(self):
        route = {"geometry": [[0, 0], [0, 1], [0, 2]], "progress": [
            (0, 0, 0), (1, 25 * METERS_PER_MILE, 1200), (2, 52 * METERS_PER_MILE, 3600),
        ]}
        result = checkpoints(route, 25, 0)
        self.assertEqual([round(sample["mile"]) for sample in result], [0, 25, 50, 52])
        self.assertEqual(result[1]["eta"], 1200)
        self.assertEqual(result[-1]["eta"], 3600)
        self.assertEqual(result[-1]["point"], [0, 2])

    def test_precipitation_uses_hour_covering_arrival(self):
        self.assertEqual(weather_at({0: (10, 0, 0), 3600: (20, 0.3, 1)}, 1800),
                         {"wind": 10, "rain": 0.3, "snow": 1})

    def test_demo_excludes_fastest_route_and_avoids_incomplete_comparison(self):
        routes, _, _ = sample_routes()
        samples = [checkpoints(route, 25, 1800) for route in routes]
        weather = sample_forecast({grid_key(s["point"]) for group in samples for s in group}, 1800)
        scored = [summarize(route, group, weather, 42_000) for route, group in zip(routes, samples)]
        self.assertTrue(scored[0]["blocked"])
        self.assertGreater(rank(scored)[0]["seconds"], scored[0]["seconds"])
        scored[-1]["complete"] = False
        self.assertEqual(rank(scored), [])

    def test_severe_miles_take_precedence_over_high_miles_and_time(self):
        a = {"blocked": False, "complete": True, "riskMiles": [0, 0, 10, 0, 0],
             "averageRisk": 2, "seconds": 200}
        b = {**a, "riskMiles": [0, 0, 0, 1, 0], "averageRisk": 1, "seconds": 10}
        self.assertEqual(rank([b, a]), [a, b])
