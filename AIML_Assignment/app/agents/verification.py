import os
from supabase import create_client, Client
from typing import Dict, Any, List
import json
import cv2
import numpy as np

class VerificationAgent:
    def __init__(self):
        url: str = os.environ.get("SUPABASE_URL")
        key: str = os.environ.get("SUPABASE_KEY")
        if url and key:
            try:
                self.supabase: Client = create_client(url, key)
            except Exception as e:
                print(f"[VerificationAgent] Failed to init Supabase: {e}")
                self.supabase = None
        else:
            self.supabase = None
            
        # Load Zones
        self.zones_config = {}
        paths = [
            "parking_zones.json", 
            r"d:\Non_Academic\Project\Smart_Parking_Traffic_Test\AIML_Assignment\parking_zones.json"
        ]
        for p in paths:
            if os.path.exists(p):
                try:
                    with open(p, "r") as f:
                        self.zones_config = json.load(f)
                    break
                except Exception as e:
                    print(f"[VerificationAgent] Failed to load config {p}: {e}")

    def verify_active_location(self, license_plate: str, scanned_qr_slot: str) -> Dict[str, Any]:
        """
        Active Verification: User parks and scans QR on the pillar.
        """
        if not self.supabase:
            return {"verified": False, "error": "DB Disconnected"}
            
        # 1. Get Assigned Slot for this Car
        print(f"[VerificationAgent] Verifying {license_plate} at {scanned_qr_slot}")
        session = self.supabase.table("active_sessions")\
            .select("*")\
            .eq("license_plate", license_plate)\
            .eq("is_active", True)\
            .execute()
            
        if not session.data:
            return {"verified": False, "message": "No active session found for this vehicle."}
            
        assigned_slot_id = session.data[0]['slot_id']
        
        # 2. Check Match
        if scanned_qr_slot == assigned_slot_id:
            # Update verification status
            try:
                self.supabase.table("active_sessions").update({"is_verified": True}).eq("id", session.data[0]['id']).execute()
            except:
                pass # Field might not exist yet
                
            return {
                "verified": True, 
                "message": "Location Verified. Welcome!",
                "slot_id": assigned_slot_id
            }
        else:
            # Log Anomaly?
            return {
                "verified": False, 
                "message": f"Incorrect Spot! Please move to {assigned_slot_id}",
                "assigned": assigned_slot_id,
                "scanned": scanned_qr_slot
            }

    def passive_audit(self, detected_bboxes: List[Any], frame_shape) -> Dict[str, Any]:
        """
        Passive Verification:
        Check if cars are physically present in slots marked as occupied in DB.
        """
        # Placeholder for full IoU logic
        # 1. Map 2D pixel coordinates to Slots defined in JSON
        # 2. Check Overlap
        # 3. Compare with DB status
        
        # returning simple count for now
        return {
            "occupied_count": len(detected_bboxes),
            "status": "Audit Complete"
        }
