import sys, os
sys.path.insert(0, '/home/user/BI-Wizard/_workspace/gate3/experiments/r3')
sys.path.insert(0, '/home/user/BI-Wizard/_workspace/gate3/experiments')
from r3lib import *
import urllib.parse
HERE = os.path.dirname(os.path.abspath(__file__))
IDS = os.path.join(HERE, 'ids.json')
def load_ids():
    return json.load(open(IDS)) if os.path.exists(IDS) else {}
def save_ids(d):
    json.dump(d, open(IDS, 'w'), ensure_ascii=False, indent=1)
def show(label, st, j, maxlen=1500):
    s = json.dumps(j, ensure_ascii=False) if not isinstance(j, str) else j
    print(f'--- {label}: HTTP {st}\n{s[:maxlen]}')
