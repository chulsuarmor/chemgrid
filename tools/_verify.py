from pathlib import Path
agents = Path('agents')
ok = 0
for d in sorted(agents.rglob('*')):
    if d.is_dir() and (d / '.clinerules').exists():
        has_all = all((d / f).exists() for f in ['context_plan.md','context_list.md','context_note.md'])
        py_count = len(list(d.glob('*.py')))
        s = 'OK' if has_all else 'MISSING'
        print(f'{str(d.relative_to(agents)):<35} docs={s:<8} py={py_count}')
        if has_all: ok += 1

root = Path('.')
for f in ['master_plan.md','context_list.md','context_note.md','.clinerules','docs/ai/mistakes.md']:
    exists = (root / f).exists()
    print(f'ROOT {f}: {"OK" if exists else "MISSING"}')

print(f'\nTotal agents with full docs: {ok}')
