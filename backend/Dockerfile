# backend 이미지: FastAPI + Alembic. migrate 서비스가 같은 이미지를 재사용한다.
# apt-get은 쓰지 않는다. 의존성은 requirements*.txt에 고정되어 있다.
FROM python:3.12.15-slim-bookworm AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /app

# 테스트 스테이지: Jenkins의 Backend Lint/Test가 `docker build --target test backend`로 쓴다.
FROM base AS test
COPY requirements-dev.txt ./
RUN pip install -r requirements-dev.txt
COPY . .
RUN ruff check . && ruff format --check . && pytest

# 실행 스테이지(기본 target): 마지막 스테이지다.
FROM base AS runtime
RUN groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app
COPY requirements.txt ./
RUN pip install -r requirements.txt
COPY alembic.ini healthcheck.py ./
COPY app ./app
COPY migrations ./migrations
USER app
EXPOSE 8000
CMD ["python", "-m", "app"]
