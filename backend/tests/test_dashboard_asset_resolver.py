"""资产类型与上海代码别名的回归测试。"""
import pytest

from backend.dashboard.asset_resolver import resolve_asset


@pytest.mark.parametrize("symbol,name", [("000001.SH", "上证指数"), (" 000300.sh ", "沪深300")])
def test_sh_index_aliases_keep_index_widgets_and_display_names(symbol, name):
    asset = resolve_asset(symbol)
    assert asset.type == "index"
    assert asset.symbol == symbol.strip().upper()
    assert asset.display_name == name

    assert resolve_asset("600519.SH").type == "equity"
