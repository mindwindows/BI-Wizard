#!/bin/sh
# Jenkins Env Validation 단계에서 쓴다(Linux 에이전트, POSIX sh).
#  1) .env.example 이 승인된 변수 목록(canonical names)과 같은지, Secret 값이 비어 있는지 검사한다.
#  2) compose.yml 이 쓰는 변수가 모두 .env.example 에 있는지 검사한다.
#  3) docker compose config/build 용 더미 값 env 파일을 만든다(기본 .env.ci, 비밀이 아닌 가짜 값, Git 제외).
# 사용: sh scripts/ci-validate-env.sh [출력파일]
# 변수를 추가/삭제하면 아래 REQUIRED(와 Secret이면 SECRETS)도 같은 변경에서 고친다.
set -eu

cd "$(dirname "$0")/.."

EXAMPLE=.env.example
COMPOSE=compose.yml
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

# 형식/기본값 규칙.
grep -Eq '^APP_BASE_PATH=(/[A-Za-z0-9._~-]+)*$' "$EXAMPLE" || fail "APP_BASE_PATH 형식(빈 값 또는 /경로, 뒤 / 금지)"
grep -Eq '^SUPERSET_APP_ROOT=(/[A-Za-z0-9._~-]+)*$' "$EXAMPLE" || fail "SUPERSET_APP_ROOT 형식(빈 값 또는 /경로, 뒤 / 금지)"
grep -Eq '^APP_PROXY_STRIP_PREFIX=false$' "$EXAMPLE" || fail "APP_PROXY_STRIP_PREFIX 기본값은 false 여야 합니다."

# compose.yml 이 쓰는 ${VAR} 는 모두 .env.example 에 있다.
for var in $(grep -o '\${[A-Za-z_][A-Za-z0-9_]*' "$COMPOSE" | sed 's/^\${//' | sort -u); do
  printf '%s\n' "$names" | grep -qx "$var" || fail "$COMPOSE 가 $EXAMPLE 에 없는 변수 $var 을(를) 씁니다."
done

# compose.yml 에 latest 태그와 down -v 가 없다.
if grep -Eq 'image:.*:latest' "$COMPOSE"; then fail "compose.yml 에 :latest 태그가 있습니다."; fi

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
