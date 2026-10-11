#!/bin/sh
# 사용: ./mark.sh start  -> 로그 줄 수 기록 / ./mark.sh save <파일> -> 기록 이후 로그 저장
case "$1" in
  start) docker logs g3x26-pg 2>&1 | wc -l > /tmp/g3x26_mark_db ;;
  save) docker logs g3x26-pg 2>&1 | tail -n +$(( $(cat /tmp/g3x26_mark_db) + 1 )) > "$2" ;;
esac
