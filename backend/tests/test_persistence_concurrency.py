from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor


def test_subscription_atomic_writes_keep_50_concurrent_records(tmp_path, monkeypatch):
    from backend.services import subscription_service as module

    monkeypatch.setattr(module, "SUBSCRIPTIONS_FILE", tmp_path / "subscriptions.json")
    service = module.SubscriptionService()

    def write_one(index: int) -> bool:
        return service.subscribe(
            email=f"user{index}@example.invalid",
            ticker="AAPL",
            alert_types=["price_change"],
            price_threshold=5,
        )

    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(write_one, range(50)))

    assert all(results)
    stored = service.get_subscriptions(allow_all=True)
    assert len(stored) == 50


def test_portfolio_sqlite_transactions_keep_50_concurrent_positions(tmp_path, monkeypatch):
    from backend.services import portfolio_store as store

    monkeypatch.setattr(store, "_DB_DIR", tmp_path)
    monkeypatch.setattr(store, "_DB_PATH", tmp_path / "portfolio.db")
    session_id = "private:concurrency:default"

    def write_one(index: int) -> None:
        store.update_position(
            session_id=session_id,
            ticker=f"T{index:02d}",
            shares=index + 1,
            avg_cost=100 + index,
        )

    with ThreadPoolExecutor(max_workers=10) as pool:
        list(pool.map(write_one, range(50)))

    positions = store.get_positions(session_id)
    assert len(positions) == 50
