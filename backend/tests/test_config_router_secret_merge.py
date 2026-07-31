from __future__ import annotations

import pytest


def test_preserve_secret_if_masked_keeps_existing_value():
    from backend.api.config_router import _preserve_secret_if_masked

    assert _preserve_secret_if_masked("sk-***abc", "sk-real-value") == "sk-real-value"
    assert _preserve_secret_if_masked("***", "sk-real-value") == "sk-real-value"
    assert _preserve_secret_if_masked("", "sk-real-value") == "sk-real-value"


def test_preserve_secret_if_masked_accepts_plain_new_value():
    from backend.api.config_router import _preserve_secret_if_masked

    assert _preserve_secret_if_masked("sk-new-value", "sk-old-value") == "sk-new-value"


def test_merge_llm_endpoints_preserves_masked_keys_by_name_and_index():
    from backend.api.config_router import _merge_llm_endpoints

    existing = [
        {"name": "ep-a", "api_key": "key-a", "api_base": "https://a.example.com/v1"},
        {"name": "ep-b", "api_key": "key-b", "api_base": "https://b.example.com/v1"},
    ]
    incoming = [
        {"name": "ep-a", "api_key": "sk-***aaa", "api_base": "https://a.example.com/v1"},
        {"name": "ep-b", "api_key": "", "api_base": "https://b.example.com/v1"},
    ]

    merged = _merge_llm_endpoints(existing, incoming)
    assert isinstance(merged, list)
    assert merged[0]["api_key"] == "key-a"
    assert merged[1]["api_key"] == "key-b"


def test_merge_llm_endpoints_accepts_new_plain_api_key():
    from backend.api.config_router import _merge_llm_endpoints

    existing = [{"name": "ep-a", "api_key": "key-a"}]
    incoming = [{"name": "ep-a", "api_key": "key-new", "api_base": "https://a.example.com/v1"}]

    merged = _merge_llm_endpoints(existing, incoming)
    assert merged[0]["api_key"] == "key-new"


def test_d3_config_save_is_atomic_and_leaves_no_tmp(tmp_path, monkeypatch):
    """D3: save_config 原子写（临时文件+os.replace），成功保存且不残留 .config_*.tmp。"""
    import json

    import backend.api.config_router as cfg

    target = tmp_path / "user_config.json"
    monkeypatch.setattr(cfg, "USER_CONFIG_PATH", str(target))

    from fastapi.testclient import TestClient

    from backend.api.main import app

    with TestClient(app) as client:
        resp = client.post("/api/config", json={"llm_model": "gpt-x", "layout_mode": "wide"})
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    saved = json.loads(target.read_text(encoding="utf-8"))
    assert saved["llm_model"] == "gpt-x"
    assert saved["layout_mode"] == "wide"
    # 原子写不得残留临时文件
    assert list(tmp_path.glob(".config_*")) == []


def test_config_save_rejects_oversized_persisted_inputs(tmp_path, monkeypatch):
    import backend.api.config_router as cfg
    from fastapi.testclient import TestClient

    from backend.api.main import app

    target = tmp_path / "user_config.json"
    monkeypatch.setattr(cfg, "USER_CONFIG_PATH", str(target))

    with TestClient(app) as client:
        endpoints_response = client.post(
            "/api/config",
            json={"llm_endpoints": [{"name": str(index)} for index in range(21)]},
        )
        watchlist_response = client.post(
            "/api/config",
            json={"watchlist": [f"T{index}" for index in range(201)]},
        )
        bytes_response = client.post(
            "/api/config",
            json={"llm_model": "x" * (256 * 1024)},
        )

    assert endpoints_response.status_code == 422
    assert watchlist_response.status_code == 422
    assert bytes_response.status_code == 413
    assert not target.exists()


@pytest.mark.parametrize("corrupt_payload", ["{ not valid json", '{"layout_mode": NaN}'])
def test_get_config_backs_up_corrupt_file(tmp_path, monkeypatch, corrupt_payload):
    import backend.api.config_router as cfg
    from fastapi.testclient import TestClient

    from backend.api.main import app

    target = tmp_path / "user_config.json"
    target.write_text(corrupt_payload, encoding="utf-8")
    monkeypatch.setattr(cfg, "USER_CONFIG_PATH", str(target))

    with TestClient(app) as client:
        response = client.get("/api/config")

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert not target.exists()
    backups = list(tmp_path.glob("user_config.json.*.corrupt"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == corrupt_payload


def test_config_save_rejects_non_finite_values(tmp_path, monkeypatch):
    import backend.api.config_router as cfg
    from fastapi.testclient import TestClient

    from backend.api.main import app

    target = tmp_path / "user_config.json"
    monkeypatch.setattr(cfg, "USER_CONFIG_PATH", str(target))

    with TestClient(app) as client:
        response = client.post(
            "/api/config",
            content='{"layout_mode": NaN}',
            headers={"content-type": "application/json"},
        )

    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid config payload"}
    assert not target.exists()


def test_save_config_backs_up_corrupt_file_before_replacing_it(tmp_path, monkeypatch):
    import json

    import backend.api.config_router as cfg
    from fastapi.testclient import TestClient

    from backend.api.main import app

    target = tmp_path / "user_config.json"
    corrupt_payload = "[[ broken"
    target.write_text(corrupt_payload, encoding="utf-8")
    monkeypatch.setattr(cfg, "USER_CONFIG_PATH", str(target))

    with TestClient(app) as client:
        response = client.post("/api/config", json={"llm_model": "gpt-x"})

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert json.loads(target.read_text(encoding="utf-8"))["llm_model"] == "gpt-x"
    backups = list(tmp_path.glob("user_config.json.*.corrupt"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == corrupt_payload


@pytest.mark.parametrize(
    "corrupt_payload",
    ["{ invalid", "[]", '{"temperature": NaN}'],
)
def test_llm_config_loader_backs_up_corrupt_user_config(
    tmp_path, monkeypatch, caplog, corrupt_payload
):
    import logging

    import backend.llm_config as llm_config

    target = tmp_path / "user_config.json"
    target.write_text(corrupt_payload, encoding="utf-8")
    monkeypatch.setattr(llm_config, "USER_CONFIG_PATH", str(target))

    with caplog.at_level(logging.WARNING, logger="backend.llm_config"):
        assert llm_config._load_user_config() == {}

    assert not target.exists()
    backups = list(tmp_path.glob("user_config.json.*.corrupt"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == corrupt_payload
    assert corrupt_payload not in caplog.text
