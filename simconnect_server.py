"""
Whisper Flight AI - SimConnect Server
Version: 5.0.1
Purpose: Provides robust MSFS flight data via SimConnect
Last Updated: March 24, 2025
Author: Brad Coulter
Changes: Updated variable names to match MSFS 2024 (from spaces to underscore
"""
import logging
try:
    from SimConnect import SimConnect, AircraftRequests
    logging.info("pysimconnect module found in environment")
except ImportError:
    logging.error("pysimconnect module not found - ensure SDK path and installation")
    raise

class SimConnectServer:
    def __init__(self):
        self.logger = logging.getLogger("SimConnectServer")
        self.logger.info("Initializing SimConnectServer")
        self.sm = SimConnect()
        self.aq = AircraftRequests(self.sm, _time=5000)  # 5s timeout
        self.last_data = {}
        self.logger.info("✅ Connected to MSFS via SimConnect")
    
    def get_aircraft_data(self):
        try:
            new_data = {}
            for key, sim_key in [
                ("Latitude", "PLANE_LATITUDE"),
                ("Longitude", "PLANE_LONGITUDE"),
                ("Altitude", "PLANE_ALTITUDE"),
                ("Heading", "PLANE_HEADING_DEGREES_TRUE")  # Changed to TRUE for consistency
            ]:
                value = self.aq.get(sim_key)
                self.logger.info(f"Fetched {sim_key}: {value}")
                if value is not None:
                    new_data[key] = value
            if new_data:
                self.last_data = new_data
                self.logger.info(f"Updated aircraft data: {new_data}")
            else:
                self.logger.warning("No data retrieved from SimConnect")
            return self.last_data
        except Exception as e:
            self.logger.error(f"Error fetching aircraft data: {e}")
            return {}
    
    def stop(self):
        try:
            self.sm.exit()
            self.logger.info("Disconnected from SimConnect")
        except Exception as e:
            self.logger.error(f"Error disconnecting: {e}")

sim_server = SimConnectServer()

def get_aircraft_data(force_update=False):
    return sim_server.get_aircraft_data()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    while True:
        data = sim_server.get_aircraft_data()
        if data:
            print(f"Current Aircraft Data: {data}")
        else:
            print("Failed to retrieve aircraft data")
        time.sleep(1)
    sim_server.stop()