import asyncio
import json
import socket

from pywizlight import discovery, wizlight

WIZ_PORT = 38899

class WizMockServer(asyncio.DatagramProtocol):
    def __init__(self):
        super().__init__()
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport
        print(f"Mock WiZ UDP server running on port {WIZ_PORT}")

    def datagram_received(self, data, addr):
        message = data.decode()
        print(f"Received from {addr}: {message}")

        try:
            request = json.loads(message)
        except json.JSONDecodeError:
            print("Invalid JSON received")
            return

        response = self.handle_request(request)
        if response:
            response_bytes = json.dumps(response).encode()
            self.transport.sendto(response_bytes, addr)
            print(f"Sent to {addr}: {response}")

    def handle_request(self, request):
        method = request.get("method")

        # Simulate common WiZ responses
        if method == "getPilot":
            return {
                "method": "getPilot",
                "result": {
                    "state": True,
                    "r": 255,
                    "g": 200,
                    "b": 150,
                    "temp": 3000,
                    "dimming": 80
                }
            }

        elif method == "setPilot":
            return {
                "method": "setPilot",
                "result": {"success": True}
            }

        elif method == "getSystemConfig":
            return {
                "method": "getSystemConfig",
                "result": {
                    "mac": "AA:BB:CC:DD:EE:FF",
                    "moduleName": "ESP01_SHDW_01",
                    "fwVersion": "1.20.0"
                }
            }

        elif method == "registration":
            return {
                "method": "registration",
                "env": "pro",
                "result": {"success": True,
                           "ownerId": 0
                           }
            }

        # Default fallback
        return {
            "error": {
                "code": -1,
                "message": "Unknown method"
            }
        }

async def lookup():
    """Sample code to work with bulbs."""
    # Discover all bulbs in the network via broadcast datagram (UDP)
    # function takes the discovery object and returns a list of wizlight objects.
    bulbs = await discovery.discover_lights(broadcast_space="192.168.178.255", wait_time=5)
    # Print the IP address of the bulb on index 0
    print(f"Bulbs: {len(bulbs)}")

    # Iterate over all returned bulbs
    for bulb in bulbs:
        print(f"Bulb IP address: {bulb.ip}")
        print(bulb.__dict__)
        # Turn off all available bulbs
        # await bulb.turn_off()

    bulb = wizlight("192.168.178.31")

    scenes = await bulb.getSupportedScenes()
    print(scenes)

    # Get the name of the current scene
    state = await bulb.updateState()
    print(state.get_scene())

    print(state.get_extended_white_range())

    # Get the features of the bulb
    bulb_type = await bulb.get_bulbtype()
    print(bulb_type.features.brightness)  # returns True if brightness is supported
    print(bulb_type.features.color)  # returns True if color is supported
    print(bulb_type.features.color_tmp)  # returns True if color temperatures are supported
    print(bulb_type.features.effect)  # returns True if effects are supported
    print(bulb_type.kelvin_range.max)  # returns max kelvin in INT
    print(bulb_type.kelvin_range.min)  # returns min kelvin in INT
    print(bulb_type.name)  # returns the module name of the bulb

    await bulb.async_close()

async def main():
    loop = asyncio.get_running_loop()

    # 1. Manually create the UDP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    # 2. Set REUSEADDR (Windows supports this, but not REUSEPORT)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    # 3. Bind the socket
    # Using "" or "0.0.0.0" listens on all interfaces
    sock.bind(("0.0.0.0", 38899))

    # 4. Set to non-blocking for asyncio
    sock.setblocking(False)

    transport, protocol = await loop.create_datagram_endpoint(
        lambda: WizMockServer(),
        sock=sock
    )

    try:
        await asyncio.sleep(3600)  # run for 1 hour
    finally:
        transport.close()


if __name__ == "__main__":
    asyncio.run(lookup())

