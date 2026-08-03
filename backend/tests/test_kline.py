import sys
import os
# Add project root to sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from backend.tools import price as price_module

def test_get_kline_data(monkeypatch):
    ticker = "^GSPC"
    fixture = {
        "kline_data": [
            {
                "time": "2026-01-02 00:00",
                "open": 100.0,
                "high": 105.0,
                "low": 99.0,
                "close": 103.0,
                "volume": 123456.0,
            }
        ],
        "period": "1y",
        "interval": "1d",
        "source": "stooq",
    }

    monkeypatch.setattr(price_module, "_fetch_with_stooq_history", lambda *_args, **_kwargs: fixture)

    print(f"Fetching K-line data for {ticker}...")
    result = price_module.get_stock_historical_data(ticker)

    assert "error" not in result, f"K-line tool returned error: {result.get('error')}"

    data = result.get("kline_data")
    assert data, "No 'kline_data' key in response"

    print(f"Successfully fetched {len(data)} data points.")

    if len(data) > 0:
        first_point = data[0]
        print("Sample data point:", first_point)
        # Verify structure
        required_keys = ["time", "open", "high", "low", "close"]
        for key in required_keys:
            assert key in first_point, f"Missing key '{key}' in data point"

if __name__ == "__main__":
    try:
        test_get_kline_data()
        print("✅ K-line data test passed!")
    except Exception as exc:
        print(f"❌ K-line data test failed! {type(exc).__name__}")
