import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
KST = ZoneInfo('Asia/Seoul')
SLOTS = {'morning': ('아침', 8, 0), 'noon': ('점심', 12, 30), 'evening': ('저녁', 20, 0)}


def read(path, fallback=None):
    return json.loads(path.read_text()) if path.exists() else fallback


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temp.replace(path)


def slot_context(now=None, slot=None):
    now = now or datetime.now(KST)
    now = now.astimezone(KST)
    slot = slot or os.getenv('SIGNAL_SLOT', 'auto')
    # Resolve schedule identity from its trigger, even when execution is delayed.
    cron = os.getenv('SIGNAL_CRON', '')
    if slot == 'auto' and cron:
        slot = {'0 8 * * *': 'morning', '30 12 * * *': 'noon', '0 20 * * *': 'evening'}[cron]
    candidates = []
    for key, (label, hour, minute) in SLOTS.items():
        if slot != 'auto' and key != slot:
            continue
        due = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if due > now:
            due -= timedelta(days=1)
        candidates.append((due, key, label))
    if not candidates:
        raise ValueError('Unknown slot')
    due, key, label = max(candidates)
    return {'date': due.date().isoformat(), 'slot': key, 'slot_label': label,
            'scheduled_at': due.isoformat(), 'collected_at': now.isoformat(timespec='seconds')}


def report_status(component, state, message, **extra):
    path = ROOT / 'data/automation-status.json'
    doc = read(path, {'version': 1, 'components': {}})
    doc['components'][component] = {'state': state, 'message': message,
        'checked_at': datetime.now(KST).isoformat(timespec='seconds'), **extra}
    write(path, doc)
