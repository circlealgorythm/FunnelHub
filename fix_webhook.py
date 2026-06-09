with open('tests/test_getcourse_webhook.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if 'funnel_key="aisu_consultation",' in line:
        lines[i] = line + '                            channel="vk",\n'

with open('tests/test_getcourse_webhook.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)
