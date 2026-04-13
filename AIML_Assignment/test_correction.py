from app.agents.vision import VisionAgent
import unittest

class TestVisionCorrection(unittest.TestCase):
    def setUp(self):
        self.agent = VisionAgent()
        
    def test_perfect_string(self):
        # TTNNTTNNNN (All correct)
        self.assertEqual(self.agent._correct_plate_format("AB12CD3456"), "AB12CD3456")

    def test_correction_char_to_int(self):
        # TTNNTTNNNN
        # AB I Z CD S B G D
        # I(2)->1, Z(3)->2, S(6)->5, B(7)->8, G(8)->6, D(9)->0
        input_str = "ABIZCDSBGD"
        expected = "AB12CD5860"
        self.assertEqual(self.agent._correct_plate_format(input_str), expected)
        print(f"Corrected {input_str} -> {expected}")

    def test_correction_int_to_char(self):
        # TTNNTTNNNN
        # 4 8 12 0 1 3456
        # 4(0)->A, 8(1)->B, 0(4)->O, 1(5)->I
        input_str = "4812013456"
        expected = "AB12OI3456"
        self.assertEqual(self.agent._correct_plate_format(input_str), expected)
        print(f"Corrected {input_str} -> {expected}")

    def test_length_check(self):
        self.assertIsNone(self.agent._correct_plate_format("SHORT"))
        self.assertIsNone(self.agent._correct_plate_format("TOOLONG12345"))

if __name__ == '__main__':
    unittest.main()
