# CLAUDE.md — FinSight 项目规则

1. **持久化必须原子且加锁**：所有落盘写入（JSON/SQLite）必须走"临时文件 + `os.replace`"原子替换，读-改-写组合操作必须持模块级锁（多处代码会各自实例化同一存储类，实例级锁无效）。参照 `backend/services/chat_history.py` 与修复后的 `backend/services/memory.py` 的写法。

2. **不许静默吞用户数据**：读到损坏的持久化文件时，先备份（`*.corrupt`）再回退默认值，并打 `logger.warning`；禁止 `except Exception: return 默认值` 这种让用户数据被下一次写入永久覆盖的写法。

3. **禁止把异常压成 200 响应**：路由层新代码不要 `except Exception: return {"success": False, "error": str(exc)}`；让 FastAPI 异常处理器返回正确状态码。存量代码顺手改，但不专门大改。

4. **新代码不进上帝文件**：`graph/nodes/synthesize.py`(2718 行)、`graph/report_builder.py`(2228)、`tools/price.py`(2179)、`dashboard/data_service.py`(1771)、`handlers/chat_handler.py`(1587) 只减不增；新功能放独立模块，从这些文件里 import。

5. **验证命令**：改后端必跑 `.\.venv\Scripts\python.exe -m pytest -q`（至少跑受影响模块的测试文件）；改前端必跑 `frontend-vue` 下 `npm run typecheck && npm run build`。测试路径见 `pytest.ini`（`backend/tests` + `tests`）。
