
import sqlite3
import datetime
import cv2
import numpy as np
import easyocr
import re
import os
import time
import threading
import logging
from ultralytics import YOLO

# Define the Database Name
DB_NAME = "parking.db"
CALIBRATION_WARNING_THRESHOLD = 2

class ParkingAgent:
    
    def __init__(self, use_gpu=False):
        self.name = "SmartParkingAgent_V1"
        self.state = {
            "slots": [],
            "current_vehicle": None,
            "alerts": []
        }
        self._use_gpu = use_gpu
        
        # Models start as None — loaded in background via load_models()
        self.ocr_reader = None
        self.model = None
        self._models_loaded = False
        self._lock = threading.Lock()
        
        # Calibration monitoring
        self.calibration_warnings = []
        self.logger = logging.getLogger(self.name)
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)
        
        # Boot status tracking (polled by loading page)
        self.boot_status = {
            "yolo": {"status": "pending", "time": None},
            "easyocr": {"status": "pending", "time": None},
        }
    
    @property
    def is_ready(self):
        return self._models_loaded
    
    def load_models(self):
        """Load YOLO and EasyOCR in parallel threads."""
        t_yolo = threading.Thread(target=self._load_yolo, daemon=True)
        t_ocr = threading.Thread(target=self._load_easyocr, daemon=True)
        
        t_yolo.start()
        t_ocr.start()
        
        # Wait for both to finish
        t_yolo.join()
        t_ocr.join()
        
        self._models_loaded = True
        print(f"[{self.name}] All models loaded and ready.")
    
    def _load_yolo(self):
        self.boot_status["yolo"]["status"] = "loading"
        start = time.time()
        model_path = r'd:\Non_Academic\Project\Smart_Parking_Traffic_Test\AI_Model\best.pt'
        try:
            if os.path.exists(model_path):
                print(f"[{self.name}] Loading YOLO Model...")
                self.model = YOLO(model_path)
                elapsed = round(time.time() - start, 1)
                self.boot_status["yolo"] = {"status": "done", "time": elapsed}
                print(f"[{self.name}] YOLO loaded in {elapsed}s")
            else:
                print(f"[{self.name}] WARNING: YOLO Model not found at {model_path}")
                self.boot_status["yolo"] = {"status": "skipped", "time": 0}
        except Exception as e:
            print(f"[{self.name}] YOLO load error: {e}")
            self.boot_status["yolo"] = {"status": "error", "time": round(time.time() - start, 1)}
    
    def _load_easyocr(self):
        self.boot_status["easyocr"]["status"] = "loading"
        start = time.time()
        try:
            print(f"[{self.name}] Loading EasyOCR...")
            self.ocr_reader = easyocr.Reader(['en'], gpu=self._use_gpu)
            elapsed = round(time.time() - start, 1)
            self.boot_status["easyocr"] = {"status": "done", "time": elapsed}
            print(f"[{self.name}] EasyOCR loaded in {elapsed}s")
        except Exception as e:
            print(f"[{self.name}] EasyOCR load error: {e}")
            self.boot_status["easyocr"] = {"status": "error", "time": round(time.time() - start, 1)}

        
    def perceive(self, percept_type, data):
        
        timestamp = datetime.datetime.now()
        # print(f"[{self.name}] Perceiving {percept_type} at {timestamp}")
        
        if percept_type == 'image':
            return self._process_visual_input(data)
        elif percept_type == 'camera_trigger':
            return self._process_camera_trigger(data)
        elif percept_type == 'nfc':
            return self._process_nfc_input(data)
        elif percept_type == 'sensor_update':
            return self._update_internal_sensor_model(data)
            
        return None

    def run_pipeline(self, percept_type, data):
        
        # Step 1: Perception
        percepts = self.perceive(percept_type, data)
        
        # Step 2: Decision
        actions = self.decide(percepts)
        
        # Step 3: Action Execution
        results = []
        for action in actions:
            result = self.act(action)
            results.append(result)
            
        return results

    def decide(self, current_percepts):
        
        actions = []
        if not current_percepts:
            return actions

        # Rule 0: Admin Reset
        if current_percepts.get('command') == 'RESET':
            return [{'type': 'RESET_ALL'}]
        
        # Rule 1: Visual Entry Request
        if 'reg_num' in current_percepts:
            reg_num = current_percepts['reg_num']
            vehicle_size = current_percepts.get('vehicle_size', 'medium')
            # Decision Logic: Check if authorized or new entry
            action = self._decide_entry_logic(reg_num, vehicle_size)
            actions.append(action)
            
        # Rule 2: NFC Entry Request
        if 'tag_id' in current_percepts:
            tag_id = current_percepts['tag_id']
            action = self._decide_nfc_logic(tag_id)
            actions.append(action)
            
        return actions

    def act(self, action):
        
        if not action:
            return None
            
        action_type = action.get('type')
        print(f"[{self.name}] Executing Action: {action_type}")
        
        if action_type == 'GRANT_ACCESS':
            return self._act_grant_access(action['data'])
        elif action_type == 'DENY_ACCESS':
            return {'status': 'error', 'message': action['reason']}
        elif action_type == 'RESERVE_SLOT':
             return self._act_reserve_slot(action['data'])
        elif action_type == 'RELEASE_SLOT':
             return self._act_release_slot(action['data'])
        elif action_type == 'RESET_ALL':
            return self._act_reset_all()
             
        return {'status': 'unknown_action'}

    # --- Internal Reasoning Methods (The "Mind") ---
    
    def _preprocess_plate(self, image):
        """
        Stage 1: Preprocessing Pipeline
        1. Resize to height=64px (maintain aspect ratio)
        2. Grayscale conversion
        3. CLAHE (clipLimit=2.0, tileGridSize=(8,8))
        4. Bilateral Filter (d=11, sigmaColor=17, sigmaSpace=17)
        5. Otsu Thresholding
        """
        if image is None or image.size == 0:
            return image
        h, w = image.shape[:2]
        new_w = int(w * (64.0 / h))
        resized = cv2.resize(image, (new_w, 64))
        
        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
        
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
        cl1 = clahe.apply(gray)
        
        bfilter = cv2.bilateralFilter(cl1, 11, 17, 17)
        
        _, thresh = cv2.threshold(bfilter, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return thresh

    def _contour_fallback_crop(self, image):
        """Fallback to contour-based detection if YOLO fails."""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        bfilter = cv2.bilateralFilter(gray, 11, 17, 17)
        edged = cv2.Canny(bfilter, 30, 200)
        
        contours, _ = cv2.findContours(edged, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        contours = sorted(contours, key=cv2.contourArea, reverse=True)[:10]
        
        for contour in contours:
            approx = cv2.approxPolyDP(contour, 10, True)
            if len(approx) == 4:
                x, y, w, h = cv2.boundingRect(contour)
                aspect_ratio = w / float(h)
                if 2.0 <= aspect_ratio <= 6.0:
                    return image[y:y+h, x:x+w]
        return None

    def _process_camera_trigger(self, get_frame_callback):
        """
        Full 5-stage pipeline for ANPR handling 5-frame bursts and up to 3 retries.
        """
        max_retries = 3
        last_error = "Camera feed empty or unavailable"
        for attempt in range(max_retries):
            print(f"[{self.name}] --- ANPR Attempt {attempt + 1}/{max_retries} ---")
            
            # Step 1: Capture 5 frames
            frames = []
            for _ in range(5):
                frame = get_frame_callback()
                if frame is not None:
                    frames.append(frame)
                time.sleep(0.033) # Simulate ~30fps delay
                
            if len(frames) < 3:
                last_error = 'Camera hardware failed to provide enough frames for a burst.'
                print(f"[{self.name}] Camera failed to provide enough frames. Retrying.")
                time.sleep(0.5)
                continue
                
            valid_results = []
            
            # Process each frame
            for i, frame in enumerate(frames):
                # Check QR first
                detector = cv2.QRCodeDetector()
                data, _, _ = detector.detectAndDecode(frame)
                if data:
                    print(f"[{self.name}] QR Code Detected: {data}")
                    return {'reg_num': data.strip().upper(), 'confidence': 'high', 'type': 'qr'}
                
                # YOLO Detect + crop
                cropped_plate = None
                if self.model:
                    results = self.model(frame, verbose=False)
                    best_conf = 0
                    best_box = None
                    for res in results:
                        for box in res.boxes:
                            if box.conf[0] > best_conf:
                                best_conf = box.conf[0]
                                best_box = box
                    
                    if best_box and best_conf >= 0.65:
                        x1, y1, x2, y2 = map(int, best_box.xyxy[0].cpu().numpy())
                        
                        # Apply 8% padding
                        pad_x = int((x2 - x1) * 0.08)
                        pad_y = int((y2 - y1) * 0.08)
                        
                        h, w = frame.shape[:2]
                        x1 = max(0, x1 - pad_x)
                        y1 = max(0, y1 - pad_y)
                        x2 = min(w, x2 + pad_x)
                        y2 = min(h, y2 + pad_y)
                        
                        cropped_plate = frame[y1:y2, x1:x2]
                
                # Fallback to contour if YOLO failed or low conf
                if cropped_plate is None:
                    cropped_plate = self._contour_fallback_crop(frame)
                
                if cropped_plate is None or cropped_plate.size == 0:
                    print(f"[{self.name}] Frame {i+1}: Failed to detect plate region. Excluding.")
                    continue
                
                # Stage 1: Preprocess
                preprocessed = self._preprocess_plate(cropped_plate)
                
                # EasyOCR Read
                if self.ocr_reader:
                    ocr_out = self.ocr_reader.readtext(preprocessed, allowlist='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789')
                    if ocr_out:
                        ocr_out.sort(key=lambda x: x[0][0][0]) # Sort horizontally
                        full_text = "".join([res[1] for res in ocr_out])
                        total_conf = sum([res[2] * len(res[1]) for res in ocr_out])
                        avg_conf = total_conf / max(1, len(full_text))
                        
                        # Level 1 Confidence Threshold
                        if avg_conf < 0.65:
                            print(f"[{self.name}] Frame {i+1}: Low confidence ({avg_conf:.2f}). Excluding.")
                            continue
                            
                        clean_text = ''.join(e for e in full_text if e.isalnum()).upper()
                        valid_results.append({'text': clean_text, 'conf': avg_conf})
                        print(f"[{self.name}] Frame {i+1}: Read '{clean_text}' (conf {avg_conf:.2f})")
            
            # Level 1 Minimum Threshold Limit
            if len(valid_results) < 3:
                last_error = 'Too many frames rejected due to low confidence (<0.65) or missing plate regions.'
                print(f"[{self.name}] Fewer than 3 frames passed Level 1 threshold. Skipping voting, triggering retry immediately.")
                continue
                
            # Level 2 Confidence: Average confidence of contributing frames
            overall_avg_conf = sum([res['conf'] for res in valid_results]) / len(valid_results)
            print(f"[{self.name}] Level 2 Avg Confidence: {overall_avg_conf:.2f}")
            if overall_avg_conf < 0.55:
                last_error = f'Multi-frame vote conflicted too highly (Avg Confidence: {overall_avg_conf:.2f} < 0.55)'
                print(f"[{self.name}] Level 2 average confidence < 0.55. Triggering full retry.")
                continue
                
            # Stage 2: Multi-Frame Voting
            lengths = [len(r['text']) for r in valid_results]
            mode_length = max(set(lengths), key=lengths.count)
            aligned_texts = [r['text'] for r in valid_results if len(r['text']) == mode_length]
            if not aligned_texts:
                aligned_texts = [r['text'] for r in valid_results]
                
            voted_chars = []
            max_len = max([len(t) for t in aligned_texts])
            for char_idx in range(max_len):
                char_votes = []
                for text in aligned_texts:
                    if char_idx < len(text):
                        char_votes.append(text[char_idx])
                if char_votes:
                    voted_char = max(set(char_votes), key=char_votes.count)
                    voted_chars.append(voted_char)
            
            voted_string = "".join(voted_chars)
            print(f"[{self.name}] Multi-frame Voted String: {voted_string}")
            
            # Stage 4: Structural Enforcement
            corrected_string = self._correct_ocr_errors(voted_string)
            print(f"[{self.name}] Structure Corrected: {corrected_string}")
            
            # Calibration Warning Monitor
            if corrected_string and len(voted_string) == len(corrected_string):
                corrections_made = sum(1 for a, b in zip(voted_string, corrected_string) if a != b)
                if corrections_made >= CALIBRATION_WARNING_THRESHOLD:
                    self.logger.warning(
                        f"High correction count ({corrections_made}) on plate "
                        f"{voted_string} -> {corrected_string}. "
                        f"EasyOCR confidence calibration may be unreliable for this capture!"
                    )
                    self.calibration_warnings.append({
                        "timestamp": datetime.datetime.now().isoformat(),
                        "voted": voted_string,
                        "corrected": corrected_string,
                        "corrections": corrections_made,
                        "avg_confidence": overall_avg_conf
                    })
            
            if not corrected_string:
                last_error = f"Structural Enforcement failed to parse length of voted string: '{voted_string}'."
                continue
            
            # Stage 5: Regex Validation
            standard_pattern = r'^[A-Z]{2}[0-9]{2}[A-Z]{1,2}[0-9]{4}$'
            bh_pattern = r'^[0-9]{2}BH[0-9]{4}[A-Z]{2}$'
            
            if re.match(standard_pattern, corrected_string) or re.match(bh_pattern, corrected_string):
                print(f"[{self.name}] Validation PASSED: {corrected_string}")
                return {'reg_num': corrected_string, 'confidence': 'high', 'method': 'easyocr_pipeline'}
            else:
                last_error = f"Regex validation failed for formatted string: '{corrected_string}'"
                print(f"[{self.name}] Validation FAILED for '{corrected_string}'. Triggering retry.")
                continue

        print(f"[{self.name}] Max retries reached. Returning failure.")
        return {'error': f"No valid plate detected after {max_retries} attempts! Chief Cause: {last_error}"}

    def _process_visual_input(self, image):
        """Fallback for single-frame paths."""
        res = self._process_camera_trigger(lambda: image)
        return res

    def _correct_ocr_errors(self, text):
        if text.startswith("IND") and len(text) > 10: text = text[3:]
        chars = list(text)
        
        digit_map = {'O': '0', 'I': '1', 'l': '1', 'B': '8', 'S': '5', 'G': '6', 'Z': '2', 'D': '0', 'Q': '0', 'A': '4', 'T': '7'}
        letter_map = {'0': 'O', '1': 'I', '8': 'B', '5': 'S', '6': 'G', '2': 'Z', '4': 'A', '7': 'T'}
        
        if len(chars) == 10:
            # BH plates often have B/8 at index 2, and H at index 3
            if chars[2] in ('B', '8') and chars[3] in ('H', '4', 'N'):
                pattern = "NNTTNNNNTT" # BH
            else:
                pattern = "TTNNTTNNNN" # Standard
        elif len(chars) == 9:
            pattern = "TTNNTNNNN" # Standard
        else:
            return "".join(chars)
            
        for i, expected in enumerate(pattern):
            c = chars[i]
            if expected == 'T':
                chars[i] = letter_map.get(c, c)
            elif expected == 'N':
                chars[i] = digit_map.get(c, c)
                
        if pattern == "NNTTNNNNTT":
            chars[2] = 'B'
            chars[3] = 'H'

        return "".join(chars)

    def _decide_entry_logic(self, reg_num, vehicle_size='medium'):
        """
        Decides whether to let a car in based on current DB state.
        """
        with sqlite3.connect(DB_NAME) as conn:
            c = conn.cursor()
            c.execute("SELECT slot_id, status FROM slots WHERE reg_num = ?", (reg_num,))
            existing = c.fetchone()
            
            if existing:
                if existing[1] == 'reserved':
                    return {'type': 'GRANT_ACCESS', 'data': {'reg_num': reg_num, 'slot_id': existing[0], 'is_reservation': True}}
                else:
                    return {'type': 'DENY_ACCESS', 'reason': f'Vehicle {reg_num} is already parked in {existing[0]}'}
            
            # Find slot based on the actual vehicle size
            slot_id = self._find_best_slot_logic(vehicle_size)
            if slot_id:
                return {'type': 'GRANT_ACCESS', 'data': {'reg_num': reg_num, 'slot_id': slot_id, 'is_reservation': False}}
            else:
                 return {'type': 'DENY_ACCESS', 'reason': f'Parking Full (No {vehicle_size} or larger slots available)'}

    def _find_best_slot_logic(self, size):
        with sqlite3.connect(DB_NAME) as conn:
            c = conn.cursor()
            # Best-fit: try exact size first, then upgrade to bigger slots
            if size == 'small':
                search_order = ['small', 'medium', 'large']
            elif size == 'large':
                search_order = ['large']
            else:  # medium (default)
                search_order = ['medium', 'large']
            for check_size in search_order:
                c.execute("SELECT slot_id FROM slots WHERE size_type = ? AND status = 'free' ORDER BY slot_id ASC LIMIT 1", (check_size,))
                result = c.fetchone()
                if result: return result[0]
        return None

    def _act_grant_access(self, data):
        reg_num = data['reg_num']
        slot_id = data['slot_id']
        
        with sqlite3.connect(DB_NAME) as conn:
            c = conn.cursor()
            # INTEGRITY FIX: Clear any previous slot for this vehicle to prevent duplicates
            c.execute("UPDATE slots SET status = 'free', reg_num = NULL, entry_time = NULL, is_verified = 0 WHERE reg_num = ?", (reg_num,))
            
            c.execute("UPDATE slots SET status = 'reserved', reg_num = ?, entry_time = ?, is_verified = 0 WHERE slot_id = ?", 
                      (reg_num, datetime.datetime.now().isoformat(), slot_id))
            conn.commit()
            
        self._log_action(reg_num, slot_id, "ENTRY")
        return {'status': 'success', 'assigned_slot': slot_id}
    
    def _act_reset_all(self):
        try:
            with sqlite3.connect(DB_NAME) as conn:
                c = conn.cursor()
                c.execute("UPDATE slots SET status = 'free', reg_num = NULL, entry_time = NULL, is_verified = 0")
                conn.commit()
            self._log_action("ADMIN", "ALL", "RESET")
            print(f"[{self.name}] All slots reset successfully.")
            return {'status': 'success', 'message': 'All slots have been reset.'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    def _log_action(self, reg_num, slot_id, action):
        with sqlite3.connect(DB_NAME) as conn:
            c = conn.cursor()
            timestamp = datetime.datetime.now().isoformat()
            c.execute("INSERT INTO logs (reg_num, slot_id, action, timestamp) VALUES (?, ?, ?, ?)", 
                      (reg_num, slot_id, action, timestamp))
            conn.commit()

