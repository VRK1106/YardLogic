import sqlite3
import datetime
import random
import cv2
import numpy as np
import re
import os
import threading
import time
import make_qrs # Import the QR generator module
from flask import Flask, render_template, request, jsonify, redirect, url_for, Response, make_response
from flask_cors import CORS
import external_sensors # Import external sensor module
from dotenv import load_dotenv
import socket

# Load environment variables
load_dotenv()

# --- Project Imports ---
from agent import ParkingAgent
from network_manager import NetworkManager
from navigation import NavigationSystem # New Feature

import sys

# 1. Helper to find resources in PyInstaller Bundle or Normal Env
def get_resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(os.path.dirname(__file__))
    return os.path.join(base_path, relative_path)

BASE_DIR = get_resource_path('')
TEMPLATE_DIR = get_resource_path('templates')
STATIC_DIR = get_resource_path('static')

# 3. Pass the absolute path when creating the Flask app
app = Flask(__name__, template_folder=TEMPLATE_DIR, static_folder=STATIC_DIR)
CORS(app, resources={r"/*": {"origins": "*"}}) # Explicitly allow all origins for static templates
DB_NAME = "parking.db"

# --- DEPLOYMENT CONTEXT ---
MODE = os.environ.get('MODE', 'production').lower()
PWA_URL_PROD = os.environ.get('PWA_URL_PROD', 'https://optislot.web.app')
TEMPLATES_URL_PROD = os.environ.get('TEMPLATES_URL_PROD', 'https://optislot-templates.web.app/dashboard')

def get_local_ip():
    """Dynamically detect the local IP address on the current network."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Doesn't even have to be reachable, just triggers OS to pick correct interface
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

if MODE == 'development':
    LOCAL_IP = get_local_ip()
    PWA_BASE_URL = f"http://{LOCAL_IP}:5173"
    print(f"Context: DEVELOPMENT MODE (Local IP: {LOCAL_IP})")
else:
    PWA_BASE_URL = PWA_URL_PROD
    print(f"Context: PRODUCTION MODE (URL: {PWA_URL_PROD})")

IS_RENDER = os.environ.get('RENDER', 'false').lower() == 'true'

# MongoDB Config (For Render Redirect)
MONGODB_URI = os.environ.get("MONGODB_URI")
CLUSTER_NAME = "SmartParkingParams"
COLLECTION_NAME = "system_config"

# --- AGENT INITIALIZATION ---
# Create skeleton agent instantly (models loaded in background)
parking_agent = None
camera_system = None

# Boot progress tracking
boot_progress = {
    "db":      {"status": "pending", "time": None},
    "network": {"status": "pending", "time": None},
    "yolo":    {"status": "pending", "time": None},
    "paddleocr": {"status": "pending", "time": None},
    "camera":  {"status": "pending", "time": None},
}
system_ready = False
local_ip_addr = None
public_url_addr = None

if not IS_RENDER:
    parking_agent = ParkingAgent()  # Skeleton only — no model loading
    print("Agent skeleton created (models pending).")
else:
    print("Skipping Agent Init (Cloud Mode)")

# --- ADMIN SECURITY ---
# Timestamp until which admin controls are unlocked
admin_unlocked_until = None
admin_pin = None  # Dynamic PIN for console verification

import secrets

# --- GATE DISPLAY STATE ---
gate_state = {
    'state': 'idle',     # idle, processing, allocated, timeout
    'plate': '',
    'slot': '',
    'level': '',
    'direction': '',
    'session_url': '',
    'expires_at': 0,
    'server_time': time.time()
}
gate_reset_timer = None

# --- SHARED CAMERA SINGLETON ---
class SharedCamera:
    def __init__(self):
        self.lock = threading.Lock()
        self.last_frame = None
        self.is_running = True
        self.cap = None
        
        # Try finding a working camera
        # Priority: 1. Environment Variable 'CAMERA_INDEX'
        #           2. Default search list [0, 1, 2, 3]
        
        env_index = os.environ.get('CAMERA_INDEX')
        search_list = [0, 1, 2, 3]
        
        if env_index is not None:
            try:
                forced_index = int(env_index)
                search_list = [forced_index] + [i for i in search_list if i != forced_index]
                print(f"Forcing Camera Search starting with Index {forced_index} (from .env)")
            except ValueError:
                print(f"Invalid CAMERA_INDEX '{env_index}' in .env. Using default search.")

        active_index = -1
        for idx in search_list:
            print(f"Checking Camera Index {idx}...")
            try:
                # Try DSHOW first for Windows compatibility, then default
                temp_cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
                if not temp_cap.isOpened():
                    temp_cap = cv2.VideoCapture(idx)
                
                if temp_cap.isOpened():
                    # Read a test frame
                    ret, frame = temp_cap.read()
                    if ret and frame is not None:
                        print(f"SUCCESS: Camera Index {idx} is active and working.")
                        self.cap = temp_cap
                        active_index = idx
                        break
                    else:
                        print(f"Index {idx} opens but returns no frame.")
                        temp_cap.release()
                else:
                     print(f"Index {idx} could not be opened.")
            except Exception as e:
                print(f"CRASH AVOIDED: Camera {idx} failed with error: {e}")

        if self.cap is None:
            print("CRITICAL ERROR: No working camera found (checked 0, 1, 2).")
            # Create a dummy capture logic or just leave it knowing it's None
        
        # Start background reading thread
        self.thread = threading.Thread(target=self._update_loop, daemon=True)
        self.thread.start()

    def _update_loop(self):
        while self.is_running:
            if self.cap and self.cap.isOpened():
                success, frame = self.cap.read()
                if success:
                    with self.lock:
                        self.last_frame = frame.copy()
                else:
                    # If read fails, wait a bit
                    time.sleep(0.1)
            else:
                # No camera, prevent busy loop
                time.sleep(1)
                
            time.sleep(0.01) # ~60 FPS cap

    def get_frame(self):
        with self.lock:
             if self.last_frame is not None:
                 return self.last_frame.copy()
        return None

    def __del__(self):
        self.is_running = False
        if self.cap and self.cap.isOpened():
            self.cap.release()


def generate_frames():
    global camera_system
    # Only init if not already done, and wrap in try-except
    if camera_system is None:
        try:
            camera_system = SharedCamera()
        except:
            camera_system = None
    
    while True:
        frame = None
        if camera_system:
             frame = camera_system.get_frame()
        
        if frame is None:
            # Send black frame if no camera
            blank = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(blank, "NO SIGNAL", (200, 240), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
            cv2.putText(blank, "Check Server Console", (180, 280), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)
            frame = blank
            
        try:
            ret, buffer = cv2.imencode('.jpg', frame)
            if not ret:
                continue
            frame_bytes = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        except Exception as e:
            print(f"Frame encoding error: {e}")
            pass
        
        # Don't loop too fast if there's no camera
        if frame is None:
            time.sleep(0.5)
            
        # --- AUTO-RELEASE LOGIC (Periodic Check) ---
        # Check every ~100 frames (~2-5 seconds) to avoid spamming DB
        if random.random() < 0.05:
            try:
                with sqlite3.connect(DB_NAME) as conn:
                    c = conn.cursor()
                    # Find slots blocked > 5 minutes ago
                    threshold = (datetime.datetime.now() - datetime.timedelta(minutes=5)).isoformat()
                    
                    c.execute("SELECT slot_id FROM slots WHERE status = 'blocked' AND entry_time < ?", (threshold,))
                    expired_slots = c.fetchall()
                    
                    if expired_slots:
                        for row in expired_slots:
                            slot = row[0]
                            print(f"[AUTO-RELEASE] Unblocking {slot} after timeout.")
                            c.execute("UPDATE slots SET status = 'free', reg_num = NULL, entry_time = NULL, is_verified = 0 WHERE slot_id = ?", (slot,))
                        conn.commit()
            except Exception as e:
                print(f"Auto-Release Error: {e}")

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        # Create slots table
        c.execute('''CREATE TABLE IF NOT EXISTS slots (
                        slot_id TEXT PRIMARY KEY,
                        size_type TEXT,
                        status TEXT DEFAULT 'free',
                        reg_num TEXT,
                        entry_time TEXT,
                        is_verified INTEGER DEFAULT 0
                    )''')
        # Create logs table for analytics
        c.execute('''CREATE TABLE IF NOT EXISTS logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        reg_num TEXT,
                        slot_id TEXT,
                        action TEXT,
                        timestamp TEXT
                    )''')

        
        # Initialize slots if empty or incomplete (Upgrade to 30 slots)
        c.execute("SELECT count(*) FROM slots")
        count = c.fetchone()[0]
        
        if count < 30:
            print(f"Updating DB from {count} to 30 Slots...")
            # Clear existing to ensure correct ordering/types
            c.execute("DELETE FROM slots")
            
            # Generate 30 Slots
            slots_data = []
            
            # Generate 30 Slots
            slots_data = []
            
            # 10 Small Slots (Slot1 - Slot10)
            slots_data.extend([(f'Slot{i}', 'small') for i in range(1, 11)])
            
            # 10 Medium Slots (Slot11 - Slot20)
            slots_data.extend([(f'Slot{i}', 'medium') for i in range(11, 21)])
            
            # 10 Large Slots (Slot21 - Slot30)
            slots_data.extend([(f'Slot{i}', 'large') for i in range(21, 31)])

            c.executemany("INSERT INTO slots (slot_id, size_type) VALUES (?, ?)", slots_data)
            print("Initialized 30 Slots (10 Small, 10 Medium, 10 Large).")
        
        # Enforce Ticket Distribution (10/10/10) on every startup to fix existing DBs
        # Small: 1-10
        for i in range(1, 11):
            c.execute("UPDATE slots SET size_type = 'small' WHERE slot_id = ?", (f"Slot{i}",))
        # Medium: 11-20
        for i in range(11, 21):
            c.execute("UPDATE slots SET size_type = 'medium' WHERE slot_id = ?", (f"Slot{i}",))
        # Large: 21-30
        for i in range(21, 31):
            c.execute("UPDATE slots SET size_type = 'large' WHERE slot_id = ?", (f"Slot{i}",))
        conn.commit()




# --- Routes Refactored to use Agent ---

@app.route('/')
def index():
    if MODE == 'production':
        print(f"Redirecting Local Root to Hosted Dashboard: {TEMPLATES_URL_PROD}")
        return redirect(TEMPLATES_URL_PROD)
    
    if not system_ready:
        return redirect(url_for('loading_page'))
    return redirect(url_for('slots_dashboard'))

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/slots')
def slots_dashboard():
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM slots ORDER BY slot_id")
        slots = c.fetchall()
        
        # Calculate stats
        total = len(slots)
        occupied = sum(1 for s in slots if s['status'] == 'occupied')
        utilization = round((occupied / total) * 100, 1) if total > 0 else 0
        
        # Check Lock Status
        is_locked = True
        if admin_unlocked_until and datetime.datetime.now() < admin_unlocked_until:
            is_locked = False
        
    return render_template('index_sensor.html', utilization=utilization, is_locked=is_locked)

@app.route('/dashboard')
def dashboard_view():
    return render_template('dashboard.html')

@app.route('/status')
def allotment_status():
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM slots ORDER BY slot_id")
        slots = c.fetchall()
    return render_template('status.html', slots=slots)

@app.route('/entry', methods=['POST'])
def entry():
    try:
        data = request.json
        
        # 1. PERCEIVE: Agent receives data
        percepts = {
            'reg_num': data.get('reg_num').replace(" ", "") if data.get('reg_num') else None,
            'vehicle_size': data.get('vehicle_size', 'medium')
        }
        
        # 2. DECIDE: Agent makes a decision
        actions = parking_agent.decide(percepts)
        
        # 3. ACT: System executes Agent's chosen action
        response = None
        for action in actions:
            result = parking_agent.act(action)
            
            if action['type'] == 'GRANT_ACCESS':
                plate = percepts['reg_num']
                slot = result['assigned_slot']
                ts = int(time.time() * 1000)
                
                # Build PWA launch URL dynamically
                pwa_launch_url = f"{PWA_BASE_URL}/?plate={plate}&slot={slot}&t={ts}"
                
                response = jsonify({
                    "message": "Entry successful",
                    "assigned_slot": slot,
                    "size": percepts['vehicle_size'],
                    "pwa_launch_url": pwa_launch_url,
                    "entry_timestamp": ts,
                })
            elif action['type'] == 'DENY_ACCESS':
                return jsonify({"error": result['message']}), 400
                
        if response:
            return response
        else:
            return jsonify({"error": "No action taken by Agent"}), 400

    except Exception as e:
        print(f"ENTRY ERROR: {e}")
        return jsonify({"error": f"Internal Server Error: {str(e)}"}), 500


@app.route('/api/entry_qr/<plate>/<slot>')
def api_entry_qr(plate, slot):
    """Generate a dynamic QR code for the entry gate display.
    Returns base64 PNG that the dashboard can show to the driver."""
    import qrcode
    import io
    import base64
    
    ts = int(time.time() * 1000)
    
    # Point to dynamic PWA URL (Hosted or Local)
    launch_url = f"{PWA_BASE_URL}/?plate={plate}&slot={slot}&t={ts}"
    
    # Generate QR in memory
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=8, border=3)
    qr.add_data(launch_url)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="#1a1a2e", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    b64 = base64.b64encode(buf.read()).decode('utf-8')
    
    return jsonify({
        "qr_base64": f"data:image/png;base64,{b64}",
        "launch_url": launch_url,
        "plate": plate,
        "slot": slot,
    })

@app.route('/exit', methods=['POST'])
def exit_vehicle():
    # Currently simplest implementation - direct DB update. 
    # Can be moved to Agent.act('RELEASE_SLOT') later.
    try:
        data = request.json
        reg_num = data.get('reg_num')
        if reg_num:
            reg_num = reg_num.replace(" ", "")
        if not reg_num: return jsonify({"error": "Registration number required"}), 400
            
        with sqlite3.connect(DB_NAME) as conn:
            c = conn.cursor()
            c.execute("SELECT slot_id, entry_time FROM slots WHERE reg_num = ?", (reg_num,))
            row = c.fetchone()
            if not row: return jsonify({"error": "Vehicle not found"}), 404
            slot_id, entry_time = row
            
            duration_sec = 0
            if entry_time:
                entry_dt = datetime.datetime.fromisoformat(entry_time)
                duration_sec = (datetime.datetime.now() - entry_dt).total_seconds()
            
            c.execute("UPDATE slots SET status = 'free', reg_num = NULL, entry_time = NULL, is_verified = 0 WHERE slot_id = ?", (slot_id,))
            conn.commit()
            
        return jsonify({"message": "Exit successful", "freed_slot": slot_id, "duration_seconds": int(duration_sec)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/gate-display')
def gate_display():
    return render_template('gate_display.html')

@app.route('/gate-state')
def get_gate_state():
    gate_state['server_time'] = time.time()
    return jsonify(gate_state)

@app.route('/update-gate-state', methods=['POST'])
def update_gate_state():
    global gate_state, gate_reset_timer
    data = request.json
    new_state = data.get('state')
    
    if new_state == 'processing':
        gate_state['state'] = 'processing'
        if 'plate' in data: gate_state['plate'] = data['plate']
            
    elif new_state == 'allocated':
        gate_state['state'] = 'allocated'
        gate_state['plate'] = data.get('plate', 'UNKNOWN')
        gate_state['slot'] = data.get('slot', 'N/A')
        gate_state['level'] = data.get('level', '1')
        gate_state['direction'] = data.get('direction', 'Follow Signs')
        
        host = request.host
        token = secrets.token_hex(3).upper()
        gate_state['session_url'] = f"http://{host}/navigate?session={token}&slot={gate_state['slot']}&level={gate_state['level']}"
        gate_state['expires_at'] = time.time() + 60.0
        
        if gate_reset_timer: gate_reset_timer.cancel()
            
        def reset_to_timeout():
            global gate_state, gate_reset_timer
            gate_state['state'] = 'timeout'
            def revert_idle():
                gate_state['state'] = 'idle'
                gate_state['plate'] = ''
                gate_state['session_url'] = ''
            gate_reset_timer = threading.Timer(5.0, revert_idle)
            gate_reset_timer.start()
            
        gate_reset_timer = threading.Timer(60.0, reset_to_timeout)
        gate_reset_timer.start()
        
    elif new_state == 'timeout':
        gate_state['state'] = 'timeout'
        if gate_reset_timer: gate_reset_timer.cancel()
        def revert_idle():
            gate_state['state'] = 'idle'
            gate_state['plate'] = ''
        gate_reset_timer = threading.Timer(3.0, revert_idle)
        gate_reset_timer.start()

    elif new_state == 'idle':
        gate_state['state'] = 'idle'
        gate_state['plate'] = ''
        if gate_reset_timer: gate_reset_timer.cancel()
            
    return jsonify({"status": "success"})

@app.route('/reset', methods=['POST'])
def reset_parking():
    try:
        # Directly create the action for the agent
        action = {'type': 'RESET_ALL'}
        
        # Agent acts on the command
        result = parking_agent.act(action)
        
        if result and result.get('status') == 'success':
             return jsonify(result)
        else:
             return jsonify({"error": "Reset failed", "details": result.get('message', '')}), 500

    except Exception as e:
        print(f"RESET ERROR: {e}")
        return jsonify({"error": f"Internal Server Error: {str(e)}"}), 500

@app.route('/anpr', methods=['POST'])
def anpr():
    print("ANPR Request Received (Agent Perception)", flush=True)
    try:
        global camera_system
        if camera_system is None:
             camera_system = SharedCamera()
             
        # Mocking Ultrasonic trigger check / Ensuring camera is ready
        if camera_system.get_frame() is None:
            return jsonify({"error": "Failed to capture image (Camera busy or off)"}), 500
            
        # 1. PERCEIVE: Send camera callback to Agent for 5-stage pipeline burst
        perception_result = parking_agent.perceive('camera_trigger', camera_system.get_frame)
        
        if not perception_result or 'error' in perception_result:
            return jsonify(perception_result or {"error": "Pipeline failed"}), 400
            
        return jsonify(perception_result)

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"ANPR CRASH: {e}")
        return jsonify({"error": f"Internal Error: {str(e)}"}), 500

@app.route('/scan/<slot_id>')
def scan_slot(slot_id):
    """
    Renders the Vehicle Verification Page.
    The actual logic is now handled in /process_verification via the UI.
    """
    try:
        with sqlite3.connect(DB_NAME) as conn:
            c = conn.cursor()
            
            # Check if status exists
            c.execute("SELECT status, reg_num FROM slots WHERE slot_id = ?", (slot_id,))
            row = c.fetchone()
            
            if not row:
                return f"<h1>Error: Slot {slot_id} not found</h1>", 404
            
            status, reg_num = row
            status_color = "#00ff9d" if status == 'free' else "#ff2a6d" if status == 'occupied' else "#00f3ff"
            
            return render_template('verify_vehicle.html', 
                                   slot_id=slot_id, 
                                   status=status, 
                                   reg_num=reg_num,
                                   status_color=status_color)
            
    except Exception as e:
        return f"<h1>Error: {str(e)}</h1>", 500

@app.route('/process_verification', methods=['POST'])
def process_verification():
    try:
        data = request.json
        slot_id = data.get('slot_id')
        actual_reg_num = data.get('actual_reg_num', '').replace(" ", "").upper()
        action = data.get('action') # 'verify' or 'report_misuse'
        
        if not slot_id or not actual_reg_num:
             return jsonify({"error": "Missing Data"}), 400

        with sqlite3.connect(DB_NAME) as conn:
            c = conn.cursor()
            c.execute("SELECT status, reg_num FROM slots WHERE slot_id = ?", (slot_id,))
            row = c.fetchone()
            if not row: return jsonify({"error": "Slot not found"}), 404
            
            db_status, expected_reg_num = row
            
            # --- ACTION: REPORT MISUSE ---
            if action == 'report_misuse':
                # Force status to misuse
                c.execute("UPDATE slots SET status = 'misuse', reg_num = ?, is_verified = 0 WHERE slot_id = ?", (actual_reg_num, slot_id))
                conn.commit()
                return jsonify({"message": "Misuse Reported. Authorities Alerted.", "is_misuse": True})

            # --- CHECK FOR EXISTING REGISTRATION (Cross-Slot Misuse) ---
            # If this car is already assigned to ANOTHER slot, it cannot verify here.
            c.execute("SELECT slot_id, status FROM slots WHERE reg_num = ?", (actual_reg_num,))
            existing = c.fetchone()
            
            if existing: # Vehicle is already in the system
                existing_slot, existing_status = existing
                
                # Exception: If it's the SAME slot, we proceed to normal verification logic below.
                if existing_slot != slot_id:
                     # MISUSE DETECTED: Car assigned to Slot A is trying to park in Slot B
                     print(f"[MISUSE] Vehicle {actual_reg_num} (assigned to {existing_slot}) trying to park in {slot_id}")
                     
                     # Flag the CURRENT slot as 'misuse' so the ALERT appears
                     c.execute("UPDATE slots SET status = 'misuse', reg_num = ?, is_verified = 0 WHERE slot_id = ?", (actual_reg_num, slot_id))
                     conn.commit()
                     return jsonify({"error": f"MISUSE DETECTED! Vehicle is assigned to {existing_slot}. Alert Sent.", "is_misuse": True}), 400

            # --- ACTION: VERIFY ---
            
            # Logic 1: Reserved Slot
            if db_status == 'reserved':
                if expected_reg_num == actual_reg_num:
                    # SUCCESS: Match
                    c.execute("UPDATE slots SET status = 'occupied', is_verified = 1 WHERE slot_id = ?", (slot_id,))
                    conn.commit()
                    return jsonify({"message": "Verification Successful. Welcome!"})
                else:
                    # FAILURE: Mismatch
                    return jsonify({"error": f"Mismatch! Expected {expected_reg_num}, Found {actual_reg_num}. Please Report Misuse."}), 400

            # Logic 2: Free Slot (Unscheduled Entry)
            elif db_status == 'free':
                # ALLOWED only if not found elsewhere (checked above)
                timestamp = datetime.datetime.now().isoformat()
                c.execute("UPDATE slots SET status = 'occupied', reg_num = ?, entry_time = ?, is_verified = 1 WHERE slot_id = ?", 
                          (actual_reg_num, timestamp, slot_id))
                conn.commit()
                return jsonify({"message": "Ad-Hoc Parking Confirmed."})

            # Logic 3: Occupied (Re-verify?)
            elif db_status == 'occupied':
                if expected_reg_num == actual_reg_num:
                     return jsonify({"message": "Already Verified."})
                else:
                     return jsonify({"error": "Slot is Occupied by another car!"}), 400
            
            # Logic 4: Misuse State
            elif db_status == 'misuse':
                 return jsonify({"error": "Slot is currently flagged for MISUSE."}), 400

            return jsonify({"error": "Unknown State"}), 500

    except Exception as e:
        print(f"VERIFY ERROR: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/resolve_misuse', methods=['POST'])
def resolve_misuse():
    try:
        data = request.json
        slot_id = data.get('slot_id') # The WRONG slot being used
        reg_num = data.get('reg_num')
        decision = data.get('decision') # 'accept' or 'reject'
        
        with sqlite3.connect(DB_NAME) as conn:
            c = conn.cursor()
            
            # Find the ORIGINALLY assigned slot
            c.execute("SELECT slot_id FROM slots WHERE reg_num = ?", (reg_num,))
            row = c.fetchone()
            # If not found, that's okay, maybe cleared already
            assigned_slot = row[0] if row else None
            
            if decision == 'accept':
                # 1. Clear the Old Slot(s) - Wipe ALL instances of this car
                c.execute("UPDATE slots SET status = 'free', reg_num = NULL, entry_time = NULL, is_verified = 0 WHERE reg_num = ?", (reg_num,))
                
                # 2. Occupy the New Slot
                c.execute("UPDATE slots SET status = 'occupied', reg_num = ?, entry_time = ?, is_verified = 1 WHERE slot_id = ?", 
                          (reg_num, datetime.datetime.now().isoformat(), slot_id))
                msg = f"Re-assigned to {slot_id}"
                
            elif decision == 'resolved':
                # Vehicle moved away. Slot is free.
                c.execute("UPDATE slots SET status = 'free', reg_num = NULL, entry_time = NULL, is_verified = 0 WHERE slot_id = ?", (slot_id,))
                msg = "Incident Resolved. Slot Freed."

            else: # reject
                # Mark current slot as BLOCKED (prev. REJECTED) so mobile can detect and show message
                # Add timestamp for auto-release logic (5 mins)
                block_time = datetime.datetime.now().isoformat()
                # BLOCKED status means: User tried to park here, was rejected, now slot is unusable for a while.
                c.execute("UPDATE slots SET status = 'blocked', reg_num = ?, entry_time = ?, is_verified = 0 WHERE slot_id = ?", (reg_num, block_time, slot_id))
                msg = "Access Rejected. Slot Blocked."
                
            conn.commit()
            return jsonify({"success": True, "message": msg})
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/slot_control', methods=['POST'])
def slot_control():
    """
    MANUAL OVERRIDE API for Dashboard
    Action: block, release, occupy_manual
    SECURED: Requires Master Key Unlock
    """
    global admin_unlocked_until
    
    # Check Security
    if not admin_unlocked_until or datetime.datetime.now() > admin_unlocked_until:
         return jsonify({"error": "Admin Access Locked. Scan Master Key."}), 403

    try:
        data = request.json
        slot_id = data.get('slot_id')
        action = data.get('action')
        
        if not slot_id or not action: return jsonify({"error": "Missing Params"}), 400
        
        with sqlite3.connect(DB_NAME) as conn:
            c = conn.cursor()
            
            if action == 'block':
                 # Manual blocking
                 c.execute("UPDATE slots SET status = 'blocked', reg_num = 'ADMIN_BLOCK', entry_time = ?, is_verified = 0 WHERE slot_id = ?", (datetime.datetime.now().isoformat(), slot_id))
                 msg = f"{slot_id} Manually Blocked."
            elif action == 'release':
                 # Force release
                 c.execute("UPDATE slots SET status = 'free', reg_num = NULL, entry_time = NULL, is_verified = 0 WHERE slot_id = ?", (slot_id,))
                 msg = f"{slot_id} Released."
            elif action == 'occupy_manual':
                 # Force Occupy
                 dummy_reg = "MANUAL"
                 c.execute("UPDATE slots SET status = 'occupied', reg_num = ?, entry_time = ?, is_verified = 1 WHERE slot_id = ?", (dummy_reg, datetime.datetime.now().isoformat(), slot_id))
                 msg = f"{slot_id} Manually Occupied."
            else:
                 return jsonify({"error": "Invalid Action"}), 400
            
            conn.commit()
            return jsonify({"success": True, "message": msg})
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/admin/request_pin', methods=['POST'])
def request_pin():
    """
    Generates a secure 6-digit PIN and shows it in a Native Server Popup.
    """
    global admin_pin
    try:
        admin_pin = f"{random.randint(100000, 999999)}"
        print(f"[SECURITY] Your Admin PIN is: {admin_pin}")
        
        # Native Popup for EXE/Kiosk Mode (Visible even without console)
        # 0x40000 = MB_TOPMOST (Force on top of all windows)
        # 0x40 = MB_ICONINFORMATION
        try:
            import ctypes
            # Using threading to prevent blocking the Flask response? 
            # Actually, blocking is fine here as it forces admin to acknowledge the PIN on the server
            # But we want the response to return to UI so the modal opens.
            # So we launch the popup in a thread.
            
            def show_popup():
                ctypes.windll.user32.MessageBoxW(0, f"Your Admin PIN is: {admin_pin}", "Admin Access Verification", 0x40 | 0x40000)

            threading.Thread(target=show_popup, daemon=True).start()
            
        except Exception as e:
            print(f"Could not show popup: {e}")
            
        return jsonify({"success": True, "message": "PIN sent to server console."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/admin/verify_pin', methods=['POST'])
def verify_pin():
    """
    Validates the PIN entered by the user.
    """
    global admin_unlocked_until, admin_pin
    
    try:
        data = request.json
        entered_pin = data.get('pin')
        
        if not admin_pin:
             return jsonify({"success": False, "error": "No PIN requested. Request PIN first."})
             
        if entered_pin == admin_pin:
            # Grant access for 2 minutes
            admin_unlocked_until = datetime.datetime.now() + datetime.timedelta(minutes=2)
            # Invalidate PIN after use
            admin_pin = None 
            return jsonify({"success": True, "message": "Dashboard Unlocked for 2 Minutes"})
        else:
             return jsonify({"success": False, "error": "Invalid PIN"})
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500





@app.route('/get_sensors', methods=['GET'])
def get_sensors():
    # Polling the Agent's state or Database
    # Here we can return database-driven alerts
    alerts = []
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("SELECT slot_id, reg_num FROM slots WHERE status = 'misuse'")
        for r in c.fetchall():
             alerts.append({"slot_id": r[0], "reg_num": r[1]})
             
    return jsonify({"alerts": alerts})

@app.route('/api/slots', methods=['GET'])
def api_slots():
    """
    Returns full slot list for the frontend dashboard.
    """
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM slots")
        rows = c.fetchall()
        
        # Convert to list of dicts
        slots = [dict(row) for row in rows]

        # Sort properly by number (Slot1, Slot2, ... Slot10)
        def get_slot_number(s):
            # Extract digits from string "Slot10" -> 10
            digits = ''.join(filter(str.isdigit, s['slot_id']))
            return int(digits) if digits else 0

        slots.sort(key=get_slot_number)
        
    return jsonify(slots)

@app.route('/api/slot_status/<slot_id>', methods=['GET'])
def get_slot_status(slot_id):
    """
    Lightweight endpoint for mobile polling during verification.
    """
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("SELECT status, reg_num FROM slots WHERE slot_id = ?", (slot_id,))
        row = c.fetchone()
        if row:
            return jsonify({"status": row[0], "reg_num": row[1]})
        return jsonify({"error": "Slot not found"}), 404

@app.route('/qr/<slot_id>')
def qr_redirect(slot_id):
    """
    STATIC GATEWAY ENTRY POINT.
    1. Scan QR (at render url).
    2. Hit this route.
    3. Look up current 'tunnel_url' from MongoDB.
    4. Redirect user to {tunnel_url}/scan/{slot_id}.
    """
    # If we are local and have the tunnel, we *could* redirect to localhost or the tunnel.
    # But usually this runs on Render.
    
    # 1. Try to get URL from MongoDB
    redirect_base = None
    if MONGODB_URI:
        try:
            from pymongo import MongoClient
            client = MongoClient(MONGODB_URI)
            db = client[CLUSTER_NAME]
            collection = db[COLLECTION_NAME]
            doc = collection.find_one({"config_id": "main_tunnel"})
            if doc and "tunnel_url" in doc:
                redirect_base = doc["tunnel_url"]
        except Exception as e:
            print(f"MongoDB Lookup Failed: {e}")
            
    # 2. Fallback if DB fails or not set (e.g. testing locally)
    if not redirect_base:
        # If we are local, we might know the tunnel?
        # For now, show error or fallback
        return "<h1>Error: Could not determine parking system address.</h1><p>System might be offline or MongoDB not configured.</p>", 503

    # 3. Perform Redirect
    if slot_id.lower() == 'app':
        vite_ip = '172.16.0.2'
        full_url = f"http://{vite_ip}:5173/"
        print(f"Redirecting to Mobile App: {full_url}")
    else:
        full_url = f"{redirect_base}/scan/{slot_id}"
        print(f"Redirecting QR scan for {slot_id} to: {full_url}")
    
    return redirect(full_url)


@app.route('/mobile')
def mobile_app():
    """Renders the Mobile App PWA"""
    response = make_response(render_template('mobile_app.html'))
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/api/navigate/<slot_id>', methods=['GET'])
def api_navigate(slot_id):
    """
    Smart Feature: Get Navigation Directions
    """
    try:
        nav_sys = NavigationSystem()
        result = nav_sys.get_directions(slot_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/find_vehicle/<reg_num>', methods=['GET'])
def api_find_vehicle(reg_num):
    """
    Smart Feature: Locator
    """
    reg_num = reg_num.replace(" ", "").upper()
    try:
        with sqlite3.connect(DB_NAME) as conn:
            c = conn.cursor()
            c.execute("SELECT slot_id, entry_time, is_verified FROM slots WHERE reg_num = ?", (reg_num,))
            row = c.fetchone()
            
            if row:
                slot_id = row[0]
                nav_sys = NavigationSystem()
                nav_data = nav_sys.get_directions(slot_id)
                return jsonify({
                    "found": True,
                    "slot_id": slot_id,
                    "entry_time": row[1],
                    "is_verified": bool(row[2]),
                    "navigation": nav_data
                })
            else:
                return jsonify({"found": False, "message": "Vehicle not found"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- BOOT STATUS API ---
@app.route('/api/boot_status')
def api_boot_status():
    """Polled by loading page to show live progress."""
    # Merge agent model status into boot_progress
    steps = dict(boot_progress)
    if parking_agent:
        steps["yolo"] = parking_agent.boot_status.get("yolo", steps["yolo"])
        steps["paddleocr"] = parking_agent.boot_status.get("paddleocr", steps["paddleocr"])
    
    # Check Lock Status
    is_locked = True
    if admin_unlocked_until and datetime.datetime.now() < admin_unlocked_until:
        is_locked = False

    return jsonify({
        "ready": system_ready,
        "is_locked": is_locked,
        "steps": steps,
    })

# --- LOADING PAGE ROUTE ---
@app.route('/loading')
def loading_page():
    return render_template('loading.html')

# --- STARTUP ORCHESTRATION ---
def _boot_network():
    """Thread: Network auto-configuration + tunnel."""
    global local_ip_addr, public_url_addr
    boot_progress["network"]["status"] = "loading"
    start = time.time()
    try:
        local_ip_addr, public_url_addr = NetworkManager.initialize()
        elapsed = round(time.time() - start, 1)
        boot_progress["network"] = {"status": "done", "time": elapsed}
        print(f"Network ready in {elapsed}s — Local: {local_ip_addr}, Public: {public_url_addr}")
    except Exception as e:
        boot_progress["network"] = {"status": "error", "time": round(time.time() - start, 1)}
        print(f"Network init error: {e}")

def _boot_models():
    """Thread: Load YOLO + PaddleOCR in parallel (inside agent)."""
    if parking_agent:
        parking_agent.load_models()

def _boot_camera():
    """Thread: Initialize shared camera."""
    global camera_system
    boot_progress["camera"]["status"] = "loading"
    start = time.time()
    try:
        camera_system = SharedCamera()
        elapsed = round(time.time() - start, 1)
        boot_progress["camera"] = {"status": "done", "time": elapsed}
        print(f"Camera ready in {elapsed}s")
    except Exception as e:
        boot_progress["camera"] = {"status": "error", "time": round(time.time() - start, 1)}
        print(f"Camera init error: {e}. Server continues without camera.")

def _background_boot():
    """Orchestrate all background loading, then mark system ready."""
    global system_ready

    # Phase 1: DB init (fast, synchronous)
    boot_progress["db"]["status"] = "loading"
    start = time.time()
    init_db()
    boot_progress["db"] = {"status": "done", "time": round(time.time() - start, 1)}

    # Phase 2: Parallel threads for Network, AI Models, Camera
    threads = [
        threading.Thread(target=_boot_network, daemon=True, name="boot-network"),
        threading.Thread(target=_boot_models, daemon=True, name="boot-models"),
        threading.Thread(target=_boot_camera, daemon=True, name="boot-camera"),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Phase 3: QR Code generation (needs network to be done)
    print("Checking QR Codes...")
    try:
        make_qrs.generate_qrs(force=False)
    except Exception as e:
        print(f"QR gen error: {e}")

    # Print access URLs
    print("\n" + "="*60)
    print("  SMART PARKING SYSTEM - READY")
    print("="*60)
    if local_ip_addr:
        print(f"  Local Network:   http://{local_ip_addr}:5000")
        print(f"  Local Mobile:    http://{local_ip_addr}:5000/mobile")
    if public_url_addr:
        print(f"  Public Access:   {public_url_addr}/mobile")
    print("="*60 + "\n")

    system_ready = True
    print(">>> ALL SYSTEMS GO <<<")


if __name__ == '__main__':
    # Start background boot thread
    boot_thread = threading.Thread(target=_background_boot, daemon=True, name="boot-main")
    boot_thread.start()

    # Start Flask immediately — loading page will engage user
    print("\n" + "="*60)
    print("  OPTISLOT EDGE NODE")
    print("  Flask starting at http://0.0.0.0:5000")
    print("  Loading page active — models loading in background")
    print("="*60 + "\n")

    try:
        app.run(host='0.0.0.0', port=5000, debug=False)
    except KeyboardInterrupt:
        print("\n[ORCHESTRATOR] Stopping Services...")
        print("[ORCHESTRATOR] Shutdown Complete.")