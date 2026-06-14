import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from typing import Optional

_HTTP_SESSION: Optional[requests.Session] = None

# 默认 (connect, read) 超时（秒）。
# 作用：调用方漏传 timeout 时兜底，避免 requests 默认的无限等待；
# 同时让国内不可达的墙外数据源快速失败降级，而不是拖垮整个请求。
_DEFAULT_TIMEOUT = (3.05, 6)


def _get_http_session() -> requests.Session:
    global _HTTP_SESSION
    if _HTTP_SESSION is not None:
        return _HTTP_SESSION
    # total=1：墙外源连不上时，重试无意义只会成倍放大等待（曾出现单次请求重试 3 次累计 40s+）。
    # 仅对 429/5xx 这类瞬时错误保留一次重试。
    retry = Retry(
        total=1,
        backoff_factor=0.2,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST", "HEAD"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
    session = requests.Session()
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    _HTTP_SESSION = session
    return session


def _http_get(url: str, **kwargs):
    kwargs.setdefault("timeout", _DEFAULT_TIMEOUT)
    return _get_http_session().get(url, **kwargs)


def _http_post(url: str, **kwargs):
    kwargs.setdefault("timeout", _DEFAULT_TIMEOUT)
    return _get_http_session().post(url, **kwargs)
