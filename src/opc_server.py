# opc_server.py
import logging
import sqlite3
from datetime import datetime, timezone, timedelta
from asyncua import Server, ua, uamethod
from asyncua.server.history_sql import HistorySQLite
from asyncua.ua.ua_binary import variant_to_binary
import config

_logger = logging.getLogger("OPC_Server")

logging.getLogger("asyncua.server.address_space").setLevel(logging.WARNING)
logging.getLogger("asyncua.server.internal_server").setLevel(logging.WARNING)


class SafeHistorySQLite(HistorySQLite):
    def _get_table_name(self, node_id: ua.NodeId) -> str:
        clean_id = str(node_id.Identifier).replace("'", "").replace('"', "")
        return f"{node_id.NamespaceIndex}_{clean_id}"

    async def force_create_event_table(self, source_id, evtypes):
        """ Forcefully creates the table bypassing the library's event loop """
        ev_fields_raw = await self._get_event_fields(evtypes)
        ev_fields = list(set(ev_fields_raw))
        self._event_fields[source_id] = ev_fields
        table = self._get_table_name(source_id)

        columns = "".join([f', "{field}" BLOB' for field in ev_fields]) if ev_fields else ""
        sql = f'CREATE TABLE IF NOT EXISTS "{table}" (_Id INTEGER PRIMARY KEY NOT NULL, _Timestamp TIMESTAMP, _EventTypeName TEXT{columns})'

        try:
            await self._db.execute(sql, None)
            await self._db.commit()
            _logger.info(f"Event table verified: {table}")
        except Exception as e:
            _logger.error(f"CREATE TABLE Failed: {e}\nQuery: {sql}")

    async def direct_insert_event(self, event):
        """ Directly injects the event into SQLite, bypassing the asyncua Subscription drops """
        table = self._get_table_name(event.emitting_node)

        # Construct event dictionary ensuring only registered OPC-UA fields are passed to the historian.
        ev_variant_dict = {}
        for key, vtype in event.data_types.items():
            val = getattr(event, key, None)

            # Prevent "None" errors on strict OPC UA types
            if val is None:
                vt_val = getattr(vtype, "value", vtype)
                if vt_val == 21:  # LocalizedText
                    val = ua.LocalizedText("")
                elif vt_val == 12:  # String
                    val = ""
                elif vt_val == 17:  # NodeId
                    val = ua.NodeId()
                elif vt_val == 15:  # ByteString
                    val = b""
                elif vt_val == 13:  # DateTime
                    val = ua.get_win_epoch()

            ev_variant_dict[key] = ua.Variant(val, vtype)

        names = list(ev_variant_dict.keys())
        names.sort()

        # Only insert columns we actually registered during table creation
        valid_names = [n for n in names if n in self._event_fields.get(event.emitting_node, [])]

        columns_str = "".join([f', "{n}"' for n in valid_names])
        placeholders_str = "".join([", ?" for _ in valid_names])

        # Serialize OPC UA Variants to Binary for BLOB columns
        evtup = tuple([sqlite3.Binary(variant_to_binary(ev_variant_dict[n])) for n in valid_names])

        # Convert OPC UA NodeId to string before handing to SQLite
        event_type = getattr(event, "EventType", "Unknown")
        if isinstance(event_type, ua.NodeId):
            event_type = event_type.to_string()

        event_time = getattr(event, "Time", datetime.now(timezone.utc))
        if hasattr(event_time, "isoformat"):
            event_time = event_time.isoformat(" ")

        # Safe parameterized SQL query
        sql = f'INSERT INTO "{table}" ("_Id", "_Timestamp", "_EventTypeName"{columns_str}) VALUES (NULL, ?, ?{placeholders_str})'
        full_tuple = (event_time, event_type) + evtup

        try:
            await self._db.execute(sql, full_tuple)
            await self._db.commit()
            _logger.debug(f"Wrote event to DB: {event.Message.Text}")
        except Exception as e:
            _logger.error(f"INSERT Failed: {e}\nQuery: {sql}")


# ------------------------------------

class HanBreakerOPCServer:
    def __init__(self, esp_client):
        self.esp_client = esp_client
        self.server = Server()
        self.variables = []
        self.nodes_to_historize = []
        self.historian = SafeHistorySQLite("hanbreaker_history.db")

    async def init(self):
        self.server.iserver.history_manager.set_storage(self.historian)
        await self.server.init()
        self.server.set_endpoint(config.OPC_ENDPOINT)
        self.server.set_server_name(config.OPC_SERVER_NAME)
        self.idx = await self.server.register_namespace(config.NAMESPACE_URI)
        await self._build_address_space()

    async def _add_analog_item(self, parent, node_id, name, unit_key, low, high):
        var = await parent.add_variable(node_id, name, ua.Variant(0.0, ua.VariantType.Float),
                                        varianttype=ua.VariantType.Float)
        await var.delete_reference(target=ua.NodeId(ua.ObjectIds.BaseDataVariableType, 0),
                                   reftype=ua.NodeId(ua.ObjectIds.HasTypeDefinition, 0), forward=True,
                                   bidirectional=False)
        await var.add_reference(target=ua.NodeId(ua.ObjectIds.AnalogItemType, 0),
                                reftype=ua.NodeId(ua.ObjectIds.HasTypeDefinition, 0), forward=True, bidirectional=False)

        eu_range = ua.Range(Low=low, High=high)
        await var.add_property(f"{node_id}.EURange", "EURange", eu_range, varianttype=ua.VariantType.ExtensionObject)

        unit_info = config.UNITS[unit_key]
        eu_info = ua.EUInformation(NamespaceUri="http://www.opcfoundation.org/UA/units/un/cefact", UnitId=0,
                                   DisplayName=ua.LocalizedText(unit_info["DisplayName"]),
                                   Description=ua.LocalizedText(unit_info["Description"]))
        await var.add_property(f"{node_id}.EngineeringUnits", "EngineeringUnits", eu_info,
                               varianttype=ua.VariantType.ExtensionObject)

        self.nodes_to_historize.append(var)
        return var

    async def _build_address_space(self):
        device_id = f"ns={self.idx};s=HanBreakerDevice"
        self.device = await self.server.nodes.objects.add_object(device_id, "HanBreakerDevice")
        self.parameter_set = await self.device.add_object(f"{device_id}.ParameterSet", "ParameterSet")
        self.method_set = await self.device.add_object(f"{device_id}.MethodSet", "MethodSet")

        for i in range(4):
            line_id = f"{device_id}.ParameterSet.Line_{i + 1}"
            line_obj = await self.parameter_set.add_object(line_id, f"Line_{i + 1}")
            line_vars = {
                'vrms': await self._add_analog_item(line_obj, f"{line_id}.Voltage", "Voltage", "V", 0.0, 650.0),
                'irms': await self._add_analog_item(line_obj, f"{line_id}.Current", "Current", "A", 0.0, 65.0),
                'pactive': await self._add_analog_item(line_obj, f"{line_id}.ActivePower", "ActivePower", "W", 0.0,
                                                       32000.0),
                'freq': await self._add_analog_item(line_obj, f"{line_id}.Frequency", "Frequency", "Hz", 0.0, 65.0),
            }
            relay_var = await line_obj.add_variable(f"{line_id}.RelayState", "RelayState",
                                                    ua.Variant(False, ua.VariantType.Boolean))
            manual_var = await line_obj.add_variable(f"{line_id}.ManualMode", "ManualMode",
                                                     ua.Variant(False, ua.VariantType.Boolean))
            self.nodes_to_historize.extend([relay_var, manual_var])
            line_vars['relay'] = relay_var
            line_vars['manual'] = manual_var
            self.variables.append(line_vars)

        inarg_line = ua.Argument()
        inarg_line.Name = "LineIndex"
        inarg_line.DataType = ua.NodeId(ua.ObjectIds.Int32)
        inarg_line.ValueRank = -1
        inarg_line.ArrayDimensions = []

        inarg_state = ua.Argument()
        inarg_state.Name = "State"
        inarg_state.DataType = ua.NodeId(ua.ObjectIds.Boolean)
        inarg_state.ValueRank = -1
        inarg_state.ArrayDimensions = []

        await self.method_set.add_method(f"{device_id}.MethodSet.SetRelayState", "SetRelayState",
                                         self.opc_set_relay_state, [inarg_line, inarg_state], [])
        await self.method_set.add_method(f"{device_id}.MethodSet.SetManualMode", "SetManualMode",
                                         self.opc_set_manual_mode, [inarg_line, inarg_state], [])
        await self.method_set.add_method(f"{device_id}.MethodSet.SetAllRelaysState", "SetAllRelaysState",
                                         self.opc_set_all_relays, [inarg_state], [])

        self.pqi_event_type = await self.server.create_custom_event_type(
            self.idx, "PowerQualityEvent", ua.ObjectIds.BaseEventType,
            [("EventTypeString", ua.VariantType.String), ("Channel", ua.VariantType.UInt32),
             ("DurationMs", ua.VariantType.UInt32), ("Value", ua.VariantType.Float)]
        )
        self.pqi_event_gen = await self.server.get_event_generator(self.pqi_event_type, self.device)

        self.sys_event_type = await self.server.create_custom_event_type(
            self.idx, "HanBreakerSystemEvent", ua.ObjectIds.BaseEventType,
            [("EventTypeString", ua.VariantType.String), ("StateValue", ua.VariantType.Int32),
             ("OldValue", ua.VariantType.String), ("NewValue", ua.VariantType.String)]
        )
        self.sys_event_gen = await self.server.get_event_generator(self.sys_event_type, self.device)

    @uamethod
    async def opc_set_relay_state(self, parent, line_index: int, state: bool):
        if not (0 <= line_index <= 3): return ua.StatusCode(ua.StatusCodes.BadInvalidArgument)
        success = await self.esp_client.set_relay_state(line_index, state)
        return ua.StatusCode(ua.StatusCodes.Good if success else ua.StatusCodes.BadDeviceFailure)

    @uamethod
    async def opc_set_manual_mode(self, parent, line_index: int, manual: bool):
        if not (0 <= line_index <= 3): return ua.StatusCode(ua.StatusCodes.BadInvalidArgument)
        success = await self.esp_client.set_manual_mode(line_index, manual)
        return ua.StatusCode(ua.StatusCodes.Good if success else ua.StatusCodes.BadDeviceFailure)

    @uamethod
    async def opc_set_all_relays(self, parent, state: bool):
        payload = {"setRelay": [1, 1, 1, 1]} if state else {"resetRelay": [1, 1, 1, 1]}
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(f"http://{config.DEVICE_IP}/api/relayComand", json=payload,
                                        timeout=5.0) as resp:
                    if resp.status != 200:
                        return ua.StatusCode(ua.StatusCodes.BadDeviceFailure)
            return ua.StatusCode(ua.StatusCodes.Good)
        except Exception as e:
            _logger.error(f"Failed to communicate: {e}")
            return ua.StatusCode(ua.StatusCodes.BadCommunicationError)

    async def update_node_values(self, m_data: list, manual_states: list):
        for i in range(min(4, len(m_data))):
            ld = m_data[i]
            await self.variables[i]['vrms'].write_value(ua.Variant(float(ld.get('vrms', 0.0)), ua.VariantType.Float))
            await self.variables[i]['irms'].write_value(ua.Variant(float(ld.get('irms', 0.0)), ua.VariantType.Float))
            await self.variables[i]['pactive'].write_value(
                ua.Variant(float(ld.get('pactive', 0.0)), ua.VariantType.Float))
            await self.variables[i]['freq'].write_value(ua.Variant(float(ld.get('freq', 0.0)), ua.VariantType.Float))
            await self.variables[i]['relay'].write_value(
                ua.Variant(bool(ld.get('relay', 0) & 1), ua.VariantType.Boolean))
            await self.variables[i]['manual'].write_value(
                ua.Variant(bool(manual_states[i] == 1), ua.VariantType.Boolean))

    async def trigger_historical_pqi_event(self, pqi_type: str, channel: int, duration: int, value: float,
                                           utc_timestamp: int):
        event_time = datetime.fromtimestamp(utc_timestamp / 1000.0, timezone.utc)
        self.pqi_event_gen.event.Time = event_time
        self.pqi_event_gen.event.Message = ua.LocalizedText(f"Power Quality Issue: {pqi_type} on Line {channel + 1}")
        self.pqi_event_gen.event.Severity = 800
        self.pqi_event_gen.event.EventTypeString = pqi_type
        self.pqi_event_gen.event.Channel = channel
        self.pqi_event_gen.event.DurationMs = duration
        self.pqi_event_gen.event.Value = value
        await self.historian.direct_insert_event(self.pqi_event_gen.event)

    async def trigger_historical_sys_event(self, evt_type: str, state: int, old_val: str, new_val: str,
                                           utc_timestamp: int):
        event_time = datetime.fromtimestamp(utc_timestamp / 1000.0, timezone.utc)
        self.sys_event_gen.event.Time = event_time
        self.sys_event_gen.event.Message = ua.LocalizedText(f"System Event: {evt_type}")
        self.sys_event_gen.event.Severity = 500
        self.sys_event_gen.event.EventTypeString = evt_type
        self.sys_event_gen.event.StateValue = state
        self.sys_event_gen.event.OldValue = old_val
        self.sys_event_gen.event.NewValue = new_val
        await self.historian.direct_insert_event(self.sys_event_gen.event)

    async def start(self):
        await self.server.start()

        await self.historian.force_create_event_table(self.device.nodeid, [self.pqi_event_type, self.sys_event_type])

        for node in self.nodes_to_historize:
            await self.server.historize_node_data_change(node, period=timedelta(days=30))

        await self.server.historize_node_event(self.device, period=timedelta(days=30))
        server_node = self.server.get_node(ua.ObjectIds.Server)
        await self.server.historize_node_event(server_node, period=timedelta(days=30))

    async def stop(self):
        await self.server.stop()