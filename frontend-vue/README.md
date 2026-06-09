# frontend-vue (FinSight Vue 前端)

`frontend-vue/` 是当前默认前端。默认链路已经收敛为:

```text
Browser -> frontend-vue/nginx -> backend/FastAPI
```

旧 React 前端不再是默认运行入口。Spring Boot BFF 不再参与默认链路。

## 技术栈

- Vue 3.5 + `<script setup lang="ts">` + Composition API
- Vite 7 + @vitejs/plugin-vue 6
- Vue Router 4(history 模式)
- Pinia 2
- Tailwind 3.4
- axios
- vue-tsc 类型门禁 + ESLint 9 + eslint-plugin-vue

默认 dev 端口 **5174**, API 默认指向 **FastAPI 8000**。

## 已覆盖页面

| 路由 | 页面 | 后端依赖 |
|---|---|---|
| `/welcome` | 入口导航 | 无 |
| `/chat` | 智能对话 | `POST /chat/supervisor/stream` |
| `/dashboard/:symbol?` | 仪表盘 | `GET /api/dashboard*` |
| `/workbench` | 工作台 | portfolio / reports / tasks |
| `/rag-inspector` | RAG 诊断 | `GET /diagnostics/rag/*` |
| `/settings/plan` | 套餐对比 | `GET /api/plans` + `/api/me/entitlements` |
| `/watchlist` | 自选清单 | `GET/POST /api/user/watchlist*` |
| `/portfolio` | 持仓组合 | `GET /api/portfolio/summary` + positions |
| `/reports` | 报告库 | `GET /api/reports/index` + favorite |
| `/alerts` | 提醒中心 | `/api/subscriptions` + `/api/alerts/feed` |

## 启动与验证

```powershell
cd frontend-vue
npm install
npm run dev

npm run typecheck
npm run lint
npm run build
```

## API 后端

默认连接 Python FastAPI:

```text
http://127.0.0.1:8000
```

容器部署时推荐不设置 `VITE_API_BASE_URL`, 由 nginx 同源反代到 `backend:8000`。本地需要覆盖时可设置:

```powershell
VITE_API_BASE_URL=http://127.0.0.1:8000
```
