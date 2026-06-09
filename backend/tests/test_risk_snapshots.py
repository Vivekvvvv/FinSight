# -*- coding: utf-8 -*-
"""测试 Risk Snapshots 存储功能"""
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.services.risk_snapshots import (
    save_risk_snapshot,
    get_risk_snapshots_history,
    get_latest_snapshot,
)


def test_save_and_retrieve_snapshot():
    """测试保存和检索快照"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_snapshots.db"

        # 构造测试数据
        risk_data = {
            "success": True,
            "as_of": datetime.now(timezone.utc).isoformat(),
            "risk_score": 45,
            "total_value": 10000,
            "total_cost": 9500,
            "concentration_risk": [{"id": "risk_1", "severity": "high"}],
            "loss_positions": [],
            "stale_research": [],
            "missing_coverage": [],
            "sector_exposure": [],
            "currency_exposure": [],
            "market_exposure": [],
            "next_actions": [],
        }

        # 保存快照
        save_risk_snapshot(
            session_id="test_session",
            user_id="test_user",
            risk_lens_data=risk_data,
            snapshot_date="2026-06-01",
            db_path=db_path,
        )

        # 检索历史
        history = get_risk_snapshots_history(
            session_id="test_session",
            user_id="test_user",
            days=7,
            db_path=db_path,
        )

        assert len(history) == 1
        assert history[0]["snapshot_date"] == "2026-06-01"
        assert history[0]["risk_score"] == 45
        assert history[0]["total_value"] == 10000
        assert history[0]["concentration_risk_count"] == 1


def test_multiple_snapshots_ordering():
    """测试多个快照按日期升序排列"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_snapshots.db"

        base_date = datetime(2026, 6, 1, tzinfo=timezone.utc)

        # 保存 5 天的快照
        for i in range(5):
            snapshot_date = (base_date + timedelta(days=i)).strftime("%Y-%m-%d")
            risk_data = {
                "success": True,
                "risk_score": 10 + i * 10,
                "total_value": 1000 + i * 100,
                "total_cost": 1000,
                "concentration_risk": [],
                "loss_positions": [],
                "stale_research": [],
                "missing_coverage": [],
            }

            save_risk_snapshot(
                session_id="test_session",
                user_id="test_user",
                risk_lens_data=risk_data,
                snapshot_date=snapshot_date,
                db_path=db_path,
            )

        # 检索历史（应按日期升序）
        history = get_risk_snapshots_history(
            session_id="test_session",
            user_id="test_user",
            days=10,
            db_path=db_path,
        )

        assert len(history) == 5
        assert history[0]["snapshot_date"] == "2026-06-01"
        assert history[4]["snapshot_date"] == "2026-06-05"
        assert history[0]["risk_score"] == 10
        assert history[4]["risk_score"] == 50


def test_get_latest_snapshot():
    """测试获取最新快照完整数据"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_snapshots.db"

        # 保存 2 个快照
        for i, date in enumerate(["2026-06-01", "2026-06-03"]):
            risk_data = {
                "success": True,
                "risk_score": 20 + i * 10,
                "total_value": 2000,
                "total_cost": 1800,
                "concentration_risk": [{"id": f"risk_{i}"}],
                "loss_positions": [],
                "stale_research": [],
                "missing_coverage": [],
            }

            save_risk_snapshot(
                session_id="test_session",
                user_id="test_user",
                risk_lens_data=risk_data,
                snapshot_date=date,
                db_path=db_path,
            )

        # 获取最新快照
        latest = get_latest_snapshot(
            session_id="test_session",
            user_id="test_user",
            db_path=db_path,
        )

        assert latest is not None
        assert latest["snapshot_date"] == "2026-06-03"
        assert latest["data"]["risk_score"] == 30
        assert len(latest["data"]["concentration_risk"]) == 1
        assert latest["data"]["concentration_risk"][0]["id"] == "risk_1"


def test_snapshot_upsert():
    """测试同一天多次保存会覆盖"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_snapshots.db"

        risk_data_v1 = {
            "success": True,
            "risk_score": 30,
            "total_value": 5000,
            "total_cost": 4800,
            "concentration_risk": [],
            "loss_positions": [],
            "stale_research": [],
            "missing_coverage": [],
        }

        risk_data_v2 = {
            "success": True,
            "risk_score": 40,
            "total_value": 6000,
            "total_cost": 5800,
            "concentration_risk": [{"id": "new_risk"}],
            "loss_positions": [],
            "stale_research": [],
            "missing_coverage": [],
        }

        # 第一次保存
        save_risk_snapshot(
            session_id="test_session",
            user_id="test_user",
            risk_lens_data=risk_data_v1,
            snapshot_date="2026-06-01",
            db_path=db_path,
        )

        # 第二次保存（同一天）
        save_risk_snapshot(
            session_id="test_session",
            user_id="test_user",
            risk_lens_data=risk_data_v2,
            snapshot_date="2026-06-01",
            db_path=db_path,
        )

        # 应该只有 1 条记录，且为最新数据
        history = get_risk_snapshots_history(
            session_id="test_session",
            user_id="test_user",
            days=7,
            db_path=db_path,
        )

        assert len(history) == 1
        assert history[0]["risk_score"] == 40
        assert history[0]["total_value"] == 6000
        assert history[0]["concentration_risk_count"] == 1


def test_no_snapshots_returns_empty():
    """测试无快照时返回空列表"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_snapshots.db"

        history = get_risk_snapshots_history(
            session_id="nonexistent_session",
            user_id="test_user",
            days=7,
            db_path=db_path,
        )

        assert history == []

        latest = get_latest_snapshot(
            session_id="nonexistent_session",
            user_id="test_user",
            db_path=db_path,
        )

        assert latest is None


def test_session_isolation():
    """测试不同 session 的快照互不干扰"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_snapshots.db"

        # Session A 的快照
        save_risk_snapshot(
            session_id="session_a",
            user_id="user_a",
            risk_lens_data={"success": True, "risk_score": 10, "total_value": 1000, "total_cost": 1000, "concentration_risk": [], "loss_positions": [], "stale_research": [], "missing_coverage": []},
            snapshot_date="2026-06-01",
            db_path=db_path,
        )

        # Session B 的快照
        save_risk_snapshot(
            session_id="session_b",
            user_id="user_b",
            risk_lens_data={"success": True, "risk_score": 20, "total_value": 2000, "total_cost": 2000, "concentration_risk": [], "loss_positions": [], "stale_research": [], "missing_coverage": []},
            snapshot_date="2026-06-01",
            db_path=db_path,
        )

        # Session A 查询
        history_a = get_risk_snapshots_history(
            session_id="session_a",
            user_id="user_a",
            days=7,
            db_path=db_path,
        )

        # Session B 查询
        history_b = get_risk_snapshots_history(
            session_id="session_b",
            user_id="user_b",
            days=7,
            db_path=db_path,
        )

        assert len(history_a) == 1
        assert len(history_b) == 1
        assert history_a[0]["risk_score"] == 10
        assert history_b[0]["risk_score"] == 20
