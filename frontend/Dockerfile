# syntax=docker/dockerfile:1

# ---- Build stage -------------------------------------------------------------
FROM node:22-alpine AS build
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY . .
RUN npm run build

# ---- Runtime stage -----------------------------------------------------------
FROM nginx:1.27-alpine AS runtime

# Upstream Django API; override at runtime, e.g. -e API_UPSTREAM=http://backend:8000
ENV API_UPSTREAM=http://api:8000

# The nginx image renders /etc/nginx/templates/*.template into /etc/nginx/conf.d/ via envsubst.
RUN rm -f /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -q -O /dev/null http://127.0.0.1/index.html || exit 1
