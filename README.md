# iON Smart Contactor OPC-UA Driver

An edge gateway driver that acts as a bridge between the iON Smart Contactor (ESP32-based REST API) and Industrial SCADA/HMI systems via **OPC-UA**.

This driver periodically polls the contactor for live telemetry, handles bidirectional method calls to control the physical relays, and features a "Store-and-Forward" synchronization loop that pulls offline historical events from the device's flash memory into a local SQLite OPC-UA Historian.

## 🚀 Supported Features

### 1. Real-Time Telemetry (Data Access)
Exposes live grid measurements as OPC-UA `AnalogItemType` nodes with EURange and EngineeringUnits configured:
*   Voltage (Vrms)
*   Current (Irms)
*   Active Power (W)
*   Frequency (Hz)
*   Relay State (Boolean)
*   Manual Mode Status (Boolean)

### 2. Remote Control (Method Calls)
Provides secure OPC-UA Methods to manipulate the contactor:
*   `SetRelayState(LineIndex, State)`: Turn a specific relay ON/OFF.
*   `SetAllRelaysState(State)`: Batch command to actuate all relays simultaneously.
*   `SetManualMode(LineIndex, State)`: Override local timetable schedules and take manual control via OPC-UA.

### 3. Historical Data Access (HDA)
*   **Variable History:** Live telemetry is automatically historized into a local SQLite database, allowing OPC-UA clients to query past voltage/current trends.
*   **Event History:** Custom events triggered on the device while offline are synchronized via a background Store-and-Forward loop. Supported custom event types:
    *   `PowerQualityEvent`: Logs Under/Overvoltage, Sags, and Surges with duration and magnitude.
    *   `HanBreakerSystemEvent`: Logs device state changes (e.g., Timetable executed, Manual override).

## ⚙️ Prerequisites & Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/ionelectricity/ion-smart-contactor-opc-ua-driver.git
   cd ion-smart-contactor-opc-ua-driver
   ```

2. Install the required Python packages (Python 3.8+ recommended):
   ```bash
   pip install -r requirements.txt
   ```

3. Update your device IP address in `src/config.py`:
   ```python
   DEVICE_IP = "10.0.0.101"
   OPC_ENDPOINT = "opc.tcp://0.0.0.0:4840/freeopcua/server/"
   ```

## 🖥️ Usage

Start the OPC-UA Edge Server by navigating to the source directory:
```bash
cd src
python main.py
```
*The driver will start an async loop polling the ESP32 for live RAM telemetry, while a background task syncs the flash history.*

### Connecting a Client
You can use any standard OPC-UA client (such as [FreeOpcUa/opcua-client-gui](https://github.com/FreeOpcUa/opcua-client-gui) or UaExpert) to connect to the driver at `opc.tcp://127.0.0.1:4840/freeopcua/server/`.

## 🧪 Testing utilities

A suite of test scripts is provided in the `tests/` directory to validate functionality without a full SCADA system:

*   **`test_relay_methods.py`**: Connects to the local OPC-UA server, takes manual control of the contactor, actuates the relays, and releases control.
*   **`test_history.py`**: Queries the SQLite historian for the last 10 minutes of voltage trends.
*   **`test_history_advanced.py`**: Constructs a complex `EventFilter` to query the SQLite historian for custom Power Quality and System Events.
*   **`inspect_db.py`**: A raw SQLite database inspector (requires `pandas`) to verify data is being committed correctly.

## 🏗️ Architecture Notes

*   **Custom SQLite Historian:** The standard `asyncua` historian struggles with custom Event Fields. This repository includes a custom `SafeHistorySQLite` class (`src/opc_server.py`) that safely marshals custom variants (Duration, OldValue, NewValue) directly into the database.
*   **Store-and-Forward:** The state of the flash memory sync is tracked in a local `sync_state.json` file. If the Python driver goes offline, it will resume downloading missing events from the ESP32 upon restart.
