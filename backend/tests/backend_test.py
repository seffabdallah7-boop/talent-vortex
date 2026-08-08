"""Backend regression tests for RecrutAI recruitment platform (captcha + OTP + admin_code).

Tests cover:
 - Auth: captcha, OTP, admin_code, forgot/reset password, strong password validation
 - Contracts CRUD (admin)
 - Interviews CRUD (admin)
 - Applications review + status
 - CSV exports (with ?auth= query token)
 - Admin stats widgets
"""
import os
import re
import subprocess
import time
import uuid

import pytest
import requests

def _load_backend_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if v:
        return v
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.strip().startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    raise RuntimeError("REACT_APP_BACKEND_URL not set")


BASE_URL = _load_backend_url().rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "seffabdallah7@gmail.com"
ADMIN_PASSWORD = "Admin@2026!"
ADMIN_CODE = "RECRUT-ADM-2026"
CANDIDATE_EMAIL = "candidate1@test.com"
CANDIDATE_PASSWORD = "Test@2026!"

LOG_FILE = "/var/log/supervisor/backend.err.log"


# ----------------------------- helpers -----------------------------
def get_captcha():
    r = requests.get(f"{API}/auth/captcha", timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    q = d["question"]  # e.g. "3 + 4"
    m = re.match(r"\s*(\d+)\s*\+\s*(\d+)", q)
    assert m, f"Unexpected captcha question: {q}"
    ans = str(int(m.group(1)) + int(m.group(2)))
    return d["captcha_id"], ans


def read_code_from_log(prefix: str, email: str, since_ts: float, timeout: float = 8.0):
    """Grep OTP/RESET code from backend logs since given timestamp."""
    deadline = time.time() + timeout
    pattern = f"{prefix} {email} = "
    while time.time() < deadline:
        try:
            out = subprocess.check_output(
                ["grep", pattern, LOG_FILE], stderr=subprocess.DEVNULL
            ).decode()
        except subprocess.CalledProcessError:
            out = ""
        # last match
        codes = re.findall(rf"{re.escape(pattern)}(\d{{6}})", out)
        if codes:
            return codes[-1]
        time.sleep(0.5)
    raise AssertionError(f"Could not read {prefix} code for {email} from logs")


def full_login(email: str, password: str, admin_code: str | None = None) -> str:
    """Perform captcha -> login -> OTP verify. Returns bearer token."""
    cid, ans = get_captcha()
    body = {"email": email, "password": password, "captcha_id": cid, "captcha_answer": ans}
    if admin_code is not None:
        body["admin_code"] = admin_code
    ts = time.time()
    r = requests.post(f"{API}/auth/login", json=body, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    assert r.json().get("otp_required") is True
    code = read_code_from_log("OTP", email, ts)
    r2 = requests.post(f"{API}/auth/verify-otp", json={"email": email, "code": code}, timeout=30)
    assert r2.status_code == 200, f"verify-otp failed: {r2.status_code} {r2.text}"
    tok = r2.json()["token"]
    assert isinstance(tok, str) and len(tok) > 10
    return tok


# ----------------------------- fixtures -----------------------------
@pytest.fixture(scope="session")
def admin_token():
    return full_login(ADMIN_EMAIL, ADMIN_PASSWORD, admin_code=ADMIN_CODE)


@pytest.fixture(scope="session")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="session")
def candidate_token():
    # Ensure candidate exists. Try login; if fails (unknown), register.
    try:
        return full_login(CANDIDATE_EMAIL, CANDIDATE_PASSWORD)
    except AssertionError:
        cid, ans = get_captcha()
        r = requests.post(f"{API}/auth/register", json={
            "name": "Candidate One", "email": CANDIDATE_EMAIL, "password": CANDIDATE_PASSWORD,
            "captcha_id": cid, "captcha_answer": ans,
        }, timeout=30)
        assert r.status_code == 200, r.text
        return r.json()["token"]


# ----------------------------- Captcha -----------------------------
class TestCaptcha:
    def test_captcha_endpoint(self):
        r = requests.get(f"{API}/auth/captcha", timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert "captcha_id" in d and "question" in d
        assert re.match(r"^\d+ \+ \d+$", d["question"])

    def test_login_wrong_captcha(self):
        cid, ans = get_captcha()
        wrong = str(int(ans) + 1)
        r = requests.post(f"{API}/auth/login", json={
            "email": CANDIDATE_EMAIL, "password": CANDIDATE_PASSWORD,
            "captcha_id": cid, "captcha_answer": wrong,
        }, timeout=30)
        assert r.status_code == 400, r.text


# ----------------------------- Admin login / OTP / admin_code -----------------------------
class TestAdminLogin:
    def test_admin_full_flow(self, admin_token):
        assert admin_token  # login + OTP verify succeeded
        # /auth/me must return admin role
        r = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {admin_token}"}, timeout=30)
        assert r.status_code == 200
        assert r.json().get("role") == "admin"

    def test_admin_wrong_admin_code_blocks(self):
        cid, ans = get_captcha()
        r = requests.post(f"{API}/auth/login", json={
            "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD,
            "captcha_id": cid, "captcha_answer": ans,
            "admin_code": "WRONG-CODE",
        }, timeout=30)
        assert r.status_code == 403, r.text

    def test_admin_missing_admin_code_blocks(self):
        cid, ans = get_captcha()
        r = requests.post(f"{API}/auth/login", json={
            "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD,
            "captcha_id": cid, "captcha_answer": ans,
        }, timeout=30)
        assert r.status_code == 403, r.text


# ----------------------------- Registration + strong password -----------------------------
class TestRegister:
    def test_register_strong(self):
        email = f"test_reg_{uuid.uuid4().hex[:6]}@test.com"
        cid, ans = get_captcha()
        r = requests.post(f"{API}/auth/register", json={
            "name": "Reg Test", "email": email, "password": "Test@2026!",
            "captcha_id": cid, "captcha_answer": ans,
        }, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "token" in d and d["user"]["email"] == email
        assert d["user"]["role"] == "candidate"

    def test_register_weak_password_rejected(self):
        email = f"test_weak_{uuid.uuid4().hex[:6]}@test.com"
        cid, ans = get_captcha()
        r = requests.post(f"{API}/auth/register", json={
            "name": "Weak", "email": email, "password": "abc",
            "captcha_id": cid, "captcha_answer": ans,
        }, timeout=30)
        assert r.status_code == 400, r.text


# ----------------------------- Forgot / Reset password -----------------------------
class TestForgotReset:
    def test_forgot_reset_flow(self):
        # 1) forgot
        cid, ans = get_captcha()
        ts = time.time()
        r = requests.post(f"{API}/auth/forgot-password", json={
            "email": CANDIDATE_EMAIL, "captcha_id": cid, "captcha_answer": ans,
        }, timeout=30)
        assert r.status_code == 200, r.text

        code = read_code_from_log("RESET", CANDIDATE_EMAIL, ts)

        # 2) reset with weak password should fail
        r_weak = requests.post(f"{API}/auth/reset-password", json={
            "email": CANDIDATE_EMAIL, "code": code, "new_password": "abc",
        }, timeout=30)
        assert r_weak.status_code == 400

        # 3) reset with strong password (same Test@2026! to keep credential valid)
        r_ok = requests.post(f"{API}/auth/reset-password", json={
            "email": CANDIDATE_EMAIL, "code": code, "new_password": CANDIDATE_PASSWORD,
        }, timeout=30)
        assert r_ok.status_code == 200, r_ok.text

        # 4) candidate can now login with new password (OTP flow)
        tok = full_login(CANDIDATE_EMAIL, CANDIDATE_PASSWORD)
        assert tok


# ----------------------------- Contracts CRUD -----------------------------
class TestContracts:
    contract_id = None

    def test_create_contract(self, admin_headers):
        r = requests.post(f"{API}/contracts", json={
            "title": "TEST_Contract_A", "client": "Acme", "status": "en_cours",
            "amount": "10000", "start_date": "2026-02-01", "end_date": "2026-08-01",
        }, headers=admin_headers, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["title"] == "TEST_Contract_A"
        assert d["status"] == "en_cours"
        assert "id" in d
        TestContracts.contract_id = d["id"]

    def test_create_contract_invalid_status(self, admin_headers):
        r = requests.post(f"{API}/contracts", json={"title": "TEST_x", "status": "bogus"},
                          headers=admin_headers, timeout=30)
        assert r.status_code == 400

    def test_list_contracts(self, admin_headers):
        r = requests.get(f"{API}/contracts", headers=admin_headers, timeout=30)
        assert r.status_code == 200
        ids = [c["id"] for c in r.json()]
        assert TestContracts.contract_id in ids

    def test_filter_contracts(self, admin_headers):
        r = requests.get(f"{API}/contracts?status=en_cours", headers=admin_headers, timeout=30)
        assert r.status_code == 200
        assert all(c["status"] == "en_cours" for c in r.json())

    def test_update_contract(self, admin_headers):
        r = requests.put(f"{API}/contracts/{TestContracts.contract_id}", json={
            "title": "TEST_Contract_A_upd", "status": "boucle",
        }, headers=admin_headers, timeout=30)
        assert r.status_code == 200
        assert r.json()["status"] == "boucle"

    def test_delete_contract(self, admin_headers):
        r = requests.delete(f"{API}/contracts/{TestContracts.contract_id}", headers=admin_headers, timeout=30)
        assert r.status_code == 200

    def test_contracts_forbidden_for_candidate(self, candidate_token):
        r = requests.get(f"{API}/contracts", headers={"Authorization": f"Bearer {candidate_token}"}, timeout=30)
        assert r.status_code == 403


# ----------------------------- Interviews CRUD -----------------------------
class TestInterviews:
    itw_id = None

    def test_create_interview(self, admin_headers):
        r = requests.post(f"{API}/interviews", json={
            "title": "TEST_Interview_A", "date": "2026-09-15", "time": "10:30",
            "candidate_name": "Candidate One",
        }, headers=admin_headers, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["title"] == "TEST_Interview_A"
        assert d["date"] == "2026-09-15"
        assert d["time"] == "10:30"
        TestInterviews.itw_id = d["id"]

    def test_list_interviews(self, admin_headers):
        r = requests.get(f"{API}/interviews", headers=admin_headers, timeout=30)
        assert r.status_code == 200
        assert any(i["id"] == TestInterviews.itw_id for i in r.json())

    def test_update_interview(self, admin_headers):
        r = requests.put(f"{API}/interviews/{TestInterviews.itw_id}", json={
            "title": "TEST_Interview_A_upd", "date": "2026-09-15", "time": "11:00",
        }, headers=admin_headers, timeout=30)
        assert r.status_code == 200
        assert r.json()["time"] == "11:00"

    def test_delete_interview(self, admin_headers):
        r = requests.delete(f"{API}/interviews/{TestInterviews.itw_id}", headers=admin_headers, timeout=30)
        assert r.status_code == 200


# ----------------------------- Admin stats widgets -----------------------------
class TestStats:
    def test_admin_stats_has_widgets(self, admin_headers):
        r = requests.get(f"{API}/admin/stats", headers=admin_headers, timeout=30)
        assert r.status_code == 200
        d = r.json()
        for k in ["contracts_active", "upcoming_interviews", "jobs", "applications"]:
            assert k in d, f"Missing key {k} in stats"


# ----------------------------- CSV exports -----------------------------
class TestExports:
    def test_export_applications(self, admin_token):
        r = requests.get(f"{API}/export/applications?auth={admin_token}", timeout=30)
        assert r.status_code == 200
        assert "text/csv" in r.headers.get("content-type", "").lower()
        assert "Candidat" in r.text.splitlines()[0]

    def test_export_contracts(self, admin_token):
        r = requests.get(f"{API}/export/contracts?auth={admin_token}", timeout=30)
        assert r.status_code == 200
        assert "text/csv" in r.headers.get("content-type", "").lower()
        assert "Intitule" in r.text.splitlines()[0]

    def test_export_forbidden_without_auth(self):
        r = requests.get(f"{API}/export/applications", timeout=30)
        assert r.status_code == 401


# ----------------------------- Application review + status -----------------------------
class TestApplicationReview:
    def test_review_and_status_flow(self, admin_headers, candidate_token):
        # find an application; if none exists, create one by applying to any active job
        apps = requests.get(f"{API}/applications", headers=admin_headers, timeout=30).json()
        if not apps:
            jobs = requests.get(f"{API}/jobs", timeout=30).json()
            if not jobs:
                pytest.skip("No jobs available to create an application")
            import io as _io
            files = {"cv": ("cv.pdf", _io.BytesIO(b"%PDF-1.4 test cv"), "application/pdf")}
            data = {"job_id": jobs[0]["id"], "cover_note": "TEST review"}
            rr = requests.post(f"{API}/applications", data=data, files=files,
                               headers={"Authorization": f"Bearer {candidate_token}"}, timeout=60)
            assert rr.status_code == 200, rr.text
            app_id = rr.json()["id"]
        else:
            app_id = apps[0]["id"]

        # review
        r = requests.put(f"{API}/applications/{app_id}/review",
                         json={"admin_note": "TEST note", "rating": 4},
                         headers=admin_headers, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("admin_note") == "TEST note"
        assert d.get("rating") == 4

        # persistence: refetch list
        apps2 = requests.get(f"{API}/applications", headers=admin_headers, timeout=30).json()
        target = next(a for a in apps2 if a["id"] == app_id)
        assert target["admin_note"] == "TEST note"
        assert target["rating"] == 4

        # status change (accepted then rejected)
        r2 = requests.put(f"{API}/applications/{app_id}/status", json={"status": "accepted"},
                          headers=admin_headers, timeout=30)
        assert r2.status_code == 200
        assert r2.json()["status"] == "accepted"
        r3 = requests.put(f"{API}/applications/{app_id}/status", json={"status": "rejected"},
                          headers=admin_headers, timeout=30)
        assert r3.status_code == 200
        assert r3.json()["status"] == "rejected"
