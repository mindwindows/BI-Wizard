#!/bin/sh
# scripts/ci-validate-env.sh 의 네거티브 케이스 시험(POSIX sh, Linux).
# 실제 파일은 건드리지 않고 임시 작업 폴더에 복사본을 만들어 규칙 위반을 일부러 넣고,
# 검증 스크립트가 올바른 메시지로 실패하는지 확인한다. 기준(위반 없음) 복사본은 통과해야 한다.
# 사용: sh scripts/test-ci-validate-env.sh   (실패한 케이스가 있으면 종료 코드 1)
# 작업 폴더: ${TMPDIR:-/tmp}/bi-wizard-ci-validate-test (실행마다 덮어쓴다. 삭제하지 않는다)
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="${TMPDIR:-/tmp}/bi-wizard-ci-validate-test"
total=0
bad=0

reset_work() {
  mkdir -p "$WORK/scripts" "$WORK/backend/bootstrap"
  cp -f "$ROOT/scripts/ci-validate-env.sh" "$WORK/scripts/ci-validate-env.sh"
  cp -f "$ROOT/.env.example" "$WORK/.env.example"
  cp -f "$ROOT/compose.yml" "$WORK/compose.yml"
  cp -f "$ROOT/Jenkinsfile" "$WORK/Jenkinsfile"
  cp -f "$ROOT/backend/bootstrap/roles.sql" "$WORK/backend/bootstrap/roles.sql"
  mkdir -p "$WORK/superset" "$WORK/backend/app"
  cp -f "$ROOT/superset/superset_config.py" "$WORK/superset/superset_config.py"
  printf '# 시험용 빈 모듈\n' > "$WORK/backend/app/__init__.py"
  cp -f "$ROOT/scripts/"*.bat "$WORK/scripts/" 2>/dev/null || true
  # frontend 파일(AG Grid Enterprise 혼입 검사용). 원본에 없으면 복사하지 않는다(검사도 건너뛴다).
  mkdir -p "$WORK/frontend"
  rm -rf "$WORK/frontend/src"
  cp -f "$ROOT/frontend/package.json" "$WORK/frontend/package.json" 2>/dev/null || true
  cp -f "$ROOT/frontend/package-lock.json" "$WORK/frontend/package-lock.json" 2>/dev/null || true
  if [ -d "$ROOT/frontend/src" ]; then cp -R "$ROOT/frontend/src" "$WORK/frontend/src"; else mkdir -p "$WORK/frontend/src"; fi
}

# 서비스 블록 안에서만 줄을 지우거나(awk) 추가한다.
add_after_service() { # 서비스 줄
  awk -v svc="$1" -v line="$2" '{print} $0 ~ ("^  " svc ":[[:space:]]*$") {print line}' "$WORK/compose.yml" > "$WORK/compose.tmp" && mv "$WORK/compose.tmp" "$WORK/compose.yml"
}
delete_in_service() { # 서비스 이름, 지울 줄에 들어 있는 문자열
  awk -v svc="$1" -v pat="$2" '
    $0 ~ ("^  " svc ":[[:space:]]*$") { on = 1 }
    on && /^  [A-Za-z0-9_-]+:/ && $0 !~ ("^  " svc ":") { on = 0 }
    on && index($0, pat) { next }
    { print }
  ' "$WORK/compose.yml" > "$WORK/compose.tmp" && mv "$WORK/compose.tmp" "$WORK/compose.yml"
}

replace_in_service() { # 서비스 이름, 찾을 문자열, 바꿀 문자열(해당 서비스 블록 안의 줄에서만 첫 번째 일치를 바꾼다)
  awk -v svc="$1" -v from="$2" -v to="$3" '
    $0 ~ ("^  " svc ":[[:space:]]*$") { on = 1 }
    on && /^  [A-Za-z0-9_-]+:/ && $0 !~ ("^  " svc ":") { on = 0 }
    on && (i = index($0, from)) { $0 = substr($0, 1, i - 1) to substr($0, i + length(from)) }
    { print }
  ' "$WORK/compose.yml" > "$WORK/compose.tmp" && mv "$WORK/compose.tmp" "$WORK/compose.yml"
}

# superset-init의 `migrate:` 바로 다음 줄(condition)만 service_started로 바꾼다.
migrate_condition_started() {
  awk '
    $0 ~ /^  superset-init:[[:space:]]*$/ { on = 1 }
    on && /^  [A-Za-z0-9_-]+:/ && $0 !~ /^  superset-init:/ { on = 0 }
    fix && /condition:/ { sub(/service_completed_successfully/, "service_started"); fix = 0 }
    on && /^      migrate:[[:space:]]*$/ { fix = 1 }
    { print }
  ' "$WORK/compose.yml" > "$WORK/compose.tmp" && mv "$WORK/compose.tmp" "$WORK/compose.yml"
  grep -q 'condition: service_started' "$WORK/compose.yml"
}

# expect_fail 이름 '기대 메시지' 변경명령...   (변경명령은 reset 직후 $WORK 안에서 실행한다)
expect_fail() {
  name="$1"; message="$2"; shift 2
  total=$((total + 1))
  reset_work
  "$@"
  out="$(cd "$WORK" && sh scripts/ci-validate-env.sh "$WORK/out.env" 2>&1)"
  rc=$?
  if [ "$rc" -ne 0 ] && printf '%s\n' "$out" | grep -qF -- "$message"; then
    echo "[ok]   $name"
  else
    echo "[FAIL] $name (rc=$rc, 기대 메시지: $message)"
    printf '%s\n' "$out" | sed 's/^/         /'
    bad=$((bad + 1))
  fi
}

expect_pass() {
  name="$1"; shift
  total=$((total + 1))
  reset_work
  "$@"
  out="$(cd "$WORK" && sh scripts/ci-validate-env.sh "$WORK/out.env" 2>&1)"
  rc=$?
  if [ "$rc" -eq 0 ]; then
    echo "[ok]   $name"
  else
    echo "[FAIL] $name (rc=$rc)"
    printf '%s\n' "$out" | sed 's/^/         /'
    bad=$((bad + 1))
  fi
}

noop() { :; }
sed_ex() { sed -i "$1" "$WORK/.env.example"; }
sed_roles() { sed -i "$1" "$WORK/backend/bootstrap/roles.sql"; }
append_roles() { printf '%s\n' "$1" >> "$WORK/backend/bootstrap/roles.sql"; }

expect_pass "기준(위반 없음)" noop

# --- 인증 스텁 스위치 ---
expect_fail "AUTH_STUB_ENABLED=true (예시 기본값은 false여야 함)" "기본값은 false" sed_ex 's/^AUTH_STUB_ENABLED=.*/AUTH_STUB_ENABLED=true/'
expect_fail "AUTH_STUB_ENABLED=true + APP_ENV=production" "local 또는 test일 때만" sh -c "sed -i 's/^AUTH_STUB_ENABLED=.*/AUTH_STUB_ENABLED=true/; s/^APP_ENV=.*/APP_ENV=production/' '$WORK/.env.example'"
expect_fail "AUTH_STUB_ENABLED=true + APP_ENV 빈 값" "local 또는 test일 때만" sh -c "sed -i 's/^AUTH_STUB_ENABLED=.*/AUTH_STUB_ENABLED=true/; s/^APP_ENV=.*/APP_ENV=/' '$WORK/.env.example'"
expect_fail "AUTH_STUB_ENABLED=yes (true/false만 허용)" "true 또는 false" sed_ex 's/^AUTH_STUB_ENABLED=.*/AUTH_STUB_ENABLED=yes/'
expect_fail "AUTH_STUB_ENABLED 빈 값" "true 또는 false" sed_ex 's/^AUTH_STUB_ENABLED=.*/AUTH_STUB_ENABLED=/'
expect_fail "AUTH_STUB_ENABLED 없음" "AUTH_STUB_ENABLED 이(가) 없습니다" sed_ex '/^AUTH_STUB_ENABLED=/d'

# --- 변수 목록 / Secret ---
expect_fail "승인되지 않은 변수" "승인 목록에 없는 변수" sh -c "printf 'EXTRA_NEW_VARIABLE=1\n' >> '$WORK/.env.example'"
expect_fail "POSTGRES_APP_PASSWORD 없음" "POSTGRES_APP_PASSWORD 이(가) 없습니다" sed_ex '/^POSTGRES_APP_PASSWORD=/d'
expect_fail "POSTGRES_OWNER_PASSWORD 없음" "POSTGRES_OWNER_PASSWORD 이(가) 없습니다" sed_ex '/^POSTGRES_OWNER_PASSWORD=/d'
expect_fail "POSTGRES_APP_PASSWORD 값이 채워짐" "POSTGRES_APP_PASSWORD 은(는)" sed_ex 's/^POSTGRES_APP_PASSWORD=.*/POSTGRES_APP_PASSWORD=abc/'
expect_fail "POSTGRES_OWNER_PASSWORD 값이 채워짐" "POSTGRES_OWNER_PASSWORD 은(는)" sed_ex 's/^POSTGRES_OWNER_PASSWORD=.*/POSTGRES_OWNER_PASSWORD=abc/'
expect_fail "POSTGRES_USER=bi_owner" "POSTGRES_USER는" sed_ex 's/^POSTGRES_USER=.*/POSTGRES_USER=bi_owner/'
expect_fail "POSTGRES_USER=bi_app" "POSTGRES_USER는" sed_ex 's/^POSTGRES_USER=.*/POSTGRES_USER=bi_app/'
expect_fail "POSTGRES_USER=bi_readonly" "POSTGRES_USER는" sed_ex 's/^POSTGRES_USER=.*/POSTGRES_USER=bi_readonly/'
expect_fail "SUPERSET_SERVICE_PASSWORD 없음" "SUPERSET_SERVICE_PASSWORD 이(가) 없습니다" sed_ex '/^SUPERSET_SERVICE_PASSWORD=/d'
expect_fail "SUPERSET_GUEST_ISSUER_PASSWORD 없음" "SUPERSET_GUEST_ISSUER_PASSWORD 이(가) 없습니다" sed_ex '/^SUPERSET_GUEST_ISSUER_PASSWORD=/d'
expect_fail "SUPERSET_SERVICE_USER 없음" "SUPERSET_SERVICE_USER 이(가) 없습니다" sed_ex '/^SUPERSET_SERVICE_USER=/d'
expect_fail "SUPERSET_GUEST_ISSUER_USER 없음" "SUPERSET_GUEST_ISSUER_USER 이(가) 없습니다" sed_ex '/^SUPERSET_GUEST_ISSUER_USER=/d'
expect_fail "SUPERSET_SERVICE_PASSWORD 값이 채워짐" "SUPERSET_SERVICE_PASSWORD 은(는)" sed_ex 's/^SUPERSET_SERVICE_PASSWORD=.*/SUPERSET_SERVICE_PASSWORD=abc/'
expect_fail "SUPERSET_GUEST_ISSUER_PASSWORD 값이 채워짐" "SUPERSET_GUEST_ISSUER_PASSWORD 은(는)" sed_ex 's/^SUPERSET_GUEST_ISSUER_PASSWORD=.*/SUPERSET_GUEST_ISSUER_PASSWORD=abc/'
expect_fail "SUPERSET_SERVICE_USER 중복 정의" "중복 정의된 변수" sh -c "printf 'SUPERSET_SERVICE_USER=other\n' >> '$WORK/.env.example'"
expect_fail "서비스 계정 이름이 관리자와 같음" "서로 달라야" sed_ex 's/^SUPERSET_SERVICE_USER=.*/SUPERSET_SERVICE_USER=admin/'
expect_fail "발급 계정 이름이 서비스 계정과 같음" "서로 달라야" sed_ex 's/^SUPERSET_GUEST_ISSUER_USER=.*/SUPERSET_GUEST_ISSUER_USER=bi_service/'
expect_fail "서비스 계정 이름 빈 값" "비어 있을 수 없습니다" sed_ex 's/^SUPERSET_SERVICE_USER=.*/SUPERSET_SERVICE_USER=/'
expect_fail "서비스 계정 이름이 관리자와 대소문자만 다름" "서로 달라야" sed_ex 's/^SUPERSET_SERVICE_USER=.*/SUPERSET_SERVICE_USER=Admin/'
expect_fail "발급 계정 이름이 서비스 계정과 대소문자만 다름" "서로 달라야" sed_ex 's/^SUPERSET_GUEST_ISSUER_USER=.*/SUPERSET_GUEST_ISSUER_USER=BI_SERVICE/'
expect_fail "관리자 이름이 발급 계정과 대소문자만 다름" "서로 달라야" sed_ex 's/^SUPERSET_ADMIN_USER=.*/SUPERSET_ADMIN_USER=Bi_Guest_Issuer/'
expect_fail "SUPERSET_ADMIN_USER 빈 값" "비어 있을 수 없습니다" sed_ex 's/^SUPERSET_ADMIN_USER=.*/SUPERSET_ADMIN_USER=/'
expect_fail "관리자 이름이 발급 계정과 정확히 같음" "서로 달라야" sed_ex 's/^SUPERSET_ADMIN_USER=.*/SUPERSET_ADMIN_USER=bi_guest_issuer/'
expect_fail "Azure OpenAI 변수" "승인 목록에 없는 변수" sh -c "printf 'AZURE_OPENAI_ENDPOINT=\n' >> '$WORK/.env.example'"

# --- roles.sql ---
expect_fail "roles.sql 식별자 보간 :\"var\"" "식별자 보간" append_roles 'CREATE SCHEMA :"x";'
expect_fail "roles.sql 구문 보간 :var" "구문 보간" append_roles 'SELECT :x;'
expect_fail "roles.sql format()" "format(" append_roles "SELECT format('%s', 1);"
expect_fail "roles.sql 허용되지 않은 :'var'" "허용되지 않은 psql 인용 보간" append_roles "SELECT :'other';"
expect_fail "roles.sql :'app_pw' 중복" ":'app_pw' 는 정확히 한 번" append_roles "ALTER ROLE bi_app PASSWORD :'app_pw';"
expect_fail "roles.sql owner 비밀번호 줄 없음" "필수 문장이 없습니다: ALTER ROLE bi_owner PASSWORD" sed_roles "/^ALTER ROLE bi_owner PASSWORD/d"
expect_fail "roles.sql 비밀번호 외 위치의 :'var'" "PASSWORD :'var' 4곳뿐" sed_roles "s/^ALTER ROLE bi_app PASSWORD :'app_pw';/ALTER ROLE bi_app SET search_path = :'app_pw';/"
expect_fail "roles.sql GRANT bi_app TO bi_owner 없음" "필수 문장이 없습니다: GRANT bi_app TO bi_owner" sed_roles "/^GRANT bi_app TO bi_owner/d"
expect_fail "roles.sql INHERIT FALSE" "필수 문장이 없습니다: GRANT bi_app TO bi_owner" sed_roles "s/WITH INHERIT TRUE, SET FALSE/WITH INHERIT FALSE, SET TRUE/"
expect_fail "roles.sql statement_timeout 없음" "필수 문장이 없습니다: ALTER ROLE bi_readonly SET statement_timeout" sed_roles "/statement_timeout/d"
expect_fail "roles.sql public CREATE 회수 없음" "필수 문장이 없습니다: REVOKE CREATE ON SCHEMA public FROM PUBLIC" sed_roles "/^REVOKE CREATE ON SCHEMA public FROM PUBLIC/d"
expect_fail "roles.sql bi_data 소유자" "필수 문장이 없습니다: CREATE SCHEMA IF NOT EXISTS bi_data AUTHORIZATION bi_owner" sed_roles "s/AUTHORIZATION bi_owner/AUTHORIZATION bi_app/"
expect_fail "roles.sql bi_app 속성 재차단 없음" "필수 문장이 없습니다: ALTER ROLE bi_app NOSUPERUSER" sed_roles "/^ALTER ROLE bi_app NOSUPERUSER/d"
expect_fail "roles.sql bi_owner 속성 재차단 없음" "필수 문장이 없습니다: ALTER ROLE bi_owner NOSUPERUSER" sed_roles "/^ALTER ROLE bi_owner NOSUPERUSER/d"
expect_fail "roles.sql bi_app 재차단이 CREATEROLE 허용" "필수 문장이 없습니다: ALTER ROLE bi_app NOSUPERUSER" sed_roles "s/^ALTER ROLE bi_app NOSUPERUSER NOCREATEDB NOCREATEROLE;/ALTER ROLE bi_app NOSUPERUSER NOCREATEDB CREATEROLE;/"
expect_fail "roles.sql 추가 \\getenv" "\\getenv 는 비밀번호 변수 4개뿐" append_roles '\getenv extra SOME_OTHER_VARIABLE'
expect_fail "roles.sql \\getenv 누락" "필수 문장이 없습니다: \\getenv app_pw POSTGRES_APP_PASSWORD" sed_roles '/^\\getenv app_pw/d'

# 문자열 리터럴 안의 '--' 로 식별자 보간을 주석처럼 숨기는 우회, ':foo' 앞 따옴표 우회, psql 메타 명령
expect_fail "roles.sql 문자열 안의 -- 로 보간 숨기기" "작은따옴표가 있는 코드 줄에 '--'" append_roles "SELECT '--', :\"x\";"
expect_fail "roles.sql 코드 뒤 주석에 따옴표" "작은따옴표가 있는 코드 줄에 '--'" append_roles "SELECT 'a'; -- note"
expect_fail "roles.sql 따옴표 뒤 :foo 우회" "구문 보간" append_roles "SELECT 'a':foo;"
expect_fail "roles.sql \\i 메타 명령" "허용되지 않은 psql 메타 명령" append_roles '\i /tmp/other.sql'
expect_fail "roles.sql \\ir 메타 명령" "허용되지 않은 psql 메타 명령" append_roles '\ir other.sql'
expect_fail "roles.sql \\! 셸 실행" "허용되지 않은 psql 메타 명령" append_roles '\! id'
expect_fail "roles.sql 다른 \\set" "\\set 은" append_roles '\set other 1'
expect_fail "roles.sql \\copy 메타 명령" "허용되지 않은 psql 메타 명령" append_roles '\copy t from stdin'

# --- compose.yml ---
expect_fail "backend에 POSTGRES_USER" "backend 서비스에 POSTGRES_USER" add_after_service backend '      POSTGRES_USER: ${POSTGRES_USER}'
expect_fail "backend에 POSTGRES_PASSWORD" "backend 서비스에 POSTGRES_PASSWORD" add_after_service backend '      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}'
expect_fail "backend에 POSTGRES_OWNER_PASSWORD" "backend 서비스에 POSTGRES_OWNER_PASSWORD" add_after_service backend '      POSTGRES_OWNER_PASSWORD: ${POSTGRES_OWNER_PASSWORD}'
expect_fail "migrate에 POSTGRES_USER" "migrate 서비스에 POSTGRES_USER" add_after_service migrate '      POSTGRES_USER: ${POSTGRES_USER}'
expect_fail "migrate에 POSTGRES_PASSWORD" "migrate 서비스에 POSTGRES_PASSWORD" add_after_service migrate '      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}'
expect_fail "migrate에 POSTGRES_APP_PASSWORD" "migrate 서비스에 POSTGRES_APP_PASSWORD" add_after_service migrate '      POSTGRES_APP_PASSWORD: ${POSTGRES_APP_PASSWORD}'
expect_fail "backend에서 POSTGRES_APP_PASSWORD 빠짐" "backend 서비스에 POSTGRES_APP_PASSWORD 가 없습니다" delete_in_service backend "POSTGRES_APP_PASSWORD:"
expect_fail "migrate에서 POSTGRES_OWNER_PASSWORD 빠짐" "migrate 서비스에 POSTGRES_OWNER_PASSWORD 가 없습니다" delete_in_service migrate "POSTGRES_OWNER_PASSWORD:"
expect_fail "backend에서 AUTH_STUB_ENABLED 빠짐" "backend 서비스에 AUTH_STUB_ENABLED 가 없습니다" delete_in_service backend "AUTH_STUB_ENABLED:"
expect_fail "frontend에 DB 비밀번호" "frontend 서비스에 DB/Secret/스텁 변수" add_after_service frontend '      POSTGRES_APP_PASSWORD: ${POSTGRES_APP_PASSWORD}'
expect_fail "frontend에 스텁 변수" "frontend 서비스에 DB/Secret/스텁 변수" add_after_service frontend '      AUTH_STUB_ENABLED: ${AUTH_STUB_ENABLED}'
expect_fail "backend env_file" "backend 서비스에 env_file" add_after_service backend '    env_file: .env'
expect_fail "migrate env_file" "migrate 서비스에 env_file" add_after_service migrate '    env_file: [.env]'
expect_fail "frontend env_file" "frontend 서비스에 DB/Secret/스텁 변수(또는 env_file)" add_after_service frontend '    env_file: .env'
expect_fail "backend 리스트 문법 POSTGRES_USER" "backend 서비스에 리스트 문법으로 POSTGRES_USER" add_after_service backend '      - POSTGRES_USER=bi_wizard'
expect_fail "backend 리스트 문법(값 없는 전달) POSTGRES_PASSWORD" "backend 서비스에 리스트 문법으로 POSTGRES_PASSWORD" add_after_service backend '      - "POSTGRES_PASSWORD"'
expect_fail "backend 리스트 문법 POSTGRES_OWNER_PASSWORD" "backend 서비스에 리스트 문법으로 POSTGRES_OWNER_PASSWORD" add_after_service backend '      - POSTGRES_OWNER_PASSWORD=x'
expect_fail "migrate 리스트 문법 POSTGRES_APP_PASSWORD" "migrate 서비스에 리스트 문법으로 POSTGRES_APP_PASSWORD" add_after_service migrate '      - POSTGRES_APP_PASSWORD=x'
expect_fail "backend가 다른 키에서 \${POSTGRES_USER} 참조" "backend 서비스가 \${POSTGRES_USER} 을(를) 참조" add_after_service backend '      LOG_LEVEL: ${POSTGRES_USER}'
expect_fail "backend가 \${POSTGRES_PASSWORD:-x} 참조" "backend 서비스가 \${POSTGRES_PASSWORD} 을(를) 참조" add_after_service backend '      LOG_LEVEL: ${POSTGRES_PASSWORD:-x}'
expect_fail "migrate가 \$POSTGRES_PASSWORD 참조" "migrate 서비스가 \${POSTGRES_PASSWORD} 을(를) 참조" add_after_service migrate '      TZ: $POSTGRES_PASSWORD'
expect_fail "backend에서 SUPERSET_SERVICE_PASSWORD 빠짐" "backend 서비스에 SUPERSET_SERVICE_PASSWORD 가 없습니다" delete_in_service backend "SUPERSET_SERVICE_PASSWORD:"
expect_fail "backend에서 SUPERSET_GUEST_ISSUER_USER 빠짐" "backend 서비스에 SUPERSET_GUEST_ISSUER_USER 가 없습니다" delete_in_service backend "SUPERSET_GUEST_ISSUER_USER:"
expect_fail "backend에서 SUPERSET_APP_ROOT 빠짐" "backend 서비스에 SUPERSET_APP_ROOT 가 없습니다" delete_in_service backend "SUPERSET_APP_ROOT:"
expect_fail "superset-init에서 SUPERSET_GUEST_ISSUER_PASSWORD 빠짐" "superset-init 서비스에 SUPERSET_GUEST_ISSUER_PASSWORD 가 없습니다" delete_in_service superset-init "SUPERSET_GUEST_ISSUER_PASSWORD:"
expect_fail "superset-init에서 SUPERSET_SERVICE_USER 빠짐" "superset-init 서비스에 SUPERSET_SERVICE_USER 가 없습니다" delete_in_service superset-init "SUPERSET_SERVICE_USER:"
expect_fail "superset(웹)에 서비스 계정 비밀번호" "superset 서비스에 SUPERSET_SERVICE_PASSWORD" add_after_service superset '      SUPERSET_SERVICE_PASSWORD: ${SUPERSET_SERVICE_PASSWORD}'
expect_fail "migrate에 발급 계정 비밀번호" "migrate 서비스에 SUPERSET_GUEST_ISSUER_PASSWORD" add_after_service migrate '      SUPERSET_GUEST_ISSUER_PASSWORD: ${SUPERSET_GUEST_ISSUER_PASSWORD}'
expect_fail "frontend에 서비스 계정 비밀번호" "frontend 서비스에 DB/Secret/스텁 변수" add_after_service frontend '      SUPERSET_SERVICE_PASSWORD: ${SUPERSET_SERVICE_PASSWORD}'
expect_fail "superset-init이 migrate를 기다리지 않음" "superset-init 서비스가 migrate 완료" delete_in_service superset-init "      migrate:"
expect_fail "migrate가 superset에 의존(순환)" "순환 의존" add_after_service migrate '    depends_on: [superset-init]'
expect_fail "backend의 SUPERSET_SERVICE_PASSWORD 필수 처리(:?) 제거" "backend 서비스의 SUPERSET_SERVICE_PASSWORD 가" replace_in_service backend '${SUPERSET_SERVICE_PASSWORD:?' '${SUPERSET_SERVICE_PASSWORD:-x'
expect_fail "backend의 SUPERSET_APP_ROOT 필수 처리(:?) 제거" "backend 서비스의 SUPERSET_APP_ROOT 가" replace_in_service backend '${SUPERSET_APP_ROOT:?' '${SUPERSET_APP_ROOT'
expect_fail "superset-init의 SUPERSET_GUEST_ISSUER_USER 필수 처리(:?) 제거" "superset-init 서비스의 SUPERSET_GUEST_ISSUER_USER 가" replace_in_service superset-init '${SUPERSET_GUEST_ISSUER_USER:?' '${SUPERSET_GUEST_ISSUER_USER-'
expect_fail "superset-init healthcheck 비활성화 제거" "superset-init 서비스에 healthcheck" delete_in_service superset-init "      disable: true"
expect_fail "superset-init의 migrate 조건을 service_started로" "superset-init 서비스가 migrate 완료" migrate_condition_started
expect_fail "frontend에 서비스 계정 이름" "frontend 서비스에 DB/Secret/스텁 변수" add_after_service frontend '      SUPERSET_SERVICE_USER: ${SUPERSET_SERVICE_USER}'
expect_fail "postgres-test에 서비스 계정 비밀번호" "postgres-test 서비스에 SUPERSET_SERVICE_PASSWORD" add_after_service postgres-test '      SUPERSET_SERVICE_PASSWORD: ${SUPERSET_SERVICE_PASSWORD}'
expect_fail "db-bootstrap에 서비스 계정 비밀번호" "db-bootstrap 서비스에 SUPERSET_SERVICE_PASSWORD" add_after_service db-bootstrap '      SUPERSET_SERVICE_PASSWORD: ${SUPERSET_SERVICE_PASSWORD}'
expect_fail "db-bootstrap에 발급 계정 이름" "db-bootstrap 서비스에 SUPERSET_GUEST_ISSUER_USER" add_after_service db-bootstrap '      SUPERSET_GUEST_ISSUER_USER: ${SUPERSET_GUEST_ISSUER_USER}'
expect_fail "postgres에 발급 계정 비밀번호" "postgres 서비스에 SUPERSET_GUEST_ISSUER_PASSWORD" add_after_service postgres '      SUPERSET_GUEST_ISSUER_PASSWORD: ${SUPERSET_GUEST_ISSUER_PASSWORD}'
expect_fail "postgres에 서비스 계정 이름" "postgres 서비스에 SUPERSET_SERVICE_USER" add_after_service postgres '      SUPERSET_SERVICE_USER: ${SUPERSET_SERVICE_USER}'
expect_fail "backend에 GUEST_TOKEN_JWT_SECRET(직접 서명 금지)" "backend 서비스에 GUEST_TOKEN_JWT_SECRET" add_after_service backend '      GUEST_TOKEN_JWT_SECRET: ${GUEST_TOKEN_JWT_SECRET}'
expect_fail "backend 리스트 문법 GUEST_TOKEN_JWT_SECRET" "backend 서비스에 리스트 문법으로 GUEST_TOKEN_JWT_SECRET" add_after_service backend '      - GUEST_TOKEN_JWT_SECRET'
expect_fail "backend가 다른 키에서 GUEST_TOKEN_JWT_SECRET 참조" "backend 서비스가 \${GUEST_TOKEN_JWT_SECRET} 을(를) 참조" add_after_service backend '      LOG_LEVEL: ${GUEST_TOKEN_JWT_SECRET}'
expect_fail "migrate에 GUEST_TOKEN_JWT_SECRET" "migrate 서비스에 GUEST_TOKEN_JWT_SECRET" add_after_service migrate '      GUEST_TOKEN_JWT_SECRET: ${GUEST_TOKEN_JWT_SECRET}'
expect_fail "backend env_file로 전체 전달(GUEST_TOKEN_JWT_SECRET 포함 가능)" "backend 서비스에 env_file" add_after_service backend '    env_file: .env'
expect_fail "backend/app 코드가 GUEST_TOKEN_JWT_SECRET 참조" "backend/app 코드가 GUEST_TOKEN_JWT_SECRET" sh -c "printf 'x = \"GUEST_TOKEN_JWT_SECRET\"\n' >> '$WORK/backend/app/__init__.py'"
expect_fail "superset_config GUEST_ROLE_NAME 변경" "GUEST_ROLE_NAME 은" sh -c "sed -i 's/^GUEST_ROLE_NAME = .*/GUEST_ROLE_NAME = \"Public\"/' '$WORK/superset/superset_config.py'"
expect_fail "superset_config GUEST_ROLE_NAME 삭제" "GUEST_ROLE_NAME 은" sh -c "sed -i '/^GUEST_ROLE_NAME = /d' '$WORK/superset/superset_config.py'"
expect_fail "superset_config 훅 설정 삭제" "GUEST_TOKEN_VALIDATOR_HOOK 설정이 없습니다" sh -c "sed -i '/^GUEST_TOKEN_VALIDATOR_HOOK = /d' '$WORK/superset/superset_config.py'"
expect_fail "superset_config에 PUBLIC_ROLE_LIKE" "PUBLIC_ROLE_LIKE 를 설정하면 안 됩니다" sh -c "printf 'PUBLIC_ROLE_LIKE = \"Gamma\"\n' >> '$WORK/superset/superset_config.py'"
expect_fail "superset_config에 PUBLIC_ROLE_LIKE(타입 주석)" "PUBLIC_ROLE_LIKE 를 설정하면 안 됩니다" sh -c "printf 'PUBLIC_ROLE_LIKE: str = \"Public\"\n' >> '$WORK/superset/superset_config.py'"
expect_fail "superset_config가 입장권 유효 시간 재정의" "GUEST_TOKEN_JWT_EXP_SECONDS 를 재정의" sh -c "printf 'GUEST_TOKEN_JWT_EXP_SECONDS = 3600\n' >> '$WORK/superset/superset_config.py'"
expect_fail "superset_config가 입장권 유효 시간 재정의(300 그대로 재선언)" "GUEST_TOKEN_JWT_EXP_SECONDS 를 재정의" sh -c "printf 'GUEST_TOKEN_JWT_EXP_SECONDS: int = 300\n' >> '$WORK/superset/superset_config.py'"
expect_fail "superset_config가 입장권 유효 시간을 딕셔너리로 우회" "GUEST_TOKEN_JWT_EXP_SECONDS 를 재정의" sh -c "printf 'globals().update({\"GUEST_TOKEN_JWT_EXP_SECONDS\": 99})\n' >> '$WORK/superset/superset_config.py'"
expect_pass "superset_config 주석에만 입장권 유효 시간 언급" sh -c "printf '# GUEST_TOKEN_JWT_EXP_SECONDS 는 기본값\n' >> '$WORK/superset/superset_config.py'"
expect_fail "compose가 .env.example에 없는 변수 사용" "에 없는 변수" add_after_service backend '      NEW_THING: ${NEW_THING}'
expect_fail "compose에 latest 태그" ":latest 태그" sh -c "printf '    image: foo:latest\n' >> '$WORK/compose.yml'"

# --- AG Grid Enterprise 혼입 / 의존성 버전 고정 ---
fe_pkg_add() { # package.json의 "dependencies": { 바로 다음 줄에 항목을 넣는다
  sed -i "s|^  \"dependencies\": {|  \"dependencies\": {\n    $1,|" "$WORK/frontend/package.json"
}
lock_add() { # package-lock.json의 "packages": { 바로 다음 줄에 키를 넣는다
  sed -i "s|^  \"packages\": {|  \"packages\": {\n    \"node_modules/ag-charts-enterprise\": {\"version\": \"1.0.0\"},|" "$WORK/frontend/package-lock.json"
}
src_add() { mkdir -p "$WORK/frontend/src" && printf '%s\n' "$1" >> "$WORK/frontend/src/enterprise-test.tsx"; }
expect_fail "package.json에 ag-grid-enterprise" "AG Grid Enterprise 패키지" fe_pkg_add '"ag-grid-enterprise": "34.0.0"'
expect_fail "package-lock.json에 node_modules/ag-charts-enterprise 키" "AG Grid Enterprise 패키지" lock_add
expect_fail "소스에 import ... from \"ag-grid-enterprise\"" "AG Grid Enterprise 패키지를 import" src_add 'import { ModuleRegistry } from "ag-grid-enterprise";'
expect_fail "소스의 동적 import(ag-charts-enterprise)" "AG Grid Enterprise 패키지를 import" src_add 'const m = await import("ag-charts-enterprise");'
expect_fail "소스의 옛 패키지 @ag-grid-enterprise/ import" "AG Grid Enterprise 패키지를 import" src_add "import '@ag-grid-enterprise/all-modules';"
expect_fail "의존성에 ^ 범위 표기" "정확한 버전이 아닌 의존성" fe_pkg_add '"some-lib": "^1.2.3"'
expect_fail "의존성에 latest 표기" "정확한 버전이 아닌 의존성" fe_pkg_add '"some-lib": "latest"'
expect_pass "소스 주석에만 ag-grid-enterprise 언급" src_add '// ag-grid-enterprise 는 금지(import "ag-grid-enterprise" 쓰지 말 것)'

# --- 파괴적 명령 ---
# (금지 명령 문구를 이 파일에 그대로 쓰지 않도록 인자를 나눠 만든다)
append_destructive() { printf '    sh "docker compose %s %s"\n' "down" "-v" >> "$WORK/Jenkinsfile"; }
expect_fail "Jenkinsfile에 볼륨 삭제 옵션" "파괴적 명령" append_destructive

echo "[test-ci-validate-env] 케이스 $total개 중 실패 $bad개"
[ "$bad" -eq 0 ]
