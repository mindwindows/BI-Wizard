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
  cp -f "$ROOT/scripts/"*.bat "$WORK/scripts/" 2>/dev/null || true
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
expect_fail "compose가 .env.example에 없는 변수 사용" "에 없는 변수" add_after_service backend '      NEW_THING: ${NEW_THING}'
expect_fail "compose에 latest 태그" ":latest 태그" sh -c "printf '    image: foo:latest\n' >> '$WORK/compose.yml'"

# --- 파괴적 명령 ---
# (금지 명령 문구를 이 파일에 그대로 쓰지 않도록 인자를 나눠 만든다)
append_destructive() { printf '    sh "docker compose %s %s"\n' "down" "-v" >> "$WORK/Jenkinsfile"; }
expect_fail "Jenkinsfile에 볼륨 삭제 옵션" "파괴적 명령" append_destructive

echo "[test-ci-validate-env] 케이스 $total개 중 실패 $bad개"
[ "$bad" -eq 0 ]
