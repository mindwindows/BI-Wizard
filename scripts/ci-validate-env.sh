#!/bin/sh
# Jenkins Env Validation 단계에서 쓴다(Linux 에이전트, POSIX sh).
#  1) .env.example 이 승인된 변수 목록(canonical names)과 같은지, Secret 값이 비어 있는지 검사한다.
#  2) compose.yml 이 쓰는 변수가 모두 .env.example 에 있는지 검사한다.
#  3) backend/bootstrap/roles.sql 정적 규칙(psql 보간은 비밀번호 리터럴 두 곳만, 식별자 보간 금지)을 검사한다.
#     (backend/.dockerignore가 bootstrap/을 test 스테이지에서 제외하므로 pytest로는 검사할 수 없다.)
#  4) 실행 파일(compose.yml, Jenkinsfile, scripts/*.bat)에 파괴적 명령이 없는지 검사한다.
#  5) docker compose config/build 용 더미 값 env 파일을 만든다(기본 .env.ci, 비밀이 아닌 가짜 값, Git 제외).
# 사용: sh scripts/ci-validate-env.sh [출력파일]
# 변수를 추가/삭제하면 아래 REQUIRED(와 Secret이면 SECRETS)도 같은 변경에서 고친다.
set -eu

cd "$(dirname "$0")/.."

EXAMPLE=.env.example
COMPOSE=compose.yml
ROLES=backend/bootstrap/roles.sql
OUT="${1:-.env.ci}"

REQUIRED="APP_NAME APP_ENV APP_DEBUG APP_BASE_PATH APP_PROXY_STRIP_PREFIX \
FRONTEND_HOST FRONTEND_PORT BACKEND_HOST BACKEND_PORT \
POSTGRES_HOST POSTGRES_PORT POSTGRES_DB POSTGRES_USER POSTGRES_PASSWORD POSTGRES_READONLY_PASSWORD \
SUPERSET_APP_ROOT SUPERSET_DB_PASSWORD SUPERSET_SECRET_KEY GUEST_TOKEN_JWT_SECRET \
SUPERSET_ADMIN_USER SUPERSET_ADMIN_PASSWORD LOG_LEVEL TZ"
SECRETS="POSTGRES_PASSWORD POSTGRES_READONLY_PASSWORD SUPERSET_DB_PASSWORD SUPERSET_SECRET_KEY \
GUEST_TOKEN_JWT_SECRET SUPERSET_ADMIN_PASSWORD"

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

# POSTGRES_USER는 상수 역할 이름과 같을 수 없다(db-bootstrap이 슈퍼유저 비밀번호를 덮어쓰고 읽기 전용을 건다).
case "$(value_of POSTGRES_USER)" in
  bi_readonly | superset_meta) fail "POSTGRES_USER는 bi_readonly, superset_meta와 같은 이름일 수 없습니다." ;;
esac

# compose.yml 이 쓰는 ${VAR} 는 모두 .env.example 에 있다.
for var in $(grep -o '\${[A-Za-z_][A-Za-z0-9_]*' "$COMPOSE" | sed 's/^\${//' | sort -u); do
  printf '%s\n' "$names" | grep -qx "$var" || fail "$COMPOSE 가 $EXAMPLE 에 없는 변수 $var 을(를) 씁니다."
done

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
  # :'변수' 인용은 :'ro_pw' 와 :'meta_pw' 가 각각 정확히 한 번(비밀번호 리터럴 두 곳)이다.
  quoted="$(printf '%s\n' "$body" | grep -o ":'[A-Za-z_][A-Za-z0-9_]*'" || true)"
  for q in $quoted; do
    case "$q" in
      ":'ro_pw'" | ":'meta_pw'") ;;
      *) fail "$ROLES 에 허용되지 않은 psql 인용 보간 $q" ;;
    esac
  done
  [ "$(printf '%s\n' "$quoted" | grep -c ":'ro_pw'" || true)" = "1" ] || fail "$ROLES 의 :'ro_pw' 는 정확히 한 번이어야 합니다."
  [ "$(printf '%s\n' "$quoted" | grep -c ":'meta_pw'" || true)" = "1" ] || fail "$ROLES 의 :'meta_pw' 는 정확히 한 번이어야 합니다."
  # 식별자 보간(:"var"), 구문 보간(:var), format(), %I 금지. ('::' 형변환은 제외한다)
  if printf '%s\n' "$body" | grep -Eq ':"[A-Za-z_]'; then fail "$ROLES 에 식별자 보간 :\"var\" 이 있습니다."; fi
  if printf '%s\n' "$body" | grep -Eq "(^|[^:']):[A-Za-z_]"; then fail "$ROLES 에 구문 보간 :var 이 있습니다."; fi
  if printf '%s\n' "$body" | grep -Eiq 'format[[:space:]]*\(|%I'; then fail "$ROLES 에 format( 또는 %I 가 있습니다."; fi
  # 역할/DB 이름은 상수 리터럴이고, 비밀번호는 \getenv 로 읽는다.
  for needle in \
    "CREATE ROLE bi_readonly " \
    "CREATE ROLE superset_meta " \
    "CREATE DATABASE superset OWNER superset_meta" \
    "ALTER ROLE bi_readonly PASSWORD :'ro_pw'" \
    "ALTER ROLE superset_meta PASSWORD :'meta_pw'" \
    "ALTER ROLE bi_readonly SET default_transaction_read_only = on" \
    "\\getenv ro_pw POSTGRES_READONLY_PASSWORD" \
    "\\getenv meta_pw SUPERSET_DB_PASSWORD" \
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
