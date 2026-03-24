import streamlit as st
import requests
import time
import os

# Configuration
API_URL = "http://127.0.0.1:5000"

# --- PAGE CONFIG ---
st.set_page_config(
    page_title="OptiSlot Driver",
    page_icon="🚗",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# --- CUSTOM CSS FOR DYNAMIC UI ---
st.markdown("""
    <style>
    /* Global Styles */
    .main {
        background-color: #0e1117;
        color: #ffffff;
    }
    
    /* Card Style */
    .stCard {
        background-color: #262730;
        padding: 20px;
        border-radius: 15px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
        margin-bottom: 20px;
        border: 1px solid #41444e;
    }
    
    /* Dynamic Status Indicators */
    .status-box {
        padding: 15px;
        border-radius: 10px;
        text-align: center;
        font-weight: bold;
        margin: 10px 0;
        animation: pulse 2s infinite;
    }
    
    @keyframes pulse {
        0% { transform: scale(1); }
        50% { transform: scale(1.02); }
        100% { transform: scale(1); }
    }
    
    .status-success { background-color: #28a745; color: white; }
    .status-wait { background-color: #ffc107; color: black; }
    .status-error { background-color: #dc3545; color: white; }
    
    /* Navigation Steps */
    .nav-step {
        background-color: #1f2937;
        border-left: 4px solid #3b82f6;
        padding: 10px 15px;
        margin: 5px 0;
        border-radius: 0 8px 8px 0;
    }
    
    /* Headers */
    h1, h2, h3 {
        font-family: 'Segoe UI', sans-serif;
        font-weight: 600;
    }
    
    .big-slot {
        font-size: 3rem;
        font-weight: 800;
        color: #3b82f6;
        text-align: center;
        margin: 20px 0;
    }
    </style>
    """, unsafe_allow_html=True)

# --- SESSION STATE INITIALIZATION ---
if 'plate' not in st.session_state:
    st.session_state.plate = ""
if 'current_slot' not in st.session_state:
    st.session_state.current_slot = None

# --- HEADER ---
col1, col2 = st.columns([1, 5])
with col1:
    st.write("🚗") 
with col2:
    st.title("OptiSlot Driver")

# --- MAIN NAVIGATION TABS ---
# Use icons for cleaner look
tab1, tab2, tab3, tab4 = st.tabs(["📍 Entry", "✅ Verify", "🚙 Find Car", "💳 Exit"])

# --- TAB 1: ENTRY & NAVIGATION ---
with tab1:
    st.markdown("<div class='stCard'>", unsafe_allow_html=True)
    st.subheader("🏁 Welcome, Driver!")
    
    entry_plate = st.text_input("Vehicle License Plate", 
                               value=st.session_state.plate,
                               placeholder="e.g., MH12AB1234",
                               key="input_entry")
    
    if st.button("🚀 Get Parking Slot", use_container_width=True):
        if not entry_plate:
            st.warning("⚠️ Please enter your license plate.")
        else:
            st.session_state.plate = entry_plate
            with st.status("🔍 Checking Availability...", expanded=True) as status:
                time.sleep(0.5) # Simulate processing
                try:
                    # Query Backend
                    response = requests.get(f"{API_URL}/api/find_vehicle/{entry_plate}")
                    if response.status_code == 200:
                        data = response.json()
                        if data.get("found"):
                            status.update(label="✅ Slot Assigned!", state="complete", expanded=False)
                            st.session_state.current_slot = data.get("slot_id")
                            nav = data.get("navigation", {})
                            
                            # Dynamic Result UI
                            st.markdown(f"""
                                <div style='text-align: center;'>
                                    <p>Assigned Slot</p>
                                    <div class='big-slot'>{data.get('slot_id')}</div>
                                    <div class='status-box status-success'>Zone: {nav.get('zone', 'General')}</div>
                                </div>
                            """, unsafe_allow_html=True)
                            
                            st.write("---")
                            st.subheader("🗺️ Navigation")
                            for idx, step in enumerate(nav.get('instructions', [])):
                                st.markdown(f"<div class='nav-step'><b>Step {idx+1}:</b> {step}</div>", unsafe_allow_html=True)
                        else:
                            status.update(label="❌ Not Found", state="error")
                            st.error("Vehicle not registered inside. Please verify entry at the gate.")
                    else:
                        status.update(label="⚠️ Connection Error", state="error")
                        st.error("Could not connect to parking system.")
                except Exception as e:
                    status.update(label="⚠️ Error", state="error")
                    st.error(f"System Error: {e}")
    st.markdown("</div>", unsafe_allow_html=True)

# --- TAB 2: VERIFY PARKING ---
with tab2:
    st.markdown("<div class='stCard'>", unsafe_allow_html=True)
    st.subheader("📍 Validating Location")
    st.info("Scan the QR code on the parking pillar to confirm you are in the right spot.")
    
    # Simulating Camera Scan with Text Input for Prototype
    qr_input = st.text_input("📱 Scan QR / Enter Slot ID", 
                            placeholder="e.g., Slot15",
                            key="input_qr")
    
    verify_btn = st.button("✅ Confirm Parking", use_container_width=True, type="primary")
    
    if verify_btn:
        if not st.session_state.plate or not qr_input:
            st.error("Ensure Plate is set and QR is scanned.")
        else:
            msg_placeholder = st.empty()
            msg_placeholder.markdown("<div class='status-box status-wait'>Verifying...</div>", unsafe_allow_html=True)
            time.sleep(1) # UX Delay
            
            try:
                payload = {
                    "slot_id": qr_input, 
                    "actual_reg_num": st.session_state.plate,
                    "action": "verify"
                }
                response = requests.post(f"{API_URL}/process_verification", json=payload)
                
                if response.status_code == 200:
                    res = response.json()
                    msg_placeholder.markdown(f"<div class='status-box status-success'>✅ {res.get('message')}</div>", unsafe_allow_html=True)
                    st.balloons()
                else:
                    err_msg = response.json().get('error', 'Mismatch')
                    msg_placeholder.markdown(f"<div class='status-box status-error'>❌ {err_msg}</div>", unsafe_allow_html=True)
            except Exception as e:
                 msg_placeholder.error(f"Error: {e}")
    st.markdown("</div>", unsafe_allow_html=True)

# --- TAB 3: FIND MY CAR ---
with tab3:
    st.markdown("<div class='stCard'>", unsafe_allow_html=True)
    st.subheader("🕵️ Where is my car?")
    
    find_plate = st.text_input("Confirmed Plate", value=st.session_state.plate, key="input_find")
    
    if st.button("🔍 Locate", use_container_width=True):
        try:
             response = requests.get(f"{API_URL}/api/find_vehicle/{find_plate}")
             if response.status_code == 200:
                 data = response.json()
                 if data.get("found"):
                    st.markdown(f"""
                        <div class='status-box status-success'>
                            <h3>FOUND AT {data.get('slot_id')}</h3>
                        </div>
                    """, unsafe_allow_html=True)
                    
                    with st.expander("🚶 Walking Directions", expanded=True):
                        nav = data.get("navigation", {})
                        for step in nav.get('instructions', []):
                            st.write(f"- {step}")
                 else:
                     st.warning("🚫 Vehicle currently not in the parking lot.")
             else:
                 st.error("API Error")
        except Exception as e:
            st.error(f"Connection Failed: {e}")
    st.markdown("</div>", unsafe_allow_html=True)

# --- TAB 4: EXIT & PAY ---
with tab4:
    st.markdown("<div class='stCard'>", unsafe_allow_html=True)
    st.subheader("💳 Checkout & Exit")
    
    exit_plate = st.text_input("License Plate for Billing", value=st.session_state.plate, key="input_exit")
    
    if st.button("💸 Calculate Fee & Exit", use_container_width=True, type="primary"):
        progress = st.progress(0)
        status_text = st.empty()
        
        status_text.text("Connecting to Gate...")
        progress.progress(20)
        time.sleep(0.5)
        
        try:
            response = requests.post(f"{API_URL}/exit", json={"reg_num": exit_plate})
            progress.progress(80)
            
            if response.status_code == 200:
                res = response.json()
                status_text.text("Exit successful.")
                progress.progress(100)
                time.sleep(0.5)
                
                st.markdown(f"""
                    <div class='status-box status-success'>
                        <h2>HAVE A SAFE TRIP</h2>
                        <p>Gate Opening...</p>
                    </div>
                """, unsafe_allow_html=True)
                
                st.write("---")
                st.caption(res.get('message', 'Thank you for using OptiSlot.'))
                
            else:
                progress.empty()
                status_text.empty()
                st.error(f"Exit Failed: {response.json().get('error')}")
        except Exception as e:
            st.error(f"Error: {e}")
            
    st.markdown("</div>", unsafe_allow_html=True)

# --- FOOTER ---
st.markdown("""
    <div style='text-align: center; color: #666; font-size: 0.8rem; margin-top: 20px;'>
        OptiSlot Intelligent Systems © 2026
    </div>
""", unsafe_allow_html=True)
