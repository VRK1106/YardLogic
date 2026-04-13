# OptiSlot AO — AI-Powered Vehicle Vision System

> **AI/ML Assignment** — A real-time vehicle detection and license plate recognition system built with YOLOv8, EasyOCR, and FastAPI.

---

## 🎯 Overview

OptiSlot AO uses a **Vision Agent** powered by deep learning to detect vehicles from camera feeds, classify their size, and read license plates using Automatic Number Plate Recognition (ANPR). The system exposes a FastAPI endpoint that accepts vehicle images and returns structured detection results in real-time.

---

## 🏗️ Architecture

```
Camera / Image Upload
        │
        ▼
┌────────────────────────────────┐
│   FastAPI Server (main.py)     │
│   POST /gate/{id}/entry        │
└────────────┬───────────────────┘
             │
             ▼
┌──────────────────────────────────────────────┐
│            Vision Agent Pipeline             │
│                                              │
│  ┌────────────┐    ┌─────────────────────┐   │
│  │  YOLOv8    │───►│  Vehicle Detection  │   │
│  │  Model     │    │  + Size Classify    │   │
│  └────────────┘    └─────────┬───────────┘   │
│                              │               │
│                              ▼               │
│                    ┌─────────────────────┐   │
│                    │  EasyOCR            │   │
│                    │  License Plate Read │   │
│                    └─────────┬───────────┘   │
│                              │               │
│                              ▼               │
│                    ┌─────────────────────┐   │
│                    │  Heuristic Corrector│   │
│                    │  TT NN TT NNNN     │   │
│                    └─────────────────────┘   │
└──────────────────────────────────────────────┘
```

---

## 🧠 Vision Agent (`app/agents/vision.py`)

The core of the project — a multi-stage computer vision pipeline:

### Stage 1: Vehicle Detection (YOLOv8)
- Loads a **custom-trained YOLO model** (`best.pt`) with fallback to `yolov8n.pt`.
- Detects vehicles in the image and classifies them:
  - `Bus` / `Truck` → **Large**
  - `Car` → **Medium**
  - `Motorcycle` → **Small**
- Extracts bounding box dimensions for size estimation.
- Thread-safe singleton model loading to avoid redundant GPU/CPU allocation.

### Stage 2: License Plate Reading (EasyOCR)
- Crops the detected vehicle region and runs **Optical Character Recognition**.
- Extracts raw text from the license plate area.

### Stage 3: Heuristic Plate Corrector
A custom algorithm that enforces the **Indian license plate format**: `TT NN TT NNNN`
- `T` = Text character (A–Z)
- `N` = Numeric digit (0–9)

**Smart character corrections:**
| OCR Misread | Position Expected | Auto-Corrected To |
|---|---|---|
| `O` (letter) | Number position | `0` (zero) |
| `0` (zero) | Letter position | `O` (letter O) |
| `I` (letter) | Number position | `1` (one) |
| `Q` | Number position | `0` (zero) |
| `S` | Number position | `5` |
| `B` | Number position | `8` |

Handles length mismatches and noise from OCR output.

### Pipeline Output
```json
{
  "license_plate": "MH 12 AB 1234",
  "vehicle_type": "car",
  "confidence": 0.92,
  "dimensions": {
    "width": 350,
    "height": 180,
    "size_class": "Medium"
  }
}
```

---

## � Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| **Object Detection** | YOLOv8 (Ultralytics) | Vehicle detection & classification |
| **OCR** | EasyOCR | License plate text extraction |
| **Image Processing** | OpenCV | Decoding & preprocessing image bytes |
| **API Server** | FastAPI + Uvicorn | REST endpoint for image submission |
| **Database** | Supabase (PostgreSQL) | Parking slot & session storage |
| **Dashboard** | Streamlit | Real-time parking grid UI |

---

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- [Supabase](https://supabase.com) project (free tier works)

### 1. Setup
```bash
cd AIML_Assignment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux/Mac
pip install -r requirements.txt
```

### 2. Configure
```bash
cp .env.example .env
# Edit .env with your Supabase URL and anon key
```

### 3. Seed Database
```bash
python seed_db.py
```

### 4. Run API Server
```bash
uvicorn app.main:app --reload
```
Swagger docs available at `http://127.0.0.1:8000/docs`

### 5. Run Dashboard
```bash
streamlit run dashboard.py
```

### 6. Test Detection
```bash
curl -X POST "http://127.0.0.1:8000/gate/GATE_01/entry" -F "file=@test_car.jpeg"
```

---

## 📁 Project Structure

```
AIML_Assignment/
├── app/
│   ├── __init__.py
│   ├── main.py                # FastAPI app & entry endpoint
│   └── agents/
│       ├── vision.py          # ★ YOLOv8 + EasyOCR + Plate Corrector
│       ├── allocation.py      # Slot allocator (supporting)
│       ├── verification.py    # QR verification (supporting)
│       └── exit_billing.py    # Billing logic (supporting)
├── dashboard.py               # Streamlit UI
├── seed_db.py                 # DB seeder script
├── db_setup.sql               # SQL schema
├── parking_zones.json         # Zone geometry config
├── requirements.txt
├── Dockerfile
├── .env.example
├── best.pt                    # Custom-trained YOLO model
├── yolov8n.pt                 # Fallback YOLO model
└── README.md
```

---

## 📜 License

MIT
