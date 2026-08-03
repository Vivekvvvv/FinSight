# FinSight Vue 前端 — 多阶段 Dockerfile
# Stage 1: build (node:20-alpine)  →  Stage 2: serve (nginx:alpine)

# ── Stage 1: Build ────────────────────────────────────────────────────────
ARG NODE_IMAGE=node:20-alpine@sha256:fb4cd12c85ee03686f6af5362a0b0d56d50c58a04632e6c0fb8363f609372293
ARG NGINX_IMAGE=nginx:alpine@sha256:4a73073bd557c65b759505da037898b61f1be6cbcc3c2c3aeac22d2a470c1752

FROM ${NODE_IMAGE} AS builder

WORKDIR /app

# build 期注入 API base (默认指向 Python FastAPI; 容器内推荐留空走同源 nginx 反代)
ARG VITE_API_BASE_URL=http://localhost:8000
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

# ── Stage 2: Serve ────────────────────────────────────────────────────────
FROM ${NGINX_IMAGE} AS runner

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

RUN chown -R nginx:nginx \
      /usr/share/nginx/html \
      /var/cache/nginx \
      /var/run \
      /run \
      /etc/nginx/conf.d

USER nginx

EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=3s --retries=3 \
  CMD wget -qO- http://127.0.0.1:8080/ || exit 1
