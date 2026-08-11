"""Phase E — Calls signaling + Recordings upload+AI pipeline tests."""
import io
import time
import uuid

import pytest
import requests

from backend_test import (
    API,
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    full_login,
    get_captcha,
)


@pytest.fixture(scope="module")
def admin_token():
    return full_login(ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="module")
def candidate():
    email = f"test_e_{uuid.uuid4().hex[:8]}@test.com"
    cid, ans = get_captcha()
    r = requests.post(f"{API}/auth/register", json={
        "name": "TEST E Cand", "email": email, "password": "Test@2026!",
        "captcha_id": cid, "captcha_answer": ans,
    }, timeout=30)
    assert r.status_code == 200, r.text
    tok = r.json()["token"]
    uid = r.json()["user"]["user_id"]
    return {"token": tok, "user_id": uid, "email": email,
            "headers": {"Authorization": f"Bearer {tok}"}}


# ============================ Calls signaling ============================
class TestCalls:
    def test_admin_start_call_creates_ringing(self, admin_headers, candidate):
        r = requests.post(f"{API}/calls",
                          json={"callee_id": candidate["user_id"], "mode": "video"},
                          headers=admin_headers, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["status"] == "ringing"
        assert data["callee_id"] == candidate["user_id"]
        assert data["mode"] == "video"
        assert data["room"].startswith("recrutai-call-")
        assert "id" in data
        pytest.call_id = data["id"]

    def test_candidate_gets_incoming(self, candidate):
        r = requests.get(f"{API}/calls/incoming", headers=candidate["headers"], timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert data.get("id") == pytest.call_id
        assert data.get("status") == "ringing"

    def test_accept_call(self, candidate):
        r = requests.put(f"{API}/calls/{pytest.call_id}/status",
                         json={"status": "accepted"},
                         headers=candidate["headers"], timeout=30)
        assert r.status_code == 200
        assert r.json()["status"] == "accepted"

    def test_incoming_empty_after_accept(self, candidate):
        r = requests.get(f"{API}/calls/incoming", headers=candidate["headers"], timeout=30)
        assert r.status_code == 200
        assert r.json() == {}

    def test_start_call_unknown_callee_404(self, admin_headers):
        r = requests.post(f"{API}/calls",
                          json={"callee_id": "does-not-exist", "mode": "video"},
                          headers=admin_headers, timeout=30)
        assert r.status_code == 404

    def test_invalid_status_400(self, admin_headers, candidate):
        # Create a fresh call
        r = requests.post(f"{API}/calls",
                          json={"callee_id": candidate["user_id"], "mode": "audio"},
                          headers=admin_headers, timeout=30)
        cid = r.json()["id"]
        r2 = requests.put(f"{API}/calls/{cid}/status",
                          json={"status": "bogus"},
                          headers=admin_headers, timeout=30)
        assert r2.status_code == 400
        # Cleanup: end it
        requests.put(f"{API}/calls/{cid}/status",
                     json={"status": "ended"},
                     headers=admin_headers, timeout=30)


# ============================ Recordings pipeline ============================
class TestRecordings:
    def test_upload_recording_and_process(self, admin_headers, candidate):
        # Minimal fake webm bytes (endpoint accepts any file); transcription will just return ""
        vbytes = b"\x1a\x45\xdf\xa3" + b"\x00" * 512  # tiny stub
        files = {
            "video": ("test.webm", io.BytesIO(vbytes), "video/webm"),
        }
        data = {
            "title": "TEST_E recording",
            "candidate_id": candidate["user_id"],
            "candidate_name": "TEST E Cand",
        }
        r = requests.post(f"{API}/recordings", files=files, data=data,
                          headers=admin_headers, timeout=60)
        assert r.status_code == 200, r.text
        rec = r.json()
        assert rec["status"] == "processing"
        assert rec["candidate_id"] == candidate["user_id"]
        assert rec["video_file_id"]
        assert "id" in rec
        pytest.rec_id = rec["id"]
        pytest.video_file_id = rec["video_file_id"]

    def test_video_file_retrievable(self, admin_headers):
        # /api/files/<id> should serve the uploaded video
        r = requests.get(f"{API}/files/{pytest.video_file_id}",
                         headers=admin_headers, timeout=30, allow_redirects=True)
        # Accept either 200 with bytes, or redirect (some setups redirect to presigned URL)
        assert r.status_code in (200, 302, 307), f"Got {r.status_code}: {r.text[:200]}"

    def test_list_recordings_contains_new(self, admin_headers):
        r = requests.get(f"{API}/recordings", headers=admin_headers, timeout=30)
        assert r.status_code == 200
        items = r.json()
        ids = [x["id"] for x in items]
        assert pytest.rec_id in ids

    def test_recording_reaches_done(self, admin_headers):
        # Poll up to 60s for status transition processing -> done
        deadline = time.time() + 60
        final_status = None
        while time.time() < deadline:
            r = requests.get(f"{API}/recordings", headers=admin_headers, timeout=30)
            items = r.json()
            rec = next((x for x in items if x["id"] == pytest.rec_id), None)
            assert rec is not None
            final_status = rec["status"]
            if final_status == "done":
                break
            time.sleep(2)
        assert final_status == "done", f"Recording did not reach 'done'; last status={final_status}"

    def test_delete_recording(self, admin_headers):
        r = requests.delete(f"{API}/recordings/{pytest.rec_id}", headers=admin_headers, timeout=30)
        assert r.status_code == 200
        # Verify removed
        r2 = requests.get(f"{API}/recordings", headers=admin_headers, timeout=30)
        ids = [x["id"] for x in r2.json()]
        assert pytest.rec_id not in ids

    def test_recordings_requires_admin(self, candidate):
        r = requests.get(f"{API}/recordings", headers=candidate["headers"], timeout=30)
        assert r.status_code in (401, 403)
