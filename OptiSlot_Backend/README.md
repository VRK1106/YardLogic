# OptiSlot Backend — Digital Twin Bridge

Lean Flask server running on **port 5050** alongside the main parking server.  
Shares `parking.db` so the real system and UE5 digital twin always show identical state.

---

## Quick Start

```powershell
# From the OptiSlot_Backend/ directory
pip install -r requirements.txt
python app.py
```

You should see:
```
  OPTISLOT DIGITAL TWIN — BACKEND BRIDGE
  Flask starting at http://0.0.0.0:5050
  UE5 endpoint : GET  http://localhost:5050/api/digital-twin/slots
  Demo inject  : POST http://localhost:5050/api/gate/manual
  Health check : GET  http://localhost:5050/health
```

> **Note**: The main parking server (`parking_proto_sensor.py`) can run simultaneously on port 5000. They share the same `parking.db`.

---

## API Reference

### `GET /health`
Server liveness check + model load status.
```json
{
  "status": "ok",
  "port": 5050,
  "ready": true,
  "models": {
    "yolo":    {"status": "done", "time": 4.2},
    "easyocr": {"status": "done", "time": 6.8}
  },
  "db": "C:\\...\\parking.db"
}
```

---

### `POST /api/gate/scan`
ANPR gate — grabs live camera frame, runs YOLO + EasyOCR, assigns slot.

**Optional body:**
```json
{"size": "small" | "medium" | "large"}
```
**Response:**
```json
{
  "plate": "TN36AM4045",
  "assigned_slot": "Slot14",
  "method": "yolo+ocr",
  "confidence": 0.94,
  "size": "medium"
}
```

---

### `POST /api/gate/manual`
⭐ **Hackathon demo backup** — inject a plate without a camera.

```bash
# PowerShell
curl -X POST http://localhost:5050/api/gate/manual `
  -H "Content-Type: application/json" `
  -d '{"plate": "TN36AM4045", "size": "medium"}'
```
```bash
# Bash/cURL
curl -X POST http://localhost:5050/api/gate/manual \
  -H "Content-Type: application/json" \
  -d '{"plate": "TN36AM4045", "size": "medium"}'
```

---

### `GET /api/digital-twin/slots`
**UE5 polls this every ~1 second.**

Returns all 30 slots sorted by number:
```json
[
  {"slot_id": "Slot1",  "size_type": "small",  "status": "free",     "reg_num": null,         "entry_time": null, "is_verified": 0},
  {"slot_id": "Slot14", "size_type": "medium", "status": "reserved", "reg_num": "TN36AM4045", "entry_time": "2026-03-12T18:05:00", "is_verified": 0},
  ...
]
```

**Status values for UE5 material mapping:**

| Status | UE5 Color (suggested) |
|---|---|
| `free` | 🟢 Green |
| `reserved` | 🟡 Yellow |
| `occupied` | 🔴 Red |
| `misuse` | 🔶 Orange |
| `blocked` | ⚫ Grey |

---

### `GET /api/stats`
Aggregate counts for UE5 HUD widget.
```json
{
  "total": 30,
  "free": 28,
  "reserved": 1,
  "occupied": 1,
  "misuse": 0,
  "blocked": 0,
  "utilization_pct": 6.7
}
```

---

### `POST /exit`
Free a slot by plate or slot ID.
```json
{"plate": "TN36AM4045"}
```
or
```json
{"slot_id": "Slot14"}
```

---

### `POST /reset`
Reset all 30 slots to free. Use between demo runs.
```bash
curl -X POST http://localhost:5050/reset
```

---

## UE5 Integration Notes

In your `BP_GameMode` Blueprint:
1. Set a **Timer** (every 1.0s) to call `UpdateSlotsFromServer()`
2. Use **VaRest** or UE5 built-in HTTP to `GET http://localhost:5050/api/digital-twin/slots`
3. Parse the JSON array and update each `BP_ParkingSlot` actor's material by matching `slot_id`

**Slot coordinate mapping** (configure in your Level Blueprint):
```
Slot1–10  → Row A (Small, left side)
Slot11–20 → Row B (Medium, center)
Slot21–30 → Row C (Large, right side)
```
