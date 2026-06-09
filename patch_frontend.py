
with open('inbox-app/src/App.tsx', encoding='utf-8') as f:
    content = f.read()

# 1. Update Broadcast type
content = content.replace('  failed_leads: number;\n  created_at: string;', '  failed_leads: number;\n  skipped_leads: number;\n  created_at: string;')

# 2. Add BroadcastTarget types
broadcast_targets_type = '''
type BroadcastTarget = {
  id: string;
  lead_id: string;
  lead_name: string | null;
  lead_contact: string | null;
  status: string;
  error: string | null;
};

type BroadcastTargetList = {
  items: BroadcastTarget[];
  total: number;
};
'''
content = content.replace('type BroadcastList = {', broadcast_targets_type + 'type BroadcastList = {')

# 3. Update BroadcastsWorkspace to select a broadcast
if 'const [selectedBroadcastId, setSelectedBroadcastId] = useState<string | null>(null);' not in content:
    content = content.replace('const [showCreate, setShowCreate] = useState(false);', 'const [showCreate, setShowCreate] = useState(false);\n  const [selectedBroadcastId, setSelectedBroadcastId] = useState<string | null>(null);')

# 4. Add "Пропущено" column in table header
if '<th>Пропущено</th>' not in content:
    content = content.replace('<th>Прогресс</th>\n              </tr>', '<th>Пропущено</th>\n                <th>Прогресс</th>\n              </tr>')

# 5. Add "Пропущено" in rows and onClick handler
row_old = '''                  <tr key={b.id}>
                    <td>{new Date(b.created_at).toLocaleString("ru-RU")}</td>
                    <td>{b.channels.map(c => channelLabels[c] || c).join(", ")}</td>
                    <td><code className="mono-badge">{b.segment_query || "Все"}</code></td>
                    <td><StatusPill status={b.status as ConversationStatus} /></td>
                    <td>
                      {b.processed_leads} / {b.total_leads}
                      {b.failed_leads > 0 && ` (${b.failed_leads} err)`}
                    </td>
                  </tr>'''

row_new = '''                  <tr key={b.id} onClick={() => setSelectedBroadcastId(b.id)} style={{ cursor: "pointer" }}>
                    <td>{new Date(b.created_at).toLocaleString("ru-RU")}</td>
                    <td>{b.channels.map(c => channelLabels[c] || c).join(", ")}</td>
                    <td><code className="mono-badge">{b.segment_query || "Все"}</code></td>
                    <td><StatusPill status={b.status as ConversationStatus} /></td>
                    <td>{b.skipped_leads}</td>
                    <td>
                      {b.processed_leads} / {b.total_leads}
                      {b.failed_leads > 0 && ` (${b.failed_leads} err)`}
                    </td>
                  </tr>'''
content = content.replace(row_old, row_new)

# 6. Add BroadcastDetailModal
detail_modal_code = '''
      {selectedBroadcastId ? (
        <BroadcastDetailModal
          broadcastId={selectedBroadcastId}
          onClose={() => setSelectedBroadcastId(null)}
        />
      ) : null}
'''
if 'BroadcastDetailModal' not in content:
    content = content.replace('{showCreate ? (', detail_modal_code + '\n      {showCreate ? (')


# 7. Define BroadcastDetailModal component
component_code = '''
function BroadcastDetailModal({
  broadcastId,
  onClose,
}: {
  broadcastId: string;
  onClose: () => void;
}) {
  const [targets, setTargets] = useState<BroadcastTarget[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const res = await fetch(`${API_BASE_URL}/api/inbox/broadcasts/${broadcastId}/targets`, {
          credentials: "include"
        });
        if (!res.ok) throw new Error(`Load failed: ${res.status}`);
        const data = (await res.json()) as BroadcastTargetList;
        setTargets(data.items);
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setLoading(false);
      }
    }
    void load();
  }, [broadcastId]);

  return (
    <div className="modal-overlay">
      <div className="modal-dialog" style={{ maxWidth: 800 }}>
        <header className="modal-header">
          <h2>Детали рассылки</h2>
          <button className="icon-button soft-button" onClick={onClose} type="button">
            <LogOut aria-hidden="true" size={18} />
          </button>
        </header>
        <div className="modal-body" style={{ overflowY: "auto", maxHeight: "60vh" }}>
          {error ? <div className="toast" role="status">{error}</div> : null}
          {loading ? (
            <div style={{ textAlign: "center", padding: "2rem" }}>Загрузка...</div>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Имя</th>
                  <th>Контакт</th>
                  <th>Статус</th>
                  <th>Ошибка</th>
                </tr>
              </thead>
              <tbody>
                {targets.map(t => (
                  <tr key={t.id}>
                    <td>{t.lead_name || "Без имени"}</td>
                    <td>{t.lead_contact || "—"}</td>
                    <td><code className="mono-badge">{t.status}</code></td>
                    <td style={{ color: "var(--danger)" }}>{t.error || ""}</td>
                  </tr>
                ))}
                {targets.length === 0 && (
                  <tr>
                    <td colSpan={4} style={{ textAlign: "center" }}>Нет получателей</td>
                  </tr>
                )}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}
'''

content += component_code

with open('inbox-app/src/App.tsx', 'w', encoding='utf-8') as f:
    f.write(content)
