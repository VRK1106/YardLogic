import os
from dotenv import load_dotenv
load_dotenv()
from supabase import create_client, Client
import sys

def seed_database():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    
    if not url or not key:
        print("ERROR: Missing Credentials in .env")
        return

    try:
        supabase: Client = create_client(url, key)
        print("Client Initialized.")
        
        # 1. Clear Existing (Optional, be careful)
        print("Clearing existing slots (if any)...")
        # supabase.table("parking_slots").delete().neq("id", "dummy").execute() # Simple clear
        
        # 2. Seed Data
        slots = [
            {'id': 'A1', 'size_type': 'Small', 'status': 'FREE'},
            {'id': 'A2', 'size_type': 'Small', 'status': 'FREE'},
            {'id': 'A3', 'size_type': 'Small', 'status': 'FREE'},
            {'id': 'A4', 'size_type': 'Small', 'status': 'FREE'},
            
            {'id': 'B1', 'size_type': 'Medium', 'status': 'FREE'},
            {'id': 'B2', 'size_type': 'Medium', 'status': 'FREE'},
            {'id': 'B3', 'size_type': 'Medium', 'status': 'FREE'},
            {'id': 'B4', 'size_type': 'Medium', 'status': 'FREE'},
            
            {'id': 'C1', 'size_type': 'Large', 'status': 'FREE'},
            {'id': 'C2', 'size_type': 'Large', 'status': 'FREE'},
            {'id': 'C3', 'size_type': 'Large', 'status': 'FREE'},
            {'id': 'C4', 'size_type': 'Large', 'status': 'FREE'},
        ]
        
        print(f"Seeding {len(slots)} slots...")
        res = supabase.table("parking_slots").upsert(slots).execute()
        print(f"Success! Inserted/Updated slots.")
        
    except Exception as e:
        print(f"\nCRITICAL ERROR: {e}")

if __name__ == "__main__":
    seed_database()
