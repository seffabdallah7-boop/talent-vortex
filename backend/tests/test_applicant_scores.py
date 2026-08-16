"""Tests for GET /api/jobs/{job_id}/applicant-scores and /suggestions with cv_data enrichment."""
import os
import re
import requests
import pytest

def _read_frontend_env():
    try:
        with open("/app/frontend/.env") as f:
            for ln in f:
                if ln.startswith("REACT_APP_BACKEND_URL="):
                    return ln.split("=", 1)[1].strip()
    except Exception:
        pass
    return None

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or _read_frontend_env() or "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL not configured"
ADMIN_EMAIL = "seffabdallah7@gmail.com"
ADMIN_PWD = "Admin@2026!"
CANDIDATE_EMAIL = "candidate_test@talentvortex.com"
CANDIDATE_PWD = "Candidate@2026!"


def _login(email, password):
    s = requests.Session()
    cap = s.get(f"{BASE_URL}/api/auth/captcha", timeout=15).json()
    # captcha is math like "3 + 4"
    q = cap.get("question") or cap.get("challenge") or cap.get("q") or ""
    m = re.match(r"\s*(\d+)\s*([\+\-\*])\s*(\d+)", q)
    assert m, f"Unexpected captcha shape: {cap}"
    a, op, b = int(m.group(1)), m.group(2), int(m.group(3))
    ans = {"+": a + b, "-": a - b, "*": a * b}[op]
    r = s.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password, "captcha_id": cap["captcha_id"], "captcha_answer": str(ans)},
        timeout=15,
    )
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    tok = r.json()["token"]
    s.headers.update({"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def admin():
    return _login(ADMIN_EMAIL, ADMIN_PWD)


@pytest.fixture(scope="module")
def candidate():
    try:
        return _login(CANDIDATE_EMAIL, CANDIDATE_PWD)
    except AssertionError:
        pytest.skip("candidate account not available")


@pytest.fixture(scope="module")
def a_job_with_apps(admin):
    """Find a job that has at least one application."""
    jobs = admin.get(f"{BASE_URL}/api/jobs", timeout=15).json()
    assert isinstance(jobs, list) and jobs, "no jobs"
    apps = admin.get(f"{BASE_URL}/api/applications", timeout=15).json()
    assert isinstance(apps, list)
    job_ids_with_apps = {a["job_id"] for a in apps if a.get("job_id")}
    for j in jobs:
        if j["id"] in job_ids_with_apps:
            return j
    pytest.skip("no job has applications")


@pytest.fixture(scope="module")
def a_job_without_apps(admin):
    jobs = admin.get(f"{BASE_URL}/api/jobs", timeout=15).json()
    apps = admin.get(f"{BASE_URL}/api/applications", timeout=15).json()
    job_ids_with_apps = {a["job_id"] for a in apps if a.get("job_id")}
    for j in jobs:
        if j["id"] not in job_ids_with_apps:
            return j
    pytest.skip("all jobs have applications")


# ------------------ /applicant-scores ------------------
class TestApplicantScores:
    def test_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/jobs/anything/applicant-scores", timeout=15)
        assert r.status_code in (401, 403), r.status_code

    def test_forbidden_for_candidate(self, candidate, a_job_with_apps):
        r = candidate.get(f"{BASE_URL}/api/jobs/{a_job_with_apps['id']}/applicant-scores", timeout=15)
        assert r.status_code == 403, r.status_code

    def test_404_unknown_job(self, admin):
        r = admin.get(f"{BASE_URL}/api/jobs/nonexistent_job_xyz/applicant-scores", timeout=30)
        assert r.status_code == 404

    def test_empty_when_no_applications(self, admin, a_job_without_apps):
        r = admin.get(f"{BASE_URL}/api/jobs/{a_job_without_apps['id']}/applicant-scores", timeout=30)
        assert r.status_code == 200
        assert r.json() == {}

    def test_scores_shape(self, admin, a_job_with_apps):
        r = admin.get(f"{BASE_URL}/api/jobs/{a_job_with_apps['id']}/applicant-scores", timeout=60)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, dict) and len(data) > 0
        for cid, v in data.items():
            assert isinstance(cid, str)
            assert isinstance(v, dict)
            assert "score" in v and "reason" in v
            assert isinstance(v["score"], int)
            assert 0 <= v["score"] <= 100
            assert isinstance(v["reason"], str)


# ------------------ /suggestions ------------------
class TestJobSuggestions:
    def test_requires_admin(self, candidate, a_job_with_apps):
        r = candidate.get(f"{BASE_URL}/api/jobs/{a_job_with_apps['id']}/suggestions", timeout=15)
        assert r.status_code == 403

    def test_404_unknown_job(self, admin):
        r = admin.get(f"{BASE_URL}/api/jobs/nonexistent_job_xyz/suggestions", timeout=30)
        assert r.status_code == 404

    def test_suggestions_shape(self, admin, a_job_with_apps):
        r = admin.get(f"{BASE_URL}/api/jobs/{a_job_with_apps['id']}/suggestions", timeout=90)
        assert r.status_code == 200
        arr = r.json()
        assert isinstance(arr, list)
        if arr:
            item = arr[0]
            for k in ("candidate_id", "name", "score", "reason", "domains"):
                assert k in item, f"missing {k}"
            assert 0 <= item["score"] <= 100
            # sorted desc
            scores = [x["score"] for x in arr]
            assert scores == sorted(scores, reverse=True)
