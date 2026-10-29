"""
tests/conftest.py
─────────────────────────────────────────────────────
Shared pytest configuration for the Physical Chatbot Trigger project.
No special fixtures are needed right now; this file just ensures that
the `backend/` directory is on the Python path so tests can import
`lambda_function` directly.
"""
import sys
import os

# Add the backend directory to sys.path
backend_dir = os.path.join(os.path.dirname(__file__), '..', 'backend')
sys.path.insert(0, os.path.abspath(backend_dir))
