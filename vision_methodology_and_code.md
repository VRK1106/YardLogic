# Consolidated Vision & ANPR Methodology

This document provides the full technical breakdown and implementation of the **Smart Parking Vision System**. This system is designed for high-accuracy **Automatic Number Plate Recognition (ANPR)** in real-world conditions.

## 1. The High-Level Pipeline (The "Big 5")

The vision agent follows a five-stage system pipeline for handling vehicle entry:

1.  **Capture & Preprocess**: Synchronous decoding and multi-stage image enhancement.
2.  **Multi-Frame Voting**: Captures 5 consecutive frames and uses a consensus algorithm to determine the most likely plate string.
3.  **OCR Extraction**: High-confidence text recognition using EasyOCR.
4.  **Structural Enforcement**: Context-aware character correction based on the Indian plate format (`TT NN TT NNNN`).
5.  **Regex Validation**: Final format verification against official regional patterns.

---

## 2. Deep Dive: 5-Stage Image Preprocessing

To maximize OCR accuracy, each detected license plate undergoes a specialized 5-stage preprocessing pipeline:

| Stage | Operation | Purpose |
| :--- | :--- | :--- |
| **1** | **Adaptive Resizing** | Standards the image height to **64px** while maintaining the aspect ratio. |
| **2** | **Grayscale Conversion** | Removes color noise and focuses on character intensity. |
| **3** | **CLAHE** | Local contrast enhancement to reveal text in shadows or bright spots. |
| **4** | **Bilateral Filtering** | Denoising while strictly preserving character edge sharpness. |
| **5** | **Otsu’s Thresholding** | Automatic binarization to create a clean black-and-white mask for OCR. |

---

## 3. Implementation Code: All-in-One Vision Module

This consolidated module captures all the logic discussed.

### Dependencies
```bash
pip install opencv-python numpy ultralytics easyocr
```

### Vision Module (`consolidated_vision.py`)
```python
import cv2
import numpy as np
import easyocr
import re
import threading
from ultralytics import YOLO

class ConsolidatedVisionAgent:
    def __init__(self, model_path="best.pt"):
        self.model = YOLO(model_path)
        self.reader = easyocr.Reader(['en'], gpu=False)
        self.lock = threading.Lock()

    def process_capture(self, frame_burst):
        """
        Full Pipeline: 5-Stage Processing + Voting
        Input: list of 5 frames (images)
        """
        valid_results = []
        
        for frame in frame_burst:
            # Stage 1: Detection (YOLOv8)
            plate_crop = self._detect_plate(frame)
            if plate_crop is None: continue

            # Stage 2: 5-Stage Preprocessing
            preprocessed = self._preprocess_image(plate_crop)

            # Stage 3: OCR Extraction
            text = self._extract_text(preprocessed)
            if text:
                valid_results.append(text)

        if not valid_results: return "UNKNOWN"

        # Stage 4: Multi-Frame Voting
        voted_string = self._vote_consensus(valid_results)

        # Stage 5: Structural Enforcement & Regex
        final_plate = self._enforce_structure(voted_string)
        
        return final_plate

    def _detect_plate(self, frame):
        results = self.model(frame, verbose=False)
        for res in results:
            for box in res.boxes:
                if box.conf[0] > 0.65:
                    x1, y1, x2, y2 = map(int, box.xyxy[0].cpu().numpy())
                    return frame[y1:y2, x1:x2]
        return None

    def _preprocess_image(self, image):
        """The core 5-stage image enhancement pipeline"""
        # Step 1: Resize (Height=64px)
        h, w = image.shape[:2]
        resized = cv2.resize(image, (int(w * (64.0 / h)), 64))
        # Step 2: Grayscale
        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
        # Step 3: CLAHE (Contrast)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
        cl1 = clahe.apply(gray)
        # Step 4: Bilateral Filter (Denoise)
        bfilter = cv2.bilateralFilter(cl1, 11, 17, 17)
        # Step 5: Otsu Thresholding (Binarize)
        _, thresh = cv2.threshold(bfilter, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return thresh

    def _extract_text(self, img):
        results = self.reader.readtext(img, allowlist='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789')
        if not results: return None
        results.sort(key=lambda x: x[0][0][0]) # Sort horizontal
        return "".join([res[1] for res in results])

    def _vote_consensus(self, results):
        """Determine most likely string from multiple frames"""
        max_len = max(len(s) for s in results)
        voted = []
        for i in range(max_len):
            chars = [s[i] for s in results if i < len(s)]
            voted.append(max(set(chars), key=chars.count))
        return "".join(voted)

    def _enforce_structure(self, text):
        """Indian Plate Format: TT NN TT NNNN"""
        if text.startswith("IND"): text = text[3:]
        chars = list(text)
        if len(chars) != 10: return text # Return raw if length unusual

        t_to_d = {'O': '0', 'I': '1', 'B': '8', 'S': '5', 'G': '6', 'Z': '2', 'A': '4'}
        d_to_t = {'0': 'O', '1': 'I', '8': 'B', '5': 'S', '6': 'G', '2': 'Z', '4': 'A'}
        
        # Structure Mask: T=True (Letter), F=False (Digit)
        mask = [True, True, False, False, True, True, False, False, False, False]
        for i, is_letter in enumerate(mask):
            c = chars[i]
            if is_letter: chars[i] = d_to_t.get(c, c) if c.isdigit() else c
            else: chars[i] = t_to_d.get(c, c) if c.isalpha() else c
        
        res = "".join(chars)
        # Regex Validation Format: TT NN TT NNNN
        return f"{res[:2]} {res[2:4]} {res[4:6]} {res[6:]}"
```

> [!IMPORTANT]
> The **CLAHE** and **Bilateral Filter** steps are the most computationally intensive but offer the highest gain in accuracy for license plates with varied lighting conditions.
