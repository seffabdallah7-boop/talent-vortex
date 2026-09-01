"""Tests for Lot 2 admin features: interview badges, cv_scanned, admin-create application, /jobs/all."""
import os
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://candidai.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "seffabdallah7@gmail.com"
ADMIN_PWD = "Admin@2026!"


@pytest.fixture(scope="module")
def admin_token():
    s = requests.Session()
    cap = s.get(f"{BASE_URL}/api/auth/captcha", timeout=15).json()
    # captcha is a math prompt like "3 + 4 = ?"
    q = cap["question"].replace("=", "").replace("?", "").strip()
    ans = str(eval(q))
    r = s.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL, "password": ADMIN_PWD,
        "captcha_id": cap["captcha_id"], "captcha_answer": ans,
    }, timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def h(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


def test_users_list_has_new_fields(h):
    r = requests.get(f"{BASE_URL}/api/users", headers=h, timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list) and len(data) > 0
    sample = data[0]
    for k in ("interview_status", "has_cv", "cv_scanned"):
        assert k in sample, f"missing field {k}"
    assert isinstance(sample["has_cv"], bool)
    assert isinstance(sample["cv_scanned"], bool)


def test_jobs_all_endpoint(h):
    r = requests.get(f"{BASE_URL}/api/jobs/all", headers=h, timeout=15)
    assert r.status_code == 200
    jobs = r.json()
    assert isinstance(jobs, list)
    if jobs:
        assert "id" in jobs[0] and "title" in jobs[0]


def test_admin_create_application_and_verify(h):
    # find a candidate
    users = requests.get(f"{BASE_URL}/api/users", headers=h, timeout=15).json()
    cand = next((u for u in users if u.get("role") == "candidate"), None)
    assert cand, "no candidate available"
    jobs = requests.get(f"{BASE_URL}/api/jobs/all", headers=h, timeout=15).json()
    assert jobs, "no jobs available"
    job = jobs[0]
    payload = {"candidate_id": cand["user_id"], "job_id": job["id"], "status": "interview_scheduled"}
    r = requests.post(f"{BASE_URL}/api/applications/admin-create", json=payload, headers=h, timeout=20)
    assert r.status_code == 200, f"{r.status_code} {r.text}"
    doc = r.json()
    assert doc["candidate_id"] == cand["user_id"]
    assert doc["job_id"] == job["id"]
    assert doc["status"] == "interview_scheduled"
    assert "_id" not in doc

    # Verify persistence via GET /users/{id}
    detail = requests.get(f"{BASE_URL}/api/users/{cand['user_id']}", headers=h, timeout=15).json()
    app_ids = [a["id"] for a in detail["applications"]]
    assert doc["id"] in app_ids

    # Verify that /api/users now surfaces interview_status for this candidate
    users2 = requests.get(f"{BASE_URL}/api/users", headers=h, timeout=15).json()
    found = next(u for u in users2 if u["user_id"] == cand["user_id"])
    assert found["interview_status"] in ("interview_scheduled", "interview_done")


def test_admin_create_invalid_status(h):
    r = requests.post(f"{BASE_URL}/api/applications/admin-create",
                      json={"candidate_id": "x", "job_id": "y", "status": "bogus"},
                      headers=h, timeout=15)
    assert r.status_code == 400


def test_admin_create_unknown_ids(h):
    r = requests.post(f"{BASE_URL}/api/applications/admin-create",
                      json={"candidate_id": "no-such", "job_id": "no-such", "status": "pending"},
                      headers=h, timeout=15)
    assert r.status_code == 404


def test_admin_create_requires_auth():
    r = requests.post(f"{BASE_URL}/api/applications/admin-create",
                      json={"candidate_id": "x", "job_id": "y", "status": "pending"},
                      timeout=15)
    assert r.status_code in (401, 403)
