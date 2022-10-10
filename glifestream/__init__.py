import os

__version__ = '0.1'

PATH_ROOT = os.path.dirname(os.path.realpath(__file__))

try:
    with open(os.path.join(PATH_ROOT, '.version'), encoding='utf-8') as f:
        ver = f.read().strip()
        VERSION, REVISION = ver, ver[-7:]
except Exception as exc:
    print(exc)
    VERSION, REVISION = 'unknown', ''
