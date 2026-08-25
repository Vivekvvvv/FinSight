"""Technical snapshot computation for the LangChain tool registry."""

from __future__ import annotations

import json

from backend.tools import get_stock_historical_data as _get_stock_historical_data


def compute_technical_snapshot(ticker: str) -> str:
    """
    Compute a lightweight technical snapshot (MA/RSI/MACD) from recent daily prices.

    Returns a JSON string so the planner/synthesizer can reliably parse it.
    """
    try:
        data = _get_stock_historical_data(ticker, period="6mo", interval="1d")
        if not isinstance(data, dict):
            return json.dumps({"ticker": ticker, "error": "invalid_kline_payload"}, ensure_ascii=False)

        kline = data.get("kline_data") or []
        if not isinstance(kline, list) or not kline:
            return json.dumps(
                {"ticker": ticker, "error": "no_kline_data", "source": data.get("source")}, ensure_ascii=False
            )

        from backend.utils.quote import safe_float

        closes = []
        last_time = None
        for item in kline:
            if not isinstance(item, dict):
                continue
            close = item.get("close")
            parsed_close = safe_float(close)
            if parsed_close is None:
                continue
            closes.append(parsed_close)
            last_time = item.get("time") or item.get("datetime") or item.get("ts") or last_time

        if len(closes) < 30:
            return json.dumps(
                {
                    "ticker": ticker,
                    "error": "insufficient_points",
                    "points": len(closes),
                    "source": data.get("source"),
                },
                ensure_ascii=False,
            )

        import pandas as pd  # local import to keep cold-start minimal

        series = pd.Series(closes)
        close = float(series.iloc[-1])

        def _ma(window: int) -> float | None:
            if len(series) < window:
                return None
            return float(series.rolling(window=window).mean().iloc[-1])

        def _rsi(window: int = 14) -> float | None:
            if len(series) < window + 1:
                return None
            delta = series.diff()
            gains = delta.where(delta > 0, 0.0)
            losses = -delta.where(delta < 0, 0.0)
            avg_gain = gains.rolling(window=window, min_periods=window).mean()
            avg_loss = losses.rolling(window=window, min_periods=window).mean()
            last_gain = float(avg_gain.iloc[-1]) if not pd.isna(avg_gain.iloc[-1]) else 0.0
            last_loss = float(avg_loss.iloc[-1]) if not pd.isna(avg_loss.iloc[-1]) else 0.0
            if last_loss == 0:
                return 100.0
            rs = last_gain / last_loss
            return 100.0 - (100.0 / (1.0 + rs))

        def _macd() -> tuple[float | None, float | None]:
            if len(series) < 26:
                return None, None
            ema12 = series.ewm(span=12, adjust=False).mean()
            ema26 = series.ewm(span=26, adjust=False).mean()
            macd_series = ema12 - ema26
            signal_series = macd_series.ewm(span=9, adjust=False).mean()
            return float(macd_series.iloc[-1]), float(signal_series.iloc[-1])

        ma20 = _ma(20)
        ma50 = _ma(50)
        ma200 = _ma(200)
        rsi14 = _rsi(14)
        macd, signal = _macd()

        trend = "sideways"
        if ma20 is not None and ma50 is not None:
            if close > ma20 > ma50:
                trend = "uptrend"
            elif close < ma20 < ma50:
                trend = "downtrend"

        rsi_state = "neutral"
        if rsi14 is not None:
            if rsi14 >= 70:
                rsi_state = "overbought"
            elif rsi14 <= 30:
                rsi_state = "oversold"

        momentum = None
        if macd is not None and signal is not None:
            momentum = "bullish" if macd > signal else "bearish"

        payload = {
            "ticker": str(ticker).upper(),
            "as_of": last_time,
            "source": data.get("source"),
            "close": close,
            "ma20": ma20,
            "ma50": ma50,
            "ma200": ma200,
            "rsi14": rsi14,
            "rsi_state": rsi_state,
            "macd": macd,
            "macd_signal": signal,
            "momentum": momentum,
            "trend": trend,
        }
        return json.dumps(payload, ensure_ascii=False)
    except Exception as exc:  # pragma: no cover - runtime data issues
        return "get_technical_snapshot failed"
