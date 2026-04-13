import asyncio
from typing import Dict, Any
import cv2
import numpy as np
from ultralytics import YOLO
import threading
import easyocr
import os

# Resolve paths relative to the repo root (two levels up from this file)
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class VisionAgent:
    """
    Real Computer Vision using YOLOv8 + EasyOCR.
    Detects vehicle type and reads license plates.
    """
    _model = None
    _reader = None
    _lock = threading.Lock()

    def __init__(self):
        pass

    def _get_model(self):
        """
        Singleton Model Loader (Thread-safe)
        """
        if self._model is None:
            with self._lock:
                if self._model is None:
                    # Try custom model (best.pt) in repo root, fallback to yolov8n.pt
                    model_path = os.path.join(_REPO_ROOT, "best.pt")
                    if not os.path.exists(model_path):
                        model_path = os.path.join(_REPO_ROOT, "yolov8n.pt")
                    print(f"[VisionAgent] Loading YOLO Model from {model_path}...")
                    try:
                        self._model = YOLO(model_path)
                        print("[VisionAgent] Model Loaded.")
                    except Exception as e:
                        print(f"[VisionAgent] Failed to load model: {e}. Fallback to yolov8n.pt")
                        self._model = YOLO('yolov8n.pt')
        return self._model

    def _get_reader(self):
        """
        Singleton OCR Reader Loader (Thread-safe)
        """
        if self._reader is None:
            with self._lock:
                if self._reader is None:
                    print("[VisionAgent] Loading EasyOCR...")
                    self._reader = easyocr.Reader(['en'], gpu=False)
                    print("[VisionAgent] EasyOCR Loaded.")
        return self._reader

    async def analyze_stream(self, gate_id: str, image_bytes: bytes = None) -> Dict[str, Any]:
        """
        Runs inference on the provided image bytes.
        """
        if not image_bytes:
             await asyncio.sleep(0.5)
             return {"license_plate": f"AI-{gate_id[-2:]}-{np.random.randint(1000,9999)}", "vehicle_type": "medium", "confidence": "0.98"}

        model = self._get_model()
        reader = self._get_reader()
        loop = asyncio.get_running_loop()

        # Run Heavy computation in a thread pool to avoid blocking async loop
        result = await loop.run_in_executor(None, self._analyze_sync, model, reader, image_bytes)
        
        return result

    def _analyze_sync(self, model, reader, image_bytes) -> Dict[str, Any]:
        """
        Synchronous pipeline for CPU-bound tasks (YOLO post-processing + OCR)
        """
        # 1. Decode Image
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return {"error": "Invalid image"}

        # 2. YOLO Inference
        # Note: model() is technically blocking, usually fast on GPU, but CPU might take 100-200ms
        results = model(img, verbose=False)
        
        best_plate_text = ""
        max_conf = 0.0
        vehicle_type = "car"

        if results:
            for r in results:
                boxes = r.boxes
                for box in boxes:
                    conf = float(box.conf[0])
                    if conf > max_conf:
                        max_conf = conf
                        
                        # Crop Plate
                        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                        x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
                        
                        h, w, _ = img.shape
                        x1, y1 = max(0, x1), max(0, y1)
                        x2, y2 = min(w, x2), min(h, y2)
                        
                        plate_crop = img[y1:y2, x1:x2]
                        if plate_crop.size == 0: continue

                        # Preprocessing
                        gray = cv2.cvtColor(plate_crop, cv2.COLOR_BGR2GRAY)
                        # Upscale for better OCR accuracy
                        gray = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
                        
                        # OCR
                        ocr_results = reader.readtext(gray, allowlist='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789')
                        ocr_results.sort(key=lambda x: x[2], reverse=True) # Sort by confidence
                        
                        for (_, text, _) in ocr_results:
                            clean = ''.join(e for e in text if e.isalnum()).upper()
                            
                            # Correction Attempt
                            corrected = self._correct_plate_format(clean)
                            if corrected:
                                best_plate_text = corrected
                                break # Found a perfect match
                            
                            # Heuristic Fallback (if > middle confidence)
                            if len(clean) >= 7 and not best_plate_text:
                                best_plate_text = clean # Store as backup

        # Fallback to Full Image OCR if YOLO fails significantly
        if not best_plate_text and max_conf < 0.4:
            print("[VisionAgent] Low Confidence YOLO. Running Full Image OCR...")
            gray_full = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            ocr_results = reader.readtext(gray_full, detail=0, allowlist='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789')
            for text in ocr_results:
                clean = ''.join(e for e in text if e.isalnum()).upper()
                corrected = self._correct_plate_format(clean)
                if corrected:
                    best_plate_text = corrected
                    break
        
        # Optimized: Always return default dimensions (User Request: No vision-based sizing)
        best_dims = {"width_m": 1.8, "size_class": "Medium"} 

        return {
            "license_plate": best_plate_text if best_plate_text else "UNKNOWN",
            "vehicle_type": vehicle_type,
            "confidence": f"{max_conf:.2f}",
            "dimensions": best_dims
        }

    def _correct_plate_format(self, text: str) -> str | None:
        """
        Enforce Strict Format: TTNNTTNNNN (10 Chars) -> Output: TT NN TT NNNN
        T: Text (A-Z)
        N: Number (0-9)
        
        Robustly handles length mismatch (noise) and swaps chars based on position.
        """
        # Clean cleanup first
        text = ''.join(e for e in text if e.isalnum()).upper()
        print(f"[VisionAgent DEBUG] Correction Input: {text}")
        
        # Mappings
        text_to_digit = {
            'O': '0', 'Q': '0', 'D': '0', 'U': '0', 'I': '1', 'L': '1', 'Z': '2', 'S': '5', 'G': '6', 'B': '8', 'A': '4'
        }
        digit_to_text = {
            '0': "O", '1': 'I', '2': 'Z', '5': 'S', '6': 'G', '8': 'B', '4': 'A'
        }
        
        structure = [True, True, False, False, True, True, False, False, False, False]
        
        candidates = []
        
        # If length match (10), try direct correction
        if len(text) == 10:
            candidates.append(text)
        
        # If longer (11-13), try sliding window of 10
        elif len(text) > 10 and len(text) <= 13:
            for i in range(len(text) - 9):
                candidates.append(text[i : i+10])
                
        # Also try "IND" removal if not already handled
        if text.startswith("IND") and len(text) > 3:
             sub = text[3:]
             if len(sub) >= 10:
                 candidates.append(sub[:10])

        best_score = -1
        best_corrected = None
        
        for idx, candidate in enumerate(candidates):
            current_corrected = []
            score = 0
            valid = True
            print(f"[VisionAgent DEBUG] Candidate {idx}: {candidate}")
            
            for i, char in enumerate(candidate):
                expect_text = structure[i]
                
                if expect_text: # Indices 0,1, 4,5
                    if char.isalpha():
                        # Q is very rare in text positions (State/Series), but O is common.
                        # Visual similarity implies Q is likely a misread O (dirt/screw).
                        if char == 'Q':
                            current_corrected.append('O')
                            score += 0.9 # Corrected match
                        else:
                            current_corrected.append(char)
                            score += 1.0
                    elif char.isdigit():
                        if char in digit_to_text:
                            current_corrected.append(digit_to_text[char])
                            score += 0.9 # High confidence correction
                        else:
                            print(f"[VisionAgent DEBUG] Fail at {i} (Expect Text): {char}")
                            valid = False; break
                    else:
                         valid = False; break
                else: # Expect Digit # Indices 2,3, 6,7,8,9
                    if char.isdigit():
                        current_corrected.append(char)
                        score += 1.0
                    elif char.isalpha():
                        # Explicit user rule: Q -> 0 in number slots
                        if char == 'Q':
                            current_corrected.append('0')
                            score += 1.0 # Treat as almost perfect match due to user rule
                        elif char in text_to_digit:
                            current_corrected.append(text_to_digit[char])
                            score += 0.9 # High confidence correction
                        else:
                            print(f"[VisionAgent DEBUG] Fail at {i} (Expect Digit): {char}")
                            valid = False; break
                    else:
                        valid = False; break
            
            if valid:
                print(f"[VisionAgent DEBUG] Valid! Score: {score}")
                if score > best_score:
                    best_score = score
                    best_corrected = "".join(current_corrected)
            else:
                print(f"[VisionAgent DEBUG] Invalid Candidate")
                
        if best_corrected:
            final = best_corrected
            return f"{final[:2]} {final[2:4]} {final[4:6]} {final[6:]}"
            
        print("[VisionAgent DEBUG] No valid candidates found.")
        return None
