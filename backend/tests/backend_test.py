"""Backend regression tests for RecrutAI recruitment platform."""
import io
import os
import time
import uuid

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://candidai.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "seffabdallah7@gmail.com"
ADMIN_PASSWORD = "Admin@2026!"


# ---------- Fixtures ----------
@pytest.fixture(scope="session")
def admin_token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    data = r.json()
    assert data["user"]["role"] == "admin"
    return data["token"]


@pytest.fixture(scope="session")
def candidate():
    email = f"test_cand_{uuid.uuid4().hex[:8]}@test.com"
    r = requests.post(f"{API}/auth/register", json={"name": "Test Candidate", "email": email, "password": "Test@2026!"}, timeout=30)
    assert r.status_code == 200, f"Register failed: {r.text}"
    data = r.json()
    return {"token": data["token"], "user": data["user"], "email": email}


@pytest.fixture(scope="session")
def created_job(admin_token):
    body = {
        "title": "TEST_Engineer",
        "company": "TEST Corp",
        "location": "Paris",
        "type": "Temps plein",
        "category": "Tech",
        "description": "Backend test job.",
        "requirements": "Python",
        "salary": "50k",
    }
    r = requests.post(f"{API}/jobs", json=body, headers={"Authorization": f"Bearer {admin_token}"}, timeout=30)
    assert r.status_code == 200, r.text
    job = r.json()
    assert job["title"] == "TEST_Engineer"
    assert "id" in job
    yield job
    # cleanup handled by delete test if run; otherwise ignore
    requests.delete(f"{API}/jobs/{job['id']}", headers={"Authorization": f"Bearer {admin_token}"})


# ---------- Auth ----------
class TestAuth:
    def test_admin_login(self, admin_token):
        assert isinstance(admin_token, str) and len(admin_token) > 10

    def test_login_invalid(self):
        r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": "wrong"}, timeout=30)
        assert r.status_code == 401

    def test_register_and_me(self, candidate):
        r = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {candidate['token']}"}, timeout=30)
        assert r.status_code == 200
        assert r.json()["role"] == "candidate"

    def test_me_unauth(self):
        r = requests.get(f"{API}/auth/me", timeout=30)
        assert r.status_code == 401

    def test_duplicate_register(self, candidate):
        r = requests.post(f"{API}/auth/register", json={"name": "x", "email": candidate["email"], "password": "x"}, timeout=30)
        assert r.status_code == 400


# ---------- Jobs ----------
class TestJobs:
    def test_public_list_jobs(self):
        r = requests.get(f"{API}/jobs", timeout=30)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_create_and_get_job(self, created_job):
        r = requests.get(f"{API}/jobs/{created_job['id']}", timeout=30)
        assert r.status_code == 200
        assert r.json()["title"] == "TEST_Engineer"

    def test_update_job(self, admin_token, created_job):
        upd = {**{k: created_job[k] for k in ["title", "company", "location", "type", "category", "description", "requirements", "salary"]}}
        upd["title"] = "TEST_Engineer_Updated"
        r = requests.put(f"{API}/jobs/{created_job['id']}", json=upd, headers={"Authorization": f"Bearer {admin_token}"}, timeout=30)
        assert r.status_code == 200
        assert r.json()["title"] == "TEST_Engineer_Updated"
        # verify via GET
        r2 = requests.get(f"{API}/jobs/{created_job['id']}", timeout=30)
        assert r2.json()["title"] == "TEST_Engineer_Updated"

    def test_jobs_all_admin_only(self, admin_token, candidate):
        r = requests.get(f"{API}/jobs/all", headers={"Authorization": f"Bearer {candidate['token']}"}, timeout=30)
        assert r.status_code == 403
        r2 = requests.get(f"{API}/jobs/all", headers={"Authorization": f"Bearer {admin_token}"}, timeout=30)
        assert r2.status_code == 200

    def test_create_job_forbidden_for_candidate(self, candidate):
        r = requests.post(f"{API}/jobs", json={"title": "x", "company": "x", "location": "x", "description": "x"},
                          headers={"Authorization": f"Bearer {candidate['token']}"}, timeout=30)
        assert r.status_code == 403


# ---------- Applications flow ----------
class TestApplications:
    def _apply(self, candidate, job_id):
        files = {"cv": ("cv.pdf", io.BytesIO(b"%PDF-1.4 test cv content"), "application/pdf")}
        data = {"job_id": job_id, "cover_note": "Bonjour, je suis interesse."}
        r = requests.post(f"{API}/applications", data=data, files=files,
                          headers={"Authorization": f"Bearer {candidate['token']}"}, timeout=90)
        return r

    def test_create_application_pending(self, candidate, created_job):
        r = self._apply(candidate, created_job["id"])
        assert r.status_code == 200, r.text
        app = r.json()
        assert app["status"] == "pending"
        assert app["candidate_id"] == candidate["user"]["user_id"]
        assert app["cv_file_id"]
        pytest.app_id = app["id"]
        pytest.cv_file_id = app["cv_file_id"]

    def test_my_applications(self, candidate):
        r = requests.get(f"{API}/applications/me", headers={"Authorization": f"Bearer {candidate['token']}"}, timeout=30)
        assert r.status_code == 200
        apps = r.json()
        assert any(a["id"] == pytest.app_id for a in apps)

    def test_admin_list_applications(self, admin_token):
        r = requests.get(f"{API}/applications", headers={"Authorization": f"Bearer {admin_token}"}, timeout=30)
        assert r.status_code == 200
        assert any(a["id"] == pytest.app_id for a in r.json())

    def test_update_status_accepted(self, admin_token, candidate):
        r = requests.put(f"{API}/applications/{pytest.app_id}/status", json={"status": "accepted"},
                         headers={"Authorization": f"Bearer {admin_token}"}, timeout=30)
        assert r.status_code == 200
        assert r.json()["status"] == "accepted"
        # verify candidate sees it
        r2 = requests.get(f"{API}/applications/me", headers={"Authorization": f"Bearer {candidate['token']}"}, timeout=30)
        assert any(a["id"] == pytest.app_id and a["status"] == "accepted" for a in r2.json())

    def test_update_status_invalid(self, admin_token):
        r = requests.put(f"{API}/applications/{pytest.app_id}/status", json={"status": "bogus"},
                         headers={"Authorization": f"Bearer {admin_token}"}, timeout=30)
        assert r.status_code == 400

    def test_cv_download_admin(self, admin_token):
        r = requests.get(f"{API}/files/{pytest.cv_file_id}", headers={"Authorization": f"Bearer {admin_token}"}, timeout=30)
        assert r.status_code == 200
        assert len(r.content) > 0

    def test_cv_download_forbidden_for_other(self):
        # A newly registered candidate should not access another's CV
        email = f"other_{uuid.uuid4().hex[:6]}@test.com"
        rr = requests.post(f"{API}/auth/register", json={"name": "O", "email": email, "password": "Test@2026!"}, timeout=30)
        tok = rr.json()["token"]
        r = requests.get(f"{API}/files/{pytest.cv_file_id}", headers={"Authorization": f"Bearer {tok}"}, timeout=30)
        assert r.status_code == 403

    def test_delete_application(self, admin_token):
        r = requests.delete(f"{API}/applications/{pytest.app_id}", headers={"Authorization": f"Bearer {admin_token}"}, timeout=30)
        assert r.status_code == 200


# ---------- Candidates ----------
class TestCandidates:
    def test_list_candidates(self, admin_token, candidate):
        r = requests.get(f"{API}/candidates", headers={"Authorization": f"Bearer {admin_token}"}, timeout=30)
        assert r.status_code == 200
        assert any(u["email"] == candidate["email"] for u in r.json())


# ---------- Chat (polling) ----------
class TestChat:
    def test_candidate_sends_message(self, candidate, admin_token):
        r = requests.post(f"{API}/chat/messages", json={"text": "Bonjour admin"},
                          headers={"Authorization": f"Bearer {candidate['token']}"}, timeout=30)
        assert r.status_code == 200
        msg = r.json()
        assert msg["sender_role"] == "candidate"
        # admin lists conversations
        r2 = requests.get(f"{API}/chat/conversations", headers={"Authorization": f"Bearer {admin_token}"}, timeout=30)
        assert r2.status_code == 200
        convs = r2.json()
        assert any(c["candidate_id"] == candidate["user"]["user_id"] for c in convs)

    def test_admin_replies(self, admin_token, candidate):
        cid = candidate["user"]["user_id"]
        r = requests.post(f"{API}/chat/messages", json={"text": "Bonjour candidat", "candidate_id": cid},
                          headers={"Authorization": f"Bearer {admin_token}"}, timeout=30)
        assert r.status_code == 200
        # candidate polls
        r2 = requests.get(f"{API}/chat/messages", headers={"Authorization": f"Bearer {candidate['token']}"}, timeout=30)
        assert r2.status_code == 200
        texts = [m["text"] for m in r2.json()]
        assert "Bonjour candidat" in texts


# ---------- Theme ----------
class TestTheme:
    def test_get_theme_public(self):
        r = requests.get(f"{API}/settings/theme", timeout=30)
        assert r.status_code == 200
        assert "primary" in r.json()

    def test_update_theme(self, admin_token):
        body = {"primary": "10 90% 50%", "primary_foreground": "0 0% 100%", "name": "TEST_Red"}
        r = requests.put(f"{API}/settings/theme", json=body, headers={"Authorization": f"Bearer {admin_token}"}, timeout=30)
        assert r.status_code == 200
        # persist check
        r2 = requests.get(f"{API}/settings/theme", timeout=30)
        assert r2.json()["primary"] == "10 90% 50%"

    def test_update_theme_forbidden(self, candidate):
        r = requests.put(f"{API}/settings/theme",
                         json={"primary": "0 0% 0%", "primary_foreground": "0 0% 100%", "name": "x"},
                         headers={"Authorization": f"Bearer {candidate['token']}"}, timeout=30)
        assert r.status_code == 403


# ---------- Admin stats ----------
class TestStats:
    def test_admin_stats(self, admin_token):
        r = requests.get(f"{API}/admin/stats", headers={"Authorization": f"Bearer {admin_token}"}, timeout=30)
        assert r.status_code == 200
        d = r.json()
        for k in ["jobs", "candidates", "applications", "pending", "accepted", "rejected"]:
            assert k in d


# ---------- AI chat ----------
class TestAI:
    def test_ai_chat_replies_french(self):
        sid = f"test-sess-{uuid.uuid4().hex[:8]}"
        r = requests.post(f"{API}/ai/chat", json={"session_id": sid, "message": "Comment puis-je postuler ?"}, timeout=90)
        assert r.status_code == 200
        reply = r.json().get("reply", "")
        assert isinstance(reply, str) and len(reply) > 5
        # should not be the fallback error
        assert "souci technique" not in reply.lower(), f"AI fell back: {reply}"


# ---------- Cleanup ----------
def test_zz_cleanup(admin_token, candidate):
    # delete candidate (cleans applications + messages)
    requests.delete(f"{API}/candidates/{candidate['user']['user_id']}", headers={"Authorization": f"Bearer {admin_token}"})
