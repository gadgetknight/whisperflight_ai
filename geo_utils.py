"""
Whisper Flight AI - Geographic Utilities
Version: 5.0.1
Purpose: Handles location data, geocoding, and navigation calculations
Last Updated: March 31, 2025
Author: Your Name

Changes in v5.0.1:
- Clears reverse geocode cache on startup to avoid stale location name reuse
"""

import os
import math
import time
import logging
import sqlite3
import threading
from functools import lru_cache
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderUnavailable
from config_manager import config


class GeoUtils:
    """Geographic utilities for flight navigation and location information."""

    def __init__(self):
        self.logger = logging.getLogger("GeoUtils")
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        self.db_path = os.path.join(self.script_dir, "geo_cache.db")
        self.lock = threading.RLock()

        user_agent = f"WhisperFlightAI/{config.get('Version', 'app_version', '5.0.0')}"
        self.geolocator = Nominatim(user_agent=user_agent, timeout=5)

        self.max_cache_size = config.getint("SimConnect", "geo_cache_size", 50)

        self.geo_cache = {
            "the alamo": (29.4252, -98.4861),
            "san antonio international airport": (29.533958, -98.469056),
            "atlantic city": (39.3642852, -74.4229351),
            "golden nugget": (39.3801, -74.4282),
            "philadelphia": (39.9525839, -75.1652215),
            "philly": (39.9525839, -75.1652215),
            "philadelphia international airport": (39.875018, -75.2352128),
            "empire state building": (40.7484, -73.9857),
            "statue of liberty": (40.6892, -74.0445),
            "grand canyon": (36.0544, -112.2583),
            "golden gate bridge": (37.8199, -122.4783),
        }

        self._init_db()
        self.clear_reverse_cache_on_startup()

    def clear_reverse_cache_on_startup(self):
        try:
            with self.lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM reverse_cache")
                    conn.commit()
            self.logger.info("✅ Reverse geocode cache cleared on startup.")
        except Exception as e:
            self.logger.warning(f"⚠️ Failed to clear reverse cache: {e}")

    def _init_db(self):
        try:
            with self.lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        CREATE TABLE IF NOT EXISTS geocode_cache (
                            query TEXT PRIMARY KEY,
                            latitude REAL,
                            longitude REAL,
                            display_name TEXT,
                            timestamp INTEGER
                        )
                    """
                    )
                    cursor.execute(
                        """
                        CREATE TABLE IF NOT EXISTS reverse_cache (
                            lat_key REAL,
                            lon_key REAL,
                            display_name TEXT,
                            timestamp INTEGER,
                            PRIMARY KEY (lat_key, lon_key)
                        )
                    """
                    )
                    conn.commit()
            self.logger.info(f"Geocoding cache database initialized at {self.db_path}")
        except Exception as e:
            self.logger.error(f"Error initializing geocoding database: {e}")

    def geocode(self, location_name, country_hint=None):
        if not location_name:
            return None, None, None

        query = location_name.lower().strip()

        if query in self.geo_cache:
            lat, lon = self.geo_cache[query]
            self.logger.info(f"Geocode cache hit for '{query}'")
            return lat, lon, query

        try:
            with self.lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT latitude, longitude, display_name FROM geocode_cache WHERE query = ?",
                        (query,),
                    )
                    result = cursor.fetchone()
                    if result:
                        lat, lon, display_name = result
                        if len(self.geo_cache) >= self.max_cache_size:
                            self.geo_cache.pop(next(iter(self.geo_cache)))
                        self.geo_cache[query] = (lat, lon)
                        self.logger.info(f"Geocode DB cache hit for '{query}'")
                        return lat, lon, display_name
        except Exception as e:
            self.logger.error(f"Error checking geocode cache: {e}")

        try:
            geocode_query = query
            if country_hint:
                geocode_query = f"{query}, {country_hint}"

            location = self.geolocator.geocode(geocode_query, exactly_one=True)
            if location:
                lat, lon = location.latitude, location.longitude
                display_name = location.address
                if len(self.geo_cache) >= self.max_cache_size:
                    self.geo_cache.pop(next(iter(self.geo_cache)))
                self.geo_cache[query] = (lat, lon)
                with self.lock:
                    with sqlite3.connect(self.db_path) as conn:
                        cursor = conn.cursor()
                        cursor.execute(
                            "INSERT OR REPLACE INTO geocode_cache VALUES (?, ?, ?, ?, ?)",
                            (query, lat, lon, display_name, int(time.time())),
                        )
                        conn.commit()
                self.logger.info(f"Geocoded '{query}' to {lat}, {lon}")
                return lat, lon, display_name
            else:
                self.logger.warning(f"Could not geocode '{query}'")
                return None, None, None
        except (GeocoderTimedOut, GeocoderUnavailable) as e:
            self.logger.error(f"Geocoding error for '{query}': {e}")
            return None, None, None

    def reverse_geocode(self, latitude, longitude):
        if latitude is None or longitude is None:
            return "Unknown location"

        lat_key = round(latitude, 5)
        lon_key = round(longitude, 5)

        try:
            with self.lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT display_name FROM reverse_cache WHERE lat_key = ? AND lon_key = ?",
                        (lat_key, lon_key),
                    )
                    result = cursor.fetchone()
                    if result:
                        self.logger.info(
                            f"Reverse geocode cache hit for {lat_key}, {lon_key}"
                        )
                        return result[0]
        except Exception as e:
            self.logger.error(f"Error checking reverse geocode cache: {e}")

        try:
            location = self.geolocator.reverse((latitude, longitude), language="en")
            if location:
                display_name = location.address
                with self.lock:
                    with sqlite3.connect(self.db_path) as conn:
                        cursor = conn.cursor()
                        cursor.execute(
                            "INSERT OR REPLACE INTO reverse_cache VALUES (?, ?, ?, ?)",
                            (lat_key, lon_key, display_name, int(time.time())),
                        )
                        conn.commit()
                self.logger.info(
                    f"Reverse geocoded {latitude}, {longitude} to '{display_name}'"
                )
                return display_name
            else:
                self.logger.warning(
                    f"Could not reverse geocode {latitude}, {longitude}"
                )
                return "Unknown location"
        except (GeocoderTimedOut, GeocoderUnavailable) as e:
            self.logger.error(
                f"Reverse geocoding error for {latitude}, {longitude}: {e}"
            )
            return "Unknown location"

    def calculate_heading_distance(self, lat1, lon1, lat2, lon2):
        try:
            lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
            dlon = lon2 - lon1
            y = math.sin(dlon) * math.cos(lat2)
            x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(
                lat2
            ) * math.cos(dlon)
            heading = math.degrees(math.atan2(y, x))
            heading = (heading + 360) % 360
            R = 3440.1
            dlat = lat2 - lat1
            a = (
                math.sin(dlat / 2) ** 2
                + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
            )
            c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
            distance = R * c
            return heading, distance
        except Exception as e:
            self.logger.error(f"Error calculating heading/distance: {e}")
            return None, None

    def get_nearest_poi(self, latitude, longitude, max_distance=50):
        nearest_poi = None
        nearest_distance = float("inf")
        nearest_heading = None

        for poi_name, (poi_lat, poi_lon) in self.geo_cache.items():
            heading, distance = self.calculate_heading_distance(
                latitude, longitude, poi_lat, poi_lon
            )
            if (
                distance is not None
                and distance < nearest_distance
                and distance < max_distance
            ):
                nearest_poi = poi_name
                nearest_distance = distance
                nearest_heading = heading

        if nearest_poi:
            return nearest_poi, nearest_heading, nearest_distance
        else:
            return None, None, None

    def clear_old_cache_entries(self, max_age_days=30):
        try:
            current_time = int(time.time())
            max_age_seconds = max_age_days * 86400
            cutoff_time = current_time - max_age_seconds

            with self.lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "DELETE FROM geocode_cache WHERE timestamp < ?", (cutoff_time,)
                    )
                    geocode_deleted = cursor.rowcount
                    cursor.execute(
                        "DELETE FROM reverse_cache WHERE timestamp < ?", (cutoff_time,)
                    )
                    reverse_deleted = cursor.rowcount
                    conn.commit()

            self.logger.info(
                f"Cleared {geocode_deleted} geocode and {reverse_deleted} reverse geocode old cache entries"
            )
        except Exception as e:
            self.logger.error(f"Error clearing old cache entries: {e}")


geo_utils = GeoUtils()
