from __future__ import annotations

from types import SimpleNamespace

from scripts import seed_local_usage_data


def test_seed_portfolio_preserves_existing_positions(monkeypatch):
    updates: list[str] = []

    monkeypatch.setattr(
        seed_local_usage_data,
        "get_positions",
        lambda _session_id: [{"ticker": "aapl", "shares": 3, "avg_cost": 99.0}],
    )
    monkeypatch.setattr(
        seed_local_usage_data,
        "update_position",
        lambda _session_id, **position: updates.append(position["ticker"]),
    )
    monkeypatch.setattr(seed_local_usage_data, "list_suggestions", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(seed_local_usage_data, "save_suggestion", lambda *_args, **_kwargs: None)

    seed_local_usage_data.seed_portfolio()

    assert "AAPL" not in updates
    assert updates == ["MSFT", "NVDA", "600519.SS", "0700.HK"]


def test_seed_portfolio_preserves_existing_suggestion(monkeypatch):
    saved: list[str] = []

    monkeypatch.setattr(seed_local_usage_data, "get_positions", lambda _session_id: [])
    monkeypatch.setattr(seed_local_usage_data, "update_position", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        seed_local_usage_data,
        "list_suggestions",
        lambda *_args, **_kwargs: [{"suggestion_id": "seed_rebalance_20260630"}],
    )
    monkeypatch.setattr(
        seed_local_usage_data,
        "save_suggestion",
        lambda suggestion_id, *_args, **_kwargs: saved.append(suggestion_id),
    )

    seed_local_usage_data.seed_portfolio()

    assert saved == []


def test_seed_watchlist_preserves_existing_items_and_preferences(monkeypatch):
    added: list[str] = []
    preferences: list[tuple[str, object]] = []

    class FakeMemory:
        def get_user_profile(self, _user_id):
            return SimpleNamespace(
                watchlist=["aapl"],
                preferences={"default_symbol": "WDC"},
            )

        def add_to_watchlist(self, _user_id, ticker, **_metadata):
            added.append(ticker)

        def set_preference(self, _user_id, key, value):
            preferences.append((key, value))

    monkeypatch.setattr(seed_local_usage_data, "MemoryService", FakeMemory)

    seed_local_usage_data.seed_watchlist()

    assert "AAPL" not in added
    assert added == ["MSFT", "NVDA", "600519.SS", "0700.HK", "9988.HK"]
    assert ("default_symbol", "AAPL") not in preferences
    assert preferences == [
        ("market_focus", ["US", "CN", "HK"]),
        ("risk_style", "balanced"),
    ]


def test_seed_subscriptions_does_not_duplicate_seed_alert(monkeypatch):
    recorded: list[str] = []

    class FakeSubscriptionService:
        def get_subscriptions(self, *, email):
            return [{"ticker": "NVDA"}]

        def subscribe(self, *_args, **_kwargs):
            return True

        def list_alert_events(self, _email, *, limit):
            assert limit == 50
            return [{
                "ticker": "NVDA",
                "event_type": "price_change",
                "metadata": {"source": "local_seed"},
            }]

        def record_alert_event(self, _email, ticker, *_args, **_kwargs):
            recorded.append(ticker)

    monkeypatch.setattr(seed_local_usage_data, "SubscriptionService", FakeSubscriptionService)

    seed_local_usage_data.seed_subscriptions()

    assert recorded == []


def test_seed_subscriptions_preserves_existing_subscription_settings(monkeypatch):
    subscribed: list[str] = []

    class FakeSubscriptionService:
        def get_subscriptions(self, *, email):
            assert email == seed_local_usage_data.EMAIL
            return [{"ticker": "nvda", "price_threshold": 9.0}]

        def subscribe(self, _email, ticker, _alert_types, **_options):
            subscribed.append(ticker)

        def list_alert_events(self, _email, *, limit):
            return [{
                "ticker": "NVDA",
                "event_type": "price_change",
                "metadata": {"source": "local_seed"},
            }]

        def record_alert_event(self, *_args, **_kwargs):
            raise AssertionError("existing seed alert must not be duplicated")

    monkeypatch.setattr(seed_local_usage_data, "SubscriptionService", FakeSubscriptionService)

    seed_local_usage_data.seed_subscriptions()

    assert subscribed == ["AAPL", "600519.SS"]


def test_seed_reports_preserves_existing_seed_reports(monkeypatch):
    upserted: list[str] = []

    class FakeReportStore:
        def list_reports(self, **kwargs):
            assert kwargs["include_blocked"] is True
            return [{"report_id": "seed_report_aapl_quality_202606"}]

        def upsert_report(self, *, session_id, report, include_blocked):
            assert session_id == seed_local_usage_data.SESSION_ID
            assert include_blocked is True
            upserted.append(report["report_id"])

    monkeypatch.setattr(seed_local_usage_data, "ReportIndexStore", FakeReportStore)

    seed_local_usage_data.seed_reports()

    assert upserted == [
        "seed_report_msft_ai_cloud_202606",
        "seed_report_cn_hk_watch_202606",
    ]


def test_seed_report_is_clearly_labeled_as_sample_data():
    report = seed_local_usage_data.report_payload(
        "seed_report_test",
        "AAPL",
        "质量复盘",
        "仅用于界面展示。",
        ["示例"],
        0.8,
        -1,
    )

    assert report["title"] == "[本地示例] 质量复盘"
    assert report["summary"].startswith("本地示例数据：")
    assert report["source_type"] == "local_seed"
    assert report["meta"]["source_type"] == "local_seed"
    assert all("example.invalid" in citation["url"] for citation in report["citations"])


def test_seed_notes_checks_all_pages_before_creating(monkeypatch):
    first_page = [{"title": f"existing-{index}"} for index in range(200)]
    seed_title = "AAPL 服务收入复查"
    created: list[str] = []
    offsets: list[int] = []

    def fake_list_notes(_session_id, _user_id, *, limit, offset):
        assert limit == 200
        offsets.append(offset)
        return first_page if offset == 0 else [{"title": seed_title}]

    monkeypatch.setattr(seed_local_usage_data, "list_notes", fake_list_notes)
    monkeypatch.setattr(
        seed_local_usage_data,
        "create_note",
        lambda _session_id, _user_id, *, title, **_kwargs: created.append(title),
    )

    seed_local_usage_data.seed_notes()

    assert offsets == [0, 200]
    assert seed_title not in created
    assert len(created) == 3
