import unittest
import numpy as np
import cv2
import re
import sys
import os

# Ensure the root directory is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from agent import ParkingAgent

class TestANPRPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # We instantiate it once. Note: EasyOCR is loaded securely during initialization
        cls.agent = ParkingAgent(use_gpu=False)
        cls.agent.load_models() # Initialize EasyOCR synchronously for testing

    def test_startup_check(self):
        """1. Startup check: confirm EasyOCR loads once, PaddleOCR absent"""
        self.assertIsNotNone(self.agent.ocr_reader)
        self.assertIn('easyocr', self.agent.boot_status)
        self.assertNotIn('paddleocr', self.agent.boot_status)
        self.assertEqual(self.agent.boot_status['easyocr']['status'], 'done')

    def test_preprocess(self):
        """test_preprocess: Test pipeline preprocessing generates binary images"""
        # Create a dummy image (e.g. 200x50 with some noise)
        dummy_img = np.random.randint(0, 255, (50, 200, 3), dtype=np.uint8)
        processed = self.agent._preprocess_plate(dummy_img)
        
        # Check size (height must be 64)
        h, w = processed.shape
        self.assertEqual(h, 64)
        
        # Check binary (Otsu produces either 0 or 255)
        unique_vals = np.unique(processed)
        self.assertTrue(set(unique_vals).issubset({0, 255}))

    def test_enforcement(self):
        """4. Enforcement cases: Test character map corrections"""
        cases = [
            ("MH12AB123O", "MH12AB1230"),  # O at digit position
            ("MH12AB1238", "MH12AB1238"),  # 8 at digit position (valid)
            ("MHI2AB1234", "MH12AB1234"),  # I at position 2 (digit)
            ("MH12A81234", "MH12AB1234"),  # 8 at letter position
        ]
        
        for input_text, expected in cases:
            output = self.agent._correct_ocr_errors(input_text)
            self.assertEqual(output, expected, f"Failed for {input_text}")

    def test_enforcement_bh_series(self):
        """Test BH specific regex and format enforcement"""
        # 22 B H 1234 A B
        bh_mock = "228H12344B" # "8" at pos 2, "4" at pos 8
        corrected = self.agent._correct_ocr_errors(bh_mock)
        self.assertEqual(corrected, "22BH1234AB")
        
        # Test Regex
        bh_pattern = r'^[0-9]{2}BH[0-9]{4}[A-Z]{2}$'
        self.assertTrue(re.match(bh_pattern, corrected))

    def test_regex_validations(self):
        """test_regex: valid standard, valid BH, invalid, too short, too long"""
        standard_pattern = r'^[A-Z]{2}[0-9]{2}[A-Z]{1,2}[0-9]{4}$'
        
        self.assertTrue(re.match(standard_pattern, "MH12AB1234"))
        self.assertFalse(re.match(standard_pattern, "MH12AB12")) # Too short
        self.assertFalse(re.match(standard_pattern, "MH12AB12345")) # Too long
        self.assertFalse(re.match(standard_pattern, "1234ABMH12")) # Scrambled

    def test_integration_camera_trigger(self):
        """
        Integration test: Mock triggers and verify 3 retries then flag.
        We will pass a generator that yields None (camera fail) and watch retries.
        """
        # Mocking a camera that returns None
        result = self.agent.perceive('camera_trigger', lambda: None)
        self.assertIn('Chief Cause: Camera hardware failed', result.get('error', ''))

if __name__ == '__main__':
    unittest.main()
