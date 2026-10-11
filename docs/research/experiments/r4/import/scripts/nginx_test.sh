#!/bin/bash
cd /home/user/BI-Wizard/_workspace/gate3/experiments/r4/import/nginx
for spec in 943718:0.9MiB 1048576:1MiB 1048577:1MiB+1B 2097152:2MiB 5242880:5MiB 10485760:10MiB 11534336:11MiB 11534337:11MiB+1B 12582912:12MiB; do
  sz=${spec%%:*}; lab=${spec##*:}
  f=bodies/b_$sz.bin; [ -f $f ] || head -c $sz /dev/urandom > $f
  for target in 18127:default_unset 18128:11m; do
    port=${target%%:*}; tl=${target##*:}
    raw=$(curl -s -o /tmp/claude-0/nginx_resp.txt -w '%{http_code}' -X POST -H 'Content-Type: application/octet-stream' --data-binary @$f http://127.0.0.1:$port/bi-wizard/api/imports)
    mp=$(curl -s -o /tmp/claude-0/nginx_resp2.txt -w '%{http_code}' -F "file=@$f;filename=x.xlsx;type=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" http://127.0.0.1:$port/bi-wizard/api/imports)
    ch=$(curl -s -o /tmp/claude-0/nginx_resp3.txt -w '%{http_code}' -X POST -H 'Transfer-Encoding: chunked' -H 'Content-Type: application/octet-stream' --data-binary @$f http://127.0.0.1:$port/bi-wizard/api/imports)
    echo "$lab | $tl | octet-stream $raw | multipart $mp | chunked $ch | $(head -c 60 /tmp/claude-0/nginx_resp.txt | tr -d '\n') | $(head -c 80 /tmp/claude-0/nginx_resp2.txt | tr -d '\n' | head -c 70)"
  done
done
