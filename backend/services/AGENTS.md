# backend/services 架构说明

`backend/services` 是后端可复用业务服务层，向 API router、LangGraph 节点和后台任务提供持久化、计算、调度与外部能力封装。这里不直接暴露 HTTP 路由，也不依赖前端结构。

## 目录骨架

```text
backend/services/
  chat_history.py        # 按 session_id 持久化 AI 问答可见聊天记录
  memory.py              # 用户画像、关注列表与长期偏好记忆
  execution_service.py   # LangGraph 执行与 SSE 流式输出编排
  report_index.py        # 研究报告索引、收藏、标签与复查状态
  research_notes.py      # 研究笔记的数据访问与查询
  portfolio_*.py         # 组合、风险、优化相关服务
  *_service.py           # 面向具体业务域的服务封装
```

## 边界约定

- `chat_history.py` 只保存用户可见的聊天轮次，不参与模型 prompt 裁剪；模型上下文仍由 LangGraph `messages` 和 `ContextManager` 负责。
- `memory.py` 保存长期用户画像和最近研究焦点，不保存完整逐字聊天记录。
- `execution_service.py` 只编排执行流程，通过依赖注入回调写入外部存储，避免和具体 router 或文件路径耦合。
- 服务层可以读写 `data/` 下的本地开发存储，但必须保持 session/user 隔离，并限制单会话数据规模。

## 变更记录

- 2026-06-17：新增 `chat_history.py`，把 AI 问答的可见历史从前端临时状态提升为后端可查询、可清空的会话记录。
