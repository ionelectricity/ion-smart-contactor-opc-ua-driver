# main.py
import asyncio
import logging
import json
import os
import config
from esp_client import HanBreakerClient
from opc_server import HanBreakerOPCServer

logging.getLogger("asyncua").setLevel(logging.CRITICAL)
_logger = logging.getLogger("Main_EdgeLoop")

STATE_FILE = "sync_state.json"


def load_sync_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    # Default to 0 to synchronize entire device history on first boot.
    return {"evepqi_idx": 0, "events_idx": 0}


def save_sync_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


async def telemetry_loop(esp_client, opc_server):
    """ Real-time Telemetry (RAM) Loop """
    while True:
        try:
            telemetry = await esp_client.get_telemetry()
            if telemetry:
                m_data = telemetry.get("m_data", [])
                meta = telemetry.get("_meta", {})
                manual_states = meta.get("relayManualState", [0, 0, 0, 0])

                await opc_server.update_node_values(m_data, manual_states)

                # Terminal Dashboard
                _logger.info("=== HanBreaker Live Telemetry ===")
                for i in range(min(4, len(m_data))):
                    v = m_data[i].get("vrms", 0.0)
                    a = m_data[i].get("irms", 0.0)
                    w = m_data[i].get("pactive", 0.0)
                    r = "ON" if (m_data[i].get("relay", 0) & 1) else "OFF"

                    _logger.info(
                        "Line %d | %6.2f V | %5.2f A | %7.2f W | Relay: %s",
                        i + 1,
                        v,
                        a,
                        w,
                        r,
                    )

                _logger.info("=================================")
        except Exception as e:
            _logger.error(f"Telemetry loop error: {e}")

        await asyncio.sleep(config.POLL_INTERVAL_SEC)


async def store_and_forward_loop(esp_client, opc_server):
    """ Offline File Synchronization Loop (Store and Forward) """
    sync_state = load_sync_state()

    # Optional: If you want to force a re-download of ALL history right now,
    # you can uncomment this line to reset the state back to zero:
    # sync_state = {"evepqi_idx": 0, "events_idx": 0}

    while True:
        try:
            info = await esp_client.get_page_info()
            if not info or "index" not in info:
                await asyncio.sleep(config.SYNC_INTERVAL_SEC)
                continue

            esp_indexes = info["index"]
            curr_evepqi_idx = esp_indexes[config.FILE_ID_EVEPQI]
            curr_events_idx = esp_indexes[config.FILE_ID_EVENTS]

            # 1. Sync PQI Events (File 6)
            while sync_state["evepqi_idx"] < curr_evepqi_idx:
                target_idx = sync_state["evepqi_idx"]
                record = await esp_client.read_file_record("EVEPQI", target_idx)

                if "logevepqi" in record:
                    pqi = record["logevepqi"]
                    _logger.info(f"Backfilling PQI Event: {pqi.get('type')} at UTC {pqi.get('utc')}")
                    await opc_server.trigger_historical_pqi_event(
                        pqi_type=pqi.get("type", "UNKNOWN"),
                        channel=pqi.get("channel", 0),
                        duration=pqi.get("duration", 0),
                        value=pqi.get("value", 0.0) / 100.0,
                        utc_timestamp=pqi.get("utc", 0)
                    )
                sync_state["evepqi_idx"] += 1
                save_sync_state(sync_state)

            # 2. Sync System Events (File 7)
            while sync_state["events_idx"] < curr_events_idx:
                target_idx = sync_state["events_idx"]
                record = await esp_client.read_file_record("EVENTS", target_idx)

                if "logevents" in record:
                    ev = record["logevents"]
                    _logger.info(f"Backfilling System Event: {ev.get('type')} at UTC {ev.get('utc')}")
                    await opc_server.trigger_historical_sys_event(
                        evt_type=ev.get("type", "UNKNOWN"),
                        state=ev.get("state", 0),
                        old_val=ev.get("oldvalue", ""),
                        new_val=ev.get("newvalue", ""),
                        utc_timestamp=ev.get("utc", 0)
                    )
                sync_state["events_idx"] += 1
                save_sync_state(sync_state)

        except Exception as e:
            _logger.error(f"Sync loop error: {e}")

        await asyncio.sleep(config.SYNC_INTERVAL_SEC)


async def run_driver():
    esp_client = HanBreakerClient(device_ip=config.DEVICE_IP)
    opc_server = HanBreakerOPCServer(esp_client=esp_client)

    await opc_server.init()
    await opc_server.start()

    _logger.info(f"OPC UA Edge Server running at {config.OPC_ENDPOINT}")

    # Run both loops concurrently
    await asyncio.gather(
        telemetry_loop(esp_client, opc_server),
        store_and_forward_loop(esp_client, opc_server)
    )


if __name__ == "__main__":
    try:
        asyncio.run(run_driver())
    except KeyboardInterrupt:
        pass