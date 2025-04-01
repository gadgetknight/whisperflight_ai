"""
Whisper Flight AI - Mock SimConnect Import Bridge
Version: 1.0.1
Purpose: Bridge file to maintain compatibility with import patterns
Last Updated: March 31, 2025

Changes in v1.0.1:
- Fixed direct import to use the simconnect_loader instead
- Preserves backward compatibility with existing imports
- Avoids circular import issues
"""

# Import from the loader instead of directly from mock_simconnect_server
from simconnect_loader import sim_server, get_connection_info

# For backward compatibility
from mock_simconnect_server import SimConnectServer


# Compatibility function
def get_aircraft_data(force_update=False):
    """Compatibility function for backward compatibility"""
    if sim_server:
        return sim_server.get_aircraft_data()
    return None
