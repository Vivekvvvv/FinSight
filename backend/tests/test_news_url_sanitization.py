from backend.tools.news import _build_news_item


def test_build_news_item_strips_finnhub_api_redirect_url():
    item = _build_news_item(
        title="Sample headline",
        source="Yahoo",
        url="https://finnhub.io/api/news?id=abc123",
        published_at="2026-02-13",
        snippet="sample",
        ticker="AAPL",
        confidence=0.8,
    )
    assert item.get("url") == ""


def test_build_news_item_keeps_normal_article_url():
    article_url = "https://www.reuters.com/world/us/apple-announces-new-product-2026-02-13/"
    item = _build_news_item(
        title="Reuters sample",
        source="Reuters",
        url=article_url,
        published_at="2026-02-13",
        snippet="sample",
        ticker="AAPL",
        confidence=0.8,
    )
    assert item.get("url") == article_url


def test_build_news_item_keeps_non_finnhub_host_url_containing_finnhub_path():
    """R86: "finnhub.io/api/news" 裸子串清空整条 URL——非 finnhub 主机但
    path/query 携带该片段的引用链接（跳转包装、内嵌提及）被误清空，
    用户拿不到真实来源。只有 URL 本身就是 finnhub API 端点才该清。"""
    article_url = "https://agg.example/redirect?u=finnhub.io/api/news&id=1"
    item = _build_news_item(
        title="Aggregator sample",
        source="Aggregator",
        url=article_url,
        published_at="2026-02-13",
        snippet="sample",
        ticker="AAPL",
        confidence=0.8,
    )
    assert item.get("url") == article_url


def test_build_news_item_schemeless_finnhub_api_url_still_stripped():
    """R86 正例：无 scheme 的 finnhub.io/api/news 直链仍是 API 端点，
    应保持清空（旧子串行为中的合理部分不能丢）。"""
    item = _build_news_item(
        title="Sample headline",
        source="finnhub",
        url="finnhub.io/api/news?id=abc123",
        published_at="2026-02-13",
        snippet="sample",
        ticker="AAPL",
        confidence=0.8,
    )
    assert item.get("url") == ""
