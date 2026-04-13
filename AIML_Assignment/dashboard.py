import streamlit as st
import requests
import time
from datetime import datetime
import os
from dotenv import load_dotenv
load_dotenv()
from supabase import create_client, Client

# Configuration
API_URL = "http://127.0.0.1:8000"

st.set_page_config(page_title="OptiSlot Dashboard", page_icon="🚗", layout="wide")

# Initialize Supabase
if "supabase" not in st.session_state:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if url and key:
        try:
             st.session_state.supabase = create_client(url, key)
        except Exception as e:
             st.error(f"Supabase Init Error: {e}")

st.title("🚗 OptiSlot Intelligent Dashboard")

# Layout: Split into Entry Gate and Map
col1, col2 = st.columns([1, 2])

with col1:
    st.markdown("### 📸 Entry Gate Vision")
    
    # Selection: Upload or Camera
    input_method = st.radio("Select Input Method", ["Upload Image", "Take Photo"], horizontal=True)
    
    image_file = None
    if input_method == "Upload Image":
        image_file = st.file_uploader("Upload Vehicle Image", type=['jpg', 'jpeg', 'png'])
    else:
        image_file = st.camera_input("Take a photo")
    
    if image_file is not None:
        if input_method == "Upload Image":
            st.image(image_file, caption="Camera Feed", use_container_width=True)
        
        if st.button("🚨 SCAN & ENTRY", type="primary"):
            with st.spinner("Processing Vision & Allocation..."):
                try:
                    files = {"file": (image_file.name if hasattr(image_file, 'name') else "camera_capture.jpg", image_file.getvalue(), "image/jpeg")}
                    
                    start_ts = time.time()
                    response = requests.post(f"{API_URL}/gate/GATE_01/entry", files=files)
                    latency = (time.time() - start_ts) * 1000
                    
                    if response.status_code == 200:
                        data = response.json()
                        st.success(f"Entry Processed in {latency:.2f}ms")
                        
                        res = data.get("data", {})
                        
                        st.metric("License Plate", res.get("license_plate", "Unknown"))
                        st.metric("Vehicle Type", res.get("vehicle_type", "Unknown").title())
                        
                        slot_id = res.get("allocated_slot_id")
                        if slot_id:
                            st.success(f"✅ Allocated Slot: {slot_id}")
                        else:
                            st.error(f"❌ Allocation Failed: {res.get('message')}")
                            
                        with st.expander("Technical JSON"):
                            st.json(data)
                        
                        # result stays on screen; grid auto-updates via fragment
                    else:
                        st.error(f"API Error: {response.text}")
                        
                except Exception as e:
                    st.error(f"Connection Error: {e}")

with col2:
    st.markdown("### 📍 Live Parking Grid")
    
    if "supabase" in st.session_state:
        # Reset Button (Place it here to be visible)
        if st.button("🔴 RESET SYSTEM", type="primary", use_container_width=True):
            try:
                # 1. Reset all slots to FREE
                st.session_state.supabase.table("parking_slots").update({
                    "status": "FREE", 
                    "current_vehicle": None
                }).neq("id", "0").execute() # Applies to all valid IDs
                
                # 2. Reset all active sessions (Mark as inactive)
                st.session_state.supabase.table("active_sessions").update({
                    "is_active": False, 
                    "exit_time": datetime.now().isoformat(), # Mark exit time as now
                    "payment_status": "Admin Reset"
                }).eq("is_active", True).execute()
                
                st.success("System Reset Successfully! (Slots Freed & Sessions Closed)")
                time.sleep(1)
                st.rerun()
            except Exception as e:
                st.error(f"Reset Failed: {e}")

        # Live Parking Grid with Auto-Refresh (No Flicker)
        @st.fragment(run_every=10)
        def render_parking_grid():
            try:
                response = st.session_state.supabase.table("parking_slots").select("*").order("id").execute()
                slots = response.data
                st.dataframe(slots, use_container_width=True)
                st.caption(f"Last Updated: {time.strftime('%H:%M:%S')}")
            except Exception as e:
                st.error(f"Data Fetch Error: {e}")
        
        render_parking_grid()
                    

    else:
        st.warning("Supabase Client not initialized.")
