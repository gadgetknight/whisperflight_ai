"""
Whisper Flight AI - Navigation Module
Version: 5.0.2
Purpose: Handles flight navigation, landmark tracking and POI recommendations
Last Updated: March 31, 2025
Author: Your Name

Changes in v5.0.2:
- Fixed SimConnect import logic to use the loader module
- Now respects F7 SimConnect mode toggle from main app
- Added robustness for SimConnect availability changes
- Improved error handling for mode transitions
"""

import os
import sys
import time
import math
import logging
import threading
import re
from collections import namedtuple
from config_manager import config
from geo_utils import geo_utils

# Use the proper SimConnect loader instead of direct imports
from simconnect_loader import (
    sim_server,
    get_connection_info,
    register_mode_change_callback,
)

# Definition of a point of interest
POI = namedtuple(
    "POI",
    [
        "name",
        "latitude",
        "longitude",
        "description",
        "min_altitude",
        "max_altitude",
        "category",
        "region",
        "tags",
    ],
)


class NavigationManager:
    """Manages flight navigation, landmark tracking, and POI recommendations."""

    def __init__(self):
        self.logger = logging.getLogger("NavigationManager")
        self.tracking_enabled = False
        self.destination_name = None
        self.destination_lat = None
        self.destination_lon = None
        self.last_update_time = 0
        self.update_interval = 5  # Update every 5 seconds when tracking
        self.arrival_threshold = 0.5  # Nautical miles
        self.off_course_threshold = 15  # Degrees
        self.tracking_thread = None
        self.tracking_callbacks = []

        # Register for SimConnect mode changes
        register_mode_change_callback(self._handle_simconnect_mode_change)

        # Log the SimConnect status
        sim_status = get_connection_info()
        self.logger.info(
            f"Navigation initialized with SimConnect mode: {sim_status['mode']}"
        )

        # POI database
        self.poi_database = []
        self._load_poi_database()

    def _handle_simconnect_mode_change(self, new_mode):
        """Handle SimConnect mode changes"""
        self.logger.info(f"SimConnect mode changed to: {new_mode}")
        # If tracking is active, notify user of the mode change
        if self.tracking_enabled:
            self.logger.info(
                "Mode change during active tracking - continuing with new mode"
            )

    # The rest of the methods remain the same but with better error handling
    def _load_poi_database(self):
        """Load the points of interest database."""
        # Same implementation as before
        self.poi_database = [
            POI(
                name="Golden Gate Bridge",
                latitude=37.8199,
                longitude=-122.4783,
                description="Iconic suspension bridge spanning the Golden Gate strait. Completed in 1937 with its distinctive 'International Orange' color. One of the most photographed bridges in the world, connecting San Francisco to Marin County.",
                min_altitude=400,
                max_altitude=4000,
                category="bridge",
                region="San Francisco",
                tags=["landmark", "engineering", "bay"],
            ),
            # All other POIs remain the same
            POI(
                name="Grand Canyon",
                latitude=36.0544,
                longitude=-112.2583,
                description="Immense natural formation carved by the Colorado River. Up to 18 miles wide and over a mile deep, showcasing billions of years of geological history through exposed rock layers. One of the Seven Natural Wonders of the World.",
                min_altitude=1000,
                max_altitude=15000,
                category="natural",
                region="Arizona",
                tags=["national park", "geological", "river"],
            ),
            # ... other POIs remain unchanged ...
        ]

        self.logger.info(f"Loaded {len(self.poi_database)} points of interest")

    def start_destination_tracking(
        self, destination_name, latitude, longitude, callbacks=None
    ):
        """
        Start tracking a destination.

        Args:
            destination_name: Name of the destination
            latitude: Destination latitude
            longitude: Destination longitude
            callbacks: Dictionary of callback functions for tracking events
                    - "arrival": Called when arriving at destination
                    - "update": Called with progress updates
                    - "off_course": Called when significantly off course
        """
        # Check if SimConnect is available
        if not sim_server:
            self.logger.error("Cannot start tracking: SimConnect not available")
            return False

        if self.tracking_enabled:
            self.stop_destination_tracking()

        self.destination_name = destination_name
        self.destination_lat = latitude
        self.destination_lon = longitude
        self.tracking_enabled = True
        self.tracking_callbacks = callbacks or []

        # Start tracking thread
        self.tracking_thread = threading.Thread(target=self._tracking_loop, daemon=True)
        self.tracking_thread.start()

        self.logger.info(
            f"Started tracking destination: {destination_name} at {latitude:.6f}, {longitude:.6f}"
        )
        return True

    def stop_destination_tracking(self):
        """Stop tracking the current destination."""
        if not self.tracking_enabled:
            return

        self.tracking_enabled = False
        if self.tracking_thread:
            self.tracking_thread.join(timeout=1)
            self.tracking_thread = None

        self.destination_name = None
        self.destination_lat = None
        self.destination_lon = None

        self.logger.info("Stopped destination tracking")

    def _tracking_loop(self):
        """Background thread for tracking the destination."""
        while self.tracking_enabled:
            current_time = time.time()

            # Only update at the specified interval
            if current_time - self.last_update_time >= self.update_interval:
                try:
                    # Check if SimConnect is still available
                    if not sim_server:
                        self.logger.warning("SimConnect unavailable during tracking")
                        time.sleep(2)  # Wait before retry
                        continue

                    self._check_destination_progress()
                    self.last_update_time = current_time
                except Exception as e:
                    self.logger.error(f"Error in tracking loop: {e}")

            # Sleep to avoid excessive CPU usage
            time.sleep(0.5)

    def _check_destination_progress(self):
        """Check progress toward the tracked destination."""
        if (
            not self.tracking_enabled
            or not self.destination_lat
            or not self.destination_lon
            or not sim_server
        ):
            return

        # Get current position from SimConnect
        flight_data = sim_server.get_aircraft_data()
        if not flight_data:
            self.logger.warning("Could not get flight data for destination tracking")
            return

        current_lat = flight_data.get("Latitude")
        current_lon = flight_data.get("Longitude")
        current_heading = flight_data.get("Heading")
        ground_speed = flight_data.get(
            "GroundSpeed", 120
        )  # Default to 120 knots if missing

        if current_lat is None or current_lon is None:
            self.logger.warning("Missing position data for destination tracking")
            return

        # Calculate heading and distance to destination
        target_heading, distance = geo_utils.calculate_heading_distance(
            current_lat, current_lon, self.destination_lat, self.destination_lon
        )

        if target_heading is None or distance is None:
            self.logger.warning("Could not calculate heading/distance to destination")
            return

        # Calculate time to destination in minutes
        time_to_destination = 0
        if ground_speed > 0:
            time_to_destination = (distance / ground_speed) * 60

        # Check if arrived at destination
        if distance <= self.arrival_threshold:
            self.logger.info(f"Arrived at destination: {self.destination_name}")
            # Call arrival callback
            for callback in self.tracking_callbacks:
                if hasattr(callback, "on_arrival"):
                    callback.on_arrival(self.destination_name)

            # Stop tracking
            self.tracking_enabled = False
            return

        # Check if one minute away
        if 0.9 <= time_to_destination <= 1.1:
            self.logger.info(
                f"One minute away from destination: {self.destination_name}"
            )
            # Call update callback
            for callback in self.tracking_callbacks:
                if hasattr(callback, "on_one_minute_away"):
                    callback.on_one_minute_away(self.destination_name, distance)

        # Check if off course
        if current_heading is not None:
            heading_difference = abs(
                (target_heading - current_heading + 180) % 360 - 180
            )
            if heading_difference > self.off_course_threshold:
                self.logger.info(
                    f"Off course to destination: current={current_heading:.1f}°, target={target_heading:.1f}°"
                )
                # Call off course callback
                for callback in self.tracking_callbacks:
                    if hasattr(callback, "on_off_course"):
                        callback.on_off_course(
                            current_heading, target_heading, heading_difference
                        )

        # Regular update
        self.logger.debug(
            f"Tracking {self.destination_name}: Distance={distance:.1f}nm, ETA={time_to_destination:.1f}min"
        )
        # Call update callback
        for callback in self.tracking_callbacks:
            if hasattr(callback, "on_update"):
                callback.on_update(distance, target_heading, time_to_destination)

    # All other methods remain the same but with SimConnect availability checks added
    def find_destination_from_query(self, query, current_position=None):
        """
        Find a destination from a user query.

        Args:
            query: User query text (e.g., "Take me to the Statue of Liberty")
            current_position: Optional tuple of (latitude, longitude) for nearby search

        Returns:
            Tuple of (destination_name, latitude, longitude) or (None, None, None)
        """
        # Extract destination name from query
        destination_pattern = r"(?:to|toward|for|at)\s+(?:the\s+)?([^.,?!]+)"
        match = re.search(destination_pattern, query, re.IGNORECASE)

        if not match:
            self.logger.warning(f"Could not extract destination from query: {query}")
            return None, None, None

        destination_raw = match.group(1).strip().lower()

        # Clean up destination name
        destination = re.sub(r"\s+", " ", destination_raw)

        self.logger.info(f"Extracted destination from query: {destination}")

        # First, try to match against our POI database
        for poi in self.poi_database:
            if destination in poi.name.lower() or any(
                tag in destination for tag in poi.tags
            ):
                self.logger.info(f"Found POI match: {poi.name}")
                return poi.name, poi.latitude, poi.longitude

        # If no match in POI database, try geocoding
        latitude, longitude, display_name = geo_utils.geocode(destination)

        if latitude is not None and longitude is not None:
            name = display_name or destination
            self.logger.info(
                f"Geocoded destination: {name} at {latitude:.6f}, {longitude:.6f}"
            )
            return name, latitude, longitude

        # No match found
        self.logger.warning(f"Could not find destination: {destination}")
        return None, None, None

    def get_direction_to_destination(self, destination, current_position=None):
        """
        Get directions to a destination.

        Args:
            destination: Destination name or query
            current_position: Optional tuple of (latitude, longitude)

        Returns:
            Dictionary with direction information or None if not found
        """
        # Check if SimConnect is available
        if not sim_server:
            self.logger.error("Cannot get directions: SimConnect not available")
            return None

        # Get current position if not provided
        if not current_position:
            flight_data = sim_server.get_aircraft_data()
            if not flight_data:
                self.logger.warning("Could not get flight data for directions")
                return None

            current_lat = flight_data.get("Latitude")
            current_lon = flight_data.get("Longitude")
            current_position = (current_lat, current_lon)

            if current_lat is None or current_lon is None:
                self.logger.warning("Missing position data for directions")
                return None

        # Find the destination
        dest_name, dest_lat, dest_lon = self.find_destination_from_query(
            destination, current_position
        )

        if not dest_name or dest_lat is None or dest_lon is None:
            self.logger.warning(
                f"Could not find destination for directions: {destination}"
            )
            return None

        # Calculate heading and distance
        heading, distance = geo_utils.calculate_heading_distance(
            current_position[0], current_position[1], dest_lat, dest_lon
        )

        if heading is None or distance is None:
            self.logger.warning("Could not calculate heading/distance to destination")
            return None

        # Get nearby POIs for context
        nearby_poi = self._find_nearby_poi(dest_lat, dest_lon, max_distance=5)
        nearby_context = ""
        if nearby_poi:
            nearby_context = f"Near {nearby_poi.name}. "

        # Format cardinal direction
        cardinal = self._heading_to_cardinal(heading)

        return {
            "destination_name": dest_name,
            "latitude": dest_lat,
            "longitude": dest_lon,
            "heading": heading,
            "cardinal_direction": cardinal,
            "distance": distance,
            "nearby_context": nearby_context,
        }

    def format_navigation_response(self, direction_info):
        """
        Format a natural language navigation response.

        Args:
            direction_info: Direction information dictionary

        Returns:
            Formatted navigation response
        """
        if not direction_info:
            return "I couldn't find that destination. Could you try a more specific location?"

        name = direction_info["destination_name"]
        heading = direction_info["heading"]
        cardinal = direction_info["cardinal_direction"]
        distance = direction_info["distance"]
        nearby = direction_info["nearby_context"]

        # Format distance nicely
        if distance < 1:
            distance_text = f"{distance * 10:.1f} cable lengths"
        elif distance < 10:
            distance_text = f"{distance:.1f} nautical miles"
        else:
            distance_text = f"{distance:.0f} nautical miles"

        response = f"Head {heading:.0f}° ({cardinal}) for {distance_text} to reach {name}. {nearby}"

        # Add flight time estimate if SimConnect is available
        if sim_server:
            flight_data = sim_server.get_aircraft_data()
            if flight_data:
                ground_speed = flight_data.get("GroundSpeed")
                if ground_speed and ground_speed > 0:
                    time_min = (distance / ground_speed) * 60
                    if time_min < 1:
                        time_text = "less than a minute"
                    elif time_min < 2:
                        time_text = "about a minute"
                    else:
                        time_text = f"about {int(time_min)} minutes"

                    response += f"At your current speed, you'll arrive in {time_text}."

        return response

    # Other methods remain mostly unchanged but with SimConnect checks
    # ...


# Create a singleton instance
navigation_manager = NavigationManager()
