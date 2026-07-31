from __future__ import annotations

import math
from typing import Any


def _int_param(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return parsed if parsed > 0 else default


def _int_value(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def _float_param(value: Any, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return parsed if math.isfinite(parsed) else default


def _ema(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    period = max(1, _int_value(period, 1))
    k = 2 / (period + 1)
    out: list[float] = [values[0]]
    for value in values[1:]:
        out.append(value * k + out[-1] * (1 - k))
    return out


def _rsi(values: list[float], period: int = 14) -> list[float | None]:
    if len(values) < 2:
        return [None for _ in values]
    period = max(2, _int_value(period, 14))
    gains: list[float] = [0.0]
    losses: list[float] = [0.0]
    for i in range(1, len(values)):
        delta = values[i] - values[i - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))

    output: list[float | None] = [None for _ in values]
    for idx in range(period, len(values)):
        window_gains = gains[idx - period + 1 : idx + 1]
        window_losses = losses[idx - period + 1 : idx + 1]
        avg_gain = sum(window_gains) / period
        avg_loss = sum(window_losses) / period
        if avg_loss == 0:
            output[idx] = 100.0
            continue
        rs = avg_gain / avg_loss
        output[idx] = 100.0 - (100.0 / (1.0 + rs))
    return output


def ma_cross_signals(closes: list[float], *, short_window: int = 20, long_window: int = 50) -> dict[str, Any]:
    short_window = max(2, _int_value(short_window, 20))
    long_window = max(short_window + 1, _int_value(long_window, 50))
    signals: list[int] = [0 for _ in closes]
    for idx in range(len(closes)):
        if idx + 1 < long_window:
            continue
        short_ma = sum(closes[idx - short_window + 1 : idx + 1]) / short_window
        long_ma = sum(closes[idx - long_window + 1 : idx + 1]) / long_window
        signals[idx] = 1 if short_ma > long_ma else 0
    return {
        "name": "ma_cross",
        "signals": signals,
        "params": {"short_window": short_window, "long_window": long_window},
    }


def macd_signals(closes: list[float], *, fast: int = 12, slow: int = 26, signal: int = 9) -> dict[str, Any]:
    fast = max(2, _int_value(fast, 12))
    slow = max(fast + 1, _int_value(slow, 26))
    signal = max(2, _int_value(signal, 9))

    ema_fast = _ema(closes, fast)
    ema_slow = _ema(closes, slow)
    macd_line = [f - s for f, s in zip(ema_fast, ema_slow)]
    signal_line = _ema(macd_line, signal)

    signals: list[int] = []
    for macd_value, sig_value in zip(macd_line, signal_line):
        signals.append(1 if macd_value > sig_value else 0)

    return {
        "name": "macd",
        "signals": signals,
        "params": {"fast": fast, "slow": slow, "signal": signal},
    }


def rsi_mean_reversion_signals(
    closes: list[float],
    *,
    period: int = 14,
    oversold: float = 30.0,
    overbought: float = 70.0,
) -> dict[str, Any]:
    rsi_values = _rsi(closes, period)
    signals: list[int] = [0 for _ in closes]
    holding = 0
    for idx, value in enumerate(rsi_values):
        if value is None:
            signals[idx] = holding
            continue
        if value <= oversold:
            holding = 1
        elif value >= overbought:
            holding = 0
        signals[idx] = holding

    return {
        "name": "rsi_mean_reversion",
        "signals": signals,
        "params": {"period": period, "oversold": oversold, "overbought": overbought},
    }


def build_strategy_signals(strategy: str, closes: list[float], params: dict[str, Any] | None = None) -> dict[str, Any]:
    strategy_norm = str(strategy or "").strip().lower()
    cfg = params if isinstance(params, dict) else {}

    if strategy_norm in {"macd", "macd_strategy"}:
        return macd_signals(
            closes,
            fast=_int_param(cfg.get("fast", 12), 12),
            slow=_int_param(cfg.get("slow", 26), 26),
            signal=_int_param(cfg.get("signal", 9), 9),
        )

    if strategy_norm in {"rsi", "rsi_mean_reversion", "rsi_mr"}:
        return rsi_mean_reversion_signals(
            closes,
            period=_int_param(cfg.get("period", 14), 14),
            oversold=_float_param(cfg.get("oversold", 30.0), 30.0),
            overbought=_float_param(cfg.get("overbought", 70.0), 70.0),
        )

    return ma_cross_signals(
        closes,
        short_window=_int_param(cfg.get("short_window", 20), 20),
        long_window=_int_param(cfg.get("long_window", 50), 50),
    )


SUPPORTED_STRATEGIES = [
    {
        "id": "ma_cross",
        "name": "MA Cross",
        "description": "短均线上穿长均线买入，下穿卖出",
        "default_params": {"short_window": 20, "long_window": 50},
    },
    {
        "id": "macd",
        "name": "MACD",
        "description": "MACD 线上穿信号线买入，下穿卖出",
        "default_params": {"fast": 12, "slow": 26, "signal": 9},
    },
    {
        "id": "rsi_mean_reversion",
        "name": "RSI Mean Reversion",
        "description": "RSI 超卖买入，超买卖出",
        "default_params": {"period": 14, "oversold": 30.0, "overbought": 70.0},
    },
]


__all__ = [
    "SUPPORTED_STRATEGIES",
    "build_strategy_signals",
    "ma_cross_signals",
    "macd_signals",
    "rsi_mean_reversion_signals",
]
