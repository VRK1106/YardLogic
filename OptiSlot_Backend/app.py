"""
OptiSlot_Backend — Digital Twin Gate Server
============================================
Runs on port 5050 alongside the main parking_proto_sensor.py (port 5000).
Shares the same parking.db for real-time state sync.

Endpoints:
  GET  /health                        — Server + model status
  POST /api/gate/scan                 — ANPR: camera → YOLO → EasyOCR → assign slot
  POST /api/gate/manual               — Demo fallback: inject plate manually
  GET  /api/digital-twin/slots        — Full slot state (UE5 polls this every ~1s)
  POST /api/digital-twin/broadcast    — Immediately push full state to UE5 via OSC
  GET  /api/stats                     — Aggregate stats for HUD overlay
  POST /exit                          — Free a slot by plate or slot_id
  POST /reset                         — Reset all slots to free (demo restart)

OSC Push (UE5 OSCServer on port 8000):
  Address: /parking/slot_update  — Args: slot_id, status, reg_num, size_type
  Address: /parking/stats        — Args: total, free, occupied, utilization_pct
  Address: /parking/reset        — Args: "RESET" (signals full clear to UE5)
"""
from pythonosc import udp_client
import os
import re
import time
import sqlite3
import datetime
import threading

import cv2
import numpy as np
from flask import Flask, request, jsonify
from flask_cors import CORS

# OSC support removed

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

# Points to the SAME database as the main parking server
# Adjust this absolute path if you move the backend folder
_THIS_DIR = os.path.abspath(os.path.dirname(__file__))
DB_NAME   = os.path.join(_THIS_DIR, "..", "parking.db")

# Path to the YOLO model used by the main project
YOLO_MODEL_PATH = os.path.join(
    _THIS_DIR, "..", "AI_Model", "best.pt"
)

app = Flask(__name__)
CORS(app)  # Allow UE5 / Postman / browser requests from any origin

# ─────────────────────────────────────────────────────────────────────────────
# Lazy Model Loader (mirrors agent.py approach)
# ─────────────────────────────────────────────────────────────────────────────

class ANPREngine:
    """Single-instance ANPR engine — loaded once at startup in a background thread."""

    def __init__(self):
        self.yolo_model  = None
        self.ocr_reader  = None
        self.is_ready    = False
        self.status = {
            "yolo":    {"status": "pending", "time": None},
            "easyocr": {"status": "pending", "time": None},
        }
        self._lock = threading.Lock()

    def load(self):
        """Call once — loads YOLO + EasyOCR in parallel threads."""
        t1 = threading.Thread(target=self._load_yolo,    daemon=True)
        t2 = threading.Thread(target=self._load_easyocr, daemon=True)
        t1.start(); t2.start()
        t1.join();  t2.join()
        self.is_ready = True
        print("[ANPR] All models loaded and ready.")

    def _load_yolo(self):
        from ultralytics import YOLO
        start = time.time()
        self.status["yolo"]["status"] = "loading"
        try:
            if os.path.exists(YOLO_MODEL_PATH):
                self.yolo_model = YOLO(YOLO_MODEL_PATH)
                elapsed = round(time.time() - start, 1)
                self.status["yolo"] = {"status": "done", "time": elapsed}
                print(f"[ANPR] YOLO loaded in {elapsed}s")
            else:
                print(f"[ANPR] WARNING: YOLO model not found at {YOLO_MODEL_PATH} — scan will use OCR fallback")
                self.status["yolo"] = {"status": "skipped", "time": 0}
        except Exception as e:
            print(f"[ANPR] YOLO load error: {e}")
            self.status["yolo"] = {"status": "error", "time": round(time.time() - start, 1)}

    def _load_easyocr(self):
        import easyocr
        start = time.time()
        self.status["easyocr"]["status"] = "loading"
        try:
            self.ocr_reader = easyocr.Reader(['en'], gpu=False)
            elapsed = round(time.time() - start, 1)
            self.status["easyocr"] = {"status": "done", "time": elapsed}
            print(f"[ANPR] EasyOCR loaded in {elapsed}s")
        except Exception as e:
            print(f"[ANPR] EasyOCR load error: {e}")
            self.status["easyocr"] = {"status": "error", "time": round(time.time() - start, 1)}

    # ── OCR correction helpers (same logic as agent.py) ─────────────────────

    @staticmethod
    def _correct_ocr(text: str) -> str:
        """
        Enforce Indian plate format: TTNNTTNNNN
        T=letter, N=digit. Misread chars are remapped.
        """
        if text.startswith("IND") and len(text) > 10:
            text = text[3:]
        chars = list(text)
        letter_map = {'0':'O','1':'I','2':'Z','3':'E','4':'A',
                      '5':'S','6':'G','7':'T','8':'B','9':'P'}
        number_map = {'O':'0','Q':'0','D':'0','I':'1','L':'1',
                      'Z':'2','E':'3','A':'4','S':'5','G':'6',
                      'T':'1','B':'8','P':'9','R':'2','C':'0'}
        pattern = "TTNNTTNNNN"
        if len(chars) == 10:
            for i, expected in enumerate(pattern):
                c = chars[i]
                if expected == 'T' and c.isdigit():
                    chars[i] = letter_map.get(c, 'X')
                elif expected == 'N' and c.isalpha():
                    chars[i] = number_map.get(c, '0')
        return "".join(chars)

    def read_plate_from_frame(self, frame: np.ndarray) -> dict:
        """
        Run YOLO plate detection then EasyOCR.
        Returns {"plate": str, "method": str} or {"error": str}.
        """
        # ── Step 1: Try QR code first (fast path used by main agent too) ──
        try:
            detector = cv2.QRCodeDetector()
            data, _, _ = detector.detectAndDecode(frame)
            if data:
                return {"plate": data.strip().upper(), "method": "qr"}
        except Exception:
            pass

        # ── Step 2: YOLO + EasyOCR ──────────────────────────────────────
        if self.yolo_model and self.ocr_reader:
            try:
                results = self.yolo_model(frame, verbose=False)
                for result in results:
                    for box in result.boxes:
                        x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].cpu().numpy()]
                        crop     = frame[y1:y2, x1:x2]
                        gray     = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
                        ocr_out  = self.ocr_reader.readtext(
                            gray,
                            allowlist='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
                        )
                        ocr_out.sort(key=lambda x: x[2], reverse=True)
                        for _, text, prob in ocr_out:
                            clean = ''.join(c for c in text if c.isalnum()).upper()
                            if len(clean) >= 6:
                                return {
                                    "plate":  self._correct_ocr(clean),
                                    "method": "yolo+ocr",
                                    "confidence": round(float(prob), 3)
                                }
            except Exception as e:
                print(f"[ANPR] YOLO/OCR error: {e}")

        # ── Step 3: Full-image OCR fallback ─────────────────────────────
        if self.ocr_reader:
            try:
                gray    = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                bfilter = cv2.bilateralFilter(gray, 11, 17, 17)
                thresh  = cv2.adaptiveThreshold(
                    bfilter, 255,
                    cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                    cv2.THRESH_BINARY, 11, 2
                )
                ocr_out = self.ocr_reader.readtext(
                    thresh,
                    allowlist='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
                )
                ocr_out.sort(key=lambda x: x[2], reverse=True)
                for _, text, prob in ocr_out:
                    clean = ''.join(c for c in text if c.isalnum()).upper()
                    if len(clean) >= 6:
                        return {
                            "plate":  self._correct_ocr(clean),
                            "method": "ocr_fallback",
                            "confidence": round(float(prob), 3)
                        }
            except Exception as e:
                print(f"[ANPR] OCR fallback error: {e}")

        return {"error": "No plate detected"}


# Global singleton
anpr_engine = ANPREngine()


# ─────────────────────────────────────────────────────────────────────────────
# Camera Singleton (mirrors SharedCamera from main server)
# ─────────────────────────────────────────────────────────────────────────────

class SharedCamera:
    def __init__(self):
        self._lock      = threading.Lock()
        self._last      = None
        self._running   = True
        self.cap        = None

        for idx in [0, 1, 2]:
            try:
                cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
                if not cap.isOpened():
                    cap = cv2.VideoCapture(idx)
                if cap.isOpened():
                    ok, frame = cap.read()
                    if ok and frame is not None:
                        self.cap = cap
                        print(f"[Camera] Using index {idx}")
                        break
                    cap.release()
            except Exception:
                pass

        if self.cap is None:
            print("[Camera] No camera found — /api/gate/scan will fail. Use /api/gate/manual instead.")

        t = threading.Thread(target=self._loop, daemon=True)
        t.start()

    def _loop(self):
        fail_count     = 0
        MAX_FAILS      = 5      # print warning after this many consecutive failures
        BACKOFF_SECS   = 5.0   # sleep this long once in backoff mode
        NORMAL_SECS    = 0.033 # ~30 fps when healthy

        while self._running:
            if self.cap and self.cap.isOpened():
                ok, frame = self.cap.read()
                if ok and frame is not None:
                    with self._lock:
                        self._last = frame.copy()
                    fail_count = 0          # reset on success
                    time.sleep(NORMAL_SECS)
                else:
                    fail_count += 1
                    if fail_count == MAX_FAILS:
                        print(
                            "[Camera] Repeated grab failures — camera may be in use by another process. "
                            "Backing off. Use /api/gate/manual for demo."
                        )
                    # Exponential backoff capped at BACKOFF_SECS
                    sleep_for = min(NORMAL_SECS * (2 ** fail_count), BACKOFF_SECS)
                    time.sleep(sleep_for)
            else:
                # No cap object at all — sleep and don't busy-wait
                time.sleep(BACKOFF_SECS)

    def get_frame(self):
        with self._lock:
            return self._last.copy() if self._last is not None else None


camera_singleton: SharedCamera | None = None
camera_lock = threading.Lock()

def get_camera() -> SharedCamera:
    global camera_singleton
    with camera_lock:
        if camera_singleton is None:
            camera_singleton = SharedCamera()
    return camera_singleton


# ─────────────────────────────────────────────────────────────────────────────
# Database Helpers
# ─────────────────────────────────────────────────────────────────────────────

def init_db():
    """Ensure parking.db exists with 30 slots. Safe to call every startup."""
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS slots (
                        slot_id    TEXT PRIMARY KEY,
                        size_type  TEXT,
                        status     TEXT DEFAULT 'free',
                        reg_num    TEXT,
                        entry_time TEXT,
                        is_verified INTEGER DEFAULT 0
                    )''')
        c.execute('''CREATE TABLE IF NOT EXISTS logs (
                        id         INTEGER PRIMARY KEY AUTOINCREMENT,
                        reg_num    TEXT,
                        slot_id    TEXT,
                        action     TEXT,
                        timestamp  TEXT
                    )''')

        c.execute("SELECT count(*) FROM slots")
        if c.fetchone()[0] < 30:
            c.execute("DELETE FROM slots")
            rows  = [(f"Slot{i}", "small")  for i in range(1, 11)]
            rows += [(f"Slot{i}", "medium") for i in range(11, 21)]
            rows += [(f"Slot{i}", "large")  for i in range(21, 31)]
            c.executemany("INSERT INTO slots (slot_id, size_type) VALUES (?, ?)", rows)
            print("[DB] Initialized 30 slots (10S / 10M / 10L)")

        conn.commit()


def find_best_slot(size: str) -> str | None:
    """Best-fit slot allocation — same logic as agent.py."""
    order = {
        "small":  ["small", "medium", "large"],
        "medium": ["medium", "large"],
        "large":  ["large"],
    }.get(size.lower(), ["medium", "large"])

    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        for sz in order:
            c.execute(
                "SELECT slot_id FROM slots WHERE size_type=? AND status='free' ORDER BY slot_id ASC LIMIT 1",
                (sz,)
            )
            row = c.fetchone()
            if row:
                return row[0]
    return None


def assign_slot(plate: str, slot_id: str, size: str = ""):
    now = datetime.datetime.now().isoformat()
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        # Clear any previous entry for this vehicle
        c.execute(
            "UPDATE slots SET status='free', reg_num=NULL, entry_time=NULL, is_verified=0 WHERE reg_num=?",
            (plate,)
        )
        c.execute(
            "UPDATE slots SET status='reserved', reg_num=?, entry_time=?, is_verified=0 WHERE slot_id=?",
            (plate, now, slot_id)
        )
        c.execute(
            "INSERT INTO logs (reg_num, slot_id, action, timestamp) VALUES (?,?,?,?)",
            (plate, slot_id, "ENTRY", now)
        )
        conn.commit()

    # Done


def get_all_slots() -> list[dict]:
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM slots")
        rows = c.fetchall()

    slots = [dict(r) for r in rows]
    slots.sort(key=lambda s: int(''.join(filter(str.isdigit, s["slot_id"])) or 0))
    return slots


# ─────────────────────────────────────────────────────────────────────────────
# Flask Routes
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/health', methods=['GET'])
def health():
    """Quick liveness + model status check."""
    return jsonify({
        "status":  "ok",
        "port":    5050,
        "models":  anpr_engine.status,
        "ready":   anpr_engine.is_ready,
        "db":      os.path.abspath(DB_NAME),
    })


@app.route('/api/gate/scan', methods=['POST'])
def gate_scan():
    """
    ANPR Gate Endpoint — captures a camera frame, detects plate, assigns slot.

    No request body needed (reads from shared camera).
    Optional JSON body: {"size": "small"|"medium"|"large"}
    """
    if not anpr_engine.is_ready:
        return jsonify({"error": "ANPR models still loading. Try /api/gate/manual for now."}), 503

    cam   = get_camera()
    frame = cam.get_frame()
    if frame is None:
        return jsonify({
            "error": "No camera frame available. Use /api/gate/manual to inject a plate."
        }), 503

    # ── Detect plate ──────────────────────────────────────────────────────
    result = anpr_engine.read_plate_from_frame(frame)
    if "error" in result:
        return jsonify(result), 422

    plate = result["plate"].replace(" ", "").upper()
    size  = (request.json or {}).get("size", "medium").lower()

    # ── Check if already parked ──────────────────────────────────────────
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("SELECT slot_id, status FROM slots WHERE reg_num=?", (plate,))
        existing = c.fetchone()
    if existing:
        return jsonify({
            "error":  f"Vehicle {plate} already parked in {existing[0]} (status: {existing[1]})"
        }), 409

    # ── Assign slot ───────────────────────────────────────────────────────
    slot = find_best_slot(size)
    if not slot:
        return jsonify({"error": f"Parking full — no {size} slot available"}), 409

    assign_slot(plate, slot, size)
    print(f"[GATE] {plate} → {slot} via camera ANPR ({result['method']})")

    return jsonify({
        "plate":         plate,
        "assigned_slot": slot,
        "method":        result["method"],
        "confidence":    result.get("confidence"),
        "size":          size,
    })


@app.route('/api/gate/manual', methods=['POST'])
def gate_manual():
    """
    ┌──────────────────────────────────────────────────────┐
    │  HACKATHON DEMO BACKUP — use this if camera fails    │
    │                                                      │
    │  POST /api/gate/manual                               │
    │  Body: {"plate": "TN36AM4045", "size": "medium"}     │
    └──────────────────────────────────────────────────────┘
    """
    data  = request.json or {}
    plate = data.get("plate", "").replace(" ", "").upper()
    size  = data.get("size", "medium").lower()

    if not plate:
        return jsonify({"error": "Field 'plate' is required"}), 400
    if len(plate) < 4:
        return jsonify({"error": "Plate too short — minimum 4 characters"}), 400

    # Check if already parked
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("SELECT slot_id, status FROM slots WHERE reg_num=?", (plate,))
        existing = c.fetchone()
    if existing:
        return jsonify({
            "error": f"Vehicle {plate} already in slot {existing[0]} (status: {existing[1]})"
        }), 409

    slot = find_best_slot(size)
    if not slot:
        return jsonify({"error": f"Parking full — no {size} slot available"}), 409

    assign_slot(plate, slot, size)
    print(f"[GATE] MANUAL INJECT: {plate} → {slot}")


    return jsonify({
        "plate":         plate,
        "assigned_slot": slot,
        "method":        "manual",
        "size":          size,
        "message":       "Slot reserved successfully",
    })




@app.route('/exit', methods=['POST'])
def exit_vehicle():
    """
    Free a slot.
    Body (one of):
      {"plate": "TN36AM4045"}     — find slot by plate
      {"slot_id": "Slot3"}        — free slot directly
    """
    data    = request.json or {}
    plate   = data.get("plate", "").replace(" ", "").upper() or None
    slot_id = data.get("slot_id") or None

    if not plate and not slot_id:
        return jsonify({"error": "Provide 'plate' or 'slot_id'"}), 400

    now = datetime.datetime.now().isoformat()
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()

        if plate:
            c.execute("SELECT slot_id, entry_time FROM slots WHERE reg_num=?", (plate,))
            row = c.fetchone()
            if not row:
                return jsonify({"error": f"Vehicle {plate} not found"}), 404
            slot_id, entry_time = row
        else:
            c.execute("SELECT reg_num, entry_time FROM slots WHERE slot_id=?", (slot_id,))
            row = c.fetchone()
            if not row:
                return jsonify({"error": f"Slot {slot_id} not found"}), 404
            plate = row[0] or "UNKNOWN"
            entry_time = row[1]

        duration = 0
        if entry_time:
            try:
                duration = int(
                    (datetime.datetime.now() - datetime.datetime.fromisoformat(entry_time))
                    .total_seconds()
                )
            except Exception:
                pass

        c.execute(
            "UPDATE slots SET status='free', reg_num=NULL, entry_time=NULL, is_verified=0 WHERE slot_id=?",
            (slot_id,)
        )
        c.execute(
            "INSERT INTO logs (reg_num, slot_id, action, timestamp) VALUES (?,?,?,?)",
            (plate, slot_id, "EXIT", now)
        )
        conn.commit()

    print(f"[EXIT] {plate} left {slot_id} after {duration}s")
    return jsonify({
        "message":          "Exit successful",
        "freed_slot":       slot_id,
        "plate":            plate,
        "duration_seconds": duration,
    })


@app.route('/reset', methods=['POST'])
def reset_all():
    """
    Reset ALL slots to free. Use between demo runs.
    Optional body: {"confirm": true}  (no body also works)
    """
    now = datetime.datetime.now().isoformat()
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute(
            "UPDATE slots SET status='free', reg_num=NULL, entry_time=NULL, is_verified=0"
        )
        c.execute(
            "INSERT INTO logs (reg_num, slot_id, action, timestamp) VALUES (?,?,?,?)",
            ("SYSTEM", "ALL", "RESET", now)
        )
        conn.commit()

    print("[RESET] All slots freed")
    return jsonify({"message": "All 30 slots reset to free", "timestamp": now})


# ─────────────────────────────────────────────────────────────────────────────
# Startup
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    # 1. Ensure DB exists
    init_db()

    # 2. Load ANPR models in background
    model_thread = threading.Thread(target=anpr_engine.load, daemon=True, name="anpr-loader")
    model_thread.start()

    # 3. Pre-warm camera
    cam_thread = threading.Thread(target=get_camera, daemon=True, name="cam-init")
    cam_thread.start()

    print("\n" + "=" * 60)
    print("  OPTISLOT BACKEND SYSTEM")
    print("  Flask   : http://0.0.0.0:5050")
    print("  ─────────────────────────────────────────")
    print("  Demo inject : POST http://localhost:5050/api/gate/manual")
    print("  Health check: GET  http://localhost:5050/health")
    print("=" * 60 + "\n")

    app.run(host='0.0.0.0', port=5050, debug=False, threaded=True)
