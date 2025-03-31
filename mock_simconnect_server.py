"""
Mock SimConnect Server
Version: 1.1.0 (Testing Only)
DO NOT INCLUDE IN COMMERCIAL RELEASE
Last Updated: March 31, 2025
Author: Whisper Flight AI Team

This mock is for development testing only.
It emulates aircraft data and SimConnect interface compatibility.
"""

import logging
import time
import threading
import random

logger = logging.getLogger("MockSimConnect")


class MockSimConnect:
    def __init__(self):
        self.connected = True
        logger.info("✅ [MOCK] SimConnect initialized")

    def connect(self):
        logger.info("✅ [MOCK] SimConnect connected")
        return True

    def disconnect(self):
        self.connected = False
        logger.info("✅ [MOCK] SimConnect disconnected")
        return True

    def is_connected(self):
        return self.connected


class MockAircraftRequests:
    def __init__(self):
        self.aircraft_data = {
            "Latitude": 40.6892,  # Statue of Liberty
            "Longitude": -74.0445,
            "Altitude": 1500.0,
            "Heading": 90.0,
            "GroundSpeed": 100.0,
        }


class MockSimConnectServer:
    def __init__(self):
        self.sim = MockSimConnect()
        self.data = MockAircraftRequests()
        self.last_data = self.data.aircraft_data.copy()
        self.running = True

        self._thread = threading.Thread(target=self._update_loop)
        self._thread.daemon = True
        self._thread.start()

        logger.info("⚠️ [MOCK] Using simulated aircraft data")
        logger.info("✅ [MOCK] Connected via MockSimConnect")

    def _update_loop(self):
        while self.running:
            # Slight heading drift
            heading = (self.last_data["Heading"] + random.uniform(-2, 2)) % 360
            self.last_data["Heading"] = heading

            # Small lat/lon drift (fake motion)
            self.last_data["Latitude"] += random.uniform(-0.0002, 0.0002)
            self.last_data["Longitude"] += random.uniform(-0.0002, 0.0002)

            # Simulate altitude variation
            alt = self.last_data["Altitude"] + random.uniform(-10, 10)
            self.last_data["Altitude"] = max(500, min(alt, 3000))

            time.sleep(5)

    def get_aircraft_data(self):
        return self.last_data.copy()

    def get_aircraft_position(self):
        return {
            "latitude": self.last_data["Latitude"],
            "longitude": self.last_data["Longitude"],
            "altitude": self.last_data["Altitude"],
            "heading": self.last_data["Heading"],
        }

    def get_nearby_poi(self):
        # Dummy POI for test output
        return {
            "name": "Statue of Liberty",
            "latitude": self.last_data["Latitude"],
            "longitude": self.last_data["Longitude"],
            "heading": 270.0,
            "distance": 1.2,
        }

    def stop(self):
        self.running = False
        if self._thread:
            self._thread.join(timeout=1)
        logger.info("✅ [MOCK] MockSimConnect server stopped")


# Singleton export
sim_server = MockSimConnectServer()


def get_aircraft_data(force_update=False):
    return sim_server.get_aircraft_data()
