#!/bin/sh
# Jenkins Env Validation 단계에서 쓴다(Linux 에이전트, POSIX sh).
#  1) .env.example 이 승인된 변수 목록(canonical names)과 같은지, Secret 값이 비어 있는지 검사한다.
#  2) compose.yml 이 쓰는 변수가 모두 .env.example 에 있는지 검사한다.
#  3) backend/bootstrap/roles.sql 정적 규칙(psql 보간은 비밀번호 리터럴 4곳만, 식별자 보간 금지, 이름은 상수)을 검사한다.
#     (backend/.dockerignore가 bootstrap/을 test 스테이지에서 제외하므로 pytest로는 검사할 수 없다.)
#  4) 실행 파일(compose.yml, Jenkinsfile, scripts/*.bat)에 파괴적 명령이 없는지 검사한다.
#  5) 계정 분리: backend/migrate 서비스에 슈퍼유저 변수를 넘기지 않고, 인증 스텁 스위치(AUTH_STUB_ENABLED)는
#     기본 false이며 true이면 APP_ENV가 local 또는 test여야 한다.
#  6) docker compose config/build 용 더미 값 env 파일을 만든다(기본 .env.ci, 비밀이 아닌 가짜 값, Git 제외).
# 사용: sh scripts/ci-validate-env.sh [출력파일]
# 이 검사의 네거티브 케이스 시험: sh scripts/test-ci-validate-env.sh
# 변수를 추가/삭제하면 아래 REQUIRED(와 Secret이면 SECRETS)도 같은 변경에서 고친다.
set -eu

cd "$(dirname "$0")/.."

EXAMPLE=.env.example
COMPOSE=compose.yml
ROLES=backend/bootstrap/roles.sql
OUT="${1:-.env.ci}"

REQUIRED="APP_NAME APP_ENV APP_DEBUG AUTH_STUB_ENABLED APP_BASE_PATH APP_PROXY_STRIP_PREFIX \
FRONTEND_HOST FRONTEND_PORT BACKEND_HOST BACKEND_PORT \
POSTGRES_HOST POSTGRES_PORT POSTGRES_DB POSTGRES_USER POSTGRES_PASSWORD \
POSTGRES_APP_PASSWORD POSTGRES_OWNER_PASSWORD POSTGRES_READONLY_PASSWORD \
SUPERSET_APP_ROOT SUPERSET_DB_PASSWORD SUPERSET_SECRET_KEY GUEST_TOKEN_JWT_SECRET \
SUPERSET_ADMIN_USER SUPERSET_ADMIN_PASSWORD LOG_LEVEL TZ"
SECRETS="POSTGRES_PASSWORD POSTGRES_APP_PASSWORD POSTGRES_OWNER_PASSWORD POSTGRES_READONLY_PASSWORD \
SUPERSET_DB_PASSWORD SUPERSET_SECRET_KEY GUEST_TOKEN_JWT_SECRET SUPERSET_ADMIN_PASSWORD"

failed=0
fail() {
  echo "[env-validation] 실패: $*" >&2
  failed=1
}

[ -f "$EXAMPLE" ] || { echo "[env-validation] $EXAMPLE 이 없습니다." >&2; exit 1; }
[ -f "$COMPOSE" ] || { echo "[env-validation] $COMPOSE 가 없습니다." >&2; exit 1; }

names="$(grep -E '^[A-Za-z_][A-Za-z0-9_]*=' "$EXAMPLE" | cut -d= -f1)"

# 필수 이름이 모두 있다.
for name in $REQUIRED; do
  printf '%s\n' "$names" | grep -qx "$name" || fail "$EXAMPLE 에 $name 이(가) 없습니다."
done

# 승인되지 않은 이름이 없다(같은 의미의 새 이름, Azure OpenAI 변수 등).
for name in $names; do
  case " $REQUIRED " in
    *" $name "*) ;;
    *) fail "$EXAMPLE 에 승인 목록에 없는 변수 $name 이(가) 있습니다." ;;
  esac
done

# 중복 정의가 없다.
duplicates="$(printf '%s\n' "$names" | sort | uniq -d)"
[ -z "$duplicates" ] || fail "중복 정의된 변수: $duplicates"

# Secret 값은 비어 있다.
for name in $SECRETS; do
  value="$(grep -E "^$name=" "$EXAMPLE" | head -n 1 | cut -d= -f2-)"
  [ -z "$value" ] || fail "$name 은(는) $EXAMPLE 에서 값이 비어 있어야 합니다."
done

# 경로 값 형식: 앞 '/' 필수, 뒤 '/' 금지, 허용 문자만, '//' 금지, '.'/'..' 세그먼트 금지(case로 값 전체를 검사한다).
valid_path() {
  v="$1"
  case "$v" in /*) ;; *) return 1 ;; esac
  case "$v" in */) return 1 ;; esac
  case "$v" in *[!A-Za-z0-9._~/-]*) return 1 ;; esac
  case "$v" in *//*) return 1 ;; esac
  case "$v" in */. | */./* | */.. | */../*) return 1 ;; esac
  return 0
}
value_of() { grep -E "^$1=" "$EXAMPLE" | head -n 1 | cut -d= -f2-; }

# 빈 값(루트 배포) 예외는 APP_BASE_PATH에만 있다. SUPERSET_APP_ROOT는 비어 있을 수 없다.
base="$(value_of APP_BASE_PATH)"
if [ -n "$base" ] && ! valid_path "$base"; then fail "APP_BASE_PATH 형식(빈 값 또는 /경로, 뒤 / 와 . .. 세그먼트 금지)"; fi
superset_root="$(value_of SUPERSET_APP_ROOT)"
if [ -z "$superset_root" ] || ! valid_path "$superset_root"; then fail "SUPERSET_APP_ROOT 형식(/경로, 빈 값 불가)"; fi
grep -Eq '^APP_PROXY_STRIP_PREFIX=false$' "$EXAMPLE" || fail "APP_PROXY_STRIP_PREFIX 기본값은 false 여야 합니다."

# POSTGRES_USER는 상수 역할 이름과 같을 수 없다(db-bootstrap이 슈퍼유저 비밀번호를 덮어쓰고 권한을 바꾼다).
case "$(value_of POSTGRES_USER)" in
  bi_readonly | superset_meta | bi_owner | bi_app)
    fail "POSTGRES_USER는 bi_readonly, superset_meta, bi_owner, bi_app과 같은 이름일 수 없습니다."
    ;;
esac

# 인증 스텁 스위치(bi-review 7-5): true/false만 허용한다. true이면 APP_ENV가 local 또는 test여야 한다.
# 커밋되는 .env.example의 기본값은 false여야 한다(fail-open 방지).
stub="$(value_of AUTH_STUB_ENABLED)"
case "$stub" in
  true | false) ;;
  *) fail "AUTH_STUB_ENABLED는 true 또는 false여야 합니다." ;;
esac
if [ "$stub" = "true" ]; then
  case "$(value_of APP_ENV)" in
    local | test) ;;
    *) fail "AUTH_STUB_ENABLED=true는 APP_ENV가 local 또는 test일 때만 허용됩니다." ;;
  esac
fi
[ "$stub" = "false" ] || fail "$EXAMPLE 의 AUTH_STUB_ENABLED 기본값은 false 여야 합니다."

# compose.yml 이 쓰는 ${VAR} 는 모두 .env.example 에 있다.
for var in $(grep -o '\${[A-Za-z_][A-Za-z0-9_]*' "$COMPOSE" | sed 's/^\${//' | sort -u); do
  printf '%s\n' "$names" | grep -qx "$var" || fail "$COMPOSE 가 $EXAMPLE 에 없는 변수 $var 을(를) 씁니다."
done

# compose 서비스 블록(서비스 이름 한 줄 아래부터 다음 서비스 직전까지).
service_block() {
  awk -v svc="$1" '
    $0 ~ ("^  " svc ":[[:space:]]*$") { on = 1; next }
    on && /^  [A-Za-z0-9_-]+:/ { on = 0 }
    on && /^[^ #]/ { on = 0 }
    on { print }
  ' "$COMPOSE"
}

# 계정 분리(03b 3-2): 이미지 슈퍼유저 변수는 postgres/db-bootstrap/postgres-test만 쓴다. backend와 migrate는
# 자기 비밀번호만 받는다(컨테이너마다 필요한 변수만 전달). frontend에는 DB 변수를 넘기지 않는다.
for forbidden in POSTGRES_USER POSTGRES_PASSWORD POSTGRES_OWNER_PASSWORD; do
  if service_block backend | grep -Eq "^[[:space:]]+$forbidden:"; then
    fail "backend 서비스에 $forbidden 을(를) 넘기면 안 됩니다(bi_app 전용)."
  fi
done
for forbidden in POSTGRES_USER POSTGRES_PASSWORD POSTGRES_APP_PASSWORD; do
  if service_block migrate | grep -Eq "^[[:space:]]+$forbidden:"; then
    fail "migrate 서비스에 $forbidden 을(를) 넘기면 안 됩니다(bi_owner 전용)."
  fi
done
if ! service_block backend | grep -Eq '^[[:space:]]+POSTGRES_APP_PASSWORD:'; then
  fail "backend 서비스에 POSTGRES_APP_PASSWORD 가 없습니다."
fi
if ! service_block migrate | grep -Eq '^[[:space:]]+POSTGRES_OWNER_PASSWORD:'; then
  fail "migrate 서비스에 POSTGRES_OWNER_PASSWORD 가 없습니다."
fi
if ! service_block backend | grep -Eq '^[[:space:]]+AUTH_STUB_ENABLED:'; then
  fail "backend 서비스에 AUTH_STUB_ENABLED 가 없습니다."
fi
if service_block frontend | grep -Eq '^[[:space:]]+[A-Z_]*(POSTGRES|PASSWORD|SECRET|AUTH_STUB)[A-Z_]*:'; then
  fail "frontend 서비스에 DB/Secret/스텁 변수를 넘기면 안 됩니다."
fi

# compose.yml 에 latest 태그가 없다.
if grep -Eq 'image:.*:latest' "$COMPOSE"; then fail "compose.yml 에 :latest 태그가 있습니다."; fi

# 실행 파일에 파괴적 명령이 없다(문서의 금지 문구는 검사하지 않는다. 이 스크립트 자신도 제외한다).
for file in "$COMPOSE" Jenkinsfile scripts/*.bat; do
  [ -f "$file" ] || continue
  if grep -Eiq 'down[[:space:]]+(-v|--volumes)|volume[[:space:]]+(rm|prune)|system[[:space:]]+prune|rm[[:space:]]+-rf|git[[:space:]]+clean[[:space:]]+-fdx|git[[:space:]]+reset[[:space:]]+--hard' "$file"; then
    fail "$file 에 파괴적 명령(down -v, volume rm/prune, system prune, rm -rf 등)이 있습니다."
  fi
done

# roles.sql 정적 규칙(bi-review 항목 3 예외 2).
if [ ! -f "$ROLES" ]; then
  fail "$ROLES 가 없습니다."
else
  # 주석(-- ...)을 뗀 본문만 검사한다.
  body="$(sed 's/--.*$//' "$ROLES")"
  # :'변수' 인용은 비밀번호 리터럴 4곳(ro_pw, meta_pw, app_pw, owner_pw)에만, 각각 정확히 한 번 쓴다.
  quoted="$(printf '%s\n' "$body" | grep -o ":'[A-Za-z_][A-Za-z0-9_]*'" || true)"
  for q in $quoted; do
    case "$q" in
      ":'ro_pw'" | ":'meta_pw'" | ":'app_pw'" | ":'owner_pw'") ;;
      *) fail "$ROLES 에 허용되지 않은 psql 인용 보간 $q" ;;
    esac
  done
  for v in ro_pw meta_pw app_pw owner_pw; do
    [ "$(printf '%s\n' "$quoted" | grep -c ":'$v'" || true)" = "1" ] || fail "$ROLES 의 :'$v' 는 정확히 한 번이어야 합니다."
  done
  # 인용 보간은 모두 `PASSWORD :'var'` 형태(비밀번호 리터럴)여야 한다.
  [ "$(printf '%s\n' "$body" | grep -Eoc "PASSWORD :'[A-Za-z_][A-Za-z0-9_]*'" || true)" = "4" ] || fail "$ROLES 의 psql 인용 보간은 ALTER ROLE ... PASSWORD :'var' 4곳뿐이어야 합니다."
  # \getenv 는 비밀번호 변수 4개뿐이다.
  [ "$(printf '%s\n' "$body" | grep -c '^[[:space:]]*\\getenv')" = "4" ] || fail "$ROLES 의 \\getenv 는 비밀번호 변수 4개뿐이어야 합니다."
  # 식별자 보간(:"var"), 구문 보간(:var), format(), %I 금지. ('::' 형변환은 제외한다)
  if printf '%s\n' "$body" | grep -Eq ':"[A-Za-z_]'; then fail "$ROLES 에 식별자 보간 :\"var\" 이 있습니다."; fi
  if printf '%s\n' "$body" | grep -Eq "(^|[^:']):[A-Za-z_]"; then fail "$ROLES 에 구문 보간 :var 이 있습니다."; fi
  if printf '%s\n' "$body" | grep -Eiq 'format[[:space:]]*\(|%I'; then fail "$ROLES 에 format( 또는 %I 가 있습니다."; fi
  # 역할/DB/schema 이름은 상수 리터럴이고, 비밀번호는 \getenv 로 읽는다.
  for needle in \
    "CREATE ROLE bi_readonly " \
    "CREATE ROLE superset_meta " \
    "CREATE ROLE bi_owner LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE" \
    "CREATE ROLE bi_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE" \
    "CREATE DATABASE superset OWNER superset_meta" \
    "ALTER ROLE bi_readonly PASSWORD :'ro_pw'" \
    "ALTER ROLE superset_meta PASSWORD :'meta_pw'" \
    "ALTER ROLE bi_owner PASSWORD :'owner_pw'" \
    "ALTER ROLE bi_app PASSWORD :'app_pw'" \
    "ALTER ROLE bi_readonly SET default_transaction_read_only = on" \
    "ALTER ROLE bi_readonly SET statement_timeout = '30s'" \
    "CREATE SCHEMA IF NOT EXISTS bi_data AUTHORIZATION bi_owner" \
    "ALTER SCHEMA bi_data OWNER TO bi_owner" \
    "REVOKE ALL ON SCHEMA bi_data FROM PUBLIC" \
    "GRANT bi_app TO bi_owner WITH INHERIT TRUE, SET FALSE" \
    "GRANT CREATE ON SCHEMA public TO bi_owner" \
    "REVOKE CREATE ON SCHEMA public FROM PUBLIC" \
    "ALTER TABLE public.alembic_version OWNER TO bi_owner" \
    "\\getenv ro_pw POSTGRES_READONLY_PASSWORD" \
    "\\getenv meta_pw SUPERSET_DB_PASSWORD" \
    "\\getenv app_pw POSTGRES_APP_PASSWORD" \
    "\\getenv owner_pw POSTGRES_OWNER_PASSWORD" \
    "\\set ON_ERROR_STOP on" \
    "SET LOCAL log_min_error_statement = panic"; do
    printf '%s\n' "$body" | grep -qF -- "$needle" || fail "$ROLES 에 필수 문장이 없습니다: $needle"
  done
fi

if [ "$failed" -ne 0 ]; then
  echo "[env-validation] 검증 실패" >&2
  exit 1
fi

# CI용 더미 env 파일: Secret 자리에 비밀이 아닌 가짜 값을 채운다.
cp "$EXAMPLE" "$OUT"
for name in $SECRETS; do
  sed -i "s/^$name=\$/$name=ci-dummy-not-a-secret/" "$OUT"
done
echo "[env-validation] 통과. CI용 env 파일 생성: $OUT (더미 값)"
