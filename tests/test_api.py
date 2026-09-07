from pathlib import Path

from fastapi.testclient import TestClient

from services.control_api.app import create_app
from services.security import ReviewTokenVerifier
from services.storage import InMemoryStore

ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK = (ROOT / "agent" / "fixtures" / "benefits-playbook.md").read_text()


def client(monkeypatch) -> tuple[TestClient, InMemoryStore]:
    monkeypatch.setenv("REVIEW_TOKEN", "review-demo")
    store = InMemoryStore(playbook=PLAYBOOK)
    return TestClient(create_app(store, ReviewTokenVerifier())), store


def test_public_reads_and_protected_actions(monkeypatch) -> None:
    api, _ = client(monkeypatch)
    assert api.get("/api/health").status_code == 200
    assert api.get("/api/targets").status_code == 200
    assert api.post("/api/runs", json={"target_id": "benefits-demo"}).status_code == 401


def test_demo_scan_and_approval(monkeypatch) -> None:
    api, store = client(monkeypatch)
    headers = {"X-Review-Token": "review-demo"}
    switched = api.post(
        "/api/demo/version",
        headers=headers,
        json={"target_id": "benefits-demo", "version": "v2"},
    )
    assert switched.status_code == 200
    result = api.post(
        "/api/runs",
        headers=headers,
        json={"target_id": "benefits-demo", "idempotency_key": "acceptance"},
    )
    assert result.status_code == 200
    payload = result.json()
    assert payload["run"]["status"] == "SUCCEEDED"
    assert len(payload["findings"]) == 3

    finding_id = payload["findings"][0]["finding_id"]
    approved = api.post(
        f"/api/findings/{finding_id}/decision",
        headers=headers,
        json={"action": "APPROVE", "note": "Evidence checked."},
    )
    assert approved.status_code == 200
    artifact_key = approved.json()["approved_artifact_key"]
    assert artifact_key in store.artifacts
    assert "not published automatically" in store.artifacts[artifact_key]
    assert store.get_finding(finding_id).approved_artifact_key == artifact_key

    second_decision = api.post(
        f"/api/findings/{finding_id}/decision",
        headers=headers,
        json={"action": "REJECT", "note": "Too late."},
    )
    assert second_decision.status_code == 409

    repeated = api.post(
        "/api/runs",
        headers=headers,
        json={"target_id": "benefits-demo", "idempotency_key": "acceptance-repeat"},
    )
    assert repeated.status_code == 200
    assert len(repeated.json()["findings"]) == 0
    assert store.get_finding(finding_id).status == "APPROVED"


def test_idempotency_does_not_duplicate_runs(monkeypatch) -> None:
    api, _ = client(monkeypatch)
    headers = {"X-Review-Token": "review-demo"}
    body = {"target_id": "benefits-demo", "idempotency_key": "same-request"}
    first = api.post("/api/runs", headers=headers, json=body)
    second = api.post("/api/runs", headers=headers, json=body)
    assert first.status_code == second.status_code == 200
    assert first.json()["run"]["run_id"] == second.json()["run"]["run_id"]


def test_approval_storage_failure_rolls_back_to_open(monkeypatch) -> None:
    api, store = client(monkeypatch)
    headers = {"X-Review-Token": "review-demo"}
    api.post(
        "/api/demo/version",
        headers=headers,
        json={"target_id": "benefits-demo", "version": "v2"},
    )
    result = api.post("/api/runs", headers=headers, json={"target_id": "benefits-demo"})
    finding_id = result.json()["findings"][0]["finding_id"]

    def fail_write(_finding):
        raise OSError("simulated S3 outage")

    monkeypatch.setattr(store, "write_approved_artifact", fail_write)
    response = api.post(
        f"/api/findings/{finding_id}/decision",
        headers=headers,
        json={"action": "APPROVE", "note": "Checked."},
    )
    assert response.status_code == 502
    assert store.get_finding(finding_id).status == "OPEN"
