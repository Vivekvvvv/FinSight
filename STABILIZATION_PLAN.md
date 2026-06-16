# FinSight v2.0.0 稳固计划

**目标**：不添加新功能，专注修复已知错误、补全测试、清理技术债务，确保现有功能稳定可用。

---

## 问题清单（已发现）

### 🔴 阻断级（必须先修）

| # | 问题 | 位置 |
|---|------|------|
| P1 | `vite.config.ts` 有两个 `export default`，**build 直接失败** | `frontend-vue/vite.config.ts` |
| P2 | 后端 49 个测试文件 import 报错，主因是 `fastapi`/`finnhub` 等包未安装到当前 Python 环境 | `backend/requirements.txt` 与当前 venv 不匹配 |

### 🟠 重要（影响稳定性）

| # | 问题 | 位置 |
|---|------|------|
| P3 | `requirements.txt` 只列了 8 个包，但代码实际依赖 20+ 个包（`finnhub`、`yfinance`、`baostock`、`apscheduler`、`beautifulsoup4` 等全部缺失） | `backend/requirements.txt` |
| P4 | 前端 lint 65 个 error（主要是 `no-unused-vars` 和 `no-explicit-any`） | 多个 `.vue`/`.ts` 文件 |
| P5 | v2.0.0 新增的后端模块（`notes_rag`、`risk_attribution`、`historical_data_store`）没有任何测试 | `backend/tests/` |

### 🟡 中等（影响代码质量）

| # | 问题 | 位置 |
|---|------|------|
| P6 | `ITERATION_PROGRESS.md` 进度文档未更新，仍显示"v2.0.0 待开始" | `docs/ITERATION_PROGRESS.md` |
| P7 | `CHANGELOG.md` 无 v2.0.0 条目，只有 Unreleased | `CHANGELOG.md` |
| P8 | 前端 1858 个 warning（vue 格式规范类，可批量 `--fix`） | 全局 |

---

## 执行计划

### 第一阶段：修复阻断问题（P1+P2+P3）

**步骤 1 — 修复 vite.config.ts 双 export**
- 删除文件末尾的旧版 `export default defineConfig({ plugins: [vue()] ... })` 重复块
- 验证：`npm run build` 通过

**步骤 2 — 修复 requirements.txt**
- 将代码实际依赖的所有包补全到 `requirements.txt`，并钉版本
- 包含：`fastapi`、`uvicorn`、`finnhub-python`、`yfinance`、`baostock`、`apscheduler`、`beautifulsoup4`、`python-dotenv`、`openai`、`langchain`、`langgraph` 等
- 验证：全局安装后 49 个 import 错误归零

**步骤 3 — 安装依赖并验证后端可以启动**
- `pip install -r backend/requirements.txt`
- `python -m pytest backend/tests/ --tb=short -q` 跑一遍，统计通过/失败数

---

### 第二阶段：补全 v2.0.0 测试（P5）

为三个新后端模块各写一个测试文件（纯单元测试，不依赖外部网络）：

**`backend/tests/test_notes_rag.py`**
- `_cosine()` 正确性（相同向量=1，正交=0）
- `vectorize_note()` 在 embedder 不可用时返回 False（不抛异常）
- `semantic_search_notes()` embedder 不可用时 fallback 到关键词搜索

**`backend/tests/test_risk_attribution.py`**
- `_beta_ols()` 用已知数据验证 beta 计算结果
- 无市场数据时返回 `method="simplified"`，不崩溃
- 所有字段类型正确（`total_portfolio_vol` 为 float）

**`backend/tests/test_historical_data_store.py`**
- `_to_bs_code("600519.SS")` → `"sh.600519"`
- `_to_bs_code("000001.SZ")` → `"sz.000001"`
- `_clean()` 过滤掉 close=0 的行
- `_clean()` 标记涨跌幅 >22% 的行为 `is_suspicious=True`

---

### 第三阶段：修复前端 lint errors（P4）

65 个 error 全部是两类：
1. **`no-unused-vars`**（未使用的变量/类型）→ 删除或加 `_` 前缀
2. **`no-explicit-any`**（裸 `any` 类型）→ 替换为具体类型或 `unknown`

先用 `npm run lint -- --fix` 处理可自动修复的，剩余手动逐文件修复。目标：**0 errors**（warnings 暂时允许存在）。

---

### 第四阶段：文档同步（P6+P7）

**`CHANGELOG.md`** — 新增 v2.0.0 条目：
- 列出本次迭代所有新增功能（AI研究报告、财报分析、情绪分析、智能问答、回测页、组合优化、PWA、RAG向量化、风险归因、历史数据、手势交互）

**`docs/ITERATION_PROGRESS.md`** — 更新进度：
- v2.0.0 所有条目标为 ✅
- 更新提交统计、代码行数、时间分配

---

## 验收标准

| 项目 | 目标 |
|------|------|
| `npm run build` | ✅ 成功，无报错 |
| `npm run typecheck` | ✅ 0 errors |
| `npm run lint` | ✅ 0 errors（warnings 不计） |
| `python -m pytest backend/tests/` | ✅ ≥90% 通过，0 collection error |
| 新增测试文件 | ✅ 3个文件，≥15个用例全部通过 |
| 文档 | ✅ CHANGELOG 有 v2.0.0 条目，进度文档已更新 |

---

## 执行顺序

```
P1（vite.config）→ P3（requirements.txt）→ P2（安装+跑测试）
    → P5（写新测试）→ P4（lint errors）→ P6+P7（文档）
```

预计工作量：4-6小时
