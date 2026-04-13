import os
from supabase import create_client, Client
from typing import Dict, Any
import datetime
import time

class BillingAgent:
    def __init__(self):
        url: str = os.environ.get("SUPABASE_URL")
        key: str = os.environ.get("SUPABASE_KEY")
        if url and key:
            try:
                self.supabase: Client = create_client(url, key)
            except Exception as e:
                print(f"[BillingAgent] Failed to init Supabase: {e}")
                self.supabase = None
        else:
            self.supabase = None

    def process_exit(self, license_plate: str) -> Dict[str, Any]:
        """
        Handle Vehicle Exit:
        1. Find Active Session
        2. Calculate Fee
        3. Close Session
        4. Free Slot
        """
        if not self.supabase:
            return {"status": "error", "message": "DB Disconnected"}
            
        print(f"[BillingAgent] Processing Exit for {license_plate}")
        
        try:
            # 1. Find Session
            session = self.supabase.table("active_sessions")\
                .select("*")\
                .eq("license_plate", license_plate)\
                .eq("is_active", True)\
                .execute()
                
            if not session.data:
                return {"status": "error", "message": "Vehicle not found inside."}
                
            record = session.data[0]
            slot_id = record.get('slot_id')
            entry_time_str = record.get('created_at') # 'created_at' is default timestamp col in Supabase
            
            # 2. Calculate Duration
            try:
                 # Default Supabase format: "2023-10-27T10:00:00+00:00" or similar
                 entry_dt = datetime.datetime.fromisoformat(entry_time_str.replace("Z", "+00:00"))
            except Exception as e:
                 print(f"[BillingAgent] Time parse error: {e}")
                 entry_dt = datetime.datetime.now(datetime.timezone.utc) # Fallback
                 
            exit_dt = datetime.datetime.now(datetime.timezone.utc)
            duration_hours = (exit_dt - entry_dt).total_seconds() / 3600.0
            
            # 3. Calculate Fee (Dynamic Pricing Mock)
            base_rate = 20.0 # Rs per hour
            fee = round(duration_hours * base_rate, 2)
            if fee < 10: fee = 10 # Min charge
            
            # 4. Update DB
            
            # A. Close Session
            self.supabase.table("active_sessions").update({
                "is_active": False,
                # "exit_time": exit_dt.isoformat(), # If column exists
                "amount_paid": fee,
                "payment_status": "PAID" 
            }).eq("id", record['id']).execute()
            
            # B. Free Slot
            if slot_id:
                self.supabase.table("parking_slots").update({
                    "status": "FREE", 
                    "current_vehicle": None
                }).eq("id", slot_id).execute()
            
            return {
                "status": "success",
                "license_plate": license_plate,
                "duration_hours": round(duration_hours, 2),
                "fee": fee,
                "slot_freed": slot_id,
                "message": "Gate Opening... Payment Successful."
            }
        except Exception as e:
            print(f"[BillingAgent] Error: {e}")
            return {"status": "error", "message": str(e)}
