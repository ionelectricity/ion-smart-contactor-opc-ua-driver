# test_history_advanced.py
import asyncio
from asyncua import Client, ua
from datetime import datetime, timedelta, timezone


async def main():
    print("Connecting to OPC UA Edge Server...")
    async with Client("opc.tcp://127.0.0.1:4840/freeopcua/server/") as client:

        print("\n=== FETCHING VOLTAGE HISTORY (LAST 10 MINUTES) ===")
        var = client.get_node("ns=2;s=HanBreakerDevice.ParameterSet.Line_1.Voltage")
        start_time = datetime.now(timezone.utc) - timedelta(minutes=10)
        end_time = datetime.now(timezone.utc)

        history = await var.read_raw_history(starttime=start_time, endtime=end_time)
        print(f"Found {len(history)} voltage data points.")

        print("\n=== FETCHING ALL EVENT HISTORY (LAST 30 DAYS) ===")
        device_node = client.get_node("ns=2;s=HanBreakerDevice")
        event_start = datetime.now(timezone.utc) - timedelta(days=30)

        # 1. Ask for ALL basic event properties (no complex WHERE clauses that break the library)
        ev_filter = ua.EventFilter()
        ev_filter.SelectClauses = [
            ua.SimpleAttributeOperand(AttributeId=ua.AttributeIds.Value,
                                      TypeDefinitionId=ua.NodeId(ua.ObjectIds.BaseEventType),
                                      BrowsePath=[ua.QualifiedName("Time", 0)]),
            ua.SimpleAttributeOperand(AttributeId=ua.AttributeIds.Value,
                                      TypeDefinitionId=ua.NodeId(ua.ObjectIds.BaseEventType),
                                      BrowsePath=[ua.QualifiedName("Message", 0)]),
        ]

        # 2. Append our Custom Fields
        custom_fields = ["EventTypeString", "Channel", "DurationMs", "Value", "StateValue", "OldValue", "NewValue"]
        for field in custom_fields:
            op = ua.SimpleAttributeOperand()
            op.AttributeId = ua.AttributeIds.Value
            op.TypeDefinitionId = ua.NodeId(
                ua.ObjectIds.BaseEventType)  # Explicitly request custom fields
            op.BrowsePath = [ua.QualifiedName(field, 2)]
            ev_filter.SelectClauses.append(op)

        details = ua.ReadEventDetails()
        details.StartTime = event_start
        details.EndTime = end_time
        details.NumValuesPerNode = 100
        details.Filter = ev_filter

        try:
            result = await device_node.history_read_events(details)
            events = result.HistoryData.Events

            if not events:
                print("No Events found in the database.")
            else:
                print(f"Found {len(events)} Events:")
                for ev in events:
                    fields = ev.EventFields

                    e_time = fields[0].Value
                    e_msg = fields[1].Value.Text if fields[1].Value else "No Message"

                    # Extract the raw EventTypeString
                    e_type = fields[2].Value

                    # Differentiate the printing based on what type of event it is
                    if "Power Quality" in e_msg:
                        e_chan = fields[3].Value
                        e_dur = fields[4].Value
                        e_val = fields[5].Value
                        print(
                            f"  [{e_time}] ⚡ PQI EVENT: {e_type} | Line: {e_chan + 1} | Duration: {e_dur}ms | Value: {e_val}")

                    elif "System Event" in e_msg:
                        e_state = fields[6].Value
                        e_old = fields[7].Value
                        e_new = fields[8].Value
                        print(f"  [{e_time}] ⚙️ SYS EVENT: {e_type} | State: {e_state} | Old: {e_old} -> New: {e_new}")

                    else:
                        print(f"  [{e_time}] ❓ {e_msg}")

        except Exception as e:
            print(f"Event query failed: {e}")


if __name__ == "__main__":
    asyncio.run(main())