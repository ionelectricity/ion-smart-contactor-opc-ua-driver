# config.py

DEVICE_IP = "10.0.0.101"
POLL_INTERVAL_SEC = 3.0  # Synced with ESP32 FAST_PERIOD_S
SYNC_INTERVAL_SEC = 10.0 # How often to check for offline files

OPC_ENDPOINT = "opc.tcp://0.0.0.0:4840/freeopcua/server/"
OPC_SERVER_NAME = "HanBreaker OPC UA Edge Node"
NAMESPACE_URI = "http://semitronica.pt/hanbreaker/"

# ESP32 File IDs (from file_hanbreaker.h)
FILE_ID_EVEPQI = 6
FILE_ID_EVENTS = 7

UNITS = {
    "V": {"DisplayName": "V", "Description": "Volts"},
    "A": {"DisplayName": "A", "Description": "Amperes"},
    "W": {"DisplayName": "W", "Description": "Watts"},
    "Hz": {"DisplayName": "Hz", "Description": "Hertz"}
}