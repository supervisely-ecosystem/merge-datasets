import os
import sys

# the platform runs `uvicorn src.main:app` from the repo root, so modules import each other as `src.*`
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
