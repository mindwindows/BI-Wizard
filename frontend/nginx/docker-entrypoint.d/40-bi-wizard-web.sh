#!/bin/sh
# 정적 파일을 nginx 문서 루트에 복사하고, 시작할 때마다 하위 경로를 주입한다.
# - index.html의 <base href>를 APP_BASE_PATH로 바꾼다.
# - config.js(window.__APP_CONFIG__)를 만든다. 공개 설정만 들어간다.
# 이미지는 경로와 무관하게 재사용된다(경로를 바꾸려면 환경변수를 바꾸고 컨테이너를 다시 시작한다).
set -eu

SRC=/opt/web/dist
DEST=/usr/share/nginx/html

base="${APP_BASE_PATH:-}"
superset="${SUPERSET_APP_ROOT:-}"

# 18-bi-wizard-env.envsh가 이미 검사했지만, 이 파일이 단독으로 실행돼도 안전하도록 한 번 더 확인한다.
# case 문으로 값 전체를 검사한다(개행, '//', '.'/'..' 세그먼트, 허용 밖 문자를 거부한다).
valid_path() {
  v="$1"
  case "$v" in /*) ;; *) return 1 ;; esac
  case "$v" in */) return 1 ;; esac
  case "$v" in *[!A-Za-z0-9._~/-]*) return 1 ;; esac
  case "$v" in *//*) return 1 ;; esac
  case "$v" in */. | */./* | */.. | */../*) return 1 ;; esac
  return 0
}
if [ -n "$base" ] && ! valid_path "$base"; then
  echo "[frontend] APP_BASE_PATH 형식 오류" >&2
  exit 1
fi
if ! valid_path "$superset"; then
  echo "[frontend] SUPERSET_APP_ROOT 형식 오류(빈 값 불가)" >&2
  exit 1
fi

# 매번 원본(/opt/web/dist)에서 새로 복사하므로 재시작해도 치환이 중복되지 않는다.
cp -R "$SRC"/. "$DEST"/

pattern='<base href="/" id="app-base" />'
if ! grep -qF "$pattern" "$DEST/index.html"; then
  echo "[frontend] index.html에서 <base> 태그를 찾지 못했습니다." >&2
  exit 1
fi
sed "s|<base href=\"/\" id=\"app-base\" />|<base href=\"${base}/\" id=\"app-base\" />|" \
  "$SRC/index.html" > "$DEST/index.html"

cat > "$DEST/config.js" <<CONFIG
window.__APP_CONFIG__ = { basePath: "${base}", supersetRoot: "${superset}" };
CONFIG

echo "[frontend] 정적 파일 준비 완료(base href='${base}/')"
