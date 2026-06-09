with open('tests/test_funnel_engine.py', 'r', encoding='utf-8') as f:
    c = f.read()

c = c.replace('channel=\\"telegram\\"', 'channel="telegram"')

with open('tests/test_funnel_engine.py', 'w', encoding='utf-8') as f:
    f.write(c)
