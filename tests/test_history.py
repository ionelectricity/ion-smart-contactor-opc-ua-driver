import asyncio
from asyncua import Client
from datetime import datetime, timedelta, timezone


async def main():
    async with Client("opc.tcp://127.0.0.1:4840/freeopcua/server/") as client:
        # Get the Voltage node
        var = client.get_node("ns=2;s=HanBreakerDevice.ParameterSet.Line_1.Voltage")

        # Read the last 10 minutes of history
        start_time = datetime.now(timezone.utc) - timedelta(minutes=10)
        end_time = datetime.now(timezone.utc)

        print("Fetching History...")
        history = await var.read_raw_history(starttime=start_time, endtime=end_time)

        for data_value in history:
            print(f"Time: {data_value.SourceTimestamp} | Value: {data_value.Value.Value} V")


if __name__ == "__main__":
    asyncio.run(main())