import {
  Archive,
  Check,
  ChevronLeft,
  Clock,
  Database as DatabaseIcon,
  Download,
  LockKeyhole,
  LogOut,
  MessageCircle,
  RefreshCw,
  Search,
  Send,
  Upload,
  UserRound,
} from "lucide-react";
import { ChangeEvent, FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

type ConversationStatus = "open" | "needs_reply" | "replied" | "closed";

type Conversation = {
  id: string;
  lead_id: string;
  channel: "telegram" | "vk" | string;
  status: ConversationStatus;
  last_message_at: string | null;
  lead_name: string | null;
  lead_status: string;
  email: string | null;
  phone: string | null;
  identity_display_name: string | null;
  identity_username: string | null;
  is_subscribed: boolean | null;
  last_message_body: string | null;
  last_message_direction: "inbound" | "outbound" | string | null;
  unread_count: number;
};

type InboxMessage = {
  id: string;
  channel: string;
  direction: "inbound" | "outbound" | string;
  message_type: string;
  body: string | null;
  status: string;
  created_at: string;
  sent_at: string | null;
  metadata: Record<string, unknown>;
};

type ConversationDetail = {
  conversation: Conversation;
  messages: InboxMessage[];
};

type LoadState = "idle" | "loading" | "error";
type AuthState = "checking" | "authenticated" | "anonymous";
type AppView = "inbox" | "database";

type DatabaseLead = {
  id: string;
  getcourse_user_id: number | null;
  name: string | null;
  email: string | null;
  phone: string | null;
  city: string | null;
  country: string | null;
  source: string | null;
  status: string;
  created_at: string;
  updated_at: string;
  telegram: string | null;
  vk: string | null;
  conversations_count: number;
  messages_count: number;
};

type DatabaseLeadList = {
  items: DatabaseLead[];
  total: number;
  limit: number;
  offset: number;
};

type DatabaseLeadDetail = {
  lead: DatabaseLead;
  contacts: Array<Record<string, unknown>>;
  identities: Array<Record<string, unknown>>;
  funnel_states: Array<Record<string, unknown>>;
  recent_messages: Array<Record<string, unknown>>;
  raw_getcourse_data: Record<string, unknown>;
};

type DatabaseImportSummary = {
  batch_id: string;
  total_rows: number;
  processed_rows: number;
  failed_rows: number;
  created_rows: number;
  updated_rows: number;
  errors: Array<Record<string, unknown>>;
};

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

const statusLabels: Record<ConversationStatus, string> = {
  open: "Открыт",
  needs_reply: "Ждет ответа",
  replied: "Отвечен",
  closed: "Закрыт",
};

const channelLabels: Record<string, string> = {
  telegram: "Telegram",
  vk: "VK",
};

const filters: Array<{ value: ConversationStatus | "all"; label: string }> = [
  { value: "needs_reply", label: "Ждут" },
  { value: "open", label: "Открытые" },
  { value: "replied", label: "Отвеченные" },
  { value: "closed", label: "Закрытые" },
  { value: "all", label: "Все" },
];

export function App() {
  const [authState, setAuthState] = useState<AuthState>("checking");
  const [adminName, setAdminName] = useState<string | null>(null);
  const [activeView, setActiveView] = useState<AppView>("inbox");
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ConversationDetail | null>(null);
  const [filter, setFilter] = useState<ConversationStatus | "all">("needs_reply");
  const [query, setQuery] = useState("");
  const [draft, setDraft] = useState("");
  const [listState, setListState] = useState<LoadState>("idle");
  const [detailState, setDetailState] = useState<LoadState>("idle");
  const [replyState, setReplyState] = useState<LoadState>("idle");
  const [databaseQuery, setDatabaseQuery] = useState("");
  const [databaseList, setDatabaseList] = useState<DatabaseLeadList | null>(null);
  const [selectedLeadId, setSelectedLeadId] = useState<string | null>(null);
  const [selectedLeadDetail, setSelectedLeadDetail] = useState<DatabaseLeadDetail | null>(null);
  const [databaseState, setDatabaseState] = useState<LoadState>("idle");
  const [databaseDetailState, setDatabaseDetailState] = useState<LoadState>("idle");
  const [databaseImportState, setDatabaseImportState] = useState<LoadState>("idle");
  const [databaseImportSummary, setDatabaseImportSummary] =
    useState<DatabaseImportSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  const checkAuth = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/auth/me`, {
        credentials: "include",
      });
      if (!response.ok) {
        setAuthState("anonymous");
        setAdminName(null);
        return;
      }
      const payload = (await response.json()) as { username: string | null };
      setAdminName(payload.username);
      setAuthState("authenticated");
    } catch {
      setAuthState("anonymous");
      setAdminName(null);
    }
  }, []);

  const selectedConversation = useMemo(
    () => conversations.find((conversation) => conversation.id === selectedId) ?? null,
    [conversations, selectedId]
  );

  const visibleConversations = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    if (!normalizedQuery) {
      return conversations;
    }
    return conversations.filter((conversation) =>
      [
        conversation.lead_name,
        conversation.identity_display_name,
        conversation.identity_username,
        conversation.email,
        conversation.phone,
        conversation.last_message_body,
      ]
        .filter(Boolean)
        .some((value) => value!.toLowerCase().includes(normalizedQuery))
    );
  }, [conversations, query]);

  const loadConversations = useCallback(async () => {
    setListState("loading");
    setError(null);
    try {
      const statusParam = filter === "all" ? "" : `?status=${filter}`;
      const response = await fetch(`${API_BASE_URL}/api/inbox/conversations${statusParam}`, {
        credentials: "include",
      });
      if (response.status === 401) {
        setAuthState("anonymous");
        setConversations([]);
        setSelectedId(null);
        setListState("idle");
        return;
      }
      if (!response.ok) {
        throw new Error(`Inbox list failed: ${response.status}`);
      }
      const payload = (await response.json()) as Conversation[];
      setConversations(payload);
      setSelectedId((current) => {
        if (current && payload.some((conversation) => conversation.id === current)) {
          return current;
        }
        const linkedConversationId = getLinkedConversationId();
        if (linkedConversationId && payload.some((conversation) => conversation.id === linkedConversationId)) {
          return linkedConversationId;
        }
        return payload[0]?.id ?? null;
      });
      setListState("idle");
    } catch (caught) {
      setListState("error");
      setError(formatError(caught));
    }
  }, [filter]);

  const loadDetail = useCallback(async (conversationId: string) => {
    setDetailState("loading");
    setError(null);
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/inbox/conversations/${conversationId}`,
        { credentials: "include" }
      );
      if (response.status === 401) {
        setAuthState("anonymous");
        setDetail(null);
        setDetailState("idle");
        return;
      }
      if (!response.ok) {
        throw new Error(`Inbox detail failed: ${response.status}`);
      }
      const payload = (await response.json()) as ConversationDetail;
      setDetail(payload);
      setDetailState("idle");
    } catch (caught) {
      setDetailState("error");
      setError(formatError(caught));
    }
  }, []);

  const loadDatabaseLeads = useCallback(async () => {
    setDatabaseState("loading");
    setError(null);
    try {
      const params = new URLSearchParams({ limit: "80", offset: "0" });
      if (databaseQuery.trim()) {
        params.set("q", databaseQuery.trim());
      }
      const response = await fetch(`${API_BASE_URL}/api/inbox/database/leads?${params}`, {
        credentials: "include",
      });
      if (response.status === 401) {
        setAuthState("anonymous");
        setDatabaseList(null);
        setSelectedLeadId(null);
        setDatabaseState("idle");
        return;
      }
      if (!response.ok) {
        throw new Error(`Database list failed: ${response.status}`);
      }
      const payload = (await response.json()) as DatabaseLeadList;
      setDatabaseList(payload);
      setSelectedLeadId((current) => {
        if (current && payload.items.some((lead) => lead.id === current)) {
          return current;
        }
        return payload.items[0]?.id ?? null;
      });
      setDatabaseState("idle");
    } catch (caught) {
      setDatabaseState("error");
      setError(formatError(caught));
    }
  }, [databaseQuery]);

  const loadDatabaseLeadDetail = useCallback(async (leadId: string) => {
    setDatabaseDetailState("loading");
    setError(null);
    try {
      const response = await fetch(`${API_BASE_URL}/api/inbox/database/leads/${leadId}`, {
        credentials: "include",
      });
      if (response.status === 401) {
        setAuthState("anonymous");
        setSelectedLeadDetail(null);
        setDatabaseDetailState("idle");
        return;
      }
      if (!response.ok) {
        throw new Error(`Database detail failed: ${response.status}`);
      }
      const payload = (await response.json()) as DatabaseLeadDetail;
      setSelectedLeadDetail(payload);
      setDatabaseDetailState("idle");
    } catch (caught) {
      setDatabaseDetailState("error");
      setError(formatError(caught));
    }
  }, []);

  useEffect(() => {
    void checkAuth();
  }, [checkAuth]);

  useEffect(() => {
    if (authState === "authenticated") {
      void loadConversations();
    }
  }, [authState, loadConversations]);

  useEffect(() => {
    if (authState === "authenticated" && activeView === "database") {
      void loadDatabaseLeads();
    }
  }, [activeView, authState, loadDatabaseLeads]);

  useEffect(() => {
    if (selectedId) {
      void loadDetail(selectedId);
    } else {
      setDetail(null);
    }
  }, [loadDetail, selectedId]);

  useEffect(() => {
    if (activeView === "database" && selectedLeadId) {
      void loadDatabaseLeadDetail(selectedLeadId);
    } else {
      setSelectedLeadDetail(null);
    }
  }, [activeView, loadDatabaseLeadDetail, selectedLeadId]);

  async function submitReply(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedId || !draft.trim()) {
      return;
    }

    setReplyState("loading");
    setError(null);
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/inbox/conversations/${selectedId}/reply`,
        {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text: draft.trim() }),
        }
      );
      if (!response.ok) {
        throw new Error(`Reply failed: ${response.status}`);
      }
      setDraft("");
      await loadConversations();
      await loadDetail(selectedId);
      setReplyState("idle");
    } catch (caught) {
      setReplyState("error");
      setError(formatError(caught));
    }
  }

  async function updateStatus(status: ConversationStatus) {
    if (!selectedId) {
      return;
    }
    setError(null);
    try {
      const response = await fetch(`${API_BASE_URL}/api/inbox/conversations/${selectedId}`, {
        method: "PATCH",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status }),
      });
      if (!response.ok) {
        throw new Error(`Status update failed: ${response.status}`);
      }
      await loadConversations();
      await loadDetail(selectedId);
    } catch (caught) {
      setError(formatError(caught));
    }
  }

  function handleSelectConversation(conversationId: string) {
    window.history.replaceState(null, "", `?conversation=${conversationId}`);
    setSelectedId(conversationId);
  }

  function switchView(view: AppView) {
    setActiveView(view);
    const url = view === "inbox" && selectedId ? `?conversation=${selectedId}` : window.location.pathname;
    window.history.replaceState(null, "", url);
  }

  function submitDatabaseSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSelectedLeadId(null);
    void loadDatabaseLeads();
  }

  async function exportDatabase() {
    setError(null);
    try {
      const params = new URLSearchParams();
      if (databaseQuery.trim()) {
        params.set("q", databaseQuery.trim());
      }
      const suffix = params.toString() ? `?${params}` : "";
      const response = await fetch(`${API_BASE_URL}/api/inbox/database/leads/export${suffix}`, {
        credentials: "include",
      });
      if (!response.ok) {
        throw new Error(`Export failed: ${response.status}`);
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `funnelhub-leads-${new Date().toISOString().slice(0, 10)}.csv`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (caught) {
      setError(formatError(caught));
    }
  }

  async function importDatabase(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) {
      return;
    }

    setDatabaseImportState("loading");
    setDatabaseImportSummary(null);
    setError(null);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const response = await fetch(`${API_BASE_URL}/api/inbox/database/leads/import`, {
        method: "POST",
        credentials: "include",
        body: formData,
      });
      if (!response.ok) {
        throw new Error(`Import failed: ${response.status}`);
      }
      const payload = (await response.json()) as DatabaseImportSummary;
      setDatabaseImportSummary(payload);
      setDatabaseImportState("idle");
      await loadDatabaseLeads();
    } catch (caught) {
      setDatabaseImportState("error");
      setError(formatError(caught));
    }
  }

  async function handleLogin(username: string, password: string) {
    setError(null);
    const response = await fetch(`${API_BASE_URL}/api/auth/login`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    if (!response.ok) {
      if (response.status === 503) {
        throw new Error("Доступ еще не настроен на сервере.");
      }
      throw new Error("Неверный логин или пароль.");
    }
    const payload = (await response.json()) as { username: string | null };
    setAdminName(payload.username);
    setAuthState("authenticated");
    await loadConversations();
  }

  async function logout() {
    await fetch(`${API_BASE_URL}/api/auth/logout`, {
      method: "POST",
      credentials: "include",
    });
    setAuthState("anonymous");
    setAdminName(null);
    setConversations([]);
    setSelectedId(null);
    setDetail(null);
    setDatabaseList(null);
    setSelectedLeadId(null);
    setSelectedLeadDetail(null);
  }

  if (authState === "checking") {
    return (
      <main className="login-shell">
        <div className="login-card">
          <div className="login-mark" aria-hidden="true">
            <LockKeyhole size={28} />
          </div>
          <p className="eyebrow">FunnelHub</p>
          <h1>Inbox</h1>
          <p className="login-copy">Проверяем доступ...</p>
        </div>
      </main>
    );
  }

  if (authState === "anonymous") {
    return <LoginScreen onLogin={handleLogin} />;
  }

  if (activeView === "database") {
    return (
      <main className="database-shell">
        <DatabaseWorkspace
          adminName={adminName}
          databaseDetailState={databaseDetailState}
          databaseImportState={databaseImportState}
          databaseImportSummary={databaseImportSummary}
          databaseList={databaseList}
          databaseQuery={databaseQuery}
          databaseState={databaseState}
          onExport={() => void exportDatabase()}
          onImport={(event) => void importDatabase(event)}
          onLogout={() => void logout()}
          onQueryChange={setDatabaseQuery}
          onRefresh={() => void loadDatabaseLeads()}
          onSearch={submitDatabaseSearch}
          onSelectLead={setSelectedLeadId}
          onSwitchView={switchView}
          selectedLeadDetail={selectedLeadDetail}
          selectedLeadId={selectedLeadId}
        />
        {error ? (
          <div className="toast" role="status">
            {error}
          </div>
        ) : null}
      </main>
    );
  }

  return (
    <main className="app-shell">
      <section className={`conversation-panel ${selectedId ? "is-hidden-mobile" : ""}`}>
        <header className="panel-header">
          <div>
            <p className="eyebrow">FunnelHub</p>
            <h1>Inbox</h1>
            <ViewSwitch activeView={activeView} onSwitchView={switchView} />
          </div>
          <div className="panel-actions" aria-label="Действия inbox">
            <button className="icon-button" onClick={() => void loadConversations()} type="button">
              <RefreshCw aria-hidden="true" size={18} />
              <span className="sr-only">Обновить список</span>
            </button>
            <button className="icon-button secondary" onClick={() => void logout()} type="button">
              <LogOut aria-hidden="true" size={18} />
              <span className="sr-only">Выйти{adminName ? `, ${adminName}` : ""}</span>
            </button>
          </div>
        </header>

        <div className="search-field">
          <Search aria-hidden="true" size={18} />
          <input
            aria-label="Поиск диалогов"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Имя, контакт, сообщение"
          />
        </div>

        <div className="filter-row" aria-label="Фильтр диалогов">
          {filters.map((item) => (
            <button
              className={filter === item.value ? "filter-chip is-active" : "filter-chip"}
              key={item.value}
              onClick={() => {
                setSelectedId(null);
                setFilter(item.value);
              }}
              type="button"
            >
              {item.label}
            </button>
          ))}
        </div>

        <div className="conversation-list" aria-live="polite">
          {listState === "loading" ? <ConversationSkeleton /> : null}
          {listState !== "loading" && visibleConversations.length === 0 ? (
            <EmptyList />
          ) : null}
          {visibleConversations.map((conversation) => (
            <button
              className={
                conversation.id === selectedId
                  ? "conversation-item is-selected"
                  : "conversation-item"
              }
              key={conversation.id}
              onClick={() => handleSelectConversation(conversation.id)}
              type="button"
            >
              <span className={`channel-dot channel-${conversation.channel}`} />
              <span className="conversation-main">
                <span className="conversation-title">
                  {displayName(conversation)}
                  {conversation.unread_count > 0 ? (
                    <span className="unread-count">{conversation.unread_count}</span>
                  ) : null}
                </span>
                <span className="conversation-preview">
                  {conversation.last_message_body ?? "Пока нет сообщений"}
                </span>
              </span>
              <span className="conversation-meta">
                <StatusPill status={conversation.status} />
                <time>{formatRelativeDate(conversation.last_message_at)}</time>
              </span>
            </button>
          ))}
        </div>
      </section>

      <section className={`chat-panel ${selectedId ? "is-active-mobile" : ""}`}>
        {selectedConversation && detail ? (
          <>
            <header className="chat-header">
              <button className="back-button" onClick={() => setSelectedId(null)} type="button">
                <ChevronLeft aria-hidden="true" size={18} />
                <span>Назад</span>
              </button>
              <div className="lead-heading">
                <div className="avatar" aria-hidden="true">
                  <UserRound size={22} />
                </div>
                <div>
                  <h2>{displayName(selectedConversation)}</h2>
                  <p>
                    {channelLabels[selectedConversation.channel] ?? selectedConversation.channel}
                    {selectedConversation.identity_username
                      ? ` · @${selectedConversation.identity_username}`
                      : ""}
                  </p>
                </div>
              </div>
              <div className="header-actions">
                <button
                  className="soft-button"
                  onClick={() => void updateStatus("replied")}
                  type="button"
                >
                  <Check aria-hidden="true" size={17} />
                  <span>Отвечен</span>
                </button>
                <button
                  className="soft-button"
                  onClick={() => void updateStatus("closed")}
                  type="button"
                >
                  <Archive aria-hidden="true" size={17} />
                  <span>Закрыть</span>
                </button>
              </div>
            </header>

            <div className="workspace">
              <div className="message-stream" aria-live="polite">
                {detailState === "loading" ? <MessageSkeleton /> : null}
                {detail.messages.map((message) => (
                  <article
                    className={
                      message.direction === "outbound"
                        ? "message-bubble is-outbound"
                        : "message-bubble is-inbound"
                    }
                    key={message.id}
                  >
                    <p>{message.body}</p>
                    <footer>
                      <span>{message.direction === "outbound" ? "Айсу" : "Клиент"}</span>
                      <time>{formatTime(message.created_at)}</time>
                    </footer>
                  </article>
                ))}
              </div>

              <aside className="lead-panel">
                <div className="lead-block">
                  <span className="lead-label">Статус</span>
                  <StatusPill status={selectedConversation.status} />
                </div>
                <div className="lead-block">
                  <span className="lead-label">Канал</span>
                  <strong>
                    {channelLabels[selectedConversation.channel] ?? selectedConversation.channel}
                  </strong>
                </div>
                <div className="lead-block">
                  <span className="lead-label">Контакты</span>
                  <p>{selectedConversation.email ?? "email не указан"}</p>
                  <p>{selectedConversation.phone ?? "телефон не указан"}</p>
                </div>
                <div className="lead-block">
                  <span className="lead-label">Подписка</span>
                  <strong>
                    {selectedConversation.is_subscribed ? "активна" : "неактивна"}
                  </strong>
                </div>
              </aside>
            </div>

            <form className="reply-box" onSubmit={(event) => void submitReply(event)}>
              <label htmlFor="reply">Ответ</label>
              <textarea
                id="reply"
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                placeholder="Напишите личный ответ..."
                rows={3}
              />
              <button className="send-button" disabled={replyState === "loading"} type="submit">
                <Send aria-hidden="true" size={18} />
                <span>{replyState === "loading" ? "Отправка" : "Отправить"}</span>
              </button>
            </form>
          </>
        ) : (
          <div className="blank-chat">
            <MessageCircle aria-hidden="true" size={42} />
            <h2>Выберите диалог</h2>
            <p>Входящие из Telegram и VK появятся здесь после первого сообщения клиента.</p>
          </div>
        )}
      </section>

      {error ? (
        <div className="toast" role="status">
          {error}
        </div>
      ) : null}
    </main>
  );
}

function getLinkedConversationId() {
  return new URLSearchParams(window.location.search).get("conversation");
}

function ViewSwitch({
  activeView,
  onSwitchView,
}: {
  activeView: AppView;
  onSwitchView: (view: AppView) => void;
}) {
  return (
    <nav className="view-switch" aria-label="Разделы">
      <button
        className={activeView === "inbox" ? "view-tab is-active" : "view-tab"}
        onClick={() => onSwitchView("inbox")}
        type="button"
      >
        <MessageCircle aria-hidden="true" size={16} />
        <span>Inbox</span>
      </button>
      <button
        className={activeView === "database" ? "view-tab is-active" : "view-tab"}
        onClick={() => onSwitchView("database")}
        type="button"
      >
        <DatabaseIcon aria-hidden="true" size={16} />
        <span>База</span>
      </button>
    </nav>
  );
}

function DatabaseWorkspace({
  adminName,
  databaseDetailState,
  databaseImportState,
  databaseImportSummary,
  databaseList,
  databaseQuery,
  databaseState,
  onExport,
  onImport,
  onLogout,
  onQueryChange,
  onRefresh,
  onSearch,
  onSelectLead,
  onSwitchView,
  selectedLeadDetail,
  selectedLeadId,
}: {
  adminName: string | null;
  databaseDetailState: LoadState;
  databaseImportState: LoadState;
  databaseImportSummary: DatabaseImportSummary | null;
  databaseList: DatabaseLeadList | null;
  databaseQuery: string;
  databaseState: LoadState;
  onExport: () => void;
  onImport: (event: ChangeEvent<HTMLInputElement>) => void;
  onLogout: () => void;
  onQueryChange: (query: string) => void;
  onRefresh: () => void;
  onSearch: (event: FormEvent<HTMLFormElement>) => void;
  onSelectLead: (leadId: string) => void;
  onSwitchView: (view: AppView) => void;
  selectedLeadDetail: DatabaseLeadDetail | null;
  selectedLeadId: string | null;
}) {
  const leads = databaseList?.items ?? [];
  return (
    <>
      <header className="database-header">
        <div>
          <p className="eyebrow">FunnelHub</p>
          <h1>База</h1>
          <ViewSwitch activeView="database" onSwitchView={onSwitchView} />
        </div>
        <div className="database-actions">
          <button className="soft-button" onClick={onRefresh} type="button">
            <RefreshCw aria-hidden="true" size={17} />
            <span>Обновить</span>
          </button>
          <button className="soft-button" onClick={onExport} type="button">
            <Download aria-hidden="true" size={17} />
            <span>Выгрузить CSV</span>
          </button>
          <label className="soft-button file-button">
            <Upload aria-hidden="true" size={17} />
            <span>{databaseImportState === "loading" ? "Загрузка" : "Загрузить CSV"}</span>
            <input accept=".csv,text/csv" onChange={onImport} type="file" />
          </label>
          <button className="icon-button secondary" onClick={onLogout} type="button">
            <LogOut aria-hidden="true" size={18} />
            <span className="sr-only">Выйти{adminName ? `, ${adminName}` : ""}</span>
          </button>
        </div>
      </header>

      <section className="database-grid">
        <div className="database-list-panel">
          <form className="database-search" onSubmit={onSearch}>
            <Search aria-hidden="true" size={18} />
            <input
              aria-label="Поиск по базе"
              onChange={(event) => onQueryChange(event.target.value)}
              placeholder="Имя, email, телефон, Telegram, VK"
              value={databaseQuery}
            />
            <button className="soft-button" type="submit">
              Найти
            </button>
          </form>

          <div className="database-summary">
            <span>{databaseList ? `${databaseList.total} лидов` : "База лидов"}</span>
            {databaseImportSummary ? (
              <span>
                Импорт: {databaseImportSummary.processed_rows} ок,{" "}
                {databaseImportSummary.failed_rows} ошибок
              </span>
            ) : null}
          </div>

          <div className="lead-table-wrap">
            <table className="lead-table">
              <thead>
                <tr>
                  <th>Лид</th>
                  <th>Контакт</th>
                  <th>Канал</th>
                  <th>Активность</th>
                </tr>
              </thead>
              <tbody>
                {databaseState === "loading" ? (
                  <tr>
                    <td colSpan={4}>Загружаем базу...</td>
                  </tr>
                ) : null}
                {databaseState !== "loading" && leads.length === 0 ? (
                  <tr>
                    <td colSpan={4}>Нет лидов по этому поиску.</td>
                  </tr>
                ) : null}
                {leads.map((lead) => (
                  <tr
                    className={lead.id === selectedLeadId ? "is-selected" : ""}
                    key={lead.id}
                    onClick={() => onSelectLead(lead.id)}
                  >
                    <td>
                      <strong>{lead.name ?? "Без имени"}</strong>
                      <span>{lead.getcourse_user_id ? `GC ${lead.getcourse_user_id}` : lead.status}</span>
                    </td>
                    <td>
                      <span>{lead.email ?? "email нет"}</span>
                      <span>{lead.phone ?? "телефон нет"}</span>
                    </td>
                    <td>
                      <span>{lead.telegram ? `TG @${lead.telegram}` : "TG нет"}</span>
                      <span>{lead.vk ? `VK @${lead.vk}` : "VK нет"}</span>
                    </td>
                    <td>
                      <span>{lead.conversations_count} диалогов</span>
                      <span>{lead.messages_count} сообщений</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <aside className="database-detail-panel">
          {databaseDetailState === "loading" ? (
            <div className="detail-empty">Загружаем карточку...</div>
          ) : selectedLeadDetail ? (
            <LeadDatabaseDetail detail={selectedLeadDetail} />
          ) : (
            <div className="detail-empty">
              <DatabaseIcon aria-hidden="true" size={34} />
              <h2>Выберите лида</h2>
              <p>Карточка покажет контакты, каналы, состояние воронки и последние сообщения.</p>
            </div>
          )}
        </aside>
      </section>
    </>
  );
}

function LeadDatabaseDetail({ detail }: { detail: DatabaseLeadDetail }) {
  return (
    <div className="lead-detail">
      <div className="lead-detail-head">
        <div className="avatar" aria-hidden="true">
          <UserRound size={22} />
        </div>
        <div>
          <h2>{detail.lead.name ?? "Без имени"}</h2>
          <p>{detail.lead.source ?? "источник не указан"}</p>
        </div>
      </div>

      <div className="detail-stats">
        <div>
          <span>Диалоги</span>
          <strong>{detail.lead.conversations_count}</strong>
        </div>
        <div>
          <span>Сообщения</span>
          <strong>{detail.lead.messages_count}</strong>
        </div>
        <div>
          <span>Статус</span>
          <strong>{detail.lead.status}</strong>
        </div>
      </div>

      <DetailSection title="Контакты">
        {detail.contacts.length === 0 ? <p>Контактов нет.</p> : null}
        {detail.contacts.map((contact, index) => (
          <p key={`${String(contact.type)}-${index}`}>
            <strong>{String(contact.type)}:</strong> {String(contact.value)}
          </p>
        ))}
      </DetailSection>

      <DetailSection title="Мессенджеры">
        {detail.identities.length === 0 ? <p>Мессенджеры не привязаны.</p> : null}
        {detail.identities.map((identity, index) => (
          <p key={`${String(identity.channel)}-${index}`}>
            <strong>{String(identity.channel)}:</strong>{" "}
            {String(identity.username || identity.display_name || identity.external_user_id)}
            {identity.is_subscribed ? " · активен" : " · отписан"}
          </p>
        ))}
      </DetailSection>

      <DetailSection title="Воронка">
        {detail.funnel_states.length === 0 ? <p>Нет активных состояний.</p> : null}
        {detail.funnel_states.map((state, index) => (
          <p key={`${String(state.funnel_key)}-${index}`}>
            <strong>{String(state.status)}:</strong>{" "}
            {String(state.current_step_key || state.funnel_key)}
          </p>
        ))}
      </DetailSection>

      <DetailSection title="Последние сообщения">
        {detail.recent_messages.length === 0 ? <p>Сообщений нет.</p> : null}
        {detail.recent_messages.map((message) => (
          <p key={String(message.id)}>
            <strong>{String(message.channel)} · {String(message.direction)}:</strong>{" "}
            {String(message.body || "без текста")}
          </p>
        ))}
      </DetailSection>

      <DetailSection title="GetCourse">
        <pre>{JSON.stringify(detail.raw_getcourse_data, null, 2)}</pre>
      </DetailSection>
    </div>
  );
}

function DetailSection({
  children,
  title,
}: {
  children: ReactNode;
  title: string;
}) {
  return (
    <section className="detail-section">
      <h3>{title}</h3>
      {children}
    </section>
  );
}

function LoginScreen({ onLogin }: { onLogin: (username: string, password: string) => Promise<void> }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [state, setState] = useState<LoadState>("idle");
  const [message, setMessage] = useState<string | null>(null);

  async function submitLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setState("loading");
    setMessage(null);
    try {
      await onLogin(username.trim(), password);
      setState("idle");
    } catch (caught) {
      setState("error");
      setMessage(formatError(caught));
    }
  }

  return (
    <main className="login-shell">
      <section className="login-card" aria-labelledby="login-title">
        <div className="login-mark" aria-hidden="true">
          <LockKeyhole size={28} />
        </div>
        <p className="eyebrow">FunnelHub</p>
        <h1 id="login-title">Вход в Inbox</h1>
        <p className="login-copy">Закрытая рабочая панель Айсу для входящих сообщений.</p>
        <form className="login-form" onSubmit={(event) => void submitLogin(event)}>
          <label htmlFor="username">Логин</label>
          <input
            id="username"
            autoComplete="username"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
          />
          <label htmlFor="password">Пароль</label>
          <input
            id="password"
            autoComplete="current-password"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
          <button
            className="login-button"
            disabled={state === "loading" || !username.trim() || !password}
            type="submit"
          >
            <LockKeyhole aria-hidden="true" size={18} />
            <span>{state === "loading" ? "Входим" : "Войти"}</span>
          </button>
        </form>
        {message ? (
          <p className="login-error" role="status">
            {message}
          </p>
        ) : null}
      </section>
    </main>
  );
}

function StatusPill({ status }: { status: ConversationStatus }) {
  return <span className={`status-pill status-${status}`}>{statusLabels[status]}</span>;
}

function ConversationSkeleton() {
  return (
    <>
      <div className="skeleton-row" />
      <div className="skeleton-row" />
      <div className="skeleton-row" />
    </>
  );
}

function MessageSkeleton() {
  return (
    <>
      <div className="skeleton-message" />
      <div className="skeleton-message is-short" />
    </>
  );
}

function EmptyList() {
  return (
    <div className="empty-list">
      <Clock aria-hidden="true" size={26} />
      <p>Нет диалогов в этом фильтре.</p>
    </div>
  );
}

function displayName(conversation: Conversation) {
  return (
    conversation.lead_name ||
    conversation.identity_display_name ||
    conversation.identity_username ||
    "Без имени"
  );
}

function formatRelativeDate(value: string | null) {
  if (!value) {
    return "";
  }
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat("ru-RU", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function formatError(caught: unknown) {
  if (caught instanceof Error) {
    return caught.message;
  }
  return "Не удалось выполнить действие.";
}
