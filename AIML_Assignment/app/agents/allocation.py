import os
from supabase import create_client, Client
from typing import Dict, Any, List, Optional
import json
import datetime

class AllocationAgent:
    def __init__(self):
        url: str = os.environ.get("SUPABASE_URL")
        key: str = os.environ.get("SUPABASE_KEY")
        if not url or not key:
            print("[AllocationAgent] WARNING: Supabase credentials not found in environment!")
            self.supabase = None
        else:
            try:
                self.supabase: Client = create_client(url, key)
                print("[AllocationAgent] Supabase Client Initialized.")
            except Exception as e:
                print(f"[AllocationAgent] Failed to init Supabase: {e}")
                self.supabase = None

    def allocate_slot(self, vehicle_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Allocates a parking slot based on vehicle size.
        """
        if not self.supabase:
             return {"allocated": False, "error": "Database not connected", "slot_id": "N/A"}

        plate = vehicle_data.get("license_plate", "UNKNOWN")
        dims = vehicle_data.get("dimensions", {})
        size_class = dims.get("size_class", "Medium")
        
        print(f"[AllocationAgent] Attempting allocation for {plate} ({size_class})")

        try:
            # 1. Check if already parked (prevent double entry)
            # We filter by status=active if you have a status column, or just existence in active_sessions
            existing = self.supabase.table("active_sessions").select("*").eq("license_plate", plate).eq("is_active", True).execute()
            if existing.data:
                return {
                    "allocated": False, 
                    "message": f"Vehicle {plate} is already inside.", 
                    "slot_id": existing.data[0].get('slot_id')
                }

            # 2. Fetch all free slots
            # We try to find a slot that matches the size, or a larger one if needed
            response = self.supabase.table("parking_slots").select("*").eq("status", "FREE").execute()
            free_slots = response.data
            
            allocated_slot = None
            
            # Strategy: Best Fit
            # 1. Try exact size match
            for slot in free_slots:
                if slot.get('size_type') == size_class:
                    allocated_slot = slot
                    break
            
            # 2. If no exact match AND car is small/medium, try larger slots
            if not allocated_slot:
                if size_class == 'Small':
                     for slot in free_slots:
                        if slot.get('size_type') in ['Medium', 'Large']:
                            allocated_slot = slot
                            break
                elif size_class == 'Medium':
                    for slot in free_slots:
                         if slot.get('size_type') == 'Large':
                            allocated_slot = slot
                            break
            
            if allocated_slot:
                slot_id = allocated_slot['id']
                print(f"[AllocationAgent] Assigning {slot_id} to {plate}")
                
                # 3. Transaction: Update Slot & Create Session
                
                # A. Update Slot Status
                self.supabase.table("parking_slots").update({
                    "status": "OCCUPIED", 
                    "current_vehicle": plate
                }).eq("id", slot_id).execute()
                
                # B. Create Active Session
                # Using standard ISO format for timestamps if needed, but Supabase handles defaults
                self.supabase.table("active_sessions").insert({
                    "license_plate": plate,
                    "slot_id": slot_id,
                    "vehicle_type": size_class,
                    "is_active": True
                    # "entry_time" defaults to now() in DB
                }).execute()
                
                return {
                    "allocated": True,
                    "slot_id": slot_id,
                    "vehicle_class": size_class,
                    "message": f"Assigned to {slot_id}"
                }
            else:
                return {
                    "allocated": False,
                    "slot_id": None,
                    "message": "Parking Full"
                }
                
        except Exception as e:
            print(f"[AllocationAgent] Error: {e}")
            return {"allocated": False, "message": f"DB Error: {str(e)}"}
