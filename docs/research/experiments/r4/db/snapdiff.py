import json, sys, re
# 사용: snapdiff.py A.json B.json [--normalize] [--ignore-dynamic]
a, b = json.load(open(sys.argv[1])), json.load(open(sys.argv[2]))
norm = "--normalize" in sys.argv
ign_dyn = "--ignore-dynamic" in sys.argv
def normalize(s):
    s = json.loads(json.dumps(s))
    if norm:
        # (1) alembic_version 표는 Alembic이 만들고 지우지 않는다 -> 비교에서 제외
        s["alembic_version"] = None
        s["public_tables"].pop("alembic_version", None)
        k = "relations(schema,name,kind,owner,acl)"
        s[k] = [r for r in s[k] if not r[1].startswith("alembic_version")]
        # (2) 스키마 ACL: NULL(기본)과 '소유자 전체 권한만 명시'는 효력이 같다
        for r in s["schemas"]:
            if r[0] == "bi_data" and r[2] == "None":
                r[2] = "{bi_owner=UC/bi_owner}"
    if ign_dyn:
        s.pop("dynamic_bi_data(schema,name,kind,owner,acl)", None)
        k = "relations(schema,name,kind,owner,acl)"
        s[k] = [r for r in s[k] if r[0] != "bi_data"]
    return s
a, b = normalize(a), normalize(b)
same = True
for k in sorted(set(a) | set(b)):
    if a.get(k) != b.get(k):
        same = False
        print(f"DIFF [{k}]\n   A: {json.dumps(a.get(k), ensure_ascii=False)[:600]}\n   B: {json.dumps(b.get(k), ensure_ascii=False)[:600]}")
print("IDENTICAL" if same else "DIFFERENT")
