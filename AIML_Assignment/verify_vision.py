import asyncio
import os
from app.agents.vision import VisionAgent

# Helper to run async code
def run_async(coro):
    return asyncio.get_event_loop().run_until_complete(coro)

async def test_vision():
    print("Initializing VisionAgent...")
    agent = VisionAgent()
    
    image_path = "test_car.jpeg"
    if not os.path.exists(image_path):
        print(f"Error: {image_path} not found.")
        return

    print(f"Reading {image_path}...")
    with open(image_path, "rb") as f:
        image_bytes = f.read()

    print("Analyzing stream...")
    result = await agent.analyze_stream(gate_id="GATE-01", image_bytes=image_bytes)
    
    print("\n=== Result ===")
    print(f"Vehicle Type: {result.get('vehicle_type')}")
    print(f"License Plate: {result.get('license_plate')}")
    print(f"Confidence: {result.get('confidence')}")

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(test_vision())
