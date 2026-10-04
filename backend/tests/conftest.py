"""
Pytest configuration for BlindSpot AI.

Ensures mock mode is set before any imports, so no real API key is needed.
"""
import os
import sys
from pathlib import Path

# Ensure mock mode before importing the app
os.environ.setdefault("MOCK_MODE", "true")
os.environ.setdefault("GEMINI_API_KEY", "test-key-not-real")
os.environ.setdefault("RATE_LIMIT_RPM", "100")

# Add the project root to sys.path so "backend.app.*" imports resolve
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
