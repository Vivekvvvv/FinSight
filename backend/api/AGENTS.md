# backend/api

FastAPI HTTP 层，只负责把请求路由到服务与图编排，不在路由层沉淀业务状态。

## 目录骨架

```text
backend/api/
├── main.py                  # 应用装配、生命周期、中间件、路由挂载
├── security_config.py       # CORS、API Key、公开路径、生产环境校验与简单限流
├── *_router.py              # 按业务边界拆分的 HTTP 路由模块
├── *_schemas.py             # 路由专用请求/响应结构
└── schemas.py               # 聊天等共享 API 结构
```

## 职责边界

- `main.py`: 维护 FastAPI app 的启动顺序、全局中间件、依赖注入和路由注册；避免继续塞入可独立测试的配置解析逻辑。
- `security_config.py`: 统一管理安全网关的纯配置逻辑，包括 CORS、API Key 提取、公开路径匹配、生产必需环境变量和内存限流器。
- `*_router.py`: 每个文件只暴露一个清晰业务域的路由，复杂业务应下沉到 `backend/services`、`backend/graph` 或对应领域模块。
- `schemas.py` / `*_schemas.py`: 只描述 API wire shape，不主动触发 IO 或业务计算。

## 依赖方向

`main.py` 可以依赖路由与轻量配置模块；路由可以依赖服务、图编排和数据适配器；服务层不应反向依赖 `backend/api/main.py`。

安全相关测试会直接引用 `main.py` 中的 `_parse_api_keys`、`_is_allowlisted_path`、`SimpleRateLimiter` 等兼容名。重构时可以移动实现，但必须保留这些导入别名，避免测试和历史内部调用断裂。

## 变更记录

- 2026-06-29: 抽出 `security_config.py`，让安全配置和限流逻辑脱离 `main.py`，降低应用装配文件体积。
