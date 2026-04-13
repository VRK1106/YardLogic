import os
from dotenv import load_dotenv
load_dotenv()
from supabase import create_client, Client
import sys

def check_setup():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    
    print(f"Checking Supabase Setup...")
    print(f"URL: {url}")
    print(f"Key Present: {'Yes' if key else 'No'}")
    
    if not url or not key:
        print("ERROR: Missing Credentials in .env")
        return

    try:
        supabase: Client = create_client(url, key)
        print("Client Initialized.")
        
        # Check parking_slots
        print("Querying 'parking_slots'...")
        res = supabase.table("parking_slots").select("*").limit(1).execute()
        print(f"Success! Found {len(res.data)} rows (limit 1).")
        
        # Check active_sessions
        print("Querying 'active_sessions'...")
        res = supabase.table("active_sessions").select("*").limit(1).execute()
        print(f"Success! Found {len(res.data)} rows (limit 1).")
        
    except Exception as e:
        print(f"\nCRITICAL ERROR: {e}")
        print("\nPossible Causes:")
        print("1. Table does not exist (Did you run db_setup.sql?)")
        print("2. Row Level Security (RLS) policies blocking access")
        print("3. Invalid API Key")

if __name__ == "__main__":
    check_setup()
