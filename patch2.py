
components_code = """

// --- Broadcasts Components ---

function BroadcastsWorkspace({
  adminName,
  activeView,
  onSwitchView,
  onLogout,
}: {
  adminName: string | null;
  activeView: AppView;
  onSwitchView: (view: AppView) => void;
  onLogout: () => void;
}) {
  const [broadcasts, setBroadcasts] = useState<Broadcast[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);

  const loadBroadcasts = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE_URL}/api/inbox/broadcasts`, {
        credentials: "include",
      });
      if (!response.ok) {
        throw new Error(`Load failed: ${response.status}`);
      }
      const data = (await response.json()) as BroadcastList;
      setBroadcasts(data.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadBroadcasts();
  }, [loadBroadcasts]);

  return (
    <>
      <header className="panel-header">
        <div>
          <p className="eyebrow">FunnelHub</p>
          <h1>Рассылки</h1>
          <ViewSwitch activeView={activeView} onSwitchView={onSwitchView} />
        </div>
        <div className="panel-actions">
          <button className="primary-button" onClick={() => setShowCreate(true)} type="button">
            Создать
          </button>
          <button className="icon-button" onClick={loadBroadcasts} type="button">
            <RefreshCw aria-hidden="true" size={18} />
          </button>
          <button className="icon-button secondary" onClick={onLogout} type="button">
            <LogOut aria-hidden="true" size={18} />
          </button>
        </div>
      </header>

      <div className="workspace is-list-only">
        {error ? <div className="toast" role="status">{error}</div> : null}
        <div className="table-wrapper">
          <table className="data-table">
            <thead>
              <tr>
                <th>Дата</th>
                <th>Каналы</th>
                <th>Сегмент</th>
                <th>Статус</th>
                <th>Прогресс</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={5} style={{ textAlign: "center", padding: "2rem" }}>Загрузка...</td>
                </tr>
              ) : broadcasts.length === 0 ? (
                <tr>
                  <td colSpan={5} style={{ textAlign: "center", padding: "2rem" }}>Нет рассылок</td>
                </tr>
              ) : (
                broadcasts.map((b) => (
                  <tr key={b.id}>
                    <td>{new Date(b.created_at).toLocaleString("ru-RU")}</td>
                    <td>{b.channels.map(c => channelLabels[c] || c).join(", ")}</td>
                    <td><code className="mono-badge">{b.segment_query || "Все"}</code></td>
                    <td><StatusPill status={b.status as ConversationStatus} /></td>
                    <td>
                      {b.processed_leads} / {b.total_leads}
                      {b.failed_leads > 0 && ` (${b.failed_leads} err)`}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {showCreate ? (
        <BroadcastCreateModal
          onClose={() => setShowCreate(false)}
          onSuccess={() => {
            setShowCreate(false);
            void loadBroadcasts();
          }}
        />
      ) : null}
    </>
  );
}

function BroadcastCreateModal({
  onClose,
  onSuccess,
}: {
  onClose: () => void;
  onSuccess: () => void;
}) {
  const [query, setQuery] = useState("");
  const [text, setText] = useState("");
  const [channels, setChannels] = useState<string[]>(["telegram"]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const toggleChannel = (ch: string) => {
    setChannels(prev => prev.includes(ch) ? prev.filter(c => c !== ch) : [...prev, ch]);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (channels.length === 0) {
      setError("Выберите хотя бы один канал");
      return;
    }
    if (!text.trim()) {
      setError("Введите текст рассылки");
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE_URL}/api/inbox/broadcasts`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          segment_query: query.trim() || null,
          channels,
          message_text: text.trim(),
        }),
      });

      if (!res.ok) {
        const payload = await res.json().catch(() => null);
        throw new Error(payload?.detail || `Ошибка ${res.status}`);
      }
      onSuccess();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setLoading(false);
    }
  };

  return (
    <div className="modal-overlay">
      <div className="modal-dialog">
        <header className="modal-header">
          <h2>Новая рассылка</h2>
          <button className="icon-button soft-button" onClick={onClose} type="button">
            <LogOut aria-hidden="true" size={18} />
          </button>
        </header>
        <form className="modal-body" onSubmit={handleSubmit}>
          {error ? <div className="form-error">{error}</div> : null}
          
          <div className="form-group">
            <label>Сегмент (запрос как в базе)</label>
            <input 
              type="text" 
              value={query} 
              onChange={e => setQuery(e.target.value)} 
              placeholder="Например: status:active"
            />
            <p className="field-hint">Оставьте пустым, чтобы отправить всем лидам.</p>
          </div>

          <div className="form-group">
            <label>Каналы отправки</label>
            <div className="channel-toggles">
              {["telegram", "vk", "email"].map((ch) => (
                <button
                  key={ch}
                  type="button"
                  className={channels.includes(ch) ? "channel-toggle is-active" : "channel-toggle"}
                  onClick={() => toggleChannel(ch)}
                >
                  <span className={`channel-dot channel-${ch}`} />
                  {channelLabels[ch] || ch}
                </button>
              ))}
            </div>
          </div>

          <div className="form-group">
            <label>Текст сообщения</label>
            <textarea 
              value={text}
              onChange={e => setText(e.target.value)}
              placeholder="Введите текст рассылки..."
              rows={6}
              required
            />
          </div>

          <footer className="modal-footer">
            <button className="secondary-button" type="button" onClick={onClose} disabled={loading}>Отмена</button>
            <button className="primary-button" type="submit" disabled={loading}>
              <Send size={16} />
              {loading ? "Запуск..." : "Запустить рассылку"}
            </button>
          </footer>
        </form>
      </div>
    </div>
  );
}
"""

with open('inbox-app/src/App.tsx', 'a', encoding='utf-8') as f:
    f.write(components_code)
