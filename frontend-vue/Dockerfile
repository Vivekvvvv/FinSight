# FinSight Vue 前端 — 多阶段 Dockerfile
# Stage 1: build (node:20-alpine)  →  Stage 2: serve (nginx:alpine)

# ── Stage 1: Build ────────────────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

# build 期注入 API base (默认指向 Python FastAPI; 容器内推荐留空走同源 nginx 反代)
ARG VITE_API_BASE_URL=http://localhost:8000
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

# ── Stage 2: Serve ────────────────────────────────────────────────────────
FROM nginx:alpine AS runner

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

RUN chown -R nginx:nginx \
      /usr/share/nginx/html \
      /var/cache/nginx \
      /var/run \
      /etc/nginx/conf.d

USER nginx

EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=3s --retries=3 \
  CMD wget -qO- http://127.0.0.1:8080/ || exit 1
