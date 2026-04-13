from fastapi import FastAPI, UploadFile, File, Body
import time
from dotenv import load_dotenv
load_dotenv()
import traceback
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from .agents.vision import VisionAgent
from .agents.allocation import AllocationAgent
from .agents.verification import VerificationAgent
from .agents.exit_billing import BillingAgent

app = FastAPI(title="OptiSlot AO - Full Logic")

# --- SINGLETON AGENTS ---
vision_agent = VisionAgent()
allocation_agent = AllocationAgent()
verification_agent = VerificationAgent()
billing_agent = BillingAgent()

# --- MODELS ---
class VerifyRequest(BaseModel):
    user_id: str # License Plate
    scanned_qr: str

class ExitRequest(BaseModel):
    license_plate: str

# --- WORKFLOW ---
async def process_entry_workflow(gate_id: str, image_bytes: bytes = None):
    """
    Full Entry Workflow: Vision -> Allocation.
    """
    start_time = time.time()
    
    # 1. Vision Analysis (Real Inference)
    vehicle_data = await vision_agent.analyze_stream(gate_id, image_bytes)
    print(f"[Workflow] Vision Result: {vehicle_data}")
    
    # 2. Allocation Logic
    allocation_result = allocation_agent.allocate_slot(vehicle_data)
    print(f"[Workflow] Allocation Result: {allocation_result}")
    
    duration = (time.time() - start_time) * 1000
    
    # Return data for the API response
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

@app.post("/verify")
async def verify_parking(req: VerifyRequest):
    """
    User Scans QR Code to Verify Location
    """
    try:
        result = verification_agent.verify_active_location(req.user_id, req.scanned_qr)
        return {"status": "success", "data": result}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

@app.post("/exit")
async def process_exit(req: ExitRequest):
    """
    Process Exit and Billing
    """
    try:
        result = billing_agent.process_exit(req.license_plate)
        return {"status": "success", "data": result}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
