import json, sys
from pathlib import Path

d = Path(sys.argv[1])

state_path = d / 'state.json'
if state_path.exists():
    state = json.loads(state_path.read_text(encoding='utf-8'))
    print('=== state.json ===')
    print('total_budget:', state.get('total_budget'))
    print('used_layers:', state.get('used_layers'))
    print('passes (%d):' % len(state.get('passes', [])))
    for i, p in enumerate(state.get('passes', []), 1):
        print('  #%d: layers=%s mask=%s' % (i, p.get('layers'), p.get('mask')))

base_path = d / 'base.json'
if base_path.exists():
    data = json.loads(base_path.read_text(encoding='utf-8'))
    shapes = data.get('shapes', data) if isinstance(data, dict) else data
    total = len(shapes)
    type16 = sum(1 for s in shapes if s.get('type') == 16)
    print()
    print('=== base.json ===')
    print('total shapes:', total, 'type16:', type16)

print()
print('=== Files ===')
for f in sorted(d.iterdir()):
    if f.suffix in ('.json', '.png', '.ini'):
        print('  %s (%s bytes)' % (f.name, f.stat().st_size))
