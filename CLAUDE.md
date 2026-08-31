# CLAUDE.md — FinSight 项目规则

1. **持久化必须原子且加锁**：所有落盘写入（JSON/SQLite）必须走"临时文件 + `os.replace`"原子替换，读-改-写组合操作必须持模块级锁（多处代码会各自实例化同一存储类，实例级锁无效）。参照 `backend/services/chat_history.py` 与修复后的 `backend/services/memory.py` 的写法。

2. **不许静默吞用户数据**：读到损坏的持久化文件时，先备份（`*.corrupt`）再回退默认值，并打 `logger.warning`；禁止 `except Exception: return 默认值` 这种让用户数据被下一次写入永久覆盖的写法。

3. **禁止把异常压成 200 响应**：路由层新代码不要 `except Exception: return {"success": False, "error": str(exc)}`；让 FastAPI 异常处理器返回正确状态码。存量代码顺手改，但不专门大改。

4. **新代码不进上帝文件**：`graph/nodes/synthesize.py`(2718 行)、`graph/report_builder.py`(2228)、`tools/price.py`(2179)、`dashboard/data_service.py`(1771)、`handlers/chat_handler.py`(1587) 只减不增；新功能放独立模块，从这些文件里 import。

5. **验证命令**：改后端必跑 `.\.venv\Scripts\python.exe -m pytest -q`（至少跑受影响模块的测试文件）；改前端必跑 `frontend-vue` 下 `npm run typecheck && npm run build`。测试路径见 `pytest.ini`（`backend/tests` + `tests`）。

6. **每次改动都要有对应的 git commit**：一次改动完成后立刻提交，一个逻辑改动一个 commit，便于后续追踪和回滚；不要把多个无关改动堆进同一个 commit，也不要攒着一堆改动不提交。只暂存本次改动涉及的文件（用 `git add <具体文件>`，别用 `git add .`），避免把工作区里其他未完成的改动带进去。

7. **每次改动都要写或更新测试，且交付前必须全绿**：新增功能补新测试，改行为就同步改断言，修 bug 先写能复现的失败用例。交付给用户之前必须实际跑过第 5 条的验证命令并确认全部通过——不许把"应该没问题"当成通过，也不许留着失败/跳过的用例就交付；跑不通就说明原因，不要谎报绿灯。
