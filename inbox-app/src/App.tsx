import {
  Archive,
  Check,
  ChevronDown,
  ChevronLeft,
  Clock,
  Copy,
  Database as DatabaseIcon,
  Download,
  ExternalLink,
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
type ReplyChannel = "telegram" | "vk" | "email";

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

type ReplyChannelOption = {
  channel: ReplyChannel;
  label: string;
  detail: string | null;
  is_default: boolean;
};

type ConversationDetail = {
  conversation: Conversation;
  messages: InboxMessage[];
  reply_channels: ReplyChannelOption[];
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
  bot_links: Array<{
    channel: string;
    label: string;
    url: string;
    token: string;
    expires_at: string | null;
  }>;
  profile_fields: Array<Record<string, unknown>>;
  contacts: Array<Record<string, unknown>>;
  identities: Array<Record<string, unknown>>;
  external_ids: Array<Record<string, unknown>>;
  utm_snapshots: Array<Record<string, unknown>>;
  custom_fields: Array<Record<string, unknown>>;
  consents: Array<Record<string, unknown>>;
  email_subscriptions: Array<Record<string, unknown>>;
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

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

const statusLabels: Record<ConversationStatus, string> = {
  open: "Открыт",
  needs_reply: "Ждет ответа",
  replied: "Отвечен",
  closed: "Закрыт",
};

const channelLabels: Record<string, string> = {
  telegram: "Telegram",
  vk: "VK",
  email: "Email",
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
  const [replyChannels, setReplyChannels] = useState<ReplyChannel[]>([]);
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
      setReplyChannels([]);
    }
  }, [loadDetail, selectedId]);

  useEffect(() => {
    if (!detail) {
      setReplyChannels([]);
      return;
    }
    const defaultChannels = detail.reply_channels
      .filter((option) => option.is_default)
      .map((option) => option.channel);
    setReplyChannels(
      defaultChannels.length > 0
        ? defaultChannels
        : detail.reply_channels.slice(0, 1).map((option) => option.channel)
    );
  }, [detail]);

  useEffect(() => {
    if (activeView === "database" && selectedLeadId) {
      void loadDatabaseLeadDetail(selectedLeadId);
    } else {
      setSelectedLeadDetail(null);
    }
  }, [activeView, loadDatabaseLeadDetail, selectedLeadId]);

  async function submitReply(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedId || !draft.trim() || replyChannels.length === 0) {
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
          body: JSON.stringify({ text: draft.trim(), channels: replyChannels }),
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

  function toggleReplyChannel(channel: ReplyChannel) {
    setReplyChannels((current) =>
      current.includes(channel)
        ? current.filter((selectedChannel) => selectedChannel !== channel)
        : [...current, channel]
    );
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
      const response = await fetch(
        `${API_BASE_URL}/api/inbox/database/leads/export.xlsx${suffix}`,
        { credentials: "include" }
      );
      if (!response.ok) {
        throw new Error(`Export failed: ${response.status}`);
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `funnelhub-leads-${new Date().toISOString().slice(0, 10)}.xlsx`;
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
                      <span>
                        {message.direction === "outbound" ? "Айсу" : "Клиент"} ·{" "}
                        {channelLabels[message.channel] ?? message.channel}
                      </span>
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
              {detail.reply_channels.length > 0 ? (
                <div className="reply-targets" role="group" aria-label="Куда отправить">
                  <span className="reply-targets-title">Куда отправить</span>
                  <div className="reply-target-list">
                    {detail.reply_channels.map((option) => (
                      <label className="reply-target" key={option.channel}>
                        <input
                          checked={replyChannels.includes(option.channel)}
                          onChange={() => toggleReplyChannel(option.channel)}
                          type="checkbox"
                        />
                        <span>
                          <strong>{option.label}</strong>
                          {option.detail ? <small>{option.detail}</small> : null}
                        </span>
                      </label>
                    ))}
                  </div>
                </div>
              ) : (
                <p className="reply-unavailable">Нет активного канала для ответа.</p>
              )}
              <textarea
                id="reply"
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                placeholder="Напишите личный ответ..."
                rows={3}
              />
              <button
                className="send-button"
                disabled={replyState === "loading" || replyChannels.length === 0}
                type="submit"
              >
                <Send aria-hidden="true" size={18} />
                <span>
                  {replyState === "loading"
                    ? "Отправка"
                    : replyChannels.length > 1
                      ? `Отправить: ${replyChannels.length}`
                      : "Отправить"}
                </span>
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
            <span>Выгрузить XLSX</span>
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
                      {leadMessengerLabels(lead).length > 0 ? (
                        leadMessengerLabels(lead).map((label) => <span key={label}>{label}</span>)
                      ) : (
                        <span>мессенджер нет</span>
                      )}
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
  const [copiedLink, setCopiedLink] = useState<string | null>(null);

  async function copyBotLink(url: string) {
    await navigator.clipboard.writeText(url);
    setCopiedLink(url);
  }

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

      <DetailSection count={detail.bot_links.length} defaultOpen title="Ссылки на ботов">
        {detail.bot_links.length === 0 ? (
          <p>Ссылки недоступны: проверьте настройки Telegram/VK ботов.</p>
        ) : null}
        <div className="bot-link-list">
          {detail.bot_links.map((link) => (
            <div className="bot-link-card" key={link.channel}>
              <div>
                <strong>{link.label}</strong>
                <span>{link.url}</span>
                {link.expires_at ? <small>Токен до {formatDetailValue(link.expires_at)}</small> : null}
              </div>
              <div className="bot-link-actions">
                <button
                  className="icon-button secondary"
                  onClick={() => void copyBotLink(link.url)}
                  title={`Скопировать ссылку ${link.label}`}
                  type="button"
                >
                  {copiedLink === link.url ? (
                    <Check aria-hidden="true" size={16} />
                  ) : (
                    <Copy aria-hidden="true" size={16} />
                  )}
                  <span className="sr-only">
                    {copiedLink === link.url ? "Скопировано" : `Скопировать ${link.label}`}
                  </span>
                </button>
                <a
                  className="icon-button secondary"
                  href={link.url}
                  rel="noreferrer"
                  target="_blank"
                  title={`Открыть ${link.label}`}
                >
                  <ExternalLink aria-hidden="true" size={16} />
                  <span className="sr-only">Открыть {link.label}</span>
                </a>
              </div>
            </div>
          ))}
        </div>
      </DetailSection>

      <DetailSection count={detail.profile_fields.length} defaultOpen title="Профиль GetCourse">
        <KeyValueRows items={detail.profile_fields} />
      </DetailSection>

      <DetailSection count={detail.contacts.length} defaultOpen title="Контакты">
        {detail.contacts.length === 0 ? <p>Контактов нет.</p> : null}
        {detail.contacts.map((contact, index) => (
          <KeyValueLine
            key={`${String(contact.type)}-${index}`}
            label={humanContactType(String(contact.type))}
            value={contact.value}
          />
        ))}
      </DetailSection>

      <DetailSection count={detail.identities.length} defaultOpen title="Мессенджеры">
        {detail.identities.length === 0 ? <p>Мессенджеры не привязаны.</p> : null}
        {detail.identities.map((identity, index) => (
          <KeyValueLine
            key={`${String(identity.channel)}-${index}`}
            label={channelLabels[String(identity.channel)] ?? String(identity.channel)}
            value={`${String(identity.username || identity.display_name || identity.external_user_id)} · ${
              identity.is_subscribed ? "активен" : "отписан"
            }`}
          />
        ))}
      </DetailSection>

      <DetailSection count={detail.external_ids.length} title="Внешние ID">
        {detail.external_ids.length === 0 ? <p>Внешних ID нет.</p> : null}
        {detail.external_ids.map((item, index) => (
          <KeyValueLine
            key={`${String(item.provider)}-${index}`}
            label={humanExternalProvider(String(item.provider))}
            value={item.external_id}
          />
        ))}
      </DetailSection>

      <DetailSection count={detail.utm_snapshots.length} defaultOpen title="Источник и UTM">
        {detail.utm_snapshots.length === 0 ? <p>UTM-данных нет.</p> : null}
        {detail.utm_snapshots.map((snapshot, index) => (
          <div className="nested-detail" key={`${String(snapshot.source_kind)}-${index}`}>
            <h4>{humanSourceKind(String(snapshot.source_kind))}</h4>
            <KeyValueRows
              items={[
                { label: "utm_source", value: snapshot.utm_source },
                { label: "utm_medium", value: snapshot.utm_medium },
                { label: "utm_campaign", value: snapshot.utm_campaign },
                { label: "utm_content", value: snapshot.utm_content },
                { label: "utm_term", value: snapshot.utm_term },
                { label: "utm_group", value: snapshot.utm_group },
              ].filter((item) => item.value !== null && item.value !== undefined)}
            />
          </div>
        ))}
      </DetailSection>

      <DetailSection count={detail.custom_fields.length} defaultOpen title="Дополнительные поля">
        {detail.custom_fields.length === 0 ? <p>Дополнительных полей нет.</p> : null}
        <div className="field-chip-list">
          {detail.custom_fields.map((field) => (
            <span className="field-chip" key={String(field.key)}>
              <strong>{String(field.label || field.key)}</strong>
              <span>{formatDetailValue(fieldValue(field))}</span>
            </span>
          ))}
        </div>
      </DetailSection>

      <DetailSection count={detail.consents.length} defaultOpen title="Согласия">
        {detail.consents.length === 0 ? <p>Согласий нет.</p> : null}
        {detail.consents.map((consent) => (
          <KeyValueLine
            key={String(consent.type)}
            label={humanConsentType(String(consent.type))}
            value={consent.is_granted ? "Да" : "Нет"}
          />
        ))}
      </DetailSection>

      <DetailSection count={detail.email_subscriptions.length} title="Рассылки">
        {detail.email_subscriptions.length === 0 ? <p>Подписок на рассылки нет.</p> : null}
        {detail.email_subscriptions.map((subscription, index) => (
          <KeyValueLine
            key={`${String(subscription.email)}-${index}`}
            label={String(subscription.email)}
            value={humanSubscriptionStatus(String(subscription.status))}
          />
        ))}
      </DetailSection>

      <DetailSection count={detail.funnel_states.length} title="Воронка">
        {detail.funnel_states.length === 0 ? <p>Нет активных состояний.</p> : null}
        <div className="funnel-state-list">
          {detail.funnel_states.map((state, index) => (
            <div className="funnel-state-card" key={`${String(state.funnel_key)}-${index}`}>
              <div>
                <strong>{humanFunnelKey(String(state.funnel_key))}</strong>
                <span>{humanFunnelStep(String(state.current_step_key || state.funnel_key))}</span>
              </div>
              <small>{humanFunnelStatus(String(state.status))}</small>
            </div>
          ))}
        </div>
      </DetailSection>

      <DetailSection count={detail.recent_messages.length} title="Последние сообщения">
        {detail.recent_messages.length === 0 ? <p>Сообщений нет.</p> : null}
        {detail.recent_messages.map((message) => (
          <KeyValueLine
            key={String(message.id)}
            label={`${channelLabels[String(message.channel)] ?? String(message.channel)} · ${String(
              humanMessageDirection(String(message.direction))
            )}`}
            value={message.body || "без текста"}
          />
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
  count,
  defaultOpen = false,
  title,
}: {
  children: ReactNode;
  count?: number;
  defaultOpen?: boolean;
  title: string;
}) {
  return (
    <details className="detail-section" open={defaultOpen}>
      <summary>
        <span>
          {title}
          {typeof count === "number" ? <small>{count}</small> : null}
        </span>
        <ChevronDown aria-hidden="true" size={16} />
      </summary>
      <div className="detail-section-body">{children}</div>
    </details>
  );
}

function KeyValueRows({ items }: { items: Array<Record<string, unknown>> }) {
  if (items.length === 0) {
    return <p>Данных нет.</p>;
  }
  return (
    <div className="key-value-list">
      {items.map((item, index) => (
        <KeyValueLine
          key={`${String(item.key || item.label)}-${index}`}
          label={String(item.label || item.key)}
          value={item.value}
        />
      ))}
    </div>
  );
}

function KeyValueLine({ label, value }: { label: string; value: unknown }) {
  return (
    <p className="key-value-line">
      <strong>{label}</strong>
      <span>{formatDetailValue(value)}</span>
    </p>
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

function leadMessengerLabels(lead: DatabaseLead) {
  return [
    lead.telegram ? "TG" : null,
    lead.vk ? "VK" : null,
  ].filter((label): label is string => label !== null);
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

function formatDetailValue(value: unknown) {
  if (value === null || value === undefined || value === "") {
    return "не указано";
  }
  if (typeof value === "boolean") {
    return value ? "Да" : "Нет";
  }
  if (typeof value === "string" && looksLikeDate(value)) {
    return new Intl.DateTimeFormat("ru-RU", {
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }).format(new Date(value));
  }
  if (typeof value === "object") {
    return JSON.stringify(value);
  }
  return String(value);
}

function fieldValue(field: Record<string, unknown>) {
  if (field.normalized_bool === true) {
    return "Да";
  }
  if (field.normalized_bool === false) {
    return "Нет";
  }
  return field.value;
}

function humanConsentType(value: string) {
  const labels: Record<string, string> = {
    personal_data: "Обработка персональных данных",
    privacy_policy: "Политика конфиденциальности",
    offer_agreement: "Договор оферты",
    email_marketing: "Email-рассылки",
    messenger_marketing: "Рассылки в мессенджерах",
  };
  return labels[value] ?? value;
}

function humanSourceKind(value: string) {
  const labels: Record<string, string> = {
    getcourse_system: "GetCourse system UTM",
    form: "Источник пользователя",
    import: "Импорт",
    manual: "Ручные данные",
  };
  return labels[value] ?? value;
}

function humanContactType(value: string) {
  const labels: Record<string, string> = {
    email: "Email",
    phone: "Телефон",
  };
  return labels[value] ?? value;
}

function humanExternalProvider(value: string) {
  const labels: Record<string, string> = {
    getcourse: "GetCourse ID",
    getcourse_vk_id: "VK-ID из GetCourse",
  };
  return labels[value] ?? value;
}

function humanSubscriptionStatus(value: string) {
  const labels: Record<string, string> = {
    subscribed: "Подписан",
    unsubscribed: "Отписан",
    bounced: "Недоставляется",
    complained: "Жалоба",
  };
  return labels[value] ?? value;
}

function humanFunnelKey(value: string) {
  const labels: Record<string, string> = {
    aisu_email_sequence: "Email-рассылка",
    aisu_consultation: "Бот-воронка",
  };
  return labels[value] ?? value;
}

function humanFunnelStatus(value: string) {
  const labels: Record<string, string> = {
    active: "Активна",
    completed: "Завершена",
    paused: "Пауза",
    failed: "Ошибка",
  };
  return labels[value] ?? value;
}

function humanFunnelStep(value: string) {
  const labels: Record<string, string> = {
    day_01_intro: "День 1: первое письмо",
    day_01_video_steps: "День 1: видео-шаги",
    day_01_meditation: "День 1: медитация",
    step_03_video: "Видео 3",
    welcome: "Приветствие",
    question_topic: "Вопрос о теме",
    question_experience: "Вопрос об опыте",
    first_video: "Первое видео",
  };
  if (labels[value]) {
    return labels[value];
  }

  const dayMatch = value.match(/^day_(\d{2})(?:_part_(\d+))?$/);
  if (dayMatch) {
    const day = Number(dayMatch[1]);
    return dayMatch[2] ? `День ${day}, часть ${dayMatch[2]}` : `День ${day}`;
  }
  return value;
}

function humanMessageDirection(value: string) {
  const labels: Record<string, string> = {
    inbound: "входящее",
    outbound: "исходящее",
  };
  return labels[value] ?? value;
}

function looksLikeDate(value: string) {
  return /^\d{4}-\d{2}-\d{2}/.test(value) && !Number.isNaN(new Date(value).getTime());
}

function formatError(caught: unknown) {
  if (caught instanceof Error) {
    return caught.message;
  }
  return "Не удалось выполнить действие.";
}
