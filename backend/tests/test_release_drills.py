from __future__ import annotations

from pathlib import Path

import pytest

from backend.services.release_drills import (
    RollbackThresholds,
    RolloutStageMetrics,
    evaluate_rollout_thresholds,
    run_report_index_rollback_rehearsal,
    simulate_llm_endpoint_failover_drill,
)


def test_evaluate_rollout_thresholds_passes_when_all_metrics_within_limits():
    result = evaluate_rollout_thresholds(
        stages=[
            RolloutStageMetrics(10, 10, 10, 0, 120.0, 80.0),
            RolloutStageMetrics(50, 50, 50, 0, 180.0, 110.0),
            RolloutStageMetrics(100, 100, 100, 1, 220.0, 130.0),
        ],
        citation_coverage=0.98,
        thresholds=RollbackThresholds(max_5xx_ratio=0.02, p95_regression_factor=2.0, min_citation_coverage=0.95),
    )

    assert result["pass"] is True
    assert result["rollback_triggered"] is False
    assert result["rollback_stage_percent"] is None


def test_evaluate_rollout_thresholds_triggers_rollback_on_5xx_and_citation():
    result = evaluate_rollout_thresholds(
        stages=[
            RolloutStageMetrics(10, 10, 10, 0, 100.0, 60.0),
            RolloutStageMetrics(50, 50, 47, 3, 190.0, 120.0),
        ],
        citation_coverage=0.90,
        thresholds=RollbackThresholds(max_5xx_ratio=0.02, p95_regression_factor=2.0, min_citation_coverage=0.95),
    )

    assert result["pass"] is False
    assert result["rollback_triggered"] is True
    assert result["rollback_stage_percent"] == 10

    stage_10 = [s for s in result["stages"] if s["stage_percent"] == 10][0]
    assert stage_10["pass_stage"] is False
    assert any("citation_coverage_below_threshold" in reason for reason in stage_10["rollback_reasons"])

    stage_50 = [s for s in result["stages"] if s["stage_percent"] == 50][0]
    assert stage_50["pass_stage"] is False
    assert any("5xx_ratio_exceeded" in reason for reason in stage_50["rollback_reasons"])
    assert any("citation_coverage_below_threshold" in reason for reason in stage_50["rollback_reasons"])


@pytest.mark.parametrize(
    ("stages", "coverage", "thresholds", "field"),
    [
        ([RolloutStageMetrics(10, 10, 10, 0, 100.0)], float("nan"), None, "citation_coverage"),
        ([RolloutStageMetrics(10, 10, 10, 0, float("inf"))], 1.0, None, "latency_p95_ms"),
        ([RolloutStageMetrics(10, 10, 10, 0, 100.0, float("-inf"))], 1.0, None, "latency_mean_ms"),
        (
            [RolloutStageMetrics(10, 10, 10, 0, 100.0)],
            1.0,
            RollbackThresholds(max_5xx_ratio=float("inf")),
            "max_5xx_ratio",
        ),
    ],
)
def test_evaluate_rollout_thresholds_rejects_non_finite_metrics(
    stages, coverage, thresholds, field
):
    with pytest.raises(ValueError, match=field):
        evaluate_rollout_thresholds(
            stages=stages,
            citation_coverage=coverage,
            thresholds=thresholds,
        )


@pytest.mark.parametrize(
    ("stage", "field"),
    [
        (RolloutStageMetrics(0, 10, 10, 0, 100.0), "stage_percent"),
        (RolloutStageMetrics(10, 0, 0, 0, 100.0), "request_count"),
        (RolloutStageMetrics(10, 10, 11, 0, 100.0), "success_count"),
        (RolloutStageMetrics(10, 10, 9, 11, 100.0), "error_5xx_count"),
        (RolloutStageMetrics(10, True, 1, 0, 100.0), "counts"),
    ],
)
def test_evaluate_rollout_thresholds_rejects_invalid_stage_counts(stage, field):
    with pytest.raises(ValueError, match=field):
        evaluate_rollout_thresholds(stages=[stage], citation_coverage=1.0)


def test_run_report_index_rollback_rehearsal_restores_snapshot(tmp_path: Path):
    result = run_report_index_rollback_rehearsal(work_dir=tmp_path)

    assert result["pass"] is True
    assert result["verification"]["pass_data_restore"] is True
    assert result["verification"]["pass_schema_rollback"] is True


def test_simulate_llm_endpoint_failover_drill_passes():
    result = simulate_llm_endpoint_failover_drill()

    assert result["pass"] is True
    assert result["pass_failover"] is True
    assert result["pass_recovery"] is True
    assert result["selected_after_primary_failure"] == "backup"


def test_write_json_atomic_no_tmp_leftover(tmp_path: Path):
    """审计 D4：证据落盘走临时文件+replace，不留 .tmp 残留，覆盖写同样干净。"""
    import json

    from backend.services.release_drills import write_json

    out = tmp_path / "evidence" / "drill.json"
    write_json(out, {"pass": True})
    assert json.loads(out.read_text(encoding="utf-8"))["pass"] is True
    assert not list(out.parent.glob("*.tmp"))

    write_json(out, {"pass": False})
    assert json.loads(out.read_text(encoding="utf-8"))["pass"] is False
    assert not list(out.parent.glob("*.tmp"))


def test_write_json_preserves_existing_file_on_replace_failure(tmp_path: Path, monkeypatch):
    import json

    from backend.services import release_drills
    from backend.services.release_drills import write_json

    out = tmp_path / "result.json"
    out.write_text('{"pass": true}', encoding="utf-8")

    def fail_replace(_source, _target):
        raise OSError("replace failed")

    monkeypatch.setattr(release_drills.os, "replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        write_json(out, {"pass": False})

    assert json.loads(out.read_text(encoding="utf-8"))["pass"] is True
    assert not list(tmp_path.glob("*.tmp"))


def test_write_json_rejects_non_finite_payload_without_overwriting(tmp_path: Path):
    from backend.services.release_drills import write_json

    out = tmp_path / "result.json"
    out.write_text('{"pass": true}', encoding="utf-8")

    with pytest.raises(ValueError, match="Out of range float values"):
        write_json(out, {"metric": float("nan")})

    assert out.read_text(encoding="utf-8") == '{"pass": true}'
    assert not list(tmp_path.glob("*.tmp"))
