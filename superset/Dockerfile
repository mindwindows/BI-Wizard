# Superset 6.1.0 위에 PostgreSQL 드라이버와 고정 설정만 얹는다(Superset 내부 코드는 수정하지 않는다).
# 기본 이미지(lean)에는 PostgreSQL 드라이버가 없다.
# psycopg2-binary는 LGPL(예외 조항 포함)이라 이 Superset 이미지에만 쓰고 backend에는 쓰지 않는다.
FROM apache/superset:6.1.0

USER root
RUN uv pip install --python /app/.venv/bin/python --no-cache psycopg2-binary==2.9.13

COPY --chown=superset:superset superset_config.py /app/pythonpath/superset_config.py
COPY --chown=superset:superset --chmod=0755 init.sh ensure_admin.py readonly_uri.py /app/bi-wizard/

USER superset
