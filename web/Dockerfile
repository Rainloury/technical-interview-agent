# syntax=docker/dockerfile:1.7

FROM node:22-alpine AS build

WORKDIR /workspace

COPY package.json package-lock.json ./
RUN npm ci

COPY index.html tokens.css tsconfig.json vite.config.ts ./
COPY public ./public
COPY src ./src

# 浏览器通过同源 Nginx 代理调用 API。
ARG VITE_API_BASE_URL=
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
ARG VITE_GTM_ID=
ENV VITE_GTM_ID=$VITE_GTM_ID
ARG VITE_ANALYTICS_ENABLED=
ENV VITE_ANALYTICS_ENABLED=$VITE_ANALYTICS_ENABLED
RUN npm run build

FROM nginx:1.27-alpine

USER nginx

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY nginx-main.conf /etc/nginx/nginx.conf
COPY --from=build /workspace/dist /usr/share/nginx/html

EXPOSE 8080

HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
  CMD wget --quiet --tries=1 --spider http://127.0.0.1:8080/healthz || exit 1

STOPSIGNAL SIGQUIT
