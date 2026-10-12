#!/bin/sh
# Jenkins Env Validation 단계에서 쓴다(Linux 에이전트, POSIX sh).
#  1) .env.example 이 승인된 변수 목록(canonical names)과 같은지, Secret 값이 비어 있는지 검사한다.
#  2) compose.yml 이 쓰는 변수가 모두 .env.example 에 있는지 검사한다.
#  3) backend/bootstrap/roles.sql 정적 규칙(psql 보간은 비밀번호 리터럴 4곳만, 식별자 보간 금지, 이름은 상수)을 검사한다.
#     (backend/.dockerignore가 bootstrap/을 test 스테이지에서 제외하므로 pytest로는 검사할 수 없다.)
#  4) 실행 파일(compose.yml, Jenkinsfile, scripts/*.bat)에 파괴적 명령이 없는지 검사한다.
#  5) 계정 분리: backend/migrate 서비스에 슈퍼유저 변수를 넘기지 않고, 인증 스텁 스위치(AUTH_STUB_ENABLED)는
#     기본 false이며 true이면 APP_ENV가 local 또는 test여야 한다.
#     Superset 계정(EW-3): 관리자·서비스·발급 전용 계정 이름은 비어 있지 않고 서로 달라야 하며, superset-init은 migrate
#     완료를 기다리고, 서비스·발급 비밀번호는 backend와 superset-init에만 전달한다.
#     guest token(EW-4, AP-1): backend와 migrate는 GUEST_TOKEN_JWT_SECRET을 받지 않고(직접 서명 금지) backend/app 코드에도 이
#     이름이 없다. superset/superset_config.py는 GUEST_ROLE_NAME을 bi_guest로 두고 PUBLIC_ROLE_LIKE와
#     GUEST_TOKEN_JWT_EXP_SECONDS(입장권 유효 시간, 기본 300초 유지, EW-5)를 설정하지 않는다.
#  6) AG Grid Enterprise 혼입 방지(03b 15절): frontend/package.json과 package-lock.json에 ag-grid-enterprise, ag-charts-enterprise가
#     없고 frontend/src에도 import하지 않으며, frontend 의존성은 정확한 버전으로 고정한다(^ ~ * latest 범위 금지).
#  7) docker compose config/build 용 더미 값 env 파일을 만든다(기본 .env.ci, 비밀이 아닌 가짜 값, Git 제외).
# 사용: sh scripts/ci-validate-env.sh [출력파일]
# 이 검사의 네거티브 케이스 시험: sh scripts/test-ci-validate-env.sh
# 변수를 추가/삭제하면 아래 REQUIRED(와 Secret이면 SECRETS)도 같은 변경에서 고친다.
set -eu

cd "$(dirname "$0")/.."

EXAMPLE=.env.example
COMPOSE=compose.yml
ROLES=backend/bootstrap/roles.sql
SUPERSET_CONFIG=superset/superset_config.py
OUT="${1:-.env.ci}"

REQUIRED="APP_NAME APP_ENV APP_DEBUG AUTH_STUB_ENABLED APP_BASE_PATH APP_PROXY_STRIP_PREFIX \
FRONTEND_HOST FRONTEND_PORT BACKEND_HOST BACKEND_PORT \
POSTGRES_HOST POSTGRES_PORT POSTGRES_DB POSTGRES_USER POSTGRES_PASSWORD \
POSTGRES_APP_PASSWORD POSTGRES_OWNER_PASSWORD POSTGRES_READONLY_PASSWORD \
SUPERSET_APP_ROOT SUPERSET_DB_PASSWORD SUPERSET_SECRET_KEY GUEST_TOKEN_JWT_SECRET \
SUPERSET_ADMIN_USER SUPERSET_ADMIN_PASSWORD \
SUPERSET_SERVICE_USER SUPERSET_SERVICE_PASSWORD SUPERSET_GUEST_ISSUER_USER SUPERSET_GUEST_ISSUER_PASSWORD \
LOG_LEVEL TZ"
SECRETS="POSTGRES_PASSWORD POSTGRES_APP_PASSWORD POSTGRES_OWNER_PASSWORD POSTGRES_READONLY_PASSWORD \
SUPERSET_DB_PASSWORD SUPERSET_SECRET_KEY GUEST_TOKEN_JWT_SECRET SUPERSET_ADMIN_PASSWORD \
SUPERSET_SERVICE_PASSWORD SUPERSET_GUEST_ISSUER_PASSWORD"

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

# Superset 계정 이름(관리자, 서비스, 발급 전용)은 비어 있지 않고 서로 달라야 한다(같으면 superset-init이 기존 계정의 역할을
# 덮어쓴다. 특히 관리자와 같으면 관리자 권한을 잃는다).
# 비교는 대소문자를 무시한다(FAB auth_username_ci가 find_user를 대소문자 무시로 비교하므로 Admin과 admin은 같은 계정이다).
# 여기서는 ASCII만 소문자로 바꾼다. 비ASCII 이름의 비교는 런타임(superset/ensure_accounts.py의 casefold)이 최종 검증한다.
lower() { printf '%s' "$1" | tr '[:upper:]' '[:lower:]'; }
admin_user="$(lower "$(value_of SUPERSET_ADMIN_USER)")"
service_user="$(lower "$(value_of SUPERSET_SERVICE_USER)")"
issuer_user="$(lower "$(value_of SUPERSET_GUEST_ISSUER_USER)")"
for account in "$admin_user" "$service_user" "$issuer_user"; do
  [ -n "$account" ] || fail "SUPERSET_ADMIN_USER, SUPERSET_SERVICE_USER, SUPERSET_GUEST_ISSUER_USER는 비어 있을 수 없습니다."
done
if [ "$admin_user" = "$service_user" ] || [ "$admin_user" = "$issuer_user" ] || [ "$service_user" = "$issuer_user" ]; then
  fail "SUPERSET_ADMIN_USER, SUPERSET_SERVICE_USER, SUPERSET_GUEST_ISSUER_USER는 서로 달라야 합니다."
fi

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

# compose 서비스 블록(서비스 이름 한 줄 아래부터 다음 서비스 직전까지). 이 아래 검사들은 compose.yml이 block 스타일 YAML
# (서비스는 2칸, 키는 4칸·6칸 들여쓰기, flow 스타일 `{}`/`[]`로 환경변수를 쓰지 않음)이라는 전제에서 줄 단위로 검사한다.
service_block() {
  awk -v svc="$1" '
    $0 ~ ("^  " svc ":[[:space:]]*$") { on = 1; next }
    on && /^  [A-Za-z0-9_-]+:/ { on = 0 }
    on && /^[^ #]/ { on = 0 }
    on { print }
  ' "$COMPOSE"
}

# 주석 줄을 뗀 서비스 블록(주석에 변수 이름이 나와도 위반으로 보지 않는다).
service_code() { service_block "$1" | grep -Ev '^[[:space:]]*#' || true; }

# 계정 분리(03b 3-2): 이미지 슈퍼유저 변수는 postgres/db-bootstrap/postgres-test만 쓴다. backend와 migrate는
# 자기 비밀번호만 받는다(컨테이너마다 필요한 변수만 전달). frontend에는 DB 변수를 넘기지 않는다.
# 금지: env_file(전체 .env 전달), `NAME:` 맵 문법, `- NAME=값`/`- NAME` 리스트 문법, ${NAME} 참조.
check_forbidden_vars() { # 서비스 이름, 금지 변수 이름들, 설명
  svc="$1"; shift
  note="$1"; shift
  code="$(service_code "$svc")"
  if printf '%s\n' "$code" | grep -Eq '^[[:space:]]+env_file[[:space:]]*:'; then
    fail "$svc 서비스에 env_file 을(를) 쓰면 안 됩니다(전체 .env 전달 금지, 필요한 변수만 environment 로 전달)."
  fi
  for forbidden in "$@"; do
    if printf '%s\n' "$code" | grep -Eq "^[[:space:]]+$forbidden[[:space:]]*:"; then
      fail "$svc 서비스에 $forbidden 을(를) 넘기면 안 됩니다($note)."
    fi
    if printf '%s\n' "$code" | grep -Eq "^[[:space:]]+-[[:space:]]*[\"']?$forbidden([=\"'[:space:]]|\$)"; then
      fail "$svc 서비스에 리스트 문법으로 $forbidden 을(를) 넘기면 안 됩니다($note)."
    fi
    if printf '%s\n' "$code" | grep -Eq "\\$\\{?$forbidden([^A-Za-z0-9_]|\$)"; then
      fail "$svc 서비스가 \${$forbidden} 을(를) 참조하면 안 됩니다($note)."
    fi
  done
}
check_forbidden_vars backend "bi_app 전용" POSTGRES_USER POSTGRES_PASSWORD POSTGRES_OWNER_PASSWORD
check_forbidden_vars migrate "bi_owner 전용" POSTGRES_USER POSTGRES_PASSWORD POSTGRES_APP_PASSWORD
# guest token 직접 서명 금지(08 §4, AP-1): 훅은 발급 API 경로에서만 불리므로 서명 비밀을 가진 쪽이 토큰을 직접 만들면
# 훅(rls·리소스 검사)을 우회한다. 비밀은 superset과 superset-init만 받는다.
check_forbidden_vars backend "guest token 직접 서명 금지: 서명 비밀은 superset과 superset-init만 받습니다" GUEST_TOKEN_JWT_SECRET
check_forbidden_vars migrate "guest token 직접 서명 금지: 서명 비밀은 superset과 superset-init만 받습니다" GUEST_TOKEN_JWT_SECRET
if [ -d backend/app ] && grep -rIq 'GUEST_TOKEN_JWT_SECRET' backend/app; then
  fail "backend/app 코드가 GUEST_TOKEN_JWT_SECRET 을(를) 참조합니다(guest token 직접 서명 금지)."
fi
if [ ! -f "$SUPERSET_CONFIG" ]; then
  fail "$SUPERSET_CONFIG 가 없습니다."
else
  grep -Eq '^GUEST_ROLE_NAME = "bi_guest"[[:space:]]*$' "$SUPERSET_CONFIG" || fail "$SUPERSET_CONFIG 의 GUEST_ROLE_NAME 은 \"bi_guest\" 여야 합니다."
  grep -Eq '^GUEST_TOKEN_VALIDATOR_HOOK = [A-Za-z_]' "$SUPERSET_CONFIG" || fail "$SUPERSET_CONFIG 에 GUEST_TOKEN_VALIDATOR_HOOK 설정이 없습니다."
  if grep -Eq '^[[:space:]]*PUBLIC_ROLE_LIKE[[:space:]]*(:[^=]*)?=' "$SUPERSET_CONFIG"; then
    fail "$SUPERSET_CONFIG 에 PUBLIC_ROLE_LIKE 를 설정하면 안 됩니다(Public 권한 0개 유지)."
  fi
  # 입장권 유효 시간(03b 12-1 ②): 이 파일이 GUEST_TOKEN_JWT_EXP_SECONDS 를 재정의하면 안 된다(Superset 기본 300초 유지).
  # 주석 줄만 제외하고 이름이 나오면 모두 실패시킨다(대입, 딕셔너리 갱신 등 우회 포함). 실제 적용값은 ensure_roles.py 가 300인지 확인한다.
  if grep -Ev '^[[:space:]]*#' "$SUPERSET_CONFIG" | grep -q 'GUEST_TOKEN_JWT_EXP_SECONDS'; then
    fail "$SUPERSET_CONFIG 가 GUEST_TOKEN_JWT_EXP_SECONDS 를 재정의합니다(입장권 유효 시간은 Superset 기본 300초 유지, 변경은 사전 승인과 bi_roles.GUEST_TOKEN_EXP_SECONDS 동시 변경)."
  fi
fi
if ! service_block backend | grep -Eq '^[[:space:]]+POSTGRES_APP_PASSWORD:'; then
  fail "backend 서비스에 POSTGRES_APP_PASSWORD 가 없습니다."
fi
if ! service_block migrate | grep -Eq '^[[:space:]]+POSTGRES_OWNER_PASSWORD:'; then
  fail "migrate 서비스에 POSTGRES_OWNER_PASSWORD 가 없습니다."
fi
if ! service_block backend | grep -Eq '^[[:space:]]+AUTH_STUB_ENABLED:'; then
  fail "backend 서비스에 AUTH_STUB_ENABLED 가 없습니다."
fi
# Superset 서비스·발급 계정(EW-3): backend(사용)와 superset-init(생성)만 받고, 모두 `${VAR:?메시지}` 필수 형태여야 한다
# (누락을 compose 단계에서 막는다). backend에는 SUPERSET_APP_ROOT도 같은 형태로 있어야 한다.
require_strict() { # 서비스 이름, 변수 이름
  service_code "$1" | grep -Eq "^[[:space:]]+$2:[[:space:]]*\\\$\{$2:\?" ||
    fail "$1 서비스의 $2 가 \${$2:?…} 필수 형태가 아닙니다(없거나 필수 처리가 빠졌습니다)."
}
for var in SUPERSET_SERVICE_USER SUPERSET_SERVICE_PASSWORD SUPERSET_GUEST_ISSUER_USER SUPERSET_GUEST_ISSUER_PASSWORD; do
  for svc in backend superset-init; do
    service_block "$svc" | grep -Eq "^[[:space:]]+$var:" || fail "$svc 서비스에 $var 가 없습니다."
    require_strict "$svc" "$var"
  done
done
if ! service_block backend | grep -Eq '^[[:space:]]+SUPERSET_APP_ROOT:'; then
  fail "backend 서비스에 SUPERSET_APP_ROOT 가 없습니다."
fi
require_strict backend SUPERSET_APP_ROOT
for svc in superset migrate db-bootstrap postgres postgres-test; do
  check_forbidden_vars "$svc" "Superset 서비스·발급 계정은 backend와 superset-init만 받습니다" \
    SUPERSET_SERVICE_USER SUPERSET_SERVICE_PASSWORD SUPERSET_GUEST_ISSUER_USER SUPERSET_GUEST_ISSUER_PASSWORD
done
# superset-init은 migrate가 성공 완료(service_completed_successfully)될 때까지 기다린다(bi_readonly의 bi_data USAGE는
# 마이그레이션 0002가 준다). 주석을 뗀 코드에서 `migrate:` 바로 다음 줄이 그 조건이어야 한다.
# migrate가 superset-init에 의존하면 순환이므로 금지한다.
if ! service_code superset-init | grep -A1 -E '^[[:space:]]+migrate:[[:space:]]*$' | grep -Eq '^[[:space:]]+condition:[[:space:]]*service_completed_successfully[[:space:]]*$'; then
  fail "superset-init 서비스가 migrate 완료(depends_on migrate, condition: service_completed_successfully)를 기다리지 않습니다."
fi
# superset-init은 일회성이라 이미지 HEALTHCHECK를 끈다(종료 뒤 unhealthy 표시 방지).
if ! service_code superset-init | grep -A1 -E '^[[:space:]]+healthcheck:[[:space:]]*$' | grep -Eq '^[[:space:]]+disable:[[:space:]]*true[[:space:]]*$'; then
  fail "superset-init 서비스에 healthcheck: disable: true 가 없습니다(종료 뒤 unhealthy 표시 방지)."
fi
if service_code migrate | grep -Eq 'superset'; then
  fail "migrate 서비스가 superset 서비스에 의존하면 순환 의존이 됩니다."
fi
if service_code frontend | grep -Eq '^[[:space:]]+(-[[:space:]]*)?[A-Z_]*(POSTGRES|PASSWORD|SECRET|AUTH_STUB|SUPERSET_[A-Z_]*_USER)[A-Z_]*[:=]|^[[:space:]]+env_file[[:space:]]*:'; then
  fail "frontend 서비스에 DB/Secret/스텁 변수(또는 env_file)를 넘기면 안 됩니다(Superset 계정 변수 포함)."
fi

# AG Grid Enterprise 혼입 방지(03b 15절): 커뮤니티 에디션만 쓴다. 파일이나 frontend/src 가 아직 없으면 해당 검사는 건너뛴다.
# 이름이 정확히 같은 키("이름") 또는 lock 파일의 "node_modules/이름" 키(중첩 경로 포함)만 막는다.
FE_PKG=frontend/package.json
FE_LOCK=frontend/package-lock.json
FE_SRC=frontend/src
ENTERPRISE_KEY='"([^"]*node_modules/)?(ag-grid-enterprise|ag-charts-enterprise|@ag-grid-enterprise/[^"]*)"'
for file in "$FE_PKG" "$FE_LOCK"; do
  [ -f "$file" ] || continue
  if grep -Eq "$ENTERPRISE_KEY" "$file"; then
    fail "$file 에 AG Grid Enterprise 패키지(ag-grid-enterprise, ag-charts-enterprise)가 있습니다(커뮤니티 에디션만 허용)."
  fi
done
if [ -d "$FE_SRC" ]; then
  # 주석 줄(// * /*)은 제외하고 import/require/동적 import 구문만 본다(문서의 금지 문구 오탐 방지).
  find "$FE_SRC" -type f \( -name '*.ts' -o -name '*.tsx' -o -name '*.js' -o -name '*.jsx' \) > "${TMPDIR:-/tmp}/ci-validate-fe-src.$$"
  while IFS= read -r srcfile; do
    if grep -Ev '^[[:space:]]*(//|\*|/\*)' "$srcfile" |
      grep -Eq "(import|require|from)[[:space:]]*\(?[[:space:]]*[\"'](ag-grid-enterprise|ag-charts-enterprise|@ag-grid-enterprise/)"; then
      fail "$srcfile 이(가) AG Grid Enterprise 패키지를 import 합니다(커뮤니티 에디션만 허용)."
    fi
  done < "${TMPDIR:-/tmp}/ci-validate-fe-src.$$"
  rm -f "${TMPDIR:-/tmp}/ci-validate-fe-src.$$"
fi
# frontend 의존성은 정확한 버전 고정이다(블록 스타일 JSON 전제: 섹션은 2칸 들여쓰기, 항목은 한 줄에 하나).
if [ -f "$FE_PKG" ]; then
  unpinned="$(awk '
    /^  "(dependencies|devDependencies|optionalDependencies|peerDependencies|overrides)"[[:space:]]*:[[:space:]]*\{/ { on = 1; next }
    on && /^  \}/ { on = 0 }
    on { print }
  ' "$FE_PKG" | grep -E ':[[:space:]]*"' | grep -Ev ':[[:space:]]*"[0-9]+\.[0-9]+\.[0-9]+([-+][0-9A-Za-z.+-]*)?"' || true)"
  if [ -n "$unpinned" ]; then
    fail "$FE_PKG 에 정확한 버전이 아닌 의존성이 있습니다(^ ~ * latest 범위 금지): $(printf '%s' "$unpinned" | tr -s '[:space:]' ' ')"
  fi
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
  # 주석(-- ...)을 뗀 본문만 검사한다. 줄 전체가 주석인 줄은 지운다. 코드 뒤에 붙은 주석은 문자열 리터럴 안의
  # '--'(예: SELECT '--', :"x";)와 구별할 수 없으므로, 작은따옴표가 있는 코드 줄에 '--'가 있으면 실패시킨다.
  if grep -Ev '^[[:space:]]*--' "$ROLES" | grep "'" | grep -q -- '--'; then
    fail "$ROLES 의 작은따옴표가 있는 코드 줄에 '--'가 있습니다(주석은 별도 줄에 쓰세요)."
  fi
  body="$(grep -Ev '^[[:space:]]*--' "$ROLES" | sed 's/--.*$//')"
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
  # psql 메타 명령은 \set ON_ERROR_STOP on, \getenv, \echo, \gexec(조건부 실행)만 허용한다(\i, \ir, \!, 다른 \set 등 금지).
  for meta in $(printf '%s\n' "$body" | grep -o '\\[A-Za-z0-9_!\\]*' || true); do
    case "$meta" in
      '\set' | '\getenv' | '\echo' | '\gexec') ;;
      *) fail "$ROLES 에 허용되지 않은 psql 메타 명령 $meta (허용: \set ON_ERROR_STOP, \getenv, \echo, \gexec)" ;;
    esac
  done
  [ "$(printf '%s\n' "$body" | grep -c '\\set')" = "1" ] || fail "$ROLES 의 \\set 은 \\set ON_ERROR_STOP on 한 줄뿐이어야 합니다."
  # 식별자 보간(:"var"), 구문 보간(:var), format(), %I 금지. ('::' 형변환은 제외한다)
  if printf '%s\n' "$body" | grep -Eq ':"[A-Za-z_]'; then fail "$ROLES 에 식별자 보간 :\"var\" 이 있습니다."; fi
  if printf '%s\n' "$body" | grep -Eq '(^|[^:]):[A-Za-z_]'; then fail "$ROLES 에 구문 보간 :var 이 있습니다."; fi
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
    "ALTER ROLE bi_owner NOSUPERUSER NOCREATEDB NOCREATEROLE;" \
    "ALTER ROLE bi_app NOSUPERUSER NOCREATEDB NOCREATEROLE;" \
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
