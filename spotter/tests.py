import json
from datetime import datetime, timezone

from django.test import Client, SimpleTestCase


class TripApiTests(SimpleTestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        self.request = {
            "origin": "Denver, CO", "destination": "Colorado Springs, CO",
            "departure": datetime.now(timezone.utc).isoformat(), "load": 42000,
            "spacing": 25, "demo": True,
        }

    def post_trip(self):
        self.client.get("/api/session/")
        return self.client.post("/api/trip/", json.dumps(self.request), content_type="application/json",
                                headers={"X-CSRFToken": self.client.cookies["csrftoken"].value})

    def test_sample_trip_response(self):
        response = self.post_trip()
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["routes"]), 3)
        self.assertTrue(data["routes"][0]["blocked"])
        self.assertIn(data["recommended"], [2, 3])
        self.assertTrue(all(len(point["levels"]) == 49 for point in data["heat"]))

    def test_timezone_required(self):
        self.request["departure"] = "2026-12-01T12:00"
        self.assertEqual(self.post_trip().status_code, 400)

    def test_csrf_required(self):
        response = self.client.post("/api/trip/", self.request, content_type="application/json")
        self.assertEqual(response.status_code, 403)
