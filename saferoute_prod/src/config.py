import os

# Base directory for runtime data
DATA_DIR = os.getenv("DATA_DIR", "/app/data")
CONFIG_DIR = os.path.join(DATA_DIR, "configs")
PROFILES_FILE = os.path.join(DATA_DIR, "profiles.json") # Stores metadata about profiles
DEVICES_FILE = os.path.join(DATA_DIR, "devices.json")   # Stores device mapping

# Routing Table Constants
TABLE_OFFSET = 100
PRIORITY_OFFSET = 50
DEVICE_PRIORITY_BASE = 1000
