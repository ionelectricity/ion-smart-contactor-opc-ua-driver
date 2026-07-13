# test_relay_methods.py
import asyncio
from asyncua import Client, ua


async def main():
    print("Connecting to OPC UA Edge Server to test Relays...")
    async with Client("opc.tcp://127.0.0.1:4840/freeopcua/server/") as client:

        objects = client.nodes.objects
        manual_method = client.get_node("ns=2;s=HanBreakerDevice.MethodSet.SetManualMode")
        relay_method = client.get_node("ns=2;s=HanBreakerDevice.MethodSet.SetAllRelaysState")

        # 1. Take Control (Enable Manual Mode for all 4 lines)
        print("Taking control: Putting all lines into MANUAL mode...")
        for i in range(4):
            # Arguments: LineIndex (Int32), State (Boolean)
            await objects.call_method(manual_method,
                                      ua.Variant(i, ua.VariantType.Int32),
                                      ua.Variant(True, ua.VariantType.Boolean))

        # 2. Turn Relays ON
        print("\nTurning ALL Relays ON... (Sending True)")
        await objects.call_method(relay_method, ua.Variant(True, ua.VariantType.Boolean))

        print("\nWaiting 5 seconds (You should hear them click!)...")
        await asyncio.sleep(5)

        # 3. Turn Relays OFF
        print("\nTurning ALL Relays OFF... (Sending False)")
        await objects.call_method(relay_method, ua.Variant(False, ua.VariantType.Boolean))

        # 4. Release Control (Restore Timetable Mode)
        print("\nReleasing control: Restoring TIMETABLE mode...")
        for i in range(4):
            await objects.call_method(manual_method,
                                      ua.Variant(i, ua.VariantType.Int32),
                                      ua.Variant(False, ua.VariantType.Boolean))

        print("Test Complete.")


if __name__ == "__main__":
    asyncio.run(main())