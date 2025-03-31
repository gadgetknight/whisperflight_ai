"""
Mock SimConnect implementation for testing WhisperFlight_AI without Flight Simulator
This module provides dummy aircraft data for testing purposes while maintaining
compatibility with the navigation module expectations.
"""

import logging
import time
import threading
import random

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MockSimConnect")

class SimConnect:
    """Mock SimConnect class that mimics the real SimConnect library"""
    
    def __init__(self):
        self.connected = True
        logger.info("Mock SimConnect initialized")
    
    def connect(self):
        """Mock connect method"""
        logger.info("Mock SimConnect: Pretending to connect to Flight Simulator")
        return True
    
    def disconnect(self):
        """Mock disconnect method"""
        logger.info("Mock SimConnect: Pretending to disconnect from Flight Simulator")
        self.connected = False
        return True

    def is_connected(self):
        """Check if connected to simulator"""
        return self.connected


class AircraftRequests:
    """Mock AircraftRequests class to provide dummy aircraft data"""
    
    def __init__(self, sim_connect):
        self.sim_connect = sim_connect
        logger.info("Mock AircraftRequests initialized")
        
        # Default aircraft data values (using your Statue of Liberty coordinates)
        self.aircraft_data = {
            "TITLE": "Cessna 172",
            "PLANE_LATITUDE": 40.6892,  # Statue of Liberty
            "PLANE_LONGITUDE": -74.0445,
            "PLANE_ALTITUDE": 1500.0,  # Altitude in feet
            "PLANE_HEADING_DEGREES_TRUE": 45.0,  # Northeast
            "AIRSPEED_INDICATED": 120.0,  # Airspeed in knots
            "VERTICAL_SPEED": 0.0,  # Vertical speed in feet per minute
            "FUEL_TOTAL_QUANTITY": 40.0,  # Fuel in gallons
        }
    
    def get(self, data_name):
        """Mock get method to return dummy data"""
        if data_name in self.aircraft_data:
            return self.aircraft_data[data_name]
        return 0.0  # Default value for unknown data
    
    def set(self, data_name, value):
        """Mock set method to update dummy data"""
        self.aircraft_data[data_name] = value
        return True


class MockSimConnectServer:
    """Mock SimConnectServer class that reuses your existing implementation"""
    
    def __init__(self):
        logger.info("Initializing MockSimConnectServer")
        self.sm = SimConnect()
        self.ae = AircraftRequests(self.sm)
        
        # Simulated aircraft data (using your original format)
        self.last_data = {
            "Latitude": 40.6892,       # Statue of Liberty
            "Longitude": -74.0445,
            "Altitude": 1500.0,        # 1500 feet
            "Heading": 45.0,           # Northeast
            "GroundSpeed": 120.0       # 120 knots
        }
                
        # Optional: Start a thread to slowly change position
        self.running = True
        self.data_thread = threading.Thread(target=self._update_data)
        self.data_thread.daemon = True
        self.data_thread.start()
                
        logger.info("✅ Connected to MSFS via MockSimConnect")
        
    def _update_data(self):
        """Slowly update aircraft position in the background"""
        while self.running:
            # Small random heading changes
            heading_change = random.uniform(-5.0, 5.0)
            new_heading = (self.last_data["Heading"] + heading_change) % 360
                        
            # Move slightly in that direction
            speed = self.last_data["GroundSpeed"]
            distance = speed * (5.0 / 3600.0)  # 5 seconds in hours
                        
            # Convert heading to radians for math
            heading_rad = new_heading * (3.14159 / 180.0)
                        
            # Calculate new position (very approximate)
            lat_change = distance * 0.01 * (-1 if heading_rad > 3.14159 else 1)
            lon_change = distance * 0.01 * (-1 if heading_rad > 1.5708 and heading_rad < 4.7124 else 1)
                        
            self.last_data["Latitude"] += lat_change
            self.last_data["Longitude"] += lon_change
            self.last_data["Heading"] = new_heading
                        
            # Random altitude changes
            self.last_data["Altitude"] += random.uniform(-25.0, 25.0)
            if self.last_data["Altitude"] < 1000:
                self.last_data["Altitude"] = 1000
            elif self.last_data["Altitude"] > 3000:
                self.last_data["Altitude"] = 3000
                            
            time.sleep(5)  # Update every 5 seconds
        
    def get_aircraft_data(self):
        """Return the current simulated aircraft data"""
        # Add some random noise to values
        noisy_data = {k: v + random.uniform(-0.001, 0.001) if k != "Heading" else v
                       for k, v in self.last_data.items()}
                
        logger.debug(f"Returning mock aircraft data: {noisy_data}")
        return noisy_data
        
    def stop(self):
        """Stop the background thread"""
        self.running = False
        if self.data_thread:
            self.data_thread.join(timeout=1.0)
        logger.info("Disconnected from MockSimConnect")

    # Add compatibility methods for SimConnect-style calls
    def get_aircraft_position(self):
        """Return dummy aircraft position data in SimConnect format"""
        data = self.get_aircraft_data()
        return {
            "latitude": data["Latitude"],
            "longitude": data["Longitude"],
            "altitude": data["Altitude"],
            "heading": data["Heading"]
        }


# Create a global instance for import
sim_server = MockSimConnectServer()

def get_aircraft_data(force_update=False):
    return sim_server.get_aircraft_data()


if __name__ == "__main__":
    # Test the mock server
    print("Testing Mock SimConnect Server")
    for i in range(5):
        data = sim_server.get_aircraft_data()
        print(f"Position {i+1}: Lat={data['Latitude']:.4f}, Lon={data['Longitude']:.4f}, Alt={data['Altitude']:.0f}ft")
        time.sleep(1)
    sim_server.stop()