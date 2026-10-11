import sys, json
sys.path.insert(0, '/home/user/BI-Wizard/_workspace/gate3/experiments/r4')
from bis import *
MIN4 = [("can_read","CurrentUserRestApi"),("can_read","Dashboard"),("can_read","Chart"),("can_time_range","Api")]
FULL = ["tab2","team","time","amount","cross","timerel","getdm"]
which = sys.argv[1]
if which == 'min4':
    res = run('min4_full', MIN4, steps=FULL); print(json.dumps(res, ensure_ascii=False))
json.dump(res, open('out/bis2_%s.json' % which, 'w'), ensure_ascii=False, indent=1)
