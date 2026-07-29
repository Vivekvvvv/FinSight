import builtins
import logging

from backend import llm_config


def test_load_user_config_error_log_is_redacted(monkeypatch, caplog):
    secret = "PRIVATE_CONFIG_ERROR_SENTINEL"
    caplog.set_level(logging.INFO, logger=llm_config.__name__)

    def fail_open(*_args, **_kwargs):
        raise OSError(secret)

    monkeypatch.setattr(llm_config.os.path, "exists", lambda _path: True)
    monkeypatch.setattr(builtins, "open", fail_open)

    assert llm_config._load_user_config() == {}
    assert secret not in caplog.text
    assert "OSError" in caplog.text
