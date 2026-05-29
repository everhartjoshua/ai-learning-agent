"""
Test configuration — loaded by pytest before any test module is imported.

Sets DATABASE_URL to a file-based SQLite path so the engine created at
models.py import-time uses the test database, not the production URL.
Must be the very first thing that runs, which pytest guarantees for conftest.py.
"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_smoke.db"
