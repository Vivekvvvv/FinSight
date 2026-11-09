from __future__ import annotations

import json

import pytest

from backend.tools import price_portfolio as module


def _set_factors(monkeypatch, betas, volatility=0.2):
    monkeypatch.setattr(module, "get_factor_exposure", lambda *args, **kwargs: {
        "error": None, "factor_beta": betas, "annualized_volatility": volatility,
    })


@pytest.mark.parametrize("betas, shocks", [
    ({"market": None}, {"market": -0.1}),
    ({"market": 1.0}, {"unknown": -0.1}),
    ({"market": 1.0}, {"market": "bad"}),
])
def test_stress_scenarios_require_measured_factor_contributions(monkeypatch, betas, shocks):
    _set_factors(monkeypatch, betas)

    result = module.run_portfolio_stress_test([{"ticker": "AAPL"}], scenarios={"shock": shocks})

    assert result["error"] == "no_valid_scenarios"
    assert result["scenarios"] == []
    assert result["worst_case_return"] is None


def test_unusable_scenario_does_not_suppress_a_valid_projection(monkeypatch):
    _set_factors(monkeypatch, {"market": 1.0})

    result = module.run_portfolio_stress_test([{"ticker": "AAPL"}], scenarios={
        "unavailable": {"unknown": -0.1}, "equity": {"market": -0.1},
    })

    assert result["error"] is None
    assert [row["name"] for row in result["scenarios"]] == ["equity"]
    assert result["worst_case_return"] == pytest.approx(-0.12)


@pytest.mark.parametrize("betas, shocks", [
    ({"market": 1e308}, {"market": 10.0}),
    ({"market": 1e308, "growth": 1e308}, {"market": -0.9, "growth": -0.9}),
    ({"market": 1.7e308}, {"market": -0.95}),
])
def test_overflowing_stress_calculations_do_not_poison_valid_scenarios(monkeypatch, betas, shocks):
    _set_factors(monkeypatch, {**betas, "gold": 1.0})

    result = module.run_portfolio_stress_test([{"ticker": "AAPL"}], scenarios={
        "overflow": shocks, "safe": {"gold": -0.1},
    })

    assert [row["name"] for row in result["scenarios"]] == ["safe"]
    assert result["worst_case_return"] == pytest.approx(-0.12)
    json.dumps(result, allow_nan=False)
