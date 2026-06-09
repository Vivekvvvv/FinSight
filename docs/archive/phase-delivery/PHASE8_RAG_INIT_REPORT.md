# PHASE8_RAG_INIT_REPORT.md

**生成时间**：2026-06-09  
**阶段**：Phase 8 — RAG 初始化验证  
**结论**：PASS（hash fallback 已验证；BGE-M3 生产模式待网络恢复后验证）

---

## 1. RAG 架构概述

FinSight 使用双模式 RAG：

| 模式 | 触发条件 | 说明 |
|------|---------|------|
| `hash` | `RAG_EMBEDDING=hash` | 使用文本哈希作为伪向量，跳过模型加载 |
| `bge-m3` | `RAG_EMBEDDING` 未设置（默认） | 加载 BAAI/BGE-M3（约 1.4GB），提供语义搜索 |
| memory fallback | `RAG_V2_ALLOW_MEMORY_FALLBACK=true` | pgvector 不可用时退回内存向量存储 |

---

## 2. Hash 模式验证（已通过）

**环境**：Docker smoke（`RAG_EMBEDDING=hash`, `RAG_V2_ALLOW_MEMORY_FALLBACK=true`）

验证结果：
- ✅ 后端容器启动健康（`/api/health` 返回 200）
- ✅ 全程无 `RAG`、`embedding`、`model load` 相关错误日志
- ✅ `/api/today` / `/api/research-quality` 等依赖 RAG 路径的端点返回 200
- ✅ 报告写入（`POST /api/research-notes`）成功，note_id 正常生成

---

## 3. BGE-M3 生产模式验证

| 验证项 | 状态 | 原因 |
|--------|------|------|
| 模型文件存在 | ⚠️ NOT_VERIFIED | 需检查 `models/bge-m3/` 目录 |
| 模型加载耗时 | ⚠️ NOT_VERIFIED | 需启动时间 / 日志 |
| 向量搜索延迟 | ⚠️ NOT_VERIFIED | 需集成测试 |
| pgvector 扩展 | ✅ PASS | `finsight-smoke-postgres` 使用 `pgvector/pgvector:pg16` 镜像 |

**原因**：当前网络无法拉取 Hugging Face 模型文件，本地 `models/` 目录不存在 BGE-M3 权重。

---

## 4. 首次部署 RAG 初始化步骤

```bash
# 1. 启动数据库（确保 pgvector 扩展已安装）
docker compose -f docker-compose.yml -f docker-compose.smoke.yml up postgres -d

# 2. 下载 BGE-M3（约 1.4GB，需 Hugging Face 访问）
python -m backend.rag.download_models

# 3. 验证模型存在
ls models/bge-m3/pytorch_model.bin

# 4. 启动后端，观察启动日志
docker compose up backend
# 预期日志：
# INFO  RAG model loaded: bge-m3
# INFO  pgvector store initialized: dim=1024

# 5. 运行 RAG 集成 smoke
python scripts/phase8_rag_integration_smoke.py
```

---

## 5. 回退预案

若 BGE-M3 加载失败（OOM / 磁盘不足），临时设置：
```bash
RAG_EMBEDDING=hash
RAG_V2_ALLOW_MEMORY_FALLBACK=true
```
系统功能降级（语义搜索变为哈希匹配），其余功能不受影响。

---

## 6. 结论

| 项目 | 结论 |
|------|------|
| hash fallback 可用性 | ✅ VERIFIED（Docker smoke 完整运行） |
| pgvector 扩展可用性 | ✅ VERIFIED（pg16 镜像内置） |
| BGE-M3 生产 embedding | ⚠️ NOT_VERIFIED_ENV_LIMIT（非代码问题） |
