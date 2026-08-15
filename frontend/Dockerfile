FROM node:20-slim AS builder

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

# Vite inlines env vars at build time, not runtime — the browser can only
# reach the backend via its host-mapped port (container DNS names like
# "backend:8001" don't resolve from the browser), so this has to be passed
# in at build time to match whatever docker-compose.yml exposes it as.
ARG VITE_API_BASE_URL=http://localhost:8002
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

RUN npm run build

# -------- STAGE 2

FROM nginx:1.27-alpine AS runtime

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://localhost:80/ || exit 1
