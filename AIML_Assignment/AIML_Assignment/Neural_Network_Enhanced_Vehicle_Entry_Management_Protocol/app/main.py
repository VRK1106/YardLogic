from fastapi import FastAPI, UploadFile, File
import time
from dotenv import load_dotenv
load_dotenv()
import traceback
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from .agents.vision import VisionAgent

# keep supabase logic for random allocation
import os, random
from supabase import create_client

# initialize supabase client if credentials available
supabase_client = None
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")
if url and key:
    try:
        supabase_client = create_client(url, key)
        print("[Main] Supabase client initialized for random allocation.")
    except Exception as e:
        print(f"[Main] Failed to init Supabase client: {e}")


def _random_allocate(vehicle_data: dict) -> dict:
    """Pick a random free parking slot (if Supabase configured).

    Returns a dict with `allocated`, `slot_id`, and `message` keys.
    """
    if not supabase_client:
        # fallback to simple random ID
        slot_id = f"RND-{random.randint(1,9999)}"
        return {"allocated": True, "slot_id": slot_id, "message": "Random (no DB)"}

    try:
        resp = supabase_client.table("parking_slots").select("*").eq("status", "FREE").execute()
        free_slots = resp.data or []
        if not free_slots:
            return {"allocated": False, "slot_id": None, "message": "Parking Full"}
        chosen = random.choice(free_slots)
        slot_id = chosen.get("id")

        # mark slot occupied and create a simple session record
        supabase_client.table("parking_slots").update({
            "status": "OCCUPIED",
            "current_vehicle": vehicle_data.get("license_plate")
        }).eq("id", slot_id).execute()
        supabase_client.table("active_sessions").insert({
            "license_plate": vehicle_data.get("license_plate"),
            "slot_id": slot_id,
            "vehicle_type": vehicle_data.get("vehicle_type", "unknown"),
            "is_active": True
        }).execute()

        return {"allocated": True, "slot_id": slot_id, "message": f"Assigned to {slot_id}"}
    except Exception as e:
        print(f"[Main][Allocation] Error: {e}")
        return {"allocated": False, "slot_id": None, "message": "DB Error"}

app = FastAPI(title="OptiSlot AO - Full Logic")

# --- SINGLETON AGENTS ---
vision_agent = VisionAgent()

# --- WORKFLOW ---
async def process_entry_workflow(gate_id: str, image_bytes: bytes = None):
    """
    Entry Workflow: Vision analysis and random slot allocation.
    """
    start_time = time.time()
    
    # 1. Vision Analysis (Real Inference)
    vehicle_data = await vision_agent.analyze_stream(gate_id, image_bytes)
    print(f"[Workflow] Vision Result: {vehicle_data}")
    
    # 2. Random Slot Allocation
    allocation_result = _random_allocate(vehicle_data)
    print(f"[Workflow] Random Allocation Result: {allocation_result}")
    
    duration = (time.time() - start_time) * 1000
    
    return {
        "license_plate": vehicle_data.get('license_plate'),
        "vehicle_type": vehicle_data.get('vehicle_type'),
        "confidence": vehicle_data.get('confidence'),
        "dimensions": vehicle_data.get('dimensions'),
        "allocated_slot_id": allocation_result.get('slot_id'),
        "allocation_status": allocation_result.get('allocated'),
        "message": allocation_result.get('message'),
        "processing_time_ms": round(duration, 2)
    }


# --- API ROUTES ---

@app.post("/gate/{gate_id}/entry")
async def trigger_entry(
    gate_id: str, 
    file: UploadFile = File(...)
):
    """
    Synchronous Entry Trigger (Wait for Result)
    """
    try:
        # Read bytes immediately
        image_bytes = await file.read()
        
        # Run workflow synchronously
        result = await process_entry_workflow(gate_id, image_bytes)
        
        # Return the full result
        return {
            "status": "success", 
            "data": result
        }
    except Exception as e:
        print(traceback.format_exc())
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e), "traceback": traceback.format_exc()}
        )

