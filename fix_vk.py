with open('tests/test_funnel_runner.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if 'await start_funnel_for_lead(session, lead_id, definition, channel="telegram", now=now)' in line and i > 400:
        lines[i] = line.replace('channel="telegram"', 'channel="vk"')
        break

with open('tests/test_funnel_runner.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)
