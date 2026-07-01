import {
  Archive,
  CalendarClock,
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
  Save,
  Search,
  Send,
  Upload,
  UserRound,
  X,
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
type AppView = "inbox" | "database" | "broadcasts" | "autoposts" | "followups";

type Broadcast = {
  id: string;
  segment_query: string | null;
  channels: string[];
  status: string;
  total_leads: number;
  processed_leads: number;
  failed_leads: number;
  skipped_leads: number;
  created_at: string;
  updated_at: string;
};


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
type BroadcastList = {
  items: Broadcast[];
  total: number;
  limit: number;
  offset: number;
};

type Autopost = {
  id: string;
  title: string;
  body: string;
  channels: string[];
  status: string;
  source_type: string;
  source_url: string | null;
  scheduled_at: string;
  published_at: string | null;
  created_at: string;
  updated_at: string;
  has_image: boolean;
  image_file_name: string | null;
  publications: AutopostPublication[];
};

type AutopostPublication = {
  id: string;
  channel: string;
  status: string;
  external_post_id: string | null;
  external_post_url: string | null;
  attempted_at: string | null;
  published_at: string | null;
  error: string | null;
};

type AutopostList = {
  items: Autopost[];
  total: number;
  limit: number;
  offset: number;
};

type AutopostScheduleMode = "now" | "scheduled";

type FollowupPost = {
  id: string;
  title: string;
  body: string;
  channels: string[];
  status: string;
  source_type: string;
  source_autopost_id: string | null;
  scheduled_at: string;
  completed_at: string | null;
  total_deliveries: number;
  sent_deliveries: number;
  failed_deliveries: number;
  skipped_deliveries: number;
  created_at: string;
  updated_at: string;
  deliveries: FollowupDelivery[];
};

type FollowupDelivery = {
  id: string;
  lead_id: string;
  lead_name: string | null;
  channel: string;
  status: string;
  external_message_id: string | null;
  attempted_at: string | null;
  sent_at: string | null;
  error: string | null;
};

type FollowupPostList = {
  items: FollowupPost[];
  total: number;
  limit: number;
  offset: number;
};

type FollowupRecipientPreview = {
  total: number;
  by_channel: Record<string, number>;
};

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

type ImportPreview = {
  headers: string[];
  rows: string[][];
  suggested_mapping: Record<string, string>;
};

type ImportBatchSummary = {
  id: string;
  file_name: string;
  file_format: string;
  status: string;
  total_rows: number;
  processed_rows: number;
  failed_rows: number;
  created_at: string;
};

type ImportBatchDetail = {
  batch: ImportBatchSummary;
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

const publicAutopostChannelLabels: Record<string, string> = {
  telegram: "Telegram",
  vk: "VK группа",
};

const autopostStatusLabels: Record<string, string> = {
  queued: "В очереди",
  scheduled: "Запланирован",
  publishing: "Публикуется",
  published: "Опубликован",
  failed: "Ошибка",
  partial_failed: "Частично",
  cancelled: "Отменен",
  pending: "Ожидает",
  sending: "Отправляется",
  completed: "Завершен",
  sent: "Отправлено",
  skipped_unsubscribed: "Пропущен",
};

const sourceTypeLabels: Record<string, string> = {
  manual: "Ручной",
  youtube: "YouTube",
  telegram: "Telegram",
  vk: "VK",
  other: "Другое",
};

const publicAutopostSourceTypes = ["manual", "telegram", "vk", "other"];

const filters: Array<{ value: ConversationStatus | "all"; label: string }> = [
  { value: "all", label: "Все" },
  { value: "needs_reply", label: "Ждут" },
  { value: "open", label: "Открытые" },
  { value: "replied", label: "Отвеченные" },
  { value: "closed", label: "Закрытые" },
];

export function App() {
  const [authState, setAuthState] = useState<AuthState>("checking");
  const [adminName, setAdminName] = useState<string | null>(null);
  const [activeView, setActiveView] = useState<AppView>("inbox");
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ConversationDetail | null>(null);
  const [filter, setFilter] = useState<ConversationStatus | "all">("all");
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

  const [importFile, setImportFile] = useState<File | null>(null);
  const [showImportHistory, setShowImportHistory] = useState(false);

  function openImportModal(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (file) {
      setImportFile(file);
    }
  }

  async function saveLeadVkId(leadId: string, vkId: string) {
    setError(null);
    const response = await fetch(`${API_BASE_URL}/api/inbox/database/leads/${leadId}/vk-id`, {
      method: "PUT",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ vk_id: vkId }),
    });
    if (!response.ok) {
      const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
      throw new Error(payload?.detail || `VK-ID save failed: ${response.status}`);
    }
    const payload = (await response.json()) as DatabaseLeadDetail;
    setSelectedLeadDetail(payload);
    await loadDatabaseLeads();
  }

  async function deleteDatabaseLead(leadId: string) {
    setError(null);
    try {
      const response = await fetch(`${API_BASE_URL}/api/inbox/database/leads/${leadId}`, {
        method: "DELETE",
        credentials: "include",
      });
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(payload?.detail || `Ошибка удаления: ${response.status}`);
      }
      setSelectedLeadId(null);
      setSelectedLeadDetail(null);
      await loadDatabaseLeads();
    } catch (caught) {
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
          onImport={openImportModal}
          onOpenHistory={() => setShowImportHistory(true)}
          onLogout={() => void logout()}
          onQueryChange={setDatabaseQuery}
          onRefresh={loadDatabaseLeads}
          onSaveLeadVkId={(leadId, vkId) => saveLeadVkId(leadId, vkId)}
          onDeleteLead={deleteDatabaseLead}
          onSearch={(event) => void submitDatabaseSearch(event)}
          onSelectLead={setSelectedLeadId}
          onSwitchView={switchView}
          selectedLeadDetail={selectedLeadDetail}
          selectedLeadId={selectedLeadId}
        />
        {importFile ? (
          <ImportManagerModal
            file={importFile}
            onClose={() => setImportFile(null)}
            onSuccess={(summary) => {
              setDatabaseImportSummary(summary);
              setImportFile(null);
              void loadDatabaseLeads();
            }}
          />
        ) : null}
        {showImportHistory ? (
          <ImportHistoryModal onClose={() => setShowImportHistory(false)} />
        ) : null}
        {error ? (
          <div className="toast" role="status">
            {error}
          </div>
        ) : null}
      </main>
    );
  }


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

  if (activeView === "autoposts") {
    return (
      <main className="database-shell">
        <AutopostsWorkspace
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

  if (activeView === "followups") {
    return (
      <main className="database-shell">
        <FollowupPostsWorkspace
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
      <button
        className={activeView === "broadcasts" ? "view-tab is-active" : "view-tab"}
        onClick={() => onSwitchView("broadcasts")}
        type="button"
      >
        <Send aria-hidden="true" size={16} />
        <span>Рассылки</span>
      </button>
      <button
        className={activeView === "autoposts" ? "view-tab is-active" : "view-tab"}
        onClick={() => onSwitchView("autoposts")}
        type="button"
      >
        <CalendarClock aria-hidden="true" size={16} />
        <span>Автопостинг</span>
      </button>
      <button
        className={activeView === "followups" ? "view-tab is-active" : "view-tab"}
        onClick={() => onSwitchView("followups")}
        type="button"
      >
        <Send aria-hidden="true" size={16} />
        <span>Фоллоу-ап</span>
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
  onOpenHistory,
  onLogout,
  onQueryChange,
  onRefresh,
  onSaveLeadVkId,
  onSearch,
  onSelectLead,
  onSwitchView,
  selectedLeadDetail,
  selectedLeadId,
  onDeleteLead,
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
  onOpenHistory: () => void;
  onLogout: () => void;
  onQueryChange: (query: string) => void;
  onRefresh: () => void;
  onSaveLeadVkId: (leadId: string, vkId: string) => Promise<void>;
  onSearch: (event: FormEvent<HTMLFormElement>) => void;
  onSelectLead: (leadId: string) => void;
  onSwitchView: (view: AppView) => void;
  selectedLeadDetail: DatabaseLeadDetail | null;
  selectedLeadId: string | null;
  onDeleteLead: (leadId: string) => Promise<void>;
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
          <button className="soft-button" onClick={onOpenHistory} type="button">
            <Clock aria-hidden="true" size={17} />
            <span>История импортов</span>
          </button>
          <label className="soft-button file-button">
            <Upload aria-hidden="true" size={17} />
            <span>Импорт CSV/XLSX</span>
            <input accept=".csv,text/csv,.xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" onChange={onImport} type="file" />
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
            <LeadDatabaseDetail detail={selectedLeadDetail} onSaveVkId={onSaveLeadVkId} onDeleteLead={onDeleteLead} />
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

function LeadDatabaseDetail({
  detail,
  onSaveVkId,
  onDeleteLead,
}: {
  detail: DatabaseLeadDetail;
  onSaveVkId: (leadId: string, vkId: string) => Promise<void>;
  onDeleteLead: (leadId: string) => Promise<void>;
}) {
  const [copiedLink, setCopiedLink] = useState<string | null>(null);
  const [vkIdDraft, setVkIdDraft] = useState(existingVkId(detail));
  const [vkIdState, setVkIdState] = useState<LoadState>("idle");
  const [vkIdMessage, setVkIdMessage] = useState<string | null>(null);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);

  useEffect(() => {
    setVkIdDraft(existingVkId(detail));
    setVkIdState("idle");
    setVkIdMessage(null);
    setShowDeleteConfirm(false);
    setIsDeleting(false);
  }, [detail.lead.id, detail.external_ids]);

  async function copyBotLink(url: string) {
    await navigator.clipboard.writeText(url);
    setCopiedLink(url);
  }

  async function submitVkId(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const cleanVkId = vkIdDraft.trim();
    if (!cleanVkId) {
      setVkIdState("error");
      setVkIdMessage("Введите VK-ID");
      return;
    }
    setVkIdState("loading");
    setVkIdMessage(null);
    try {
      await onSaveVkId(detail.lead.id, cleanVkId);
      setVkIdState("idle");
      setVkIdMessage("VK-ID сохранен");
    } catch (caught) {
      setVkIdState("error");
      setVkIdMessage(formatError(caught));
    }
  }

  return (
    <div className="lead-detail">
      <div className="lead-detail-head" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div style={{ display: "flex", gap: "1rem" }}>
          <div className="avatar" aria-hidden="true">
            <UserRound size={22} />
          </div>
          <div>
            <h2>{detail.lead.name ?? "Без имени"}</h2>
            <p>{detail.lead.source ?? "источник не указан"}</p>
          </div>
        </div>
        <button 
          type="button" 
          className="soft-button" 
          style={{ color: "#d94242", boxShadow: "inset 0 0 0 1px #d94242" }}
          onClick={() => setShowDeleteConfirm(true)}
        >
          Удалить лида
        </button>
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
        <form className="vk-id-form" onSubmit={(event) => void submitVkId(event)}>
          <label htmlFor={`vk-id-${detail.lead.id}`}>VK-ID</label>
          <div>
            <input
              id={`vk-id-${detail.lead.id}`}
              inputMode="numeric"
              onChange={(event) => setVkIdDraft(event.target.value)}
              placeholder="Например 123456789"
              value={vkIdDraft}
            />
            <button className="soft-button" disabled={vkIdState === "loading"} type="submit">
              <Save aria-hidden="true" size={16} />
              <span>{vkIdState === "loading" ? "Сохраняем" : "Сохранить"}</span>
            </button>
          </div>
          {vkIdMessage ? (
            <small className={vkIdState === "error" ? "form-message is-error" : "form-message"}>
              {vkIdMessage}
            </small>
          ) : null}
        </form>
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
            <div className="funnel-state-card" key={`${String(state.funnel_key)}-${String(state.channel)}-${index}`}>
              <div>
                <strong>
                  {String(state.channel) !== "unknown" ? `${channelLabels[String(state.channel)] ?? String(state.channel)}: ` : ""}
                  {humanFunnelKey(String(state.funnel_key))}
                </strong>
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

      {showDeleteConfirm && (
        <div className="modal-overlay">
          <div className="modal-content">
            <h3>Удалить лида?</h3>
            <p>Вы уверены? Это действие необратимо и удалит все диалоги и историю воронки для этого лида.</p>
            <div className="modal-actions">
              <button className="soft-button" onClick={() => setShowDeleteConfirm(false)} disabled={isDeleting}>Отмена</button>
              <button 
                className="soft-button" 
                style={{ backgroundColor: "#d94242", color: "white", border: "none" }} 
                onClick={async () => {
                  setIsDeleting(true);
                  try {
                    await onDeleteLead(detail.lead.id);
                  } finally {
                    setIsDeleting(false);
                    setShowDeleteConfirm(false);
                  }
                }}
                disabled={isDeleting}
              >
                {isDeleting ? "Удаление..." : "Удалить безвозвратно"}
              </button>
            </div>
          </div>
        </div>
      )}
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

function existingVkId(detail: DatabaseLeadDetail) {
  const externalId = detail.external_ids.find(
    (item) => item.provider === "getcourse_vk_id" && typeof item.external_id === "string"
  );
  return typeof externalId?.external_id === "string" ? externalId.external_id : "";
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

function ImportManagerModal({
  file,
  onClose,
  onSuccess,
}: {
  file: File;
  onClose: () => void;
  onSuccess: (summary: DatabaseImportSummary) => void;
}) {
  const [step, setStep] = useState<"preview" | "mapping" | "importing">("preview");
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);

  const TARGET_FIELDS = [
    { value: "", label: "-- Пропустить --" },
    { value: "gc_user_id", label: "GetCourse ID" },
    { value: "name", label: "ФИО" },
    { value: "first_name", label: "Имя" },
    { value: "last_name", label: "Фамилия" },
    { value: "email", label: "Email" },
    { value: "phone", label: "Телефон" },
    { value: "city", label: "Город" },
    { value: "country", label: "Страна" },
    { value: "source", label: "Источник" },
    { value: "registration_type", label: "Тип регистрации" },
    { value: "created", label: "Создан в GC" },
    { value: "last_activity", label: "Последняя активность в GC" },
    { value: "utm_source", label: "UTM Source" },
    { value: "utm_medium", label: "UTM Medium" },
    { value: "utm_campaign", label: "UTM Campaign" },
    { value: "utm_term", label: "UTM Term" },
    { value: "utm_content", label: "UTM Content" },
    { value: "utm_group", label: "UTM Group" },
    { value: "vk_id", label: "VK-ID" },
    { value: "getcourse_groups", label: "Группы GetCourse" },
  ];

  useEffect(() => {
    async function loadPreview() {
      try {
        const formData = new FormData();
        formData.append("file", file);
        const response = await fetch(`${API_BASE_URL}/api/inbox/database/leads/import/preview`, {
          method: "POST",
          credentials: "include",
          body: formData,
        });
        if (!response.ok) {
          const text = await response.text();
          throw new Error(text || "Ошибка предпросмотра");
        }
        const data = (await response.json()) as ImportPreview;
        setPreview(data);
        
        // Initialize mapping
        const initMap: Record<string, string> = {};
        for (const header of data.headers) {
            initMap[header] = data.suggested_mapping[header] || `custom_${header}`;
        }
        setMapping(initMap);
        setStep("mapping");
      } catch (err) {
        setError(formatError(err));
      }
    }
    void loadPreview();
  }, [file]);

  async function handleImport() {
    setStep("importing");
    setError(null);
    try {
      const formData = new FormData();
      formData.append("file", file);
      // Only include fields that are actually mapped to something
      const cleanMapping = Object.fromEntries(
          Object.entries(mapping).filter(([_, v]) => v !== "")
      );
      formData.append("mapping", JSON.stringify(cleanMapping));

      const response = await fetch(`${API_BASE_URL}/api/inbox/database/leads/import`, {
        method: "POST",
        credentials: "include",
        body: formData,
      });
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(payload?.detail || `Ошибка импорта: ${response.status}`);
      }
      const summary = (await response.json()) as DatabaseImportSummary;
      onSuccess(summary);
    } catch (err) {
      setError(formatError(err));
      setStep("mapping"); // back to mapping to allow retry
    }
  }

  return (
    <div className="modal-overlay">
      <div className="modal-content" style={{ maxWidth: "800px", width: "90%" }}>
        <h3>Импорт файла: {file.name}</h3>
        
        {step === "preview" ? (
          <p>Загрузка предпросмотра...</p>
        ) : null}

        {step === "mapping" && preview ? (
          <div className="import-mapping">
            <p>Настройте соответствие колонок из файла к полям базы.</p>
            <div className="table-responsive" style={{ maxHeight: "50vh", overflowY: "auto" }}>
                <table className="lead-table">
                <thead>
                    <tr>
                    <th>Колонка в файле</th>
                    <th>Поле в базе</th>
                    <th>Пример данных (первая строка)</th>
                    </tr>
                </thead>
                <tbody>
                    {preview.headers.map((header, idx) => (
                    <tr key={`${header}-${idx}`}>
                        <td><strong>{header}</strong></td>
                        <td>
                        <select 
                            value={mapping[header] || ""} 
                            onChange={(e) => {
                                const val = e.target.value;
                                setMapping(m => ({ ...m, [header]: val }));
                            }}
                        >
                            {TARGET_FIELDS.map(f => (
                                <option key={f.value} value={f.value}>{f.label}</option>
                            ))}
                            <option value={`custom_${header}`}>Новое доп. поле (custom_{header})</option>
                        </select>
                        </td>
                        <td>{preview.rows[0]?.[idx] || ""}</td>
                    </tr>
                    ))}
                </tbody>
                </table>
            </div>
          </div>
        ) : null}

        {step === "importing" ? (
            <p>Выполняется импорт... Пожалуйста, подождите.</p>
        ) : null}

        {error ? <p className="form-message is-error">{error}</p> : null}

        <div className="modal-actions" style={{ marginTop: "20px" }}>
          <button className="soft-button" onClick={onClose} disabled={step === "importing"}>Отмена</button>
          {step === "mapping" ? (
              <button className="soft-button" onClick={() => void handleImport()} style={{ backgroundColor: "#24483C", color: "white" }}>
                Запустить импорт
              </button>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function ImportHistoryModal({ onClose }: { onClose: () => void }) {
  const [batches, setBatches] = useState<ImportBatchSummary[]>([]);
  const [selectedBatch, setSelectedBatch] = useState<ImportBatchDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadBatches() {
      try {
        const response = await fetch(`${API_BASE_URL}/api/inbox/database/leads/import/batches`, {
          credentials: "include",
        });
        if (!response.ok) throw new Error("Не удалось загрузить историю");
        const data = await response.json();
        setBatches(data);
      } catch (err) {
        setError(formatError(err));
      } finally {
        setLoading(false);
      }
    }
    void loadBatches();
  }, []);

  async function loadDetail(batchId: string) {
    try {
      const response = await fetch(`${API_BASE_URL}/api/inbox/database/leads/import/batches/${batchId}`, {
        credentials: "include",
      });
      if (!response.ok) throw new Error("Не удалось загрузить детали");
      const data = await response.json();
      setSelectedBatch(data);
    } catch (err) {
      setError(formatError(err));
    }
  }

  return (
    <div className="modal-overlay">
      <div className="modal-content" style={{ maxWidth: "800px", width: "90%" }}>
        <h3>История импортов</h3>

        {error ? <p className="form-message is-error">{error}</p> : null}

        {!selectedBatch ? (
          <>
            {loading ? <p>Загрузка...</p> : (
              <div className="table-responsive" style={{ maxHeight: "50vh", overflowY: "auto" }}>
                  <table className="lead-table">
                  <thead>
                      <tr>
                      <th>Дата</th>
                      <th>Файл</th>
                      <th>Статус</th>
                      <th>Строк</th>
                      <th>Ошибок</th>
                      </tr>
                  </thead>
                  <tbody>
                      {batches.length === 0 ? <tr><td colSpan={5}>Нет истории импортов</td></tr> : null}
                      {batches.map(b => (
                          <tr key={b.id} onClick={() => void loadDetail(b.id)} style={{ cursor: "pointer" }}>
                              <td>{formatRelativeDate(b.created_at)}</td>
                              <td>{b.file_name}</td>
                              <td>{humanFunnelStatus(b.status)}</td>
                              <td>{b.processed_rows} / {b.total_rows}</td>
                              <td style={{ color: b.failed_rows > 0 ? "#d94242" : "inherit" }}>{b.failed_rows}</td>
                          </tr>
                      ))}
                  </tbody>
                  </table>
              </div>
            )}
            <div className="modal-actions" style={{ marginTop: "20px" }}>
                <button className="soft-button" onClick={onClose}>Закрыть</button>
            </div>
          </>
        ) : (
          <>
            <div style={{ marginBottom: "20px" }}>
              <button className="soft-button" onClick={() => setSelectedBatch(null)}>&larr; Назад к списку</button>
            </div>
            
            <p><strong>Файл:</strong> {selectedBatch.batch.file_name}</p>
            <p><strong>Статус:</strong> {humanFunnelStatus(selectedBatch.batch.status)} ({selectedBatch.batch.processed_rows} обработано, {selectedBatch.batch.failed_rows} ошибок)</p>
            
            {selectedBatch.errors && selectedBatch.errors.length > 0 ? (
                <div style={{ marginTop: "20px" }}>
                    <h4>Список ошибок</h4>
                    <div className="table-responsive" style={{ maxHeight: "35vh", overflowY: "auto" }}>
                        <table className="lead-table">
                        <thead>
                            <tr>
                            <th>Строка</th>
                            <th>Ошибка</th>
                            </tr>
                        </thead>
                        <tbody>
                            {selectedBatch.errors.map((e, idx) => (
                                <tr key={idx}>
                                    <td>{e.row_number as number}</td>
                                    <td style={{ color: "#d94242" }}>{e.message as string}</td>
                                </tr>
                            ))}
                        </tbody>
                        </table>
                    </div>
                </div>
            ) : (
                <p style={{ marginTop: "20px" }}>Ошибок нет.</p>
            )}

            <div className="modal-actions" style={{ marginTop: "20px" }}>
                <button className="soft-button" onClick={onClose}>Закрыть</button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}


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
  const [selectedBroadcastId, setSelectedBroadcastId] = useState<string | null>(null);

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
          <button className="send-button" onClick={() => setShowCreate(true)} type="button">
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
        <div className="lead-table-wrap">
          <table className="lead-table">
            <thead>
              <tr>
                <th>Дата</th>
                <th>Каналы</th>
                <th>Сегмент</th>
                <th>Статус</th>
                <th>Пропущено</th>
                <th>Прогресс</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={6} style={{ textAlign: "center", padding: "2rem" }}>Загрузка...</td>
                </tr>
              ) : broadcasts.length === 0 ? (
                <tr>
                  <td colSpan={6} style={{ textAlign: "center", padding: "2rem" }}>Нет рассылок</td>
                </tr>
              ) : (
                broadcasts.map((b) => (
                  <tr key={b.id} onClick={() => setSelectedBroadcastId(b.id)} style={{ cursor: "pointer" }}>
                    <td>{new Date(b.created_at).toLocaleString("ru-RU")}</td>
                    <td>{b.channels.map(c => channelLabels[c] || c).join(", ")}</td>
                    <td><code className="mono-badge">{b.segment_query || "Все"}</code></td>
                    <td><StatusPill status={b.status as ConversationStatus} /></td>
                    <td>{b.skipped_leads}</td>
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

      
      {selectedBroadcastId ? (
        <BroadcastDetailModal
          broadcastId={selectedBroadcastId}
          onClose={() => setSelectedBroadcastId(null)}
        />
      ) : null}

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

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
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
            <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", marginTop: "4px" }}>
              {["telegram", "vk", "email"].map((ch) => (
                <button
                  key={ch}
                  type="button"
                  className={channels.includes(ch) ? "filter-chip is-active" : "filter-chip"}
                  onClick={() => toggleChannel(ch)}
                  style={{ display: "flex", alignItems: "center", gap: "6px" }}
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
            <button className="soft-button" type="button" onClick={onClose} disabled={loading}>Отмена</button>
            <button className="send-button" type="submit" disabled={loading}>
              <Send size={16} />
              {loading ? "Запуск..." : "Запустить рассылку"}
            </button>
          </footer>
        </form>
      </div>
    </div>
  );
}

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
            <table className="lead-table">
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


// --- Autoposting Components ---

function AutopostsWorkspace({
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
  const [autoposts, setAutoposts] = useState<Autopost[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [selectedAutopostId, setSelectedAutopostId] = useState<string | null>(null);

  const loadAutoposts = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE_URL}/api/inbox/autoposts`, {
        credentials: "include",
      });
      if (!response.ok) {
        throw new Error(`Load failed: ${response.status}`);
      }
      const data = (await response.json()) as AutopostList;
      setAutoposts(data.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadAutoposts();
  }, [loadAutoposts]);

  return (
    <>
      <header className="panel-header">
        <div>
          <p className="eyebrow">FunnelHub</p>
          <h1>Автопостинг</h1>
          <ViewSwitch activeView={activeView} onSwitchView={onSwitchView} />
        </div>
        <div className="panel-actions">
          <button className="send-button" onClick={() => setShowCreate(true)} type="button">
            <CalendarClock aria-hidden="true" size={16} />
            Создать
          </button>
          <button className="icon-button" onClick={loadAutoposts} type="button">
            <RefreshCw aria-hidden="true" size={18} />
          </button>
          <button className="icon-button secondary" onClick={onLogout} type="button">
            <LogOut aria-hidden="true" size={18} />
            <span className="sr-only">Выйти{adminName ? `, ${adminName}` : ""}</span>
          </button>
        </div>
      </header>

      <div className="workspace is-list-only">
        {error ? <div className="toast" role="status">{error}</div> : null}
        <div className="lead-table-wrap">
          <table className="lead-table">
            <thead>
              <tr>
                <th>Публикация</th>
                <th>Расписание</th>
                <th>Каналы</th>
                <th>Источник</th>
                <th>Статус</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={5} style={{ textAlign: "center", padding: "2rem" }}>Загрузка...</td>
                </tr>
              ) : autoposts.length === 0 ? (
                <tr>
                  <td colSpan={5} style={{ textAlign: "center", padding: "2rem" }}>
                    Нет запланированных публикаций
                  </td>
                </tr>
              ) : (
                autoposts.map((post) => (
                  <tr
                    key={post.id}
                    onClick={() => setSelectedAutopostId(post.id)}
                    style={{ cursor: "pointer" }}
                  >
                    <td>
                      <strong>{post.title}</strong>
                      <p className="field-hint" style={{ margin: "4px 0 0" }}>
                        {trimPreview(post.body, 96)}
                      </p>
                      {post.has_image ? (
                        <span className="attachment-pill">
                          <Upload aria-hidden="true" size={13} />
                          VK изображение
                        </span>
                      ) : null}
                    </td>
                    <td>{formatDetailValue(post.scheduled_at)}</td>
                    <td>{post.channels.map((c) => publicAutopostChannelLabels[c] || c).join(", ")}</td>
                    <td>{sourceTypeLabels[post.source_type] || post.source_type}</td>
                    <td><GenericStatusPill status={post.status} /></td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {selectedAutopostId ? (
        <AutopostDetailModal
          autopostId={selectedAutopostId}
          onClose={() => setSelectedAutopostId(null)}
          onChanged={() => void loadAutoposts()}
        />
      ) : null}

      {showCreate ? (
        <AutopostCreateModal
          onClose={() => setShowCreate(false)}
          onSuccess={() => {
            setShowCreate(false);
            void loadAutoposts();
          }}
        />
      ) : null}
    </>
  );
}

function AutopostCreateModal({
  onClose,
  onSuccess,
}: {
  onClose: () => void;
  onSuccess: () => void;
}) {
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [channels, setChannels] = useState<string[]>(["telegram"]);
  const [scheduleMode, setScheduleMode] = useState<AutopostScheduleMode>("now");
  const [scheduledAt, setScheduledAt] = useState("");
  const [sourceType, setSourceType] = useState("manual");
  const [sourceUrl, setSourceUrl] = useState("");
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const toggleChannel = (ch: string) => {
    setChannels((prev) => prev.includes(ch) ? prev.filter((c) => c !== ch) : [...prev, ch]);
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!title.trim()) {
      setError("Введите название публикации");
      return;
    }
    if (!body.trim()) {
      setError("Введите текст публикации");
      return;
    }
    if (channels.length === 0) {
      setError("Выберите хотя бы один канал");
      return;
    }
    if (scheduleMode === "scheduled" && !scheduledAt) {
      setError("Выберите дату и время публикации");
      return;
    }

    setLoading(true);
    setError(null);
    try {
      let res: Response;
      if (imageFile) {
        const formData = new FormData();
        formData.append("title", title.trim());
        formData.append("body", body.trim());
        channels.forEach((channel) => formData.append("channels", channel));
        if (scheduleMode === "scheduled" && scheduledAt) {
          formData.append("scheduled_at", new Date(scheduledAt).toISOString());
        }
        formData.append("source_type", sourceType);
        if (sourceUrl.trim()) {
          formData.append("source_url", sourceUrl.trim());
        }
        formData.append("image", imageFile);
        res = await fetch(`${API_BASE_URL}/api/inbox/autoposts/with-media`, {
          method: "POST",
          credentials: "include",
          body: formData,
        });
      } else {
        res = await fetch(`${API_BASE_URL}/api/inbox/autoposts`, {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            title: title.trim(),
            body: body.trim(),
            channels,
            scheduled_at:
              scheduleMode === "scheduled" && scheduledAt
                ? new Date(scheduledAt).toISOString()
                : null,
            source_type: sourceType,
            source_url: sourceUrl.trim() || null,
          }),
        });
      }

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
          <h2>Новая публикация</h2>
          <button className="icon-button soft-button" onClick={onClose} type="button">
            <LogOut aria-hidden="true" size={18} />
          </button>
        </header>
        <form className="modal-body" onSubmit={handleSubmit}>
          {error ? <div className="form-error">{error}</div> : null}

          <div className="form-group">
            <label>Название</label>
            <input
              type="text"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="Название для истории"
              required
            />
          </div>

          <div className="form-group">
            <label>Текст поста</label>
            <textarea
              value={body}
              onChange={(event) => setBody(event.target.value)}
              placeholder="Текст публикации..."
              rows={7}
              required
            />
          </div>

          <div className="form-group">
            <label>Каналы публикации</label>
            <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", marginTop: "4px" }}>
              {["telegram", "vk"].map((ch) => (
                <button
                  key={ch}
                  type="button"
                  className={channels.includes(ch) ? "filter-chip is-active" : "filter-chip"}
                  onClick={() => toggleChannel(ch)}
                  style={{ display: "flex", alignItems: "center", gap: "6px" }}
                >
                  <span className={`channel-dot channel-${ch}`} />
                  {publicAutopostChannelLabels[ch] || ch}
                </button>
              ))}
            </div>
          </div>

          <div className="form-group">
            <label>Время публикации</label>
            <div className="segmented-control" role="group" aria-label="Время публикации">
              <button
                className={scheduleMode === "now" ? "filter-chip is-active" : "filter-chip"}
                onClick={() => setScheduleMode("now")}
                type="button"
              >
                Сразу
              </button>
              <button
                className={scheduleMode === "scheduled" ? "filter-chip is-active" : "filter-chip"}
                onClick={() => setScheduleMode("scheduled")}
                type="button"
              >
                По времени
              </button>
            </div>
            {scheduleMode === "scheduled" ? (
              <input
                type="datetime-local"
                value={scheduledAt}
                onChange={(event) => setScheduledAt(event.target.value)}
                required
              />
            ) : (
              <p className="field-hint">Пост уйдет в ближайший проход worker, обычно в течение минуты.</p>
            )}
          </div>

          <div className="form-group">
            <label>Изображение для VK</label>
            <label className="file-drop">
              <Upload aria-hidden="true" size={18} />
              <span>{imageFile ? imageFile.name : "Выбрать JPEG, PNG или WebP"}</span>
              <input
                accept="image/jpeg,image/png,image/webp"
                type="file"
                onChange={(event) => setImageFile(event.target.files?.[0] || null)}
              />
            </label>
            {imageFile ? (
              <div className="attachment-preview">
                <span>
                  <strong>Прикреплено:</strong> {imageFile.name}
                </span>
                <button
                  aria-label="Убрать изображение"
                  className="icon-button soft-button compact"
                  onClick={() => setImageFile(null)}
                  type="button"
                >
                  <X aria-hidden="true" size={15} />
                </button>
              </div>
            ) : null}
            <p className="field-hint">
              Картинка прикрепится только к VK-публикациям. Telegram отправит текст без изображения.
            </p>
          </div>

          <div className="form-group">
            <label>Источник</label>
            <select value={sourceType} onChange={(event) => setSourceType(event.target.value)}>
              {publicAutopostSourceTypes.map((value) => (
                <option key={value} value={value}>{sourceTypeLabels[value] || value}</option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label>Ссылка на источник</label>
            <input
              type="text"
              value={sourceUrl}
              onChange={(event) => setSourceUrl(event.target.value)}
              placeholder="Telegram, VK или другая ссылка"
            />
          </div>

          <footer className="modal-footer">
            <button className="soft-button" type="button" onClick={onClose} disabled={loading}>Отмена</button>
            <button className="send-button" type="submit" disabled={loading}>
              <CalendarClock size={16} />
              {loading
                ? "Сохраняем..."
                : scheduleMode === "now"
                  ? "Отправить сразу"
                  : "Поставить в очередь"}
            </button>
          </footer>
        </form>
      </div>
    </div>
  );
}

function AutopostDetailModal({
  autopostId,
  onClose,
  onChanged,
}: {
  autopostId: string;
  onClose: () => void;
  onChanged: () => void;
}) {
  const [post, setPost] = useState<Autopost | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadPost = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE_URL}/api/inbox/autoposts/${autopostId}`, {
        credentials: "include",
      });
      if (!res.ok) {
        throw new Error(`Load failed: ${res.status}`);
      }
      setPost((await res.json()) as Autopost);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [autopostId]);

  useEffect(() => {
    void loadPost();
  }, [loadPost]);

  const cancelPost = async () => {
    setActionLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE_URL}/api/inbox/autoposts/${autopostId}/cancel`, {
        method: "PATCH",
        credentials: "include",
      });
      if (!res.ok) {
        const payload = await res.json().catch(() => null);
        throw new Error(payload?.detail || `Ошибка ${res.status}`);
      }
      setPost((await res.json()) as Autopost);
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setActionLoading(false);
    }
  };

  const canCancel = post && ["queued", "scheduled", "failed", "partial_failed"].includes(post.status);

  return (
    <div className="modal-overlay">
      <div className="modal-dialog" style={{ maxWidth: 900 }}>
        <header className="modal-header">
          <h2>{post?.title || "Публикация"}</h2>
          <button className="icon-button soft-button" onClick={onClose} type="button">
            <LogOut aria-hidden="true" size={18} />
          </button>
        </header>
        <div className="modal-body" style={{ overflowY: "auto", maxHeight: "70vh" }}>
          {error ? <div className="toast" role="status">{error}</div> : null}
          {loading ? (
            <div style={{ textAlign: "center", padding: "2rem" }}>Загрузка...</div>
          ) : post ? (
            <>
              <div className="key-value-list">
                <KeyValueLine label="Статус" value={autopostStatusLabels[post.status] || post.status} />
                <KeyValueLine label="Расписание" value={post.scheduled_at} />
                <KeyValueLine label="Каналы" value={post.channels.map((c) => publicAutopostChannelLabels[c] || c).join(", ")} />
                <KeyValueLine label="Источник" value={sourceTypeLabels[post.source_type] || post.source_type} />
                <KeyValueLine label="Ссылка" value={post.source_url || "не указано"} />
                <KeyValueLine label="Изображение" value={post.has_image ? post.image_file_name || "прикреплено" : "нет"} />
              </div>

              <div className="form-group">
                <label>Текст поста</label>
                <div className="message-bubble outbound" style={{ width: "100%", maxWidth: "100%" }}>
                  {post.body}
                </div>
              </div>

              <table className="lead-table">
                <thead>
                  <tr>
                    <th>Канал</th>
                    <th>Статус</th>
                    <th>Внешний ID</th>
                    <th>Попытка</th>
                    <th>Ошибка</th>
                  </tr>
                </thead>
                <tbody>
                  {post.publications.map((publication) => (
                    <tr key={publication.id}>
                      <td>{channelLabels[publication.channel] || publication.channel}</td>
                      <td><GenericStatusPill status={publication.status} /></td>
                      <td>
                        {publication.external_post_url ? (
                          <a
                            className="mono-badge"
                            href={publication.external_post_url}
                            rel="noreferrer"
                            target="_blank"
                          >
                            {publication.external_post_id}
                          </a>
                        ) : (
                          <code className="mono-badge">{publication.external_post_id || "—"}</code>
                        )}
                      </td>
                      <td>{publication.attempted_at ? formatDetailValue(publication.attempted_at) : "—"}</td>
                      <td style={{ color: "var(--danger)" }}>{publication.error || ""}</td>
                    </tr>
                  ))}
                  {post.publications.length === 0 ? (
                    <tr>
                      <td colSpan={5} style={{ textAlign: "center" }}>История пуста</td>
                    </tr>
                  ) : null}
                </tbody>
              </table>

              <footer className="modal-footer">
                <button className="soft-button" type="button" onClick={onClose}>Закрыть</button>
                {canCancel ? (
                  <button
                    className="soft-button"
                    type="button"
                    onClick={() => void cancelPost()}
                    disabled={actionLoading}
                  >
                    Отменить публикацию
                  </button>
                ) : null}
              </footer>
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
}

// --- Follow-up Components ---

function FollowupPostsWorkspace({
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
  const [posts, setPosts] = useState<FollowupPost[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [selectedPostId, setSelectedPostId] = useState<string | null>(null);

  const loadPosts = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE_URL}/api/inbox/followup-posts`, {
        credentials: "include",
      });
      if (!response.ok) {
        throw new Error(`Load failed: ${response.status}`);
      }
      const data = (await response.json()) as FollowupPostList;
      setPosts(data.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadPosts();
  }, [loadPosts]);

  return (
    <>
      <header className="panel-header">
        <div>
          <p className="eyebrow">FunnelHub</p>
          <h1>Фоллоу-ап</h1>
          <ViewSwitch activeView={activeView} onSwitchView={onSwitchView} />
        </div>
        <div className="panel-actions">
          <button className="send-button" onClick={() => setShowCreate(true)} type="button">
            <Send aria-hidden="true" size={16} />
            Создать
          </button>
          <button className="icon-button" onClick={loadPosts} type="button">
            <RefreshCw aria-hidden="true" size={18} />
          </button>
          <button className="icon-button secondary" onClick={onLogout} type="button">
            <LogOut aria-hidden="true" size={18} />
            <span className="sr-only">Выйти{adminName ? `, ${adminName}` : ""}</span>
          </button>
        </div>
      </header>

      <div className="workspace is-list-only">
        {error ? <div className="toast" role="status">{error}</div> : null}
        <div className="lead-table-wrap">
          <table className="lead-table">
            <thead>
              <tr>
                <th>Пост</th>
                <th>Расписание</th>
                <th>Каналы</th>
                <th>Доставки</th>
                <th>Статус</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={5} style={{ textAlign: "center", padding: "2rem" }}>Загрузка...</td>
                </tr>
              ) : posts.length === 0 ? (
                <tr>
                  <td colSpan={5} style={{ textAlign: "center", padding: "2rem" }}>
                    Нет follow-up постов
                  </td>
                </tr>
              ) : (
                posts.map((post) => (
                  <tr
                    key={post.id}
                    onClick={() => setSelectedPostId(post.id)}
                    style={{ cursor: "pointer" }}
                  >
                    <td>
                      <strong>{post.title}</strong>
                      <p className="field-hint" style={{ margin: "4px 0 0" }}>
                        {trimPreview(post.body, 96)}
                      </p>
                    </td>
                    <td>{formatDetailValue(post.scheduled_at)}</td>
                    <td>{post.channels.map((c) => channelLabels[c] || c).join(", ")}</td>
                    <td>
                      {post.sent_deliveries}/{post.total_deliveries}
                      {post.failed_deliveries ? `, ошибок: ${post.failed_deliveries}` : ""}
                      {post.skipped_deliveries ? `, пропущено: ${post.skipped_deliveries}` : ""}
                    </td>
                    <td><GenericStatusPill status={post.status} /></td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {selectedPostId ? (
        <FollowupDetailModal
          postId={selectedPostId}
          onClose={() => setSelectedPostId(null)}
          onChanged={() => void loadPosts()}
        />
      ) : null}

      {showCreate ? (
        <FollowupCreateModal
          onClose={() => setShowCreate(false)}
          onSuccess={() => {
            setShowCreate(false);
            void loadPosts();
          }}
        />
      ) : null}
    </>
  );
}

function FollowupCreateModal({
  onClose,
  onSuccess,
}: {
  onClose: () => void;
  onSuccess: () => void;
}) {
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [channels, setChannels] = useState<string[]>(["telegram", "vk"]);
  const [scheduledAt, setScheduledAt] = useState("");
  const [preview, setPreview] = useState<FollowupRecipientPreview | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const toggleChannel = (ch: string) => {
    setChannels((prev) => prev.includes(ch) ? prev.filter((c) => c !== ch) : [...prev, ch]);
  };

  useEffect(() => {
    async function loadPreview() {
      if (channels.length === 0) {
        setPreview(null);
        return;
      }
      const params = new URLSearchParams();
      channels.forEach((channel) => params.append("channels", channel));
      const response = await fetch(
        `${API_BASE_URL}/api/inbox/followup-posts/recipient-preview?${params}`,
        { credentials: "include" }
      );
      if (!response.ok) {
        setPreview(null);
        return;
      }
      setPreview((await response.json()) as FollowupRecipientPreview);
    }
    void loadPreview();
  }, [channels]);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!title.trim()) {
      setError("Введите название follow-up поста");
      return;
    }
    if (!body.trim()) {
      setError("Введите текст сообщения");
      return;
    }
    if (channels.length === 0) {
      setError("Выберите хотя бы один канал");
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE_URL}/api/inbox/followup-posts`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: title.trim(),
          body: body.trim(),
          channels,
          scheduled_at: scheduledAt ? new Date(scheduledAt).toISOString() : null,
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
          <h2>Новый follow-up пост</h2>
          <button className="icon-button soft-button" onClick={onClose} type="button">
            <LogOut aria-hidden="true" size={18} />
          </button>
        </header>
        <form className="modal-body" onSubmit={handleSubmit}>
          {error ? <div className="form-error">{error}</div> : null}

          <div className="form-group">
            <label>Название</label>
            <input
              type="text"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="Название для истории"
              required
            />
          </div>

          <div className="form-group">
            <label>Текст сообщения</label>
            <textarea
              value={body}
              onChange={(event) => setBody(event.target.value)}
              placeholder="Сообщение после завершения основной воронки..."
              rows={7}
              required
            />
          </div>

          <div className="form-group">
            <label>Каналы доставки</label>
            <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", marginTop: "4px" }}>
              {["telegram", "vk"].map((ch) => (
                <button
                  key={ch}
                  type="button"
                  className={channels.includes(ch) ? "filter-chip is-active" : "filter-chip"}
                  onClick={() => toggleChannel(ch)}
                  style={{ display: "flex", alignItems: "center", gap: "6px" }}
                >
                  <span className={`channel-dot channel-${ch}`} />
                  {channelLabels[ch] || ch}
                </button>
              ))}
            </div>
            <p className="field-hint">
              Получателей сейчас: {preview ? preview.total : "—"}
              {preview
                ? ` · Telegram: ${preview.by_channel.telegram || 0}, VK: ${preview.by_channel.vk || 0}`
                : ""}
            </p>
          </div>

          <div className="form-group">
            <label>Дата и время</label>
            <input
              type="datetime-local"
              value={scheduledAt}
              onChange={(event) => setScheduledAt(event.target.value)}
            />
            <p className="field-hint">Пустое значение отправит пост в ближайший проход worker.</p>
          </div>

          <footer className="modal-footer">
            <button className="soft-button" type="button" onClick={onClose} disabled={loading}>Отмена</button>
            <button className="send-button" type="submit" disabled={loading}>
              <Send size={16} />
              {loading ? "Сохраняем..." : "Поставить в очередь"}
            </button>
          </footer>
        </form>
      </div>
    </div>
  );
}

function FollowupDetailModal({
  postId,
  onClose,
  onChanged,
}: {
  postId: string;
  onClose: () => void;
  onChanged: () => void;
}) {
  const [post, setPost] = useState<FollowupPost | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadPost = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE_URL}/api/inbox/followup-posts/${postId}`, {
        credentials: "include",
      });
      if (!res.ok) {
        throw new Error(`Load failed: ${res.status}`);
      }
      setPost((await res.json()) as FollowupPost);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [postId]);

  useEffect(() => {
    void loadPost();
  }, [loadPost]);

  const cancelPost = async () => {
    setActionLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE_URL}/api/inbox/followup-posts/${postId}/cancel`, {
        method: "PATCH",
        credentials: "include",
      });
      if (!res.ok) {
        const payload = await res.json().catch(() => null);
        throw new Error(payload?.detail || `Ошибка ${res.status}`);
      }
      setPost((await res.json()) as FollowupPost);
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setActionLoading(false);
    }
  };

  const canCancel = post && ["queued", "scheduled", "failed", "partial_failed"].includes(post.status);

  return (
    <div className="modal-overlay">
      <div className="modal-dialog" style={{ maxWidth: 900 }}>
        <header className="modal-header">
          <h2>{post?.title || "Follow-up пост"}</h2>
          <button className="icon-button soft-button" onClick={onClose} type="button">
            <LogOut aria-hidden="true" size={18} />
          </button>
        </header>
        <div className="modal-body" style={{ overflowY: "auto", maxHeight: "70vh" }}>
          {error ? <div className="toast" role="status">{error}</div> : null}
          {loading ? (
            <div style={{ textAlign: "center", padding: "2rem" }}>Загрузка...</div>
          ) : post ? (
            <>
              <div className="key-value-list">
                <KeyValueLine label="Статус" value={autopostStatusLabels[post.status] || post.status} />
                <KeyValueLine label="Расписание" value={post.scheduled_at} />
                <KeyValueLine label="Каналы" value={post.channels.map((c) => channelLabels[c] || c).join(", ")} />
                <KeyValueLine label="Всего доставок" value={post.total_deliveries} />
                <KeyValueLine label="Отправлено" value={post.sent_deliveries} />
                <KeyValueLine label="Ошибки" value={post.failed_deliveries} />
                <KeyValueLine label="Пропущено" value={post.skipped_deliveries} />
              </div>

              <div className="form-group">
                <label>Текст сообщения</label>
                <div className="message-bubble outbound" style={{ width: "100%", maxWidth: "100%" }}>
                  {post.body}
                </div>
              </div>

              <table className="lead-table">
                <thead>
                  <tr>
                    <th>Лид</th>
                    <th>Канал</th>
                    <th>Статус</th>
                    <th>Внешний ID</th>
                    <th>Попытка</th>
                    <th>Ошибка</th>
                  </tr>
                </thead>
                <tbody>
                  {post.deliveries.map((delivery) => (
                    <tr key={delivery.id}>
                      <td>{delivery.lead_name || "Без имени"}</td>
                      <td>{channelLabels[delivery.channel] || delivery.channel}</td>
                      <td><GenericStatusPill status={delivery.status} /></td>
                      <td><code className="mono-badge">{delivery.external_message_id || "—"}</code></td>
                      <td>{delivery.attempted_at ? formatDetailValue(delivery.attempted_at) : "—"}</td>
                      <td style={{ color: "var(--danger)" }}>{delivery.error || ""}</td>
                    </tr>
                  ))}
                  {post.deliveries.length === 0 ? (
                    <tr>
                      <td colSpan={6} style={{ textAlign: "center" }}>Получателей нет</td>
                    </tr>
                  ) : null}
                </tbody>
              </table>

              <footer className="modal-footer">
                <button className="soft-button" type="button" onClick={onClose}>Закрыть</button>
                {canCancel ? (
                  <button
                    className="soft-button"
                    type="button"
                    onClick={() => void cancelPost()}
                    disabled={actionLoading}
                  >
                    Отменить follow-up
                  </button>
                ) : null}
              </footer>
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function GenericStatusPill({ status }: { status: string }) {
  return (
    <span className={`status-pill status-${status}`}>
      {autopostStatusLabels[status] || status}
    </span>
  );
}

function trimPreview(value: string, limit: number) {
  if (value.length <= limit) {
    return value;
  }
  return `${value.slice(0, limit - 1)}…`;
}
