"""Запуск усіх unit-тестів:  python run_tests.py   (докладніше: python run_tests.py -v)"""
import sys
import unittest

if __name__ == "__main__":
    verbosity = 2 if "-v" in sys.argv else 1
    suite = unittest.defaultTestLoader.discover("tests")
    result = unittest.TextTestRunner(verbosity=verbosity).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
