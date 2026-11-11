# CLAUDE.md — FinSight 项目规则

1. **持久化必须原子且加锁**：JSON 等文件写入采用“同目录临时文件 + `os.replace`”；读-改-写组合操作持模块级锁，避免多个存储实例各自加锁而发生竞争。SQLite 写入使用数据库事务及适当的并发控制，不对正在使用的数据库文件做替换。参照 `backend/services/chat_history.py` 与 `backend/services/memory.py`。

2. **不许静默吞用户数据**：读取损坏的持久化文件时，先备份（`*.corrupt`）再回退默认值，并打 `logger.warning`；备份失败时停止可能覆盖原数据的写入。禁止 `except Exception: return 默认值` 这种让用户数据被下一次写入永久覆盖的写法。

3. **禁止把异常压成 200 响应**：路由层新代码不要 `except Exception: return {"success": False, "error": str(exc)}`；让 FastAPI 异常处理器返回正确状态码。修改涉及的存量代码时顺手修正，不为此扩大任务范围。

4. **新代码不进上帝文件**：`backend/graph/nodes/synthesize.py`、`backend/graph/report_builder.py`、`backend/tools/price.py`、`backend/dashboard/data_service.py`、`backend/handlers/chat_handler.py` 只减不增，已删除的文件不得恢复；新功能放独立模块，从这些文件里 import。以现有增长门禁为准，不在规则中维护容易过期的行数。

5. **按改动范围实际验证**：改后端至少跑受影响测试，Windows 使用 `.venv/Scripts/python.exe -m pytest -q <测试路径>`，Linux 使用环境中的 `python -m pytest -q <测试路径>`。测试路径见 `pytest.ini`（`backend/tests` + `tests`）。依赖或公共运行时变更须跑 `.github/workflows/ci.yml` 中的后端测试集合及受影响阶段；改前端在 `frontend-vue` 下分别执行 `npm run typecheck` 和 `npm run build`。纯文档或规则改动检查差异、链接和规则一致性，无需为此新增测试或重跑全套。

6. **按完整逻辑改动提交，避免细碎提交**：用户已授权提交时，一个完整问题及其回归测试对应一个 commit；同一问题的试验、补断言和修正失败属于同一个工作单元，验证后再提交。不得按循环轮数、工具调用或单个边界用例制造提交，不为凑次数制造改动，也不得将无关修复塞入一个 commit。只用 `git add <具体文件>` 暂存相关文件，禁止 `git add .`。未获得用户授权时不自动提交或推送；批量任务按用户约定统一 push，不逐轮 push。改写已推送历史须有明确授权、备份和新旧最终文件树一致性核验，并使用指定预期旧 SHA 的 `--force-with-lease`。

7. **行为改动必须有回归，验证结果必须如实报告**：修 bug 先复现失败；新增功能补测试，改行为同步断言。必要检查失败时继续修复，不得把“应该没问题”当成通过。已有明确退役或手工集成测试的跳过项，须核对原因并报告数量与影响；本次改动所需覆盖不得用 skip、删测试或放宽断言绕过。区分本地测试结果与远程 CI 状态；远程尚未结束、失败或相关阶段被跳过时，不宣称整条流水线通过。报告改动、实际验证结果和剩余风险。

8. **依赖锁定必须兼容**：版本变更同步 `requirements.in` 与 `requirements.txt`，保持精确锁定。核对上游 `Requires-Python`、`Requires-Dist` 和支持的平台，在依赖解析后用锁定版本实际跑测试；验证不能只依赖已安装但与锁文件不同的本地版本。执行 `python scripts/check_requirements_lock.py` 和受影响的供应链审计。优先选择满足兼容性与安全要求的最小变更，不无关升级、不新增无关依赖；镜像延迟或下载失败与版本冲突分别诊断，不用 `--no-deps`、删除锁定或扩大漏洞豁免掩盖问题。

9. **测试兼顾 Windows 与 Linux**：CI 使用 Ubuntu，本地可能使用 Windows；共享测试避免直接依赖 `ctypes.windll`、系统属性或固定路径。优先通过可恢复的故障注入验证异常处理；真正的平台专用行为需说明适用平台，并保留其他平台的等价覆盖。测试临时资源必须清理，修改环境变量或 monkeypatch 必须限定作用域。

10. **最小改动，先核对再执行**：开始任务先读现有改动、相关规则和失败证据，保留用户未完成工作。只修已复现且在授权范围内的问题；不重构、不加无关依赖、不碰无关文件。重复排查任务按证据选择问题，未发现问题时如实记录，不把检查轮数当作修复数。更新项目规则时保持根目录 `AGENTS.md` 与 `CLAUDE.md` 的共同规则一致；用户指定只更新某一文件时遵照其范围。
