# -*- coding: utf-8 -*-
import backend.tools.macro_official as macro_official_mod


def test_search_official_macro_releases_parses_official_feed(monkeypatch):
    sample_xml = """
    <rss version="2.0">
      <channel>
        <item>
          <title>BLS CPI News Release</title>
          <link>https://www.bls.gov/news.release/cpi.nr0.htm</link>
          <description>Latest CPI update from BLS.</description>
          <pubDate>Tue, 11 Feb 2026 13:30:00 GMT</pubDate>
        </item>
      </channel>
    </rss>
    """.strip()

    monkeypatch.setattr(
        macro_official_mod,
        "_OFFICIAL_FEEDS",
        (("bls", "BLS", "https://www.bls.gov/feed/bls_latest.rss"),),
    )
    monkeypatch.setattr(macro_official_mod, "_fetch_feed", lambda _url: sample_xml)

    rows = macro_official_mod.search_official_macro_releases("cpi inflation", max_results=5)

    assert rows
    assert rows[0].get("source") == "BLS"
    assert rows[0].get("domain") == "bls.gov"
    assert rows[0].get("is_official") is True


def test_get_official_macro_releases_fail_open_on_exception(monkeypatch):
    def _raise(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(macro_official_mod, "search_official_macro_releases", _raise)

    payload = macro_official_mod.get_official_macro_releases("cpi", max_results=5)

    assert payload.get("count") == 0
    assert str(payload.get("error") or "").startswith("fetch_failed:")


def test_matches_query_short_token_phantom_in_longer_word():
    """R78：3 字符 token 裸 substring 幻影命中——"war" 命中 "forWARd"、
    "aid" 命中 "sAID"，不相关官方发布被误判相关。"""
    item = {
        "title": "Fed issues forward guidance",
        "snippet": "Officials said rates stay unchanged",
        "url": "https://www.federalreserve.gov/newsevents/press.htm",
    }
    assert macro_official_mod._matches_query(item, ["war"]) is False
    assert macro_official_mod._matches_query(item, ["aid"]) is False


def test_matches_query_short_token_legit_match_kept():
    """3 字符 token 独立出现时仍命中——CPI / CPI-U（连字符是边界）。"""
    item = {
        "title": "CPI news release",
        "snippet": "Consumer Price Index",
        "url": "https://www.bls.gov/news.release/cpi.nr0.htm",
    }
    assert macro_official_mod._matches_query(item, ["cpi"]) is True
    hyphen_item = {
        "title": "CPI-U detailed tables",
        "snippet": "",
        "url": "https://www.bls.gov/feed/x.rss",
    }
    assert macro_official_mod._matches_query(hyphen_item, ["cpi"]) is True


def test_matches_query_long_token_substring_unchanged():
    """4+ 字符 token 保持 substring 语义——"payroll" 命中 "Payrolls"。"""
    item = {
        "title": "Payrolls data",
        "snippet": "",
        "url": "https://www.bls.gov/feed/x.rss",
    }
    assert macro_official_mod._matches_query(item, ["payroll"]) is True


def test_search_official_macro_releases_filters_phantom_hits(monkeypatch):
    """端到端：查询 'war impact'（impact 是 stopword → tokens=['war']），
    幻影命中项（forward guidance）应被过滤，真实 war 项保留。"""
    sample_xml = """
    <rss version="2.0">
      <channel>
        <item>
          <title>Fed issues forward guidance on rates</title>
          <link>https://www.federalreserve.gov/press/guidance.htm</link>
          <description>Forward-looking rate path.</description>
          <pubDate>Tue, 11 Feb 2026 19:00:00 GMT</pubDate>
        </item>
        <item>
          <title>War effects on energy prices</title>
          <link>https://www.bls.gov/news.release/war.htm</link>
          <description>Impact of war on CPI energy.</description>
          <pubDate>Tue, 11 Feb 2026 13:30:00 GMT</pubDate>
        </item>
      </channel>
    </rss>
    """.strip()

    monkeypatch.setattr(
        macro_official_mod,
        "_OFFICIAL_FEEDS",
        (("bls", "BLS", "https://www.bls.gov/feed/bls_latest.rss"),),
    )
    monkeypatch.setattr(macro_official_mod, "_fetch_feed", lambda _url: sample_xml)

    rows = macro_official_mod.search_official_macro_releases("war impact", max_results=5)

    assert [row["title"] for row in rows] == ["War effects on energy prices"]
