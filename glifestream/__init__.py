from pathlib import Path

__version__ = '0.1'

PATH_ROOT = Path(__file__).resolve().parent
VERSION = 'unknown'
REVISION = ''

try:
    ver = (PATH_ROOT / '.version').read_text(encoding='utf-8').strip()
except OSError:
    pass
else:
    if ver:
        VERSION, REVISION = ver, ver[-7:]
