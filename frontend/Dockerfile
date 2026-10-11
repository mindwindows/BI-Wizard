# frontend 이미지: React 정적 빌드 + nginx. 경로(APP_BASE_PATH 등)는 이미지에 굽지 않고 시작 때 주입한다.
# Secret은 이 이미지에 넣지 않는다. apt-get은 쓰지 않는다.
FROM node:22.23.3-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts --no-audit --no-fund

# 테스트 스테이지: Jenkins의 Frontend Lint/Test가 `docker build --target test frontend`로 쓴다.
FROM deps AS test
COPY . .
RUN npm run lint && npm run typecheck && npm test

FROM deps AS build
COPY . .
RUN npm run build

# 실행 스테이지(기본 target): 마지막 스테이지다.
FROM nginx:1.28.3-alpine AS runtime
ENV NGINX_ENVSUBST_FILTER=^NGX_ \
    NGINX_ENTRYPOINT_LOCAL_RESOLVERS=1
COPY --from=build /app/dist /opt/web/dist
COPY nginx/templates/ /etc/nginx/templates/
COPY nginx/snippets/ /etc/nginx/snippets/
COPY --chmod=0755 nginx/docker-entrypoint.d/ /docker-entrypoint.d/
EXPOSE 80
