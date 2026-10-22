# syntax=docker/dockerfile:1.7

FROM node:22-alpine AS build

WORKDIR /workspace

COPY package.json package-lock.json ./
RUN npm ci

COPY index.html tokens.css tsconfig.json vite.config.ts ./
COPY src ./src

# The browser calls the API through the same-origin Nginx proxy.
ARG VITE_API_BASE_URL=
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build

FROM nginx:1.27-alpine

USER nginx

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /workspace/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
  CMD wget --quiet --tries=1 --spider http://127.0.0.1/healthz || exit 1

STOPSIGNAL SIGQUIT
