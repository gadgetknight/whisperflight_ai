# mock_simconnect_server.py
"""
Whisper Flight AI - Mock SimConnect Server
Version: 1.0.0
Purpose: Provides simulated MSFS flight data for testing
Last Updated: March 28, 2025
"""
import logging
import time
import threading
import random

class MockSimConnectServer:
   def __init__(self):
       self.logger = logging.getLogger("MockSimConnectServer")
       self.logger.info("Initializing MockSimConnectServer")
       
       # Simulated aircraft data
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
       
       self.logger.info("✅ Connected to MSFS via MockSimConnect")
   
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
       
       self.logger.debug(f"Returning mock aircraft data: {noisy_data}")
       return noisy_data
   
   def stop(self):
       """Stop the background thread"""
       self.running = False
       if self.data_thread:
           self.data_thread.join(timeout=1.0)
       self.logger.info("Disconnected from MockSimConnect")

# Singleton instance
sim_server = MockSimConnectServer()

def get_aircraft_data(force_update=False):
   return sim_server.get_aircraft_data()

if __name__ == "__main__":
   logging.basicConfig(level=logging.INFO)
   # Test the mock server
   print("Testing Mock SimConnect Server")
   for i in range(5):
       data = sim_server.get_aircraft_data()
       print(f"Position {i+1}: Lat={data['Latitude']:.4f}, Lon={data['Longitude']:.4f}, Alt={data['Altitude']:.0f}ft")
       time.sleep(1)
   sim_server.stop()