"""
Whisper Flight AI - Geographic Utilities
Version: 5.0.0
Purpose: Handles location data, geocoding, and navigation calculations
Last Updated: March 25, 2025, 09:00 UTC
Author: Your Name

This module provides geographic utilities for the AI Flight Tour Guide,
including geocoding, distance/heading calculations, and location caching.
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
        
        # Initialize geolocator with increased timeout
        user_agent = f"WhisperFlightAI/{config.get('Version', 'app_version', '5.0.0')}"
        self.geolocator = Nominatim(user_agent=user_agent, timeout=5)
        
        # Maximum entries in the in-memory cache
        self.max_cache_size = config.getint("SimConnect", "geo_cache_size", 50)
        
        # Initialize in-memory cache with common POIs
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
            "golden gate bridge": (37.8199, -122.4783)
        }
        
        # Initialize the database
        self._init_db()
    
    def _init_db(self):
        """Initialize the geocoding cache database."""
        try:
            with self.lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    # Create the geocoding cache table if it doesn't exist
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS geocode_cache (
                            query TEXT PRIMARY KEY,
                            latitude REAL,
                            longitude REAL,
                            display_name TEXT,
                            timestamp INTEGER
                        )
                    """)
                    # Create the reverse geocoding cache table if it doesn't exist
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS reverse_cache (
                            lat_key REAL,
                            lon_key REAL,
                            display_name TEXT,
                            timestamp INTEGER,
                            PRIMARY KEY (lat_key, lon_key)
                        )
                    """)
                    conn.commit()
            self.logger.info(f"Geocoding cache database initialized at {self.db_path}")
        except Exception as e:
            self.logger.error(f"Error initializing geocoding database: {e}")
    
    def geocode(self, location_name, country_hint=None):
        """
        Geocode a location name to coordinates.
        
        Args:
            location_name: Name of the location to geocode
            country_hint: Optional country hint to improve geocoding accuracy
            
        Returns:
            Tuple of (latitude, longitude, display_name) or (None, None, None) if geocoding fails
        """
        if not location_name:
            return None, None, None
        
        # Normalize the query for caching
        query = location_name.lower().strip()
        
        # Check in-memory cache first
        if query in self.geo_cache:
            lat, lon = self.geo_cache[query]
            self.logger.info(f"Geocode cache hit for '{query}'")
            return lat, lon, query
        
        # Check database cache
        try:
            with self.lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT latitude, longitude, display_name FROM geocode_cache WHERE query = ?", 
                        (query,)
                    )
                    result = cursor.fetchone()
                    if result:
                        lat, lon, display_name = result
                        # Update in-memory cache
                        if len(self.geo_cache) >= self.max_cache_size:
                            # Remove a random entry if cache is full
                            self.geo_cache.pop(next(iter(self.geo_cache)))
                        self.geo_cache[query] = (lat, lon)
                        self.logger.info(f"Geocode DB cache hit for '{query}'")
                        return lat, lon, display_name
        except Exception as e:
            self.logger.error(f"Error checking geocode cache: {e}")
        
        # Not in cache, perform geocoding
        try:
            # Build the query with country hint if provided
            geocode_query = query
            if country_hint:
                geocode_query = f"{query}, {country_hint}"
            
            location = self.geolocator.geocode(geocode_query, exactly_one=True)
            if location:
                lat, lon = location.latitude, location.longitude
                display_name = location.address
                
                # Update both caches
                if len(self.geo_cache) >= self.max_cache_size:
                    self.geo_cache.pop(next(iter(self.geo_cache)))
                self.geo_cache[query] = (lat, lon)
                
                # Update database cache
                with self.lock:
                    with sqlite3.connect(self.db_path) as conn:
                        cursor = conn.cursor()
                        cursor.execute(
                            "INSERT OR REPLACE INTO geocode_cache VALUES (?, ?, ?, ?, ?)",
                            (query, lat, lon, display_name, int(time.time()))
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
        """
        Reverse geocode coordinates to a location name.
        
        Args:
            latitude: Latitude coordinate
            longitude: Longitude coordinate
            
        Returns:
            Location name or "Unknown location" if reverse geocoding fails
        """
        if latitude is None or longitude is None:
            return "Unknown location"
        
        # Round coordinates for consistent caching
        lat_key = round(latitude, 5)
        lon_key = round(longitude, 5)
        
        # Check database cache
        try:
            with self.lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT display_name FROM reverse_cache WHERE lat_key = ? AND lon_key = ?", 
                        (lat_key, lon_key)
                    )
                    result = cursor.fetchone()
                    if result:
                        self.logger.info(f"Reverse geocode cache hit for {lat_key}, {lon_key}")
                        return result[0]
        except Exception as e:
            self.logger.error(f"Error checking reverse geocode cache: {e}")
        
        # Not in cache, perform reverse geocoding
        try:
            location = self.geolocator.reverse((latitude, longitude), language="en")
            if location:
                display_name = location.address
                
                # Update database cache
                with self.lock:
                    with sqlite3.connect(self.db_path) as conn:
                        cursor = conn.cursor()
                        cursor.execute(
                            "INSERT OR REPLACE INTO reverse_cache VALUES (?, ?, ?, ?)",
                            (lat_key, lon_key, display_name, int(time.time()))
                        )
                        conn.commit()
                
                self.logger.info(f"Reverse geocoded {latitude}, {longitude} to '{display_name}'")
                return display_name
            else:
                self.logger.warning(f"Could not reverse geocode {latitude}, {longitude}")
                return "Unknown location"
                
        except (GeocoderTimedOut, GeocoderUnavailable) as e:
            self.logger.error(f"Reverse geocoding error for {latitude}, {longitude}: {e}")
            return "Unknown location"
    
    def calculate_heading_distance(self, lat1, lon1, lat2, lon2):
        """
        Calculate the heading and distance between two sets of coordinates.
        
        Args:
            lat1, lon1: Starting coordinates
            lat2, lon2: Ending coordinates
            
        Returns:
            Tuple of (heading, distance) in degrees and nautical miles,
            or (None, None) if calculation fails
        """
        try:
            # Convert to radians
            lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
            
            # Calculate heading
            dlon = lon2 - lon1
            y = math.sin(dlon) * math.cos(lat2)
            x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
            heading = math.degrees(math.atan2(y, x))
            heading = (heading + 360) % 360  # Normalize to 0-360
            
            # Calculate distance using haversine formula
            R = 3440.1  # Earth radius in nautical miles
            dlat = lat2 - lat1
            a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
            c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
            distance = R * c
            
            return heading, distance
        except Exception as e:
            self.logger.error(f"Error calculating heading/distance: {e}")
            return None, None
    
    def get_nearest_poi(self, latitude, longitude, max_distance=50):
        """
        Find the nearest point of interest from current coordinates.
        
        Args:
            latitude, longitude: Current coordinates
            max_distance: Maximum distance to consider (nautical miles)
            
        Returns:
            Tuple of (poi_name, heading, distance) or (None, None, None) if none found
        """
        nearest_poi = None
        nearest_distance = float('inf')
        nearest_heading = None
        
        for poi_name, (poi_lat, poi_lon) in self.geo_cache.items():
            heading, distance = self.calculate_heading_distance(
                latitude, longitude, poi_lat, poi_lon
            )
            
            if distance is not None and distance < nearest_distance and distance < max_distance:
                nearest_poi = poi_name
                nearest_distance = distance
                nearest_heading = heading
        
        if nearest_poi:
            return nearest_poi, nearest_heading, nearest_distance
        else:
            return None, None, None
    
    def clear_old_cache_entries(self, max_age_days=30):
        """
        Clear old entries from the cache database.
        
        Args:
            max_age_days: Maximum age of entries to keep in days
        """
        try:
            current_time = int(time.time())
            max_age_seconds = max_age_days * 24 * 60 * 60
            cutoff_time = current_time - max_age_seconds
            
            with self.lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "DELETE FROM geocode_cache WHERE timestamp < ?", 
                        (cutoff_time,)
                    )
                    geocode_deleted = cursor.rowcount
                    
                    cursor.execute(
                        "DELETE FROM reverse_cache WHERE timestamp < ?", 
                        (cutoff_time,)
                    )
                    reverse_deleted = cursor.rowcount
                    
                    conn.commit()
            
            self.logger.info(f"Cleared {geocode_deleted} geocode and {reverse_deleted} reverse geocode old cache entries")
        except Exception as e:
            self.logger.error(f"Error clearing old cache entries: {e}")


# Create a singleton instance
geo_utils = GeoUtils()

# Example usage
if __name__ == "__main__":
    # Setup basic logging for the example
    logging.basicConfig(level=logging.INFO)
    
    # Test geocoding
    lat, lon, name = geo_utils.geocode("Eiffel Tower")
    print(f"Geocoded Eiffel Tower: {lat}, {lon} - {name}")
    
    # Test reverse geocoding
    location = geo_utils.reverse_geocode(48.8584, 2.2945)
    print(f"Reverse geocoded 48.8584, 2.2945: {location}")
    
    # Test heading/distance calculation
    heading, distance = geo_utils.calculate_heading_distance(
        40.7128, -74.0060,  # New York
        34.0522, -118.2437  # Los Angeles
    )
    print(f"Heading from NY to LA: {heading:.1f}°, Distance: {distance:.1f} nautical miles")
    
    # Test nearest POI
    poi, heading, distance = geo_utils.get_nearest_poi(29.4300, -98.4800)
    if poi:
        print(f"Nearest POI to 29.4300, -98.4800: {poi}, {heading:.1f}°, {distance:.1f} nautical miles")