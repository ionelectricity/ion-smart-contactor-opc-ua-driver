# esp_client.py
import aiohttp
import logging

_logger = logging.getLogger("ESP_Client")


class HanBreakerClient:
    def __init__(self, device_ip: str):
        self.base_url = f"http://{device_ip}/api"

    async def _post_json(self, endpoint: str, payload: dict) -> dict:
        timeout = aiohttp.ClientTimeout(total=5)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(f"{self.base_url}/{endpoint}", json=payload) as resp:
                    if resp.status == 200:
                        return await resp.json()
        except Exception as e:
            _logger.debug(f"HTTP Error on {endpoint}: {e}")
        return {}

    async def get_telemetry(self) -> dict:
        """ Real-time telemetry (RAM) """
        return await self._post_json("readInfo", {"page": "pageMData"})

    async def get_page_info(self) -> dict:
        """ Gets device metadata, including the file index array """
        return await self._post_json("readInfo", {"page": "pageInfo"})

    async def read_file_record(self, filename: str, index: int) -> dict:
        """ Downloads a specific historical record from ESP32 Flash """
        return await self._post_json("readFile", {"fn": filename, "index": index})

    async def set_relay_state(self, line_index: int, state: bool) -> bool:
        relays = [0, 0, 0, 0]
        relays[line_index] = 1
        payload = {"setRelay": relays} if state else {"resetRelay": relays}
        res = await self._post_json("relayComand", payload)
        return bool(res)

    async def set_manual_mode(self, line_index: int, manual: bool) -> bool:
        relays_mode = [255, 255, 255, 255]
        relays_mode[line_index] = 1 if manual else 0
        res = await self._post_json("enableRelayComand", {"relayMode": relays_mode})
        return bool(res)