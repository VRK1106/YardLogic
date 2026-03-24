import json
import os
from typing import Dict, Any

class NavigationSystem:
    def __init__(self):
        self.zones_config = {}
        # Try to find parking_zones.json
        paths = [
            "parking_zones.json", 
            os.path.join(os.path.dirname(__file__), "AIML_Assignment", "parking_zones.json")
        ]
        for p in paths:
            if os.path.exists(p):
                try:
                    with open(p, "r") as f:
                        self.zones_config = json.load(f)
                    # print(f"[Navigation] Loaded config from {p}")
                    break
                except Exception as e:
                    print(f"[Navigation] Failed to load config {p}: {e}")
        
    def get_directions(self, slot_id: str) -> Dict[str, Any]:
        """
        Returns navigation instructions for a given slot.
        """
        try:
            slot_num = int(''.join(filter(str.isdigit, slot_id)))
        except:
             return {"message": "Invalid Slot ID format", "directions": []}

        zone_name = "General"
        directions = []
        
        # Hardcoded logic matching the previous Plan
        if 1 <= slot_num <= 10:
            zone_name = "Small Vehicles (Zone A)"
            directions = [
                "Proceed straight from Entry Gate.",
                "Turn LEFT immediately for Zone A.",
                f"Look for {slot_id} on your RIGHT."
            ]
        elif 11 <= slot_num <= 20:
            zone_name = "Medium Vehicles (Zone B)"
            directions = [
                "Proceed straight from Entry Gate.",
                "Drive past Zone A.",
                f"Zone B is in the center. {slot_id} is on your LEFT."
            ]
        elif 21 <= slot_num <= 30:
            zone_name = "Large Vehicles (Zone C)"
            directions = [
                "Proceed straight from Entry Gate.",
                "Drive to the back of the lot.",
                f"Zone C is for Large Vehicles. {slot_id} is centrally located."
            ]
        else:
             directions = ["Follow signs to designated parking area."]

        return {
            "target_slot": slot_id,
            "zone": zone_name,
            "instructions": directions
        }
