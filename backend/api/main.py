import logging
import json
import asyncio
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import os
import re
import asyncio
import sys
from threading import Lock
from typing import Any, Dict
from urllib import request as urllib_request
from uuid import uuid4
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from contextlib import asynccontextmanager
from backend.api.schemas import (
    ChatRequest,
)
from backend.api.chat_router import ChatRouterDeps, create_chat_router
from backend.tools.us_market import fetch_nasdaq_intraday, fetch_nasdaq_quote
from backend.api.security_config import (
    PRODUCTION_REQUIRED_ENV as _PRODUCTION_REQUIRED_ENV,
    SimpleRateLimiter,
    cors_allow_credentials as _cors_allow_credentials,
    cors_allow_origin_regex as _cors_allow_origin_regex,
    cors_allow_origins as _cors_allow_origins,
    env_int as _env_int,
    extract_api_key as _extract_api_key,
    is_allowlisted_path as _is_allowlisted_path,
    missing_production_env as _missing_production_env,
    parse_api_keys as _parse_api_keys,
    parse_csv_env as _parse_csv_env,
    validate_production_runtime_config as _validate_production_runtime_config,
)
from backend.api.agent_router import AgentRouterDeps, create_agent_router
from backend.api.config_router import ConfigRouterDeps, create_config_router
from backend.api.dashboard_router import dashboard_router
from backend.api.execution_router import ExecutionRouterDeps, create_execution_router
from backend.api.market_router import MarketRouterDeps, create_market_router
from backend.api.portfolio_router import portfolio_router
from backend.api.rebalance_router import RebalanceRouterDeps, create_rebalance_router
from backend.api.report_router import ReportRouterDeps, create_report_router
from backend.api.subscription_router import create_subscription_router
from backend.api.alerts_router import create_alerts_router
from backend.api.screener_router import screener_router
from backend.api.cn_market_router import cn_market_router
from backend.api.backtest_router import backtest_router
from backend.api.system_router import SystemRouterDeps, create_system_router
from backend.api.morning_brief_router import MorningBriefRouterDeps, create_morning_brief_router
from backend.api.task_router import TaskRouterDeps, create_task_router
from backend.api.today_router import TodayRouterDeps, create_today_router
from backend.api.tools_router import create_tools_router
from backend.api.user_router import UserRouterDeps, create_user_router
from backend.api.auth_router import router as auth_router
from backend.api.entitlements_router import create_entitlements_router
from backend.api.demo_router import demo_router
from backend.contracts import CHAT_RESPONSE_SCHEMA_VERSION, SSE_EVENT_SCHEMA_VERSION, contract_manifest
from backend.metrics import METRICS_ENABLED, metrics_payload
from backend.conversation.context import ContextManager
from backend.graph import aget_graph_runner, get_graph_checkpointer_info, graph_runner_ready, reset_graph_runner
from backend.orchestration.tools_bridge import get_global_orchestrator
from backend.graph.nodes.planner import get_planner_ab_metrics
from backend.rag import get_rag_observability_store, install_rag_observability_hooks
from backend.security.auth import (
    api_key_fingerprint,
    dev_principal,
    env_bool as _auth_env_bool,
    guest_principal,
    is_dev_mode,
    principal_from_api_key,
    secure_secret_in,
)
from backend.services.langfuse_tracer import flush_langfuse, shutdown_langfuse
from backend.services.chat_history import ChatHistoryStore
from backend.services.portfolio_store import get_positions as get_portfolio_positions
from backend.services.report_index import get_report_index_store
from backend.utils.env_config import env_float as _env_float

from backend.api.session_context import (
    _ESSENTIAL_SSE_TYPES,
    _SESSION_PART_PATTERN,
    _build_trace_digest,
    _build_ui_context,
    _cleanup_session_contexts,
    _contract_info,
    _get_orchestrator_safe,
    _get_session_context,
    _index_report_async,
    _is_raw_trace_event,
    _normalize_session_key,
    _reference_context_last_access,
    _reference_contexts,
    _reference_lock,
    _resolve_query_reference,
    _resolve_thread_id,
    _schedule_report_index,
    _update_session_context,
)
from backend.api.auth_identity import (
    _AUTH_IDENTITY_CACHE_SENTINEL,
    _auth_identity_cache,
    _auth_identity_lock,
    _resolve_supabase_auth_config,
    _is_supabase_auth_configured,
    _resolve_rag_observability_dev_auth_config,
    _is_rag_observability_dev_auth_enabled,
    _resolve_rag_observability_dev_user_identity,
    _is_internal_api_key_authorized,
    _auth_identity_cache_ttl_seconds,
    _auth_identity_cache_max_entries,
    _auth_token_cache_key,
    _prune_auth_identity_cache,
    _fetch_supabase_user_identity,
    _resolve_request_user_identity,
    _require_rag_read_access,
)

logger = logging.getLogger(__name__)
_DEFAULT_CONFIG_LOCK = Lock()

# Ensure project root is on sys.path for backend imports.
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Windows + psycopg async ??? Selector Event LoopPolicy???????? PostgreSQL checkpointer ??????????
if sys.platform.startswith('win') and hasattr(asyncio, 'WindowsSelectorEventLoopPolicy'):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Load env once for scheduler/SMTP configs, etc.
load_dotenv()

# Logging (avoid duplicate handlers in reload)
if not logging.getLogger().handlers:
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

# 尝试导入核心工�??
try:
    from backend.tools import (
        get_stock_price,
        get_company_news,
        get_stock_historical_data,
        get_financial_statements,
        get_financial_statements_summary,
        get_company_info,
    )
    logger.info("[Init] Core tools imported successfully.")
except ImportError as e:
    # 如�??backend.tools 导入失败，则尝试从根目录 tools 导入（兼容旧结构�?
    try:
        from tools import (
            get_stock_price,
            get_company_news,
            get_stock_historical_data,
            get_financial_statements,
            get_financial_statements_summary,
            get_company_info,
        )
        logger.info("[Init] Core tools imported from root successfully.")
    except ImportError as e2:
        logger.error("[Init] Error importing tools")

# Import chart detector.
try:
    from backend.api.chart_detector import ChartTypeDetector
    logger.info("[Init] Chart detector imported successfully.")
except ImportError as e:
    logger.info("[Init] Error importing chart detector")
    ChartTypeDetector = None

# 导�??MemoryService
try:
    from backend.services.memory import MemoryService, UserProfile
    memory_service = MemoryService()
    logger.info("[Init] MemoryService initialized successfully.")
except Exception as e:
    logger.error("[Init] Error initializing MemoryService")
    memory_service = None


_schedulers = []
chat_history_store = ChatHistoryStore()

_SENSITIVE_KEY_FRAGMENTS = (
    "api_key",
    "apikey",
    "authorization",
    "auth",
    "token",
    "cookie",
    "password",
    "secret",
)


def _mask_secret(value: str) -> str:
    raw = str(value or "")
    if len(raw) <= 8:
        return "***"
    return f"{raw[:3]}***{raw[-3:]}"


def _redact_sensitive_payload(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, inner in value.items():
            key_text = str(key).lower()
            if any(fragment in key_text for fragment in _SENSITIVE_KEY_FRAGMENTS):
                redacted[key] = _mask_secret(str(inner)) if inner is not None else "***"
                continue
            redacted[key] = _redact_sensitive_payload(inner)
        return redacted
    if isinstance(value, list):
        return [_redact_sensitive_payload(item) for item in value]
    if isinstance(value, str):
        # Best-effort key/token masking in free text.
        masked = re.sub(r"(?i)(sk-[a-z0-9_-]{8,})", lambda m: _mask_secret(m.group(1)), value)
        masked = re.sub(
            r"(?i)(authorization\s*[:=]\s*bearer\s+)([a-z0-9._-]{8,})",
            lambda m: f"{m.group(1)}{_mask_secret(m.group(2))}",
            masked,
        )
        return masked
    return value


def _resolve_trace_raw_enabled(request: ChatRequest) -> bool:
    default_enabled = _env_bool("TRACE_RAW_ENABLED", "true")
    override = None
    if getattr(request, "options", None):
        override = request.options.trace_raw_override
    if override == "on":
        return True
    if override == "off":
        return False
    return default_enabled


def _env_bool(key: str, default: str = "false") -> bool:
    return _auth_env_bool(key, default)


def _require_rag_mutation_access(request: Request) -> Dict[str, Any]:
    if _is_internal_api_key_authorized(request):
        principal = {"user_id": "internal", "email": None, "auth_type": "api_key", "role": "internal"}
        request.state.rag_authenticated_user = principal
        return principal
    raise HTTPException(status_code=403, detail="RAG diagnostics is read-only for logged-in users; mutation requires internal API key")


_rate_limiter = SimpleRateLimiter.from_env()
_rag_auth_rate_limiter = SimpleRateLimiter.from_env()

def _init_default_user_config() -> None:
    """Write LLM config from explicit env on first boot if user_config.json does not exist."""
    import json as _json
    from backend.llm_config import USER_CONFIG_PATH

    with _DEFAULT_CONFIG_LOCK:
        if os.path.exists(USER_CONFIG_PATH):
            return

        _DEFAULT_API_BASE = str(os.getenv("OPENAI_COMPATIBLE_API_BASE") or "").strip()
        _DEFAULT_API_KEY = str(os.getenv("OPENAI_COMPATIBLE_API_KEY") or "").strip()
        _DEFAULT_MODEL = str(os.getenv("OPENAI_COMPATIBLE_MODEL") or "gpt-4o-mini").strip()
        if not (_DEFAULT_API_BASE and _DEFAULT_API_KEY):
            logger.info("[Config] no explicit LLM env found; skip default user config bootstrap")
            return

        default_cfg = {
            "llm_provider": "openai_compatible",
            "llm_model":    _DEFAULT_MODEL,
            "llm_api_base": _DEFAULT_API_BASE,
            "llm_api_key":  _DEFAULT_API_KEY,
            "llm_endpoints": [
                {
                    "name":        "primary",
                    "provider":    "openai_compatible",
                    "api_base":    _DEFAULT_API_BASE,
                    "api_key":     _DEFAULT_API_KEY,
                    "model":       _DEFAULT_MODEL,
                    "weight":      1,
                    "enabled":     True,
                    "cooldown_sec": 30,
                }
            ],
        }
        temp_path = f"{USER_CONFIG_PATH}.{uuid4().hex}.tmp"
        try:
            os.makedirs(os.path.dirname(USER_CONFIG_PATH), exist_ok=True)
            with open(temp_path, "w", encoding="utf-8") as _f:
                _json.dump(default_cfg, _f, indent=2, ensure_ascii=False)
                _f.flush()
                os.fsync(_f.fileno())
            os.replace(temp_path, USER_CONFIG_PATH)
            logger.info("[Config] wrote default user config")
        except Exception as _exc:
            logger.warning("[Config] failed to write default user config")
        finally:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan handler to start/stop price_change scheduler."""
    _validate_production_runtime_config()
    # Ensure a working default LLM config exists on first boot.
    _init_default_user_config()

    # Initialize Prometheus metrics
    from backend.monitoring import init_app_info
    init_app_info(version="1.8.0", environment=os.getenv("ENV", "production"))

    from backend.services.alert_scheduler import run_price_change_cycle
    from backend.services.scheduler_runner import start_interval_scheduler, start_price_change_scheduler

    enabled = _env_bool("PRICE_ALERT_SCHEDULER_ENABLED", "false")
    if enabled:
        interval = _env_float("PRICE_ALERT_INTERVAL_MINUTES", 15.0, minimum=0.1)
        sched = start_price_change_scheduler(
            run_price_change_cycle,
            interval_minutes=interval,
            enabled=True,
        )
        if sched:
            _schedulers.append(sched)
    else:
        logger.info("[Scheduler] PRICE_ALERT_SCHEDULER_ENABLED is false; skip start.")

    # News scheduler
    from backend.services.alert_scheduler import run_news_alert_cycle
    news_enabled = _env_bool("NEWS_ALERT_SCHEDULER_ENABLED", "false")
    if news_enabled:
        news_interval = _env_float("NEWS_ALERT_INTERVAL_MINUTES", 30.0, minimum=0.1)
        sched = start_price_change_scheduler(
            run_news_alert_cycle,
            interval_minutes=news_interval,
            enabled=True,
        )
        if sched:
            _schedulers.append(sched)
    else:
        logger.info("[Scheduler] NEWS_ALERT_SCHEDULER_ENABLED is false; skip start.")

    # Risk scheduler
    from backend.services.alert_scheduler import run_risk_alert_cycle
    risk_enabled = _env_bool("RISK_ALERT_SCHEDULER_ENABLED", "false")
    if risk_enabled:
        risk_interval = _env_float("RISK_ALERT_INTERVAL_MINUTES", 60.0, minimum=0.1)
        sched = start_price_change_scheduler(
            run_risk_alert_cycle,
            interval_minutes=risk_interval,
            enabled=True,
        )
        if sched:
            _schedulers.append(sched)
    else:
        logger.info("[Scheduler] RISK_ALERT_SCHEDULER_ENABLED is false; skip start.")

    # Health probe scheduler (optional)
    from backend.services.health_probe import run_health_probe_cycle
    health_enabled = _env_bool("HEALTH_PROBE_ENABLED", "false")
    if health_enabled:
        health_interval = _env_float("HEALTH_PROBE_INTERVAL_MINUTES", 30.0, minimum=0.1)
        sched = start_price_change_scheduler(
            run_health_probe_cycle,
            interval_minutes=health_interval,
            enabled=True,
        )
        if sched:
            _schedulers.append(sched)
    else:
        logger.info("[Scheduler] HEALTH_PROBE_ENABLED is false; skip start.")

    try:
        install_rag_observability_hooks()
        rag_observability_status = get_rag_observability_store().ensure_schema() if hasattr(get_rag_observability_store(), 'ensure_schema') else False
        logger.info("[RAGObservability] initialization completed")
    except Exception as exc:
        logger.error("[RAGObservability] initialization failed in lifespan")

    rag_retention_enabled = _env_bool("RAG_OBSERVABILITY_RETENTION_ENABLED", "true")
    if rag_retention_enabled:
        rag_retention_interval = _env_float(
            "RAG_OBSERVABILITY_RETENTION_INTERVAL_MINUTES", 360.0, minimum=0.1
        )

        def _run_rag_observability_retention_cycle() -> None:
            try:
                deleted = get_rag_observability_store().cleanup_retention()
                logger.info("[RAGObservability] retention cleanup completed")
            except Exception as exc:
                logger.error("[RAGObservability] retention cleanup failed")

        sched = start_interval_scheduler(
            _run_rag_observability_retention_cycle,
            interval_minutes=rag_retention_interval,
            enabled=True,
            job_id="rag_observability_retention",
            job_label="rag observability retention",
        )
        if sched:
            _schedulers.append(sched)
    else:
        logger.info("[RAGObservability] RAG_OBSERVABILITY_RETENTION_ENABLED is false; skip retention scheduler.")

    try:
        await aget_graph_runner()
        logger.info("[GraphRunner] initialized in lifespan")
    except Exception as exc:
        logger.error("[GraphRunner] initialization failed in lifespan")

    try:
        yield
    finally:
        try:
            flush_langfuse()
            shutdown_langfuse()
        except Exception:
            logger.debug("[LangFuse] flush/shutdown error on shutdown (ignored)")
        scheduler_count = len(_schedulers)
        for sched in list(_schedulers):
            try:
                sched.shutdown(wait=True)
            except Exception as e:
                logger.error("[Scheduler] shutdown error")
        if scheduler_count:
            logger.info("[Scheduler] all schedulers stopped.")
        _schedulers.clear()
        try:
            from backend.graph.checkpointer import areset_checkpointer_caches

            await areset_checkpointer_caches()
            reset_graph_runner()
            logger.info("[GraphRunner] checkpointer/runner caches cleared on shutdown")
        except Exception as e:
            logger.error("[GraphRunner] shutdown cleanup error")

app = FastAPI(
    title="FinSight API",
    description="FinSight 后端服务",
    version="1.0.0",
    lifespan=lifespan,
)

@app.middleware("http")
async def security_gate(request: Request, call_next):
    if _is_allowlisted_path(request.url.path):
        return await call_next(request)

    api_key = None
    if request.url.path.startswith("/diagnostics/rag") or request.url.path in {
        "/diagnostics/orchestrator",
        "/diagnostics/planner-ab",
        "/diagnostics/planner_ab",
    }:
        if _rag_auth_rate_limiter.enabled:
            client_host = request.client.host if request.client else "anonymous"
            allowed, retry_after = _rag_auth_rate_limiter.allow(f"rag-auth:{client_host}")
            if not allowed:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Rate limit exceeded"},
                    headers={"Retry-After": str(retry_after)},
                )
        try:
            # 内部经 _fetch_supabase_user_identity 做同步 urlopen(timeout=5)：
            # 缓存未命中时会把整个事件循环阻塞最长 5 秒，必须卸载线程池（R34）
            user_identity = await asyncio.to_thread(_require_rag_read_access, request)
            request.state.rag_authenticated_user = user_identity
        except HTTPException as exc:
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
        except Exception as exc:
            # Supabase 抖动/超时抛 RuntimeError/TimeoutError：认证上游不可用应是
            # 503 而非裸 500（R35），不泄露内部栈
            logger.error("rag access check failed due to upstream auth error")
            return JSONResponse(status_code=503, content={"detail": "Auth upstream unavailable"})
        # rag 路径此前直接 return，完全绕过限流（且使主路径的"按用户限流"
        # 分支成为死代码）——在本分支内按登录用户限流（R40）
        if _rate_limiter.enabled:
            if isinstance(user_identity, dict) and user_identity.get("user_id"):
                client_id = f"user:{user_identity['user_id']}"
            else:
                client_id = request.client.host if request.client else "anonymous"
            allowed, retry_after = _rate_limiter.allow(client_id)
            if not allowed:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Rate limit exceeded"},
                    headers={"Retry-After": str(retry_after)},
                )
        return await call_next(request)

    if is_dev_mode():
        request.state.principal = dev_principal()
        return await call_next(request)

    keys = _parse_api_keys()
    if not keys:
        return JSONResponse(status_code=503, content={"detail": "API auth enabled but no keys configured"})
    api_key = _extract_api_key(request)
    if not api_key or not secure_secret_in(api_key, keys):
        return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
    else:
        request.state.principal = principal_from_api_key(api_key)

    if _rate_limiter.enabled:
        # rag_authenticated_user 只在上方 rag 分支赋值且该分支已 return，
        # 此处恒为 api key 维度
        client_id = api_key_fingerprint(api_key) if api_key else (request.client.host if request.client else "anonymous")
        allowed, retry_after = _rate_limiter.allow(client_id)
        if not allowed:
            headers = {"Retry-After": str(retry_after)}
            return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"}, headers=headers)

    return await call_next(request)

# CORS 必须在 security_gate 之后注册（Starlette 后注册者在最外层）：
# 若在内层，生产模式下浏览器预检 OPTIONS（不带鉴权头）会先被 security_gate
# 401 拦下且响应缺 CORS 头——跨域部署的前端完全无法调用，真实鉴权错误
# 也全部被浏览器显示成 CORS 错误。
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_allow_origins(),
    allow_origin_regex=_cors_allow_origin_regex(),
    allow_credentials=_cors_allow_credentials(),
    allow_methods=["*"],
    allow_headers=["*"],
)

# === API routers ===

chat_router = create_chat_router(
    ChatRouterDeps(
        get_graph_runner=lambda: aget_graph_runner(),
        resolve_thread_id=_resolve_thread_id,
        build_ui_context=_build_ui_context,
        resolve_query_reference=_resolve_query_reference,
        schedule_report_index=_schedule_report_index,
        update_session_context=_update_session_context,
        contract_info=_contract_info,
        resolve_trace_raw_enabled=_resolve_trace_raw_enabled,
        is_raw_trace_event=_is_raw_trace_event,
        redact_sensitive_payload=_redact_sensitive_payload,
        get_session_context=_get_session_context,
        chat_history_store=chat_history_store,
        chat_response_schema_version=CHAT_RESPONSE_SCHEMA_VERSION,
        sse_event_schema_version=SSE_EVENT_SCHEMA_VERSION,
    )
)

system_router = create_system_router(
    SystemRouterDeps(
        metrics_enabled=METRICS_ENABLED,
        metrics_payload=metrics_payload,
        graph_runner_ready=graph_runner_ready,
        get_graph_checkpointer_info=get_graph_checkpointer_info,
        get_orchestrator_safe=_get_orchestrator_safe,
        get_planner_ab_metrics=get_planner_ab_metrics,
        get_rag_observability_store=lambda: get_rag_observability_store(),
        require_rag_read_access=lambda request: _require_rag_read_access(request),
        require_rag_mutation_access=lambda request: _require_rag_mutation_access(request),
        memory_service=memory_service,
        logger=logger,
    )
)

user_router = create_user_router(
    UserRouterDeps(
        memory_service=memory_service,
        user_profile_cls=UserProfile,
    )
)

agent_router = create_agent_router(
    AgentRouterDeps(
        memory_service=memory_service,
    )
)

market_router = create_market_router(
    MarketRouterDeps(
        get_orchestrator_safe=_get_orchestrator_safe,
        get_stock_price=globals().get("get_stock_price") or (lambda _ticker: {"error": "price tool unavailable"}),
        get_company_news=globals().get("get_company_news") or (lambda _ticker: {"error": "news tool unavailable"}),
        get_financial_statements=globals().get("get_financial_statements") or (lambda _ticker: {"error": "financials tool unavailable"}),
        get_financial_statements_summary=globals().get("get_financial_statements_summary") or (lambda _ticker: {"error": "financials summary tool unavailable"}),
        get_stock_historical_data=globals().get("get_stock_historical_data") or (lambda _ticker, **_kwargs: {"error": "history tool unavailable"}),
        detect_chart_type=(ChartTypeDetector.detect_chart_type if ChartTypeDetector else None),
        logger=logger,
        get_us_quote=fetch_nasdaq_quote,
        get_us_intraday=fetch_nasdaq_intraday,
    )
)

subscription_router = create_subscription_router()
alerts_router = create_alerts_router()

config_router = create_config_router(
    ConfigRouterDeps(
        project_root=project_root,
        logger=logger,
    )
)

report_router = create_report_router(
    ReportRouterDeps(
        resolve_thread_id=_resolve_thread_id,
        get_report_index_store=lambda: get_report_index_store(),
    )
)

task_router = create_task_router(
    TaskRouterDeps(
        resolve_thread_id=_resolve_thread_id,
        get_report_index_store=lambda: get_report_index_store(),
        get_portfolio_positions=get_portfolio_positions,
        get_stock_price=globals().get("get_stock_price") or (lambda _ticker: None),
    )
)
tools_router = create_tools_router()

morning_brief_router = create_morning_brief_router(
    MorningBriefRouterDeps(
        resolve_thread_id=_resolve_thread_id,
        get_portfolio_positions=get_portfolio_positions,
        get_stock_price=globals().get("get_stock_price") or (lambda _ticker: None),
        get_company_news=globals().get("get_company_news") or (lambda _ticker, _limit=5: []),
        get_graph_runner=lambda: aget_graph_runner(),
    )
)

# --- Phase 3: Today Workspace router ---
from backend.services.subscription_service import get_subscription_service

today_router = create_today_router(
    TodayRouterDeps(
        resolve_thread_id=_resolve_thread_id,
        memory_service=memory_service,
        subscription_service=get_subscription_service(),
    )
)

# --- Phase 4: Risk Lens router ---
from backend.api.risk_lens_router import RiskLensRouterDeps, create_risk_lens_router

risk_lens_router = create_risk_lens_router(
    RiskLensRouterDeps(
        resolve_thread_id=_resolve_thread_id,
    )
)

# --- Phase 4: Research Notes router ---
from backend.api.research_notes_router import ResearchNotesRouterDeps, create_research_notes_router

research_notes_router = create_research_notes_router(
    ResearchNotesRouterDeps(
        resolve_thread_id=_resolve_thread_id,
    )
)

# --- Phase 4.3: Timeline router ---
from backend.api.timeline_router import TimelineRouterDeps, create_timeline_router

timeline_router = create_timeline_router(
    TimelineRouterDeps(
        resolve_thread_id=_resolve_thread_id,
    )
)

# --- Phase 4.4: What Changed router ---
from backend.api.what_changed_router import create_what_changed_router

what_changed_router = create_what_changed_router()

# --- Phase 4.5: Research Quality router ---
from backend.api.research_quality_router import create_research_quality_router

research_quality_router = create_research_quality_router()
entitlements_router = create_entitlements_router()

execution_router = create_execution_router(
    ExecutionRouterDeps(
        get_graph_runner=lambda: aget_graph_runner(),
        resolve_thread_id=_resolve_thread_id,
        schedule_report_index=_schedule_report_index,
        update_session_context=_update_session_context,
        redact_sensitive_payload=_redact_sensitive_payload,
        is_raw_trace_event=_is_raw_trace_event,
        contract_info=_contract_info,
        sse_event_schema_version=SSE_EVENT_SCHEMA_VERSION,
    )
)

# --- Phase 3: Portfolio & Rebalance routers ---
from backend.services.rebalance_engine import RebalanceEngine as _RebalanceEngine
from backend.services.rebalance_llm_enhancer import AgentBackedEnhancer as _AgentBackedEnhancer

_rebalance_llm_enhancer = _AgentBackedEnhancer(
    get_company_news=globals().get("get_company_news"),
    get_company_info=globals().get("get_company_info"),
    create_llm_fn=None,  # Lazy init: set after LLM config is ready
)
try:
    from backend.llm_config import create_llm as _create_llm_for_rebalance
    _rebalance_llm_enhancer = _AgentBackedEnhancer(
        get_company_news=globals().get("get_company_news"),
        get_company_info=globals().get("get_company_info"),
        create_llm_fn=_create_llm_for_rebalance,
    )
except Exception:
    pass  # LLM unavailable, enhancer will be no-op

_rebalance_engine = _RebalanceEngine(llm_enhancer=_rebalance_llm_enhancer)

rebalance_router = create_rebalance_router(
    RebalanceRouterDeps(
        rebalance_engine=_rebalance_engine,
        get_stock_price=globals().get("get_stock_price"),
        get_company_info=globals().get("get_company_info"),
    )
)

app.include_router(system_router)
app.include_router(demo_router)
app.include_router(auth_router)
app.include_router(entitlements_router)
app.include_router(user_router)
app.include_router(agent_router)
app.include_router(chat_router)
app.include_router(market_router)
app.include_router(subscription_router)
app.include_router(alerts_router)
app.include_router(screener_router)
app.include_router(cn_market_router)
app.include_router(backtest_router)
app.include_router(config_router)
app.include_router(report_router)
app.include_router(task_router)
app.include_router(tools_router)
app.include_router(execution_router)
app.include_router(dashboard_router)
app.include_router(portfolio_router)
app.include_router(rebalance_router)
app.include_router(morning_brief_router)
app.include_router(today_router)
app.include_router(risk_lens_router)
app.include_router(research_notes_router)
app.include_router(timeline_router)
app.include_router(what_changed_router)
app.include_router(research_quality_router)

# Prometheus metrics endpoint
from backend.monitoring import metrics_router
app.include_router(metrics_router)

# Research report endpoint
from backend.api.research_router import router as research_router
app.include_router(research_router)
# 启动入�?U
if __name__ == "__main__":
    uvicorn.run("backend.api.main:app", host="0.0.0.0", port=8000, reload=True)
