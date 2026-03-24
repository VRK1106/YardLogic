import unittest
import sys

with open("test_output_log.txt", "w", encoding="utf-8") as f:
    runner = unittest.TextTestRunner(stream=f, verbosity=2)
    suite = unittest.TestLoader().discover("tests", pattern="test_pipeline.py")
    runner.run(suite)
