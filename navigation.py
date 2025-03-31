"""
Whisper Flight AI - Navigation Module
Version: 5.0.1
Purpose: Handles flight navigation, landmark tracking and POI recommendations
Last Updated: March 25, 2025, 09:00 UTC
Author: Your Name

This module provides navigation assistance and points of interest
suitable for aerial viewing from different altitudes.
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

# Try to use the mock SimConnect directly first for testing
try:
    from mock_simconnect_server import sim_server
    print("Using mock SimConnect server directly")
except ImportError:
    try:
        # Fall back to real SimConnect if mock not available
        from simconnect_server import sim_server
        print("Using real SimConnect server")
    except Exception as e:
        print(f"SimConnect error: {e}")
        print("No SimConnect implementation available - exiting")
        sys.exit(1)

# Definition of a point of interest
POI = namedtuple('POI', ['name', 'latitude', 'longitude', 'description', 
                         'min_altitude', 'max_altitude', 'category', 'region', 'tags'])

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
        
        # POI database
        self.poi_database = []
        self._load_poi_database()
    
    def _load_poi_database(self):
        """Load the points of interest database."""
        # In a full implementation, this would load from a JSON/CSV file
        # For now, we'll initialize with some sample data
        
        self.poi_database = [
            POI(
                name="Empire State Building",
                latitude=40.7484,
                longitude=-73.9857,
                description="Iconic 102-story skyscraper in Midtown Manhattan. Completed in 1931, it was the world's tallest building until 1970. Distinctive Art Deco design with a spire that's often lit in different colors for special occasions.",
                min_altitude=500,
                max_altitude=5000,
                category="architecture",
                region="New York",
                tags=["skyscraper", "landmark", "observation deck"]
            ),
            POI(
                name="Statue of Liberty",
                latitude=40.6892,
                longitude=-74.0445,
                description="Colossal neoclassical sculpture on Liberty Island in New York Harbor. A gift from France, dedicated in 1886. The statue represents Libertas, the Roman goddess of freedom, and is a symbol of liberty and democracy.",
                min_altitude=300,
                max_altitude=3000,
                category="monument",
                region="New York",
                tags=["landmark", "historic", "harbor"]
            ),
            POI(
                name="Golden Gate Bridge",
                latitude=37.8199,
                longitude=-122.4783,
                description="Iconic suspension bridge spanning the Golden Gate strait. Completed in 1937 with its distinctive 'International Orange' color. One of the most photographed bridges in the world, connecting San Francisco to Marin County.",
                min_altitude=400,
                max_altitude=4000,
                category="bridge",
                region="San Francisco",
                tags=["landmark", "engineering", "bay"]
            ),
            POI(
                name="Grand Canyon",
                latitude=36.0544,
                longitude=-112.2583,
                description="Immense natural formation carved by the Colorado River. Up to 18 miles wide and over a mile deep, showcasing billions of years of geological history through exposed rock layers. One of the Seven Natural Wonders of the World.",
                min_altitude=1000,
                max_altitude=15000,
                category="natural",
                region="Arizona",
                tags=["national park", "geological", "river"]
            ),
            POI(
                name="The Alamo",
                latitude=29.4252,
                longitude=-98.4861,
                description="Historic Spanish mission and fortress compound founded in the 18th century. Site of the 1836 Battle of the Alamo and symbol of Texas' struggle for independence. Recognized as part of a UNESCO World Heritage Site.",
                min_altitude=300,
                max_altitude=3000,
                category="historic",
                region="San Antonio",
                tags=["mission", "battle site", "texas"]
            ),
            POI(
                name="San Antonio River Walk",
                latitude=29.4238,
                longitude=-98.4895,
                description="Network of walkways along the San Antonio River lined with restaurants, shops, and attractions. Sitting below street level, it winds through the city center and connects major tourist areas. Beautiful urban oasis with lush vegetation.",
                min_altitude=300,
                max_altitude=2000,
                category="urban",
                region="San Antonio",
                tags=["river", "dining", "entertainment"]
            ),
            POI(
                name="Independence Hall",
                latitude=39.9495,
                longitude=-75.1497,
                description="Historic building in Philadelphia where both the Declaration of Independence and the United States Constitution were debated and adopted. A UNESCO World Heritage Site, recognizable by its red brick construction and clock tower.",
                min_altitude=300,
                max_altitude=3000,
                category="historic",
                region="Philadelphia",
                tags=["revolution", "founding fathers", "liberty bell"]
            ),
            POI(
                name="Atlantic City Boardwalk",
                latitude=39.3559,
                longitude=-74.4304,
                description="Oldest and longest boardwalk in the United States, stretching along the Atlantic Ocean. Features casinos, hotels, restaurants, and attractions. An iconic symbol of the Jersey Shore and American seaside entertainment.",
                min_altitude=300,
                max_altitude=2500,
                category="entertainment",
                region="New Jersey",
                tags=["beach", "casinos", "resorts"]
            ),
            POI(
                name="Golden Nugget Casino",
                latitude=39.3801,
                longitude=-74.4282,
                description="Luxury casino and hotel in Atlantic City with a distinctive gold facade. Located in the marina district with views of the bay. Features gaming tables, slots, fine dining, and entertainment venues.",
                min_altitude=200,
                max_altitude=2000,
                category="entertainment",
                region="Atlantic City",
                tags=["gambling", "marina", "resort"]
            ),
            POI(
                name="Philadelphia Museum of Art",
                latitude=39.9656,
                longitude=-75.1810,
                description="One of the largest art museums in the United States, known for its steps which were featured in the movie 'Rocky'. Neoclassical building housing over 240,000 objects including major collections of Renaissance, American, and Impressionist art.",
                min_altitude=300,
                max_altitude=3000,
                category="cultural",
                region="Philadelphia",
                tags=["art", "rocky steps", "architecture"]
            ),
        ]
        
        self.logger.info(f"Loaded {len(self.poi_database)} points of interest")
    
    def start_destination_tracking(self, destination_name, latitude, longitude, callbacks=None):
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
        
        self.logger.info(f"Started tracking destination: {destination_name} at {latitude:.6f}, {longitude:.6f}")
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
                    self._check_destination_progress()
                    self.last_update_time = current_time
                except Exception as e:
                    self.logger.error(f"Error in tracking loop: {e}")
            
            # Sleep to avoid excessive CPU usage
            time.sleep(0.5)
    
    def _check_destination_progress(self):
        """Check progress toward the tracked destination."""
        if not self.tracking_enabled or not self.destination_lat or not self.destination_lon:
            return
        
        # Get current position from SimConnect
        flight_data = sim_server.get_aircraft_data()
        if not flight_data:
            self.logger.warning("Could not get flight data for destination tracking")
            return
        
        current_lat = flight_data.get("Latitude")
        current_lon = flight_data.get("Longitude")
        current_heading = flight_data.get("Heading")
        ground_speed = flight_data.get("GroundSpeed", 120)  # Default to 120 knots if missing
        
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
            self.logger.info(f"One minute away from destination: {self.destination_name}")
            # Call update callback
            for callback in self.tracking_callbacks:
                if hasattr(callback, "on_one_minute_away"):
                    callback.on_one_minute_away(self.destination_name, distance)
        
        # Check if off course
        if current_heading is not None:
            heading_difference = abs((target_heading - current_heading + 180) % 360 - 180)
            if heading_difference > self.off_course_threshold:
                self.logger.info(f"Off course to destination: current={current_heading:.1f}°, target={target_heading:.1f}°")
                # Call off course callback
                for callback in self.tracking_callbacks:
                    if hasattr(callback, "on_off_course"):
                        callback.on_off_course(current_heading, target_heading, heading_difference)
        
        # Regular update
        self.logger.debug(f"Tracking {self.destination_name}: Distance={distance:.1f}nm, ETA={time_to_destination:.1f}min")
        # Call update callback
        for callback in self.tracking_callbacks:
            if hasattr(callback, "on_update"):
                callback.on_update(distance, target_heading, time_to_destination)
    
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
        destination = re.sub(r'\s+', ' ', destination_raw)
        
        self.logger.info(f"Extracted destination from query: {destination}")
        
        # First, try to match against our POI database
        for poi in self.poi_database:
            if destination in poi.name.lower() or any(tag in destination for tag in poi.tags):
                self.logger.info(f"Found POI match: {poi.name}")
                return poi.name, poi.latitude, poi.longitude
        
        # If no match in POI database, try geocoding
        latitude, longitude, display_name = geo_utils.geocode(destination)
        
        if latitude is not None and longitude is not None:
            name = display_name or destination
            self.logger.info(f"Geocoded destination: {name} at {latitude:.6f}, {longitude:.6f}")
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
        dest_name, dest_lat, dest_lon = self.find_destination_from_query(destination, current_position)
        
        if not dest_name or dest_lat is None or dest_lon is None:
            self.logger.warning(f"Could not find destination for directions: {destination}")
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
            "nearby_context": nearby_context
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
        
        # Add flight time estimate
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
    
    def find_aerial_pois(self, altitude=None, max_distance=None, category=None):
        """
        Find points of interest suitable for viewing from the air.
        
        Args:
            altitude: Current altitude in feet (optional)
            max_distance: Maximum distance in nautical miles (optional)
            category: Category filter (optional)
            
        Returns:
            List of POIs suitable for aerial viewing
        """
        # Get current position and altitude if not provided
        current_lat = None
        current_lon = None
        
        if max_distance is not None:
            flight_data = sim_server.get_aircraft_data()
            if flight_data:
                current_lat = flight_data.get("Latitude")
                current_lon = flight_data.get("Longitude")
                
                if altitude is None:
                    altitude = flight_data.get("Altitude")
        
        # Filter POIs based on criteria
        filtered_pois = []
        
        for poi in self.poi_database:
            # Filter by altitude if provided
            if altitude is not None:
                if poi.min_altitude > altitude or poi.max_altitude < altitude:
                    continue
            
            # Filter by category if provided
            if category is not None and poi.category != category:
                continue
            
            # Filter by distance if provided
            if max_distance is not None and current_lat is not None and current_lon is not None:
                _, distance = geo_utils.calculate_heading_distance(
                    current_lat, current_lon, poi.latitude, poi.longitude
                )
                
                if distance is None or distance > max_distance:
                    continue
                
                # Add distance to POI
                poi_with_distance = poi._replace(distance=distance)
                filtered_pois.append(poi_with_distance)
            else:
                filtered_pois.append(poi)
        
        # Sort by distance if available
        if max_distance is not None and current_lat is not None and current_lon is not None:
            filtered_pois.sort(key=lambda p: getattr(p, 'distance', float('inf')))
        
        return filtered_pois
    
    def format_poi_description(self, poi, include_navigation=True):
        """
        Format a POI description suitable for narration.
        
        Args:
            poi: POI object
            include_navigation: Whether to include navigation instructions
            
        Returns:
            Formatted POI description
        """
        description = f"{poi.name}: {poi.description}"
        
        # Add navigation information if requested
        if include_navigation:
            flight_data = sim_server.get_aircraft_data()
            if flight_data:
                current_lat = flight_data.get("Latitude")
                current_lon = flight_data.get("Longitude")
                
                if current_lat is not None and current_lon is not None:
                    heading, distance = geo_utils.calculate_heading_distance(
                        current_lat, current_lon, poi.latitude, poi.longitude
                    )
                    
                    if heading is not None and distance is not None:
                        cardinal = self._heading_to_cardinal(heading)
                        
                        if distance < 1:
                            distance_text = f"{distance * 10:.1f} cable lengths"
                        elif distance < 10:
                            distance_text = f"{distance:.1f} nautical miles"
                        else:
                            distance_text = f"{distance:.0f} nautical miles"
                        
                        description += f" Located {distance_text} {cardinal} from your position, heading {heading:.0f}°."
        
        return description
    
    def _find_nearby_poi(self, latitude, longitude, max_distance=5):
        """
        Find a POI near the specified coordinates.
        
        Args:
            latitude: Target latitude
            longitude: Target longitude
            max_distance: Maximum distance in nautical miles
            
        Returns:
            Nearest POI within max_distance or None
        """
        nearest_poi = None
        nearest_distance = float('inf')
        
        for poi in self.poi_database:
            _, distance = geo_utils.calculate_heading_distance(
                latitude, longitude, poi.latitude, poi.longitude
            )
            
            if distance is not None and distance < nearest_distance and distance <= max_distance:
                nearest_poi = poi
                nearest_distance = distance
        
        return nearest_poi
    
    def _heading_to_cardinal(self, heading):
        """
        Convert a heading in degrees to a cardinal direction.
        
        Args:
            heading: Heading in degrees
            
        Returns:
            Cardinal direction as string
        """
        # Define cardinal directions
        directions = [
            "north", "north-northeast", "northeast", "east-northeast",
            "east", "east-southeast", "southeast", "south-southeast",
            "south", "south-southwest", "southwest", "west-southwest",
            "west", "west-northwest", "northwest", "north-northwest"
        ]
        
        # Convert heading to index
        index = round(heading / 22.5) % 16
        
        return directions[index]
    
    def get_current_location_description(self):
        """
        Get a description of the current location.
        
        Returns:
            Description of current location with context
        """
        flight_data = sim_server.get_aircraft_data()
        if not flight_data:
            return "I couldn't determine our current location."
        
        latitude = flight_data.get("Latitude")
        longitude = flight_data.get("Longitude")
        altitude = flight_data.get("Altitude")
        heading = flight_data.get("Heading")
        
        if latitude is None or longitude is None:
            return "I couldn't determine our current location."
        
        # Get location name
        location_name = geo_utils.reverse_geocode(latitude, longitude)
        
        # Format altitude
        altitude_text = "at an unknown altitude"
        if altitude is not None:
            if altitude < 1000:
                altitude_text = f"at {altitude:.0f} feet"
            else:
                altitude_text = f"at {altitude/1000:.1f} thousand feet"
        
        # Format heading
        heading_text = ""
        if heading is not None:
            cardinal = self._heading_to_cardinal(heading)
            heading_text = f", heading {heading:.0f}° ({cardinal})"
        
        # Find nearby POIs
        nearby_pois = self.find_aerial_pois(altitude=altitude, max_distance=10)
        poi_text = ""
        
        if nearby_pois:
            poi = nearby_pois[0]
            _, distance = geo_utils.calculate_heading_distance(
                latitude, longitude, poi.latitude, poi.longitude
            )
            
            if distance is not None:
                if distance < 1:
                    distance_text = f"{distance * 10:.1f} cable lengths"
                elif distance < 10:
                    distance_text = f"{distance:.1f} nautical miles"
                else:
                    distance_text = f"{distance:.0f} nautical miles"
                
                heading_to_poi, _ = geo_utils.calculate_heading_distance(
                    latitude, longitude, poi.latitude, poi.longitude
                )
                
                if heading_to_poi is not None:
                    cardinal_to_poi = self._heading_to_cardinal(heading_to_poi)
                    poi_text = f" {poi.name} is {distance_text} {cardinal_to_poi} from here."
        
        return f"You're flying over {location_name} {altitude_text}{heading_text}.{poi_text}"


# Create a singleton instance
navigation_manager = NavigationManager()

# Example usage
if __name__ == "__main__":
    # Setup basic logging for the example
    logging.basicConfig(level=logging.INFO)
    
    # Test destination parsing
    print("\nTesting destination parsing:")
    test_queries = [
        "Take me to the Statue of Liberty",
        "Which direction to the Grand Canyon?",
        "How do I get to the Golden Gate Bridge?",
        "I want to fly toward the Empire State Building"
    ]
    
    for query in test_queries:
        name, lat, lon = navigation_manager.find_destination_from_query(query)
        print(f"Query: {query}")
        print(f"Result: {name} at {lat}, {lon}")
    
    # Test navigation response
    print("\nTesting navigation response:")
    direction_info = {
        "destination_name": "Statue of Liberty",
        "latitude": 40.6892,
        "longitude": -74.0445,
        "heading": 187.3,
        "cardinal_direction": "south",
        "distance": 8.5,
        "nearby_context": "Near New York Harbor."
    }
    
    response = navigation_manager.format_navigation_response(direction_info)
    print(response)
    
    # Test POI filtering
    print("\nTesting POI filtering:")
    pois = navigation_manager.find_aerial_pois(altitude=1000, category="historic")
    for poi in pois:
        print(f"- {poi.name} ({poi.category}): Visible from {poi.min_altitude}-{poi.max_altitude}ft")