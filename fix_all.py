import re
import glob

for filepath in glob.glob('tests/*.py'):
    with open(filepath, 'r', encoding='utf-8') as f:
        c = f.read()

    original_c = c
    
    # replace start_funnel_for_lead(...)
    c = re.sub(
        r'start_funnel_for_lead\(\s*session,\s*lead_id,\s*definition,\s*now=',
        r'start_funnel_for_lead(session, lead_id, definition, channel="telegram", now=',
        c
    )
    c = re.sub(
        r'start_funnel_for_lead\(\s*session,\s*lead_id,\s*definition\s*\)',
        r'start_funnel_for_lead(session, lead_id, definition, channel="telegram")',
        c
    )
    
    if c != original_c:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(c)
        print(f"Patched {filepath}")
