import re

with open('inbox-app/src/App.tsx', encoding='utf-8') as f:
    content = f.read()

if 'Send,' not in content and 'Send }' not in content:
    content = content.replace('Archive,', 'Archive,\n  Send,')

route_code = """
  if (activeView === "broadcasts") {
    return (
      <main className="database-shell">
        <BroadcastsWorkspace
          adminName={adminName}
          activeView={activeView}
          onSwitchView={switchView}
          onLogout={() => void logout()}
        />
        {error ? (
          <div className="toast" role="status">
            {error}
          </div>
        ) : null}
      </main>
    );
  }

  return ("""

content = content.replace('  return (\n    <main className="app-shell">', route_code + '\n    <main className="app-shell">')

view_tab = """      <button
        className={activeView === "database" ? "view-tab is-active" : "view-tab"}
        onClick={() => onSwitchView("database")}
        type="button"
      >
        <DatabaseIcon aria-hidden="true" size={16} />
        <span>База</span>
      </button>
      <button
        className={activeView === "broadcasts" ? "view-tab is-active" : "view-tab"}
        onClick={() => onSwitchView("broadcasts")}
        type="button"
      >
        <Send aria-hidden="true" size={16} />
        <span>Рассылки</span>
      </button>"""

if '<Send aria-hidden="true" size={16} />' not in content:
    content = re.sub(r'<button[^>]*onClick={\(\) => onSwitchView\("database"\)}.*?</button>', view_tab, content, flags=re.DOTALL)

with open('inbox-app/src/App.tsx', 'w', encoding='utf-8') as f:
    f.write(content)
