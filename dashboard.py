import streamlit as st
import requests
import time
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
                        
                        # Trigger refresh
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error(f"API Error: {response.text}")
                        
                except Exception as e:
                    st.error(f"Connection Error: {e}")

with col2:
    st.markdown("### 📍 Live Parking Grid")
    
    if "supabase" in st.session_state:
        # Default to Manual Refresh to avoid "hanging" the UI
        auto_refresh = st.toggle("Enable Auto-Refresh (5s)", value=False)
        
        if auto_refresh:
            time.sleep(5)
            st.rerun()
            
        if st.button("🔄 Refresh Grid"):
            st.rerun()
            
        try:
            response = st.session_state.supabase.table("parking_slots").select("*").order("id").execute()
            slots = response.data
            
            # Grid Layout
            cols = st.columns(4)
            for i, slot in enumerate(slots):
                status = slot['status']
                s_type = slot['size_type']
                s_id = slot['id']
                vehicle = slot.get('current_vehicle')
                
                # Colors
                bg_color = "#28a745" if status == "FREE" else "#dc3545" if status == "OCCUPIED" else "#ffc107"
                
                with cols[i % 4]:
                    st.markdown(f"""
                    <div style="
                        background-color: {bg_color}; 
                        padding: 15px; 
                        border-radius: 10px; 
                        text-align: center; 
                        color: white;
                        margin-bottom: 10px;
                        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
                        border: 2px solid white;
                    ">
                        <h2 style="margin:0; color:white;">{s_id}</h2>
                        <span style="background:rgba(0,0,0,0.2); padding:2px 8px; border-radius:10px; font-size:0.8em;">{s_type}</span>
                        <p style="margin-top:5px; font-weight:bold;">{vehicle if vehicle else 'EMPTY'}</p>
                    </div>
                    """, unsafe_allow_html=True)
                    
        except Exception as e:
            st.info("Waiting for Database Connection... Ensure .env has SUPABASE_URL")
    else:
        st.warning("Supabase Client not initialized.")
