"""命盘接口测试：免登录计算、保存、越权 404、笔记、导出、分享。"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.services.export import AI_NOTICE

PASSWORD = "Passw0rd123"


def _signup(client: TestClient) -> dict[str, str]:
    email = f"chart_{uuid.uuid4().hex[:10]}@example.com"
    response = client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _save(client: TestClient, headers: dict[str, str], **overrides: Any) -> dict[str, Any]:
    payload = {
        "birth_datetime": "2001-02-04T15:20:00",
        "timezone": "Asia/Shanghai",
        "gender": "male",
        "time_known": True,
        "convention": {},
        "title": "测试命盘",
    }
    payload.update(overrides)
    response = client.post("/api/v1/charts", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def test_calculate_is_anonymous(client: TestClient) -> None:
    response = client.post(
        "/api/v1/charts/bazi/calculate",
        json={
            "birth_datetime": "2001-02-04T15:20:00",
            "timezone": "Asia/Shanghai",
            "gender": "male",
            "convention": {},
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["domain"] == "bazi"
    assert body["chart_facts"]["pillars"]["day"]["text"]
    assert body["algorithm_version"]
    assert "id" not in body  # 免登录计算不落库
    assert set(body["convention"]) >= {"year_boundary", "day_boundary", "solar_time", "school"}


def test_calculate_echoes_custom_convention(client: TestClient) -> None:
    response = client.post(
        "/api/v1/charts/bazi/calculate",
        json={
            "birth_datetime": "2016-11-30T23:30:00",
            "timezone": "Asia/Shanghai",
            "gender": "male",
            "convention": {"day_boundary": "zi_hour_policy_b", "solar_time": "true_solar_time"},
            "longitude": 116.4,
        },
    )
    assert response.status_code == 200
    convention = response.json()["convention"]
    assert convention["day_boundary"] == "zi_hour_policy_b"
    assert convention["day_boundary_note"]
    assert response.json()["chart_facts"]["solar_time_adjust"]["applied"] is True


def test_calculate_rejects_unknown_convention(client: TestClient) -> None:
    response = client.post(
        "/api/v1/charts/bazi/calculate",
        json={
            "birth_datetime": "2001-02-04T15:20:00",
            "convention": {"day_boundary": "no_such_policy"},
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_calculate_rejects_timezone_aware_input(client: TestClient) -> None:
    response = client.post(
        "/api/v1/charts/bazi/calculate",
        json={"birth_datetime": "2001-02-04T15:20:00+08:00"},
    )
    assert response.status_code == 422


def test_save_requires_login(client: TestClient) -> None:
    response = client.post("/api/v1/charts", json={"birth_datetime": "2001-02-04T15:20:00"})
    assert response.status_code == 401


def test_save_and_read_chart(client: TestClient) -> None:
    headers = _signup(client)
    saved = _save(client, headers, delete_after_days=30)
    assert saved["id"] > 0
    assert saved["domain"] == "bazi"
    assert saved["chart_facts"]["pillars"]["year"]["text"]
    assert saved["triggered_rules"]
    assert saved["source_refs"]

    detail = client.get(f"/api/v1/charts/{saved['id']}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["id"] == saved["id"]

    listing = client.get("/api/v1/charts", headers=headers)
    assert listing.status_code == 200
    page = listing.json()
    assert page["total"] == 1
    assert page["items"][0]["pillars_text"]


def test_save_rejects_client_supplied_chart(client: TestClient) -> None:
    headers = _signup(client)
    response = client.post(
        "/api/v1/charts",
        json={
            "birth_datetime": "2001-02-04T15:20:00",
            "chart_facts": {"pillars": {}},
        },
        headers=headers,
    )
    assert response.status_code == 422  # 客户端盘面一律不采信


def test_cross_user_access_returns_404(client: TestClient) -> None:
    owner = _signup(client)
    chart = _save(client, owner)
    intruder = _signup(client)

    assert client.get(f"/api/v1/charts/{chart['id']}", headers=intruder).status_code == 404
    assert (
        client.patch(f"/api/v1/charts/{chart['id']}", json={"title": "x"}, headers=intruder).status_code == 404
    )
    assert client.delete(f"/api/v1/charts/{chart['id']}", headers=intruder).status_code == 404
    assert client.get(f"/api/v1/charts/{chart['id']}/notes", headers=intruder).status_code == 404
    assert client.get(f"/api/v1/charts/{chart['id']}/export", headers=intruder).status_code == 404
    assert client.post(f"/api/v1/charts/{chart['id']}/share", json={}, headers=intruder).status_code == 404
    # 越权不返回 403，避免用状态码探测资源是否存在
    assert client.get(f"/api/v1/charts/{chart['id']}", headers=intruder).json()["error"]["code"] == "CHART_NOT_FOUND"


def test_patch_chart(client: TestClient) -> None:
    headers = _signup(client)
    chart = _save(client, headers)
    response = client.patch(
        f"/api/v1/charts/{chart['id']}",
        json={"title": "新标题", "visibility": "link", "delete_after_days": 7},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["title"] == "新标题"


def test_delete_chart_is_soft_and_hidden(client: TestClient) -> None:
    headers = _signup(client)
    chart = _save(client, headers)
    assert client.delete(f"/api/v1/charts/{chart['id']}", headers=headers).status_code == 204
    assert client.get(f"/api/v1/charts/{chart['id']}", headers=headers).status_code == 404
    assert client.get("/api/v1/charts", headers=headers).json()["total"] == 0


def test_notes_lifecycle(client: TestClient) -> None:
    headers = _signup(client)
    chart = _save(client, headers)

    created = client.post(f"/api/v1/charts/{chart['id']}/notes", json={"content": "第一条笔记"}, headers=headers)
    assert created.status_code == 201
    note_id = created.json()["id"]

    listing = client.get(f"/api/v1/charts/{chart['id']}/notes", headers=headers)
    assert [item["content"] for item in listing.json()] == ["第一条笔记"]

    assert client.delete(f"/api/v1/charts/{chart['id']}/notes/{note_id}", headers=headers).status_code == 204
    assert client.get(f"/api/v1/charts/{chart['id']}/notes", headers=headers).json() == []


def test_export_carries_ai_notice(client: TestClient) -> None:
    headers = _signup(client)
    chart = _save(client, headers)

    markdown = client.get(f"/api/v1/charts/{chart['id']}/export?format=md", headers=headers)
    assert markdown.status_code == 200
    assert AI_NOTICE.split("。")[0] in markdown.text
    assert "algorithm_version" in markdown.text or "算法版本" in markdown.text
    assert markdown.headers["content-type"].startswith("text/markdown")

    plain = client.get(f"/api/v1/charts/{chart['id']}/export?format=txt", headers=headers)
    assert plain.headers["content-type"].startswith("text/plain")


def test_export_rejects_unknown_format(client: TestClient) -> None:
    headers = _signup(client)
    chart = _save(client, headers)
    assert client.get(f"/api/v1/charts/{chart['id']}/export?format=pdf", headers=headers).status_code == 422


def test_share_flow(client: TestClient) -> None:
    headers = _signup(client)
    chart = _save(client, headers)

    created = client.post(
        f"/api/v1/charts/{chart['id']}/share", json={"expires_in_days": 7}, headers=headers
    )
    assert created.status_code == 201
    token = created.json()["token"]
    assert len(token) >= 24

    preview = client.get(f"/api/v1/share/{token}")
    assert preview.status_code == 200
    body = preview.json()
    assert "dayun" not in body["chart_facts"]  # 脱敏：不含大运
    assert body["pillars_text"]
    assert body["warnings"]

    assert client.delete(f"/api/v1/share/{token}", headers=headers).status_code == 204
    assert client.get(f"/api/v1/share/{token}").status_code == 404


def test_share_token_is_not_stored_in_plaintext(client: TestClient, session) -> None:
    from app.models import ShareLink

    headers = _signup(client)
    chart = _save(client, headers)
    token = client.post(f"/api/v1/charts/{chart['id']}/share", json={}, headers=headers).json()["token"]

    links = session.query(ShareLink).all()
    assert links
    assert token not in {link.token_hash for link in links}
    assert all(len(link.token_hash) == 64 for link in links)


def test_revoke_share_by_other_user_returns_404(client: TestClient) -> None:
    owner = _signup(client)
    chart = _save(client, owner)
    token = client.post(f"/api/v1/charts/{chart['id']}/share", json={}, headers=owner).json()["token"]

    intruder = _signup(client)
    assert client.delete(f"/api/v1/share/{token}", headers=intruder).status_code == 404


@pytest.mark.parametrize("days", [0, 31])
def test_share_expiry_bounds(client: TestClient, days: int) -> None:
    headers = _signup(client)
    chart = _save(client, headers)
    response = client.post(
        f"/api/v1/charts/{chart['id']}/share", json={"expires_in_days": days}, headers=headers
    )
    assert response.status_code == 422
