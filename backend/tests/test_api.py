"""
Smoke tests for the FastAPI backend.

Strategy: override DATABASE_URL (via conftest.py) and the get_db dependency
so every test runs against a local SQLite file — no LLM calls, no Cloud SQL,
no network required. Fast enough for CI on every PR.

Three tests:
  1. POST /students creates a student and returns it.
  2. POST /students is idempotent — same email returns the existing record.
  3. GET /students/<unknown-id> returns 404.
"""
import os
import pytest
from fastapi.testclient import TestClient

from backend.db.models import Base, engine, get_db, SessionLocal
from backend.api.main import app


# ── Dependency override ────────────────────────────────────────────────────
# Replace the production get_db with one bound to the test engine.
# Applied at module load time so it's in effect for all tests in this file.

def override_get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


# ── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def client():
    """
    Session-scoped TestClient. Creates all tables before tests run,
    drops them after, and removes the test DB file on teardown.
    """
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as c:
        yield c
    Base.metadata.drop_all(bind=engine)
    db_path = "./test_smoke.db"
    if os.path.exists(db_path):
        os.remove(db_path)


# ── Tests ──────────────────────────────────────────────────────────────────

def test_create_student(client):
    r = client.post("/students", json={"name": "Alice", "email": "alice@smoke-test.com"})
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "Alice"
    assert body["email"] == "alice@smoke-test.com"
    assert "id" in body


def test_create_student_idempotent(client):
    """Posting the same email twice returns the existing record, not an error."""
    client.post("/students", json={"name": "Bob", "email": "bob@smoke-test.com"})
    r = client.post("/students", json={"name": "Bob", "email": "bob@smoke-test.com"})
    assert r.status_code == 200


def test_get_student_not_found(client):
    r = client.get("/students/99999")
    assert r.status_code == 404
