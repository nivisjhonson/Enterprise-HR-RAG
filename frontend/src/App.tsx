import { useCallback, useEffect, useMemo, useState, type FormEvent, type ReactNode } from "react";
import {
  ArrowDown,
  ArrowUpRight,
  BookOpen,
  Check,
  ChevronDown,
  CircleHelp,
  Clock3,
  FileText,
  KeyRound,
  Library,
  LoaderCircle,
  LockKeyhole,
  LogOut,
  MessageCircle,
  Plus,
  Search,
  Send,
  Settings,
  ShieldCheck,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
  Upload,
  Users,
  X,
} from "lucide-react";

import { api, postJson } from "./api";
import type {
  ApplicationSettings,
  Dashboard,
  ManagedUser,
  Message,
  PolicyDocument,
  Source,
  User,
} from "./types";

type Page = "chat" | "library" | "admin" | "settings";

const suggestedQuestions = [
  "How do I request annual leave?",
  "What is the remote-work approval process?",
  "Which documents are required for onboarding?",
  "How do I submit an expense reimbursement?",
];

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : "Something went wrong. Please try again.";
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function Badge({ children, tone = "neutral" }: { children: ReactNode; tone?: string }) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}

function Logo({ small = false }: { small?: boolean }) {
  return (
    <span className={`brand-mark${small ? " brand-mark-small" : ""}`}>
      <BookOpen size={small ? 18 : 20} strokeWidth={2.2} />
    </span>
  );
}

function formatAnswerInline(text: string, keyPrefix: string): ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*|__[^_]+__|\*[^*\n]+\*|_[^_\n]+_|\[S\d+\])/g);
  return parts.map((part, index) => {
    const key = `${keyPrefix}-${index}`;
    if (/^\*\*[^*]+\*\*$/.test(part) || /^__[^_]+__$/.test(part)) {
      return <strong key={key}>{part.slice(2, -2)}</strong>;
    }
    if (/^\*[^*\n]+\*$/.test(part) || /^_[^_\n]+_$/.test(part)) {
      return <em key={key}>{part.slice(1, -1)}</em>;
    }
    if (/^\[S\d+\]$/.test(part)) {
      return <span className="citation" key={key}>{part}</span>;
    }
    return part;
  });
}

function Login({
  onLogin,
}: {
  onLogin: (username: string, password: string) => Promise<void>;
}) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [administratorReady, setAdministratorReady] = useState(true);

  useEffect(() => {
    api<{ administrator_ready: boolean }>("/api/auth/status")
      .then(({ administrator_ready }) => setAdministratorReady(administrator_ready))
      .catch(() => setAdministratorReady(true));
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await onLogin(username, password);
    } catch (reason) {
      setError(messageOf(reason));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="login-layout">
      <section className="login-story">
        <div className="login-story-inner">
          <div className="brand brand-light">
            <Logo />
            <span>PeopleDesk</span>
          </div>
          <div className="story-copy">
            <Badge tone="glass">YOUR HR KNOWLEDGE, MADE CLEAR</Badge>
            <h1>Good work starts with knowing where you stand.</h1>
            <p>
              One thoughtful place to find trusted answers about your workplace
              policies.
            </p>
          </div>
          <div className="story-note">
            <ShieldCheck size={18} />
            <span>Answers grounded in the documents you’re allowed to see.</span>
          </div>
          <div className="story-decoration story-decoration-one" />
          <div className="story-decoration story-decoration-two" />
        </div>
      </section>
      <section className="login-panel">
        <div className="login-card">
          <div className="login-mobile-brand brand">
            <Logo />
            <span>PeopleDesk</span>
          </div>
          <div className="eyebrow">WELCOME BACK</div>
          <h2>Sign in to your workspace</h2>
          <p className="muted login-description">
            Use your organization account to continue.
          </p>
          {!administratorReady && (
            <div className="notice notice-info">
              <CircleHelp size={18} />
              <span>
                No administrator is set up yet. Open a second terminal in the
                project folder and run{" "}
                <code>.\.venv\Scripts\python.exe -m scripts.bootstrap_admin</code>.
                It prompts for the initial account securely; then refresh this page.
              </span>
            </div>
          )}
          {error && <div className="notice notice-error">{error}</div>}
          <form className="login-form" onSubmit={submit}>
            <label>
              Work username
              <div className="input-icon">
                <Users size={17} />
                <input
                  autoComplete="username"
                  value={username}
                  onChange={(event) => setUsername(event.target.value)}
                  placeholder="your.name"
                  required
                />
              </div>
            </label>
            <label>
              Password
              <div className="input-icon">
                <KeyRound size={17} />
                <input
                  type="password"
                  autoComplete="current-password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  placeholder="Enter your password"
                  required
                />
              </div>
            </label>
            <button className="button button-primary login-submit" disabled={submitting}>
              {submitting ? <LoaderCircle className="spin" size={18} /> : null}
              Sign in securely
              {!submitting && <ArrowUpRight size={17} />}
            </button>
          </form>
          <div className="login-footer">
            <LockKeyhole size={15} />
            <span>Your session is protected with a secure, HTTP-only cookie.</span>
          </div>
        </div>
        <div className="login-panel-footer">PeopleDesk · HR Policy Assistant</div>
      </section>
    </div>
  );
}

function CitationText({ text }: { text: string }) {
  const blocks: ReactNode[] = [];
  let paragraph: string[] = [];
  let listItems: { text: string; ordered: boolean }[] = [];

  function flushParagraph() {
    if (paragraph.length) {
      blocks.push(
        <p key={`paragraph-${blocks.length}`}>
          {formatAnswerInline(paragraph.join(" "), `paragraph-${blocks.length}`)}
        </p>,
      );
      paragraph = [];
    }
  }

  function flushList() {
    if (!listItems.length) return;
    const ordered = listItems[0].ordered;
    const items = listItems;
    const List = ordered ? "ol" : "ul";
    blocks.push(
      <List key={`list-${blocks.length}`}>
        {items.map((item, index) => (
          <li key={`list-${blocks.length}-${index}`}>
            {formatAnswerInline(item.text, `list-${blocks.length}-${index}`)}
          </li>
        ))}
      </List>,
    );
    listItems = [];
  }

  for (const rawLine of text.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line) {
      flushParagraph();
      flushList();
      continue;
    }

    const orderedMatch = line.match(/^\d+[.)]\s+(.+)$/);
    const bulletMatch = line.match(/^[-*+]\s+(.+)$/);
    if (orderedMatch || bulletMatch) {
      flushParagraph();
      const ordered = Boolean(orderedMatch);
      if (listItems.length && listItems[0].ordered !== ordered) flushList();
      listItems.push({ text: orderedMatch?.[1] ?? bulletMatch![1], ordered });
      continue;
    }

    flushList();
    const headingMatch = line.match(/^#{1,3}\s+(.+)$/);
    if (headingMatch) {
      flushParagraph();
      blocks.push(
        <h3 key={`heading-${blocks.length}`}>
          {formatAnswerInline(headingMatch[1], `heading-${blocks.length}`)}
        </h3>,
      );
      continue;
    }
    paragraph.push(line);
  }
  flushParagraph();
  flushList();

  return (
    <div className="answer-text">{blocks}</div>
  );
}

function SourceList({ sources }: { sources: Source[] }) {
  const [open, setOpen] = useState(false);
  if (!sources.length) return null;
  return (
    <div className={`sources-card${open ? " sources-open" : ""}`}>
      <button className="sources-toggle" onClick={() => setOpen((value) => !value)}>
        <span className="source-count">
          <FileText size={15} />
          {sources.length} cited {sources.length === 1 ? "source" : "sources"}
        </span>
        <ChevronDown size={16} />
      </button>
      {open && (
        <div className="source-list">
          {sources.map((source) => (
            <article className="source-item" key={`${source.label}-${source.filename}`}>
              <div className="source-heading">
                <span className="citation">{source.label}</span>
                <strong>{source.filename}</strong>
                {source.page_number ? (
                  <span className="muted">· Page {source.page_number}</span>
                ) : null}
              </div>
              <p>{source.excerpt}</p>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}

function Chat({ username, canUpload }: { username: string; canUpload: boolean }) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [question, setQuestion] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [uploadNotice, setUploadNotice] = useState("");
  const [uploading, setUploading] = useState(false);
  const [draggingFile, setDraggingFile] = useState(false);
  const [attachment, setAttachment] = useState<File | null>(null);
  const [maxUploadSizeMb, setMaxUploadSizeMb] = useState(100);

  useEffect(() => {
    if (canUpload) {
      api<ApplicationSettings>("/api/settings")
        .then((settings) => setMaxUploadSizeMb(settings.max_upload_size_mb))
        .catch((reason: unknown) => setError(messageOf(reason)));
    }
  }, [canUpload]);

  function chooseAttachment(file: File | undefined) {
    if (!file) return;
    const extension = file.name.split(".").pop()?.toLowerCase();
    if (!extension || !["pdf", "docx", "txt"].includes(extension)) {
      setError("Choose a PDF, DOCX, or TXT policy document.");
      return;
    }
    if (file.size > maxUploadSizeMb * 1024 * 1024) {
      setError(`${file.name} exceeds the ${maxUploadSizeMb} MB per-file limit.`);
      return;
    }
    setError("");
    setUploadNotice("");
    setAttachment(file);
  }

  async function uploadAttachment() {
    if (!attachment || uploading) return;
    const file = attachment;
    setUploading(true);
    setError("");
    setUploadNotice("");
    const form = new FormData();
    form.append("files", file);
    form.append("category", "General");
    form.append("access_level", "employee");
    try {
      const response = await api<{
        results: { filename: string; status: string; chunk_count?: number; error?: string }[];
      }>("/api/admin/documents", { method: "POST", body: form });
      const result = response.results[0];
      if (!result || result.status === "failed") {
        throw new Error(result?.error ?? "The document could not be indexed.");
      }
      setUploadNotice(
        `${result.filename} ${result.status === "unchanged" ? "is already indexed" : "is indexed and ready"}${result.chunk_count ? ` · ${result.chunk_count} searchable passages` : ""}.`,
      );
      setAttachment(null);
    } catch (reason) {
      setError(messageOf(reason));
    } finally {
      setUploading(false);
    }
  }

  async function ask(rawQuestion: string) {
    const text = rawQuestion.trim();
    if (!text || sending) return;
    setMessages((items) => [...items, { id: crypto.randomUUID(), role: "user", content: text }]);
    setQuestion("");
    setError("");
    setSending(true);
    try {
      const answer = await postJson<{
        answer: string;
        sources: Source[];
        answer_id: string;
      }>("/api/chat", { question: text });
      setMessages((items) => [
        ...items,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: answer.answer,
          sources: answer.sources,
          answerId: answer.answer_id,
        },
      ]);
    } catch (reason) {
      setError(messageOf(reason));
    } finally {
      setSending(false);
    }
  }

  async function rateAnswer(answerId: string, rating: number) {
    setError("");
    try {
      await postJson("/api/feedback", { answer_id: answerId, rating });
      setMessages((items) =>
        items.map((item) =>
          item.answerId === answerId ? { ...item, feedback: rating } : item,
        ),
      );
    } catch (reason) {
      setError(messageOf(reason));
    }
  }

  return (
    <div className="chat-page">
      <div className="page-heading chat-heading">
        <div>
          <div className="eyebrow">YOUR POLICY COMPANION</div>
          <h1>How can I help, {username}?</h1>
          <p>
            Ask about work. I’ll use your HR policies when available and clearly
            label general guidance.
          </p>
        </div>
        {messages.length > 0 && (
          <button className="button button-quiet" onClick={() => setMessages([])}>
            <Plus size={16} />
            New conversation
          </button>
        )}
      </div>

      <div className={`chat-canvas${messages.length ? " chat-canvas-active" : ""}`}>
        {messages.length === 0 ? (
          <div className="welcome-panel">
            <div className="welcome-icon">
              <Sparkles size={25} />
            </div>
            <h2>Find the answer, not another document.</h2>
            <p>
              I’ll use your indexed HR policies when available. Without them,
              I can still share general guidance and clearly label it as such.
            </p>
            <div className="suggestion-grid">
              {suggestedQuestions.map((item) => (
                <button className="suggestion" key={item} onClick={() => void ask(item)}>
                  <span>{item}</span>
                  <ArrowUpRight size={16} />
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="message-list">
            {messages.map((message) => (
              <article
                className={`message message-${message.role}`}
                key={message.id}
              >
                {message.role === "assistant" && (
                  <div className="assistant-avatar">
                    <Sparkles size={15} />
                  </div>
                )}
                <div className="message-body">
                  {message.role === "user" ? (
                    <p className="user-bubble">{message.content}</p>
                  ) : (
                    <>
                      <CitationText text={message.content} />
                      <SourceList sources={message.sources ?? []} />
                      {message.answerId && (
                        <div className="feedback-row">
                          <span>Was this helpful?</span>
                          <button
                            aria-label="Helpful"
                            className={message.feedback === 1 ? "selected" : ""}
                            disabled={message.feedback !== undefined}
                            onClick={() => void rateAnswer(message.answerId!, 1)}
                          >
                            {message.feedback === 1 ? <Check size={15} /> : <ThumbsUp size={15} />}
                          </button>
                          <button
                            aria-label="Not helpful"
                            className={message.feedback === -1 ? "selected" : ""}
                            disabled={message.feedback !== undefined}
                            onClick={() => void rateAnswer(message.answerId!, -1)}
                          >
                            {message.feedback === -1 ? <Check size={15} /> : <ThumbsDown size={15} />}
                          </button>
                          {message.feedback !== undefined && <span>Thanks for your feedback.</span>}
                        </div>
                      )}
                    </>
                  )}
                </div>
              </article>
            ))}
            {sending && (
              <div className="message message-assistant">
                <div className="assistant-avatar">
                  <Sparkles size={15} />
                </div>
                <div className="typing-indicator">
                  <span />
                  <span />
                  <span />
                  <small>Searching authorized policies…</small>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {error && <div className="notice notice-error chat-error">{error}</div>}
      <form
        className="chat-composer"
        onDragOver={(event) => {
          if (!canUpload) return;
          event.preventDefault();
          setDraggingFile(true);
        }}
        onDragLeave={(event) => {
          if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
            setDraggingFile(false);
          }
        }}
        onDrop={(event) => {
          event.preventDefault();
          setDraggingFile(false);
          if (canUpload) chooseAttachment(event.dataTransfer.files[0]);
        }}
        onSubmit={(event) => {
          event.preventDefault();
          void ask(question);
        }}
      >
        {draggingFile && <div className="chat-drop-overlay"><Upload size={20} /> Drop a policy document to add it</div>}
        <textarea
          aria-label="Ask about HR policies"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              void ask(question);
            }
          }}
          placeholder="Ask a question about HR policies…"
          rows={1}
          maxLength={4000}
          disabled={sending}
        />
        {attachment && (
          <div className="chat-attachment">
            <FileText size={16} />
            <span className="chat-attachment-name">{attachment.name}</span>
            <span>{formatFileSize(attachment.size)}</span>
            <button type="button" aria-label="Remove attached document" disabled={uploading} onClick={() => setAttachment(null)}>
              <X size={15} />
            </button>
          </div>
        )}
        <div className="composer-footer">
          {canUpload ? (
            <div className="composer-tools">
              <label className="attach-button" title={`Add a PDF, DOCX, or TXT file up to ${maxUploadSizeMb} MB`}>
                <input
                  type="file"
                  accept=".pdf,.docx,.txt,application/pdf"
                  hidden
                  disabled={uploading}
                  onChange={(event) => {
                    chooseAttachment(event.target.files?.[0]);
                    event.target.value = "";
                  }}
                />
                <Upload size={15} />
                <span>Add policy</span>
              </label>
              <span className="upload-limit">Up to {maxUploadSizeMb} MB</span>
            </div>
          ) : <span />}
          {canUpload && attachment ? (
            <button className="button button-primary chat-upload-button" type="button" onClick={() => void uploadAttachment()} disabled={uploading}>
              {uploading ? <LoaderCircle className="spin" size={16} /> : <Upload size={15} />}
              {uploading ? "Uploading and indexing…" : "Index document"}
            </button>
          ) : (
            <button
              className="send-button"
              aria-label="Send question"
              type="submit"
              disabled={sending || !question.trim()}
            >
              {sending ? <LoaderCircle className="spin" size={18} /> : <Send size={17} />}
            </button>
          )}
        </div>
      </form>
      {uploadNotice && <div className="chat-upload-notice"><Check size={15} />{uploadNotice}</div>}
      <div className="privacy-caption">
        Documents are processed locally for search; general guidance is not company policy.
      </div>
    </div>
  );
}

function DocumentLibrary() {
  const [documents, setDocuments] = useState<PolicyDocument[]>([]);
  const [category, setCategory] = useState("All categories");
  const [search, setSearch] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    api<PolicyDocument[]>("/api/documents")
      .then(setDocuments)
      .catch((reason: unknown) => setError(messageOf(reason)));
  }, []);

  const categories = useMemo(
    () => ["All categories", ...Array.from(new Set(documents.map((doc) => doc.category))).sort()],
    [documents],
  );
  const visible = documents.filter(
    (document) =>
      (category === "All categories" || document.category === category) &&
      document.filename.toLowerCase().includes(search.trim().toLowerCase()),
  );

  return (
    <section>
      <div className="page-heading">
        <div>
          <div className="eyebrow">YOUR KNOWLEDGE BASE</div>
          <h1>Policy library</h1>
          <p>Browse active HR documents available to your account.</p>
        </div>
        <div className="heading-count">
          <strong>{documents.length}</strong>
          <span>available policies</span>
        </div>
      </div>
      <div className="library-toolbar">
        <label className="search-field">
          <Search size={17} />
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search policies"
          />
        </label>
        <select value={category} onChange={(event) => setCategory(event.target.value)}>
          {categories.map((option) => (
            <option key={option}>{option}</option>
          ))}
        </select>
      </div>
      {error && <div className="notice notice-error">{error}</div>}
      {!error && visible.length === 0 ? (
        <div className="empty-card">
          <div className="empty-icon">
            <Library size={22} />
          </div>
          <h3>{documents.length ? "No policies match your search" : "No policies available yet"}</h3>
          <p>
            {documents.length
              ? "Try a different title or category."
              : "Your administrator will add approved HR policies here."}
          </p>
        </div>
      ) : (
        <div className="document-grid">
          {visible.map((document) => (
            <article className="document-card" key={document.id}>
              <div className="document-icon">
                <FileText size={20} />
              </div>
              <div className="document-card-body">
                <Badge tone="green">{document.category}</Badge>
                <h3>{document.filename}</h3>
                <p>Current version {document.version}</p>
              </div>
              <ShieldCheck className="document-access" size={18} />
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

function AdminPage() {
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [tab, setTab] = useState<"upload" | "documents" | "users">("upload");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [files, setFiles] = useState<File[]>([]);
  const [draggingFiles, setDraggingFiles] = useState(false);
  const [category, setCategory] = useState("General");
  const [accessLevel, setAccessLevel] = useState<"employee" | "admin">("employee");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<"employee" | "admin">("employee");

  const refresh = useCallback(async () => {
    setError("");
    try {
      setDashboard(await api<Dashboard>("/api/admin/dashboard"));
    } catch (reason) {
      setError(messageOf(reason));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function submitUploads(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!files.length) return;
    setBusy(true);
    setNotice("");
    setError("");
    const form = new FormData();
    form.append("category", category);
    form.append("access_level", accessLevel);
    files.forEach((file) => form.append("files", file));
    try {
      const response = await api<{
        results: { filename: string; status: string; chunk_count?: number; error?: string }[];
      }>("/api/admin/documents", { method: "POST", body: form });
      const summary = response.results
        .map((item) =>
          item.status === "failed"
            ? `${item.filename}: ${item.error}`
            : `${item.filename}: ${item.status}${item.chunk_count ? ` (${item.chunk_count} chunks)` : ""}`,
        )
        .join(" · ");
      setNotice(summary || "No documents were processed.");
      setFiles([]);
      await refresh();
    } catch (reason) {
      setError(messageOf(reason));
    } finally {
      setBusy(false);
    }
  }

  async function removeDocument(document: PolicyDocument) {
    if (!window.confirm(`Delete "${document.filename}" and its indexed content?`)) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await api<{ warning?: string | null }>(
        `/api/admin/documents/${encodeURIComponent(document.id)}`,
        { method: "DELETE" },
      );
      setNotice(result.warning || `${document.filename} was deleted.`);
      await refresh();
    } catch (reason) {
      setError(messageOf(reason));
    } finally {
      setBusy(false);
    }
  }

  async function retryCleanup(documentId: string, version: number) {
    setBusy(true);
    setError("");
    try {
      const result = await api<{ warning?: string | null }>(
        `/api/admin/documents/${encodeURIComponent(documentId)}/cleanup/${version}`,
        { method: "POST" },
      );
      setNotice(result.warning || "Obsolete vectors removed.");
      await refresh();
    } catch (reason) {
      setError(messageOf(reason));
    } finally {
      setBusy(false);
    }
  }

  async function createAccount(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await postJson("/api/admin/users", { username, password, role });
      setUsername("");
      setPassword("");
      setNotice(`Created ${role} account.`);
      await refresh();
    } catch (reason) {
      setError(messageOf(reason));
    } finally {
      setBusy(false);
    }
  }

  async function toggleUser(account: ManagedUser) {
    setBusy(true);
    setError("");
    try {
      await api(`/api/admin/users/${encodeURIComponent(account.username)}`, {
        method: "PATCH",
        body: JSON.stringify({ is_active: !Boolean(account.is_active) }),
        headers: { "Content-Type": "application/json" },
      });
      await refresh();
    } catch (reason) {
      setError(messageOf(reason));
    } finally {
      setBusy(false);
    }
  }

  const statistics = dashboard?.statistics;
  return (
    <section>
      <div className="page-heading">
        <div>
          <div className="eyebrow">WORKSPACE MANAGEMENT</div>
          <h1>Admin dashboard</h1>
          <p>Manage trusted policy content and workspace access.</p>
        </div>
        <button className="button button-quiet" onClick={() => void refresh()}>
          <ArrowDown size={15} className="refresh-icon" />
          Refresh
        </button>
      </div>
      {error && <div className="notice notice-error">{error}</div>}
      {notice && (
        <div className="notice notice-success">
          <Check size={17} />
          <span>{notice}</span>
          <button aria-label="Dismiss" onClick={() => setNotice("")}><X size={15} /></button>
        </div>
      )}
      {loading ? (
        <div className="loading-state"><LoaderCircle className="spin" /> Loading workspace…</div>
      ) : dashboard && (
        <>
          <div className="stat-grid">
            <StatCard label="Indexed policies" value={statistics?.indexed_documents ?? 0} icon={<FileText />} />
            <StatCard label="Searchable passages" value={statistics?.chunks ?? 0} icon={<Sparkles />} />
            <StatCard label="Completed uploads" value={statistics?.successful_jobs ?? 0} icon={<Check />} />
            <StatCard label="Needs attention" value={statistics?.failed_jobs ?? 0} icon={<CircleHelp />} warning={(statistics?.failed_jobs ?? 0) > 0} />
          </div>
          <div className="admin-panel">
            <div className="admin-tabs" role="tablist">
              {([
                ["upload", <Upload size={16} />, "Upload policies"],
                ["documents", <FileText size={16} />, "Manage documents"],
                ["users", <Users size={16} />, "Manage people"],
              ] as const).map(([key, icon, label]) => (
                <button
                  className={tab === key ? "admin-tab active" : "admin-tab"}
                  key={key}
                  onClick={() => setTab(key)}
                  role="tab"
                  aria-selected={tab === key}
                >
                  {icon}{label}
                </button>
              ))}
            </div>
            {tab === "upload" && (
              <div className="admin-content">
                <div className="admin-section-heading">
                  <div>
                    <h2>Add policy documents</h2>
                    <p>PDF, DOCX, and TXT · up to {dashboard.max_upload_size_mb} MB each</p>
                  </div>
                  <Badge tone="blue"><ShieldCheck size={13} /> Private by default</Badge>
                </div>
                <form className="upload-form" onSubmit={submitUploads}>
                  <label
                    className={`upload-dropzone${draggingFiles ? " drag-over" : ""}`}
                    onDragOver={(event) => {
                      event.preventDefault();
                      setDraggingFiles(true);
                    }}
                    onDragLeave={() => setDraggingFiles(false)}
                    onDrop={(event) => {
                      event.preventDefault();
                      setFiles(Array.from(event.dataTransfer.files));
                      setDraggingFiles(false);
                    }}
                  >
                    <input
                      type="file"
                      accept=".pdf,.docx,.txt"
                      multiple
                      onChange={(event) => setFiles(Array.from(event.target.files ?? []))}
                    />
                    <span className="upload-icon"><Upload size={20} /></span>
                    <strong>Choose files to upload</strong>
                    <span>or drop them here · PDF, DOCX, TXT</span>
                  </label>
                  {files.length > 0 && (
                    <div className="selected-files">
                      {files.map((file) => (
                        <span className="selected-file" key={`${file.name}-${file.size}`}>
                          <FileText size={14} />{file.name}
                          <button
                            type="button"
                            aria-label={`Remove ${file.name}`}
                            onClick={() => setFiles((items) => items.filter((item) => item !== file))}
                          ><X size={14} /></button>
                        </span>
                      ))}
                    </div>
                  )}
                  <div className="form-grid">
                    <label>Category
                      <input value={category} onChange={(event) => setCategory(event.target.value)} required maxLength={80} />
                    </label>
                    <label>Who can access this?
                      <select value={accessLevel} onChange={(event) => setAccessLevel(event.target.value as "employee" | "admin")}>
                        <option value="employee">All employees</option>
                        <option value="admin">Administrators only</option>
                      </select>
                    </label>
                  </div>
                  <div className="form-actions">
                    <span>Replacing a file with the same name creates a new version.</span>
                    <button className="button button-primary" disabled={busy || !files.length}>
                      {busy ? <LoaderCircle className="spin" size={17} /> : <Upload size={16} />}
                      Index {files.length ? `${files.length} file${files.length === 1 ? "" : "s"}` : "documents"}
                    </button>
                  </div>
                </form>
              </div>
            )}
            {tab === "documents" && (
              <div className="admin-content">
                <div className="admin-section-heading">
                  <div>
                    <h2>Policy documents</h2>
                    <p>Review access, index status, and document versions.</p>
                  </div>
                </div>
                {dashboard.pending_cleanup.length > 0 && (
                  <div className="cleanup-list">
                    <h3>Obsolete vector cleanup</h3>
                    {dashboard.pending_cleanup.map((item) => (
                      <div className="cleanup-row" key={`${item.document_id}-${item.version}`}>
                        <div><strong>{item.filename}</strong><span>Version {item.version} · {item.error_message}</span></div>
                        <button className="button button-secondary button-small" disabled={busy} onClick={() => void retryCleanup(item.document_id, item.version)}>Retry cleanup</button>
                      </div>
                    ))}
                  </div>
                )}
                {dashboard.failed_jobs.length > 0 && (
                  <div className="failed-jobs">
                    <h3>Recent failed uploads</h3>
                    {dashboard.failed_jobs.map((job) => (
                      <div className="failed-job" key={job.id}><strong>{job.filename}</strong><span>{job.error_message}</span></div>
                    ))}
                  </div>
                )}
                <div className="managed-list">
                  {dashboard.documents.length === 0 ? (
                    <div className="empty-inline">No documents have been uploaded.</div>
                  ) : dashboard.documents.map((document) => (
                    <ManagedDocument
                      document={document}
                      disabled={busy}
                      key={document.id}
                      onDelete={() => void removeDocument(document)}
                    />
                  ))}
                </div>
              </div>
            )}
            {tab === "users" && (
              <div className="admin-content">
                <div className="admin-section-heading">
                  <div>
                    <h2>People and access</h2>
                    <p>Create accounts or pause access for a team member.</p>
                  </div>
                </div>
                <form className="create-user-form" onSubmit={createAccount}>
                  <label>Username
                    <input value={username} onChange={(event) => setUsername(event.target.value)} minLength={3} maxLength={64} required />
                  </label>
                  <label>Temporary password
                    <input type="password" autoComplete="new-password" value={password} onChange={(event) => setPassword(event.target.value)} minLength={12} required />
                  </label>
                  <label>Role
                    <select value={role} onChange={(event) => setRole(event.target.value as "employee" | "admin")}>
                      <option value="employee">Employee</option>
                      <option value="admin">Administrator</option>
                    </select>
                  </label>
                  <button className="button button-primary" disabled={busy}><Plus size={16} />Create account</button>
                </form>
                <div className="user-table">
                  <div className="user-table-head"><span>Account</span><span>Role</span><span>Status</span><span>Action</span></div>
                  {dashboard.users.map((account) => (
                    <div className="user-table-row" key={account.username}>
                      <div className="user-name"><span className="user-avatar">{account.username.slice(0, 1).toUpperCase()}</span><strong>{account.username}</strong></div>
                      <span className="user-role">{account.role}</span>
                      <Badge tone={Boolean(account.is_active) ? "green" : "neutral"}>{Boolean(account.is_active) ? "Active" : "Disabled"}</Badge>
                      <button
                        className="text-button"
                        disabled={busy}
                        onClick={() => void toggleUser(account)}
                      >
                        {Boolean(account.is_active) ? "Disable" : "Enable"}
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </>
      )}
    </section>
  );
}

function StatCard({
  label,
  value,
  icon,
  warning = false,
}: {
  label: string;
  value: number;
  icon: ReactNode;
  warning?: boolean;
}) {
  return (
    <article className="stat-card">
      <span className={`stat-icon${warning ? " stat-icon-warning" : ""}`}>{icon}</span>
      <span className="stat-value">{value.toLocaleString()}</span>
      <span className="stat-label">{label}</span>
    </article>
  );
}

function LandingPage({
  onNavigate,
  isAdmin,
}: {
  onNavigate: (page: Page) => void;
  isAdmin: boolean;
}) {
  return (
    <div className="public-landing">
      <header className="landing-header">
        <div className="brand landing-brand">
          <Logo />
          <span>PeopleDesk</span>
        </div>
        <button className="button button-primary landing-header-cta" onClick={() => onNavigate("chat")}>
          Open HR workspace <ArrowUpRight size={16} />
        </button>
      </header>
      <main className="landing-page">
      <div className="landing-hero">
        <div className="landing-copy">
          <Badge tone="landing"><span className="status-dot" /> YOUR HR WORKSPACE</Badge>
          <h1>Clear answers for the moments that matter at work.</h1>
          <p>
            Ask a question in everyday language. PeopleDesk searches your HR
            policies first and shows the sources behind its answers.
          </p>
          <div className="landing-actions">
            <button className="button button-primary landing-primary" onClick={() => onNavigate("chat")}>
              <MessageCircle size={17} /> Ask HR <ArrowUpRight size={16} />
            </button>
            <button className="button button-secondary" onClick={() => onNavigate("library")}>
              <Library size={16} /> Explore policy library
            </button>
          </div>
          <div className="landing-trust"><ShieldCheck size={16} /> Private workspace · Policy answers include citations</div>
        </div>
        <div className="landing-preview" aria-hidden="true">
          <div className="preview-topline"><span className="preview-dot" /><span className="preview-dot" /><span className="preview-dot" /><span>SAMPLE CONVERSATION</span></div>
          <div className="preview-question"><span className="preview-user">Y</span><p>Where can I find our time-off policy?</p></div>
          <div className="preview-answer">
            <span className="preview-assistant"><Sparkles size={15} /></span>
            <div><strong>Start with your policy library</strong><p>Search your indexed HR documents for the organization's current guidance and process.</p><span className="preview-source"><FileText size={12} /> Example source citation</span></div>
          </div>
          <div className="preview-input"><span>Ask about your workplace…</span><span className="preview-send"><ArrowUpRight size={15} /></span></div>
        </div>
      </div>
      <div className="landing-section-heading">
        <div><span className="eyebrow">A BETTER WAY TO FIND YOUR WAY</span><h2>Helpful by design</h2></div>
        <span>Everything you need to get started.</span>
      </div>
      <div className="landing-feature-grid">
        <button className="landing-feature" onClick={() => onNavigate("chat")}>
          <span className="landing-feature-icon feature-purple"><MessageCircle size={19} /></span>
          <strong>Ask in plain language</strong>
          <span>Get a clear starting point without searching through folders.</span>
          <span className="feature-link">Start a conversation <ArrowUpRight size={14} /></span>
        </button>
        <button className="landing-feature" onClick={() => onNavigate("library")}>
          <span className="landing-feature-icon feature-blue"><BookOpen size={19} /></span>
          <strong>Explore your policies</strong>
          <span>Browse indexed HR documents and review their source details.</span>
          <span className="feature-link">Browse library <ArrowUpRight size={14} /></span>
        </button>
        {isAdmin && (
          <button className="landing-feature" onClick={() => onNavigate("admin")}>
            <span className="landing-feature-icon feature-green"><Upload size={19} /></span>
            <strong>Keep knowledge current</strong>
            <span>Workspace admins can add and manage policy documents.</span>
            <span className="feature-link">Manage workspace <ArrowUpRight size={14} /></span>
          </button>
        )}
      </div>
      <div className="landing-note"><CircleHelp size={17} /><span><strong>Need an official answer?</strong> Use the cited policy as your source of truth or contact your HR team. General guidance is clearly labeled.</span></div>
      </main>
      <footer className="landing-footer">
        <span>PeopleDesk · HR Policy Assistant</span>
        <span>Clear answers, grounded in your workplace policies.</span>
      </footer>
    </div>
  );
}

function ManagedDocument({
  document,
  disabled,
  onDelete,
}: {
  document: PolicyDocument;
  disabled: boolean;
  onDelete: () => void;
}) {
  const canDelete = !["deleted", "deleting"].includes(document.status);
  return (
    <article className="managed-document">
      <div className="document-icon"><FileText size={18} /></div>
      <div className="managed-document-info">
        <div className="managed-document-name">{document.filename}</div>
        <span>{document.category} · v{document.version} · {document.chunk_count} passages</span>
      </div>
      <Badge tone={document.status === "indexed" ? "green" : document.status === "failed" ? "red" : "neutral"}>{document.status}</Badge>
      <Badge tone={document.access_level === "admin" ? "purple" : "blue"}>{document.access_level === "admin" ? "Admin only" : "Employee access"}</Badge>
      {document.error_message && <span className="document-error">{document.error_message}</span>}
      {canDelete && <button className="icon-button danger-hover" aria-label={`Delete ${document.filename}`} disabled={disabled} onClick={onDelete}><X size={17} /></button>}
    </article>
  );
}

function SettingsPage() {
  const [settings, setSettings] = useState<ApplicationSettings | null>(null);
  const [health, setHealth] = useState<{ ok: boolean; indexed_vectors: number } | null>(null);
  const [error, setError] = useState("");
  const [checking, setChecking] = useState(false);
  useEffect(() => {
    api<ApplicationSettings>("/api/settings")
      .then(setSettings)
      .catch((reason: unknown) => setError(messageOf(reason)));
  }, []);

  async function checkStorage() {
    setChecking(true);
    setError("");
    try {
      setHealth(await api("/api/settings/health"));
    } catch (reason) {
      setError(messageOf(reason));
      setHealth(null);
    } finally {
      setChecking(false);
    }
  }

  return (
    <section>
      <div className="page-heading">
        <div>
          <div className="eyebrow">WORKSPACE DETAILS</div>
          <h1>Settings</h1>
          <p>Private configuration details for this assistant.</p>
        </div>
      </div>
      {error && <div className="notice notice-error">{error}</div>}
      {settings && (
        <>
          <div className="settings-grid">
            <SettingCard label="Language model" value={settings.gemini_model} icon={<Sparkles size={18} />} />
            <SettingCard label="API key" value={settings.google_api_key_configured ? "Configured · secret hidden" : "Not configured"} icon={<KeyRound size={18} />} status={settings.google_api_key_configured} />
            <SettingCard label="Search results" value={`${settings.retrieval_top_k} passages per question`} icon={<Search size={18} />} />
            <SettingCard label="Text processing" value={`${settings.chunk_size} characters · ${settings.chunk_overlap} overlap`} icon={<FileText size={18} />} />
            <SettingCard label="Embedding model" value={settings.embedding_model} icon={<BookOpen size={18} />} />
            <SettingCard label="Environment" value={settings.environment} icon={<ShieldCheck size={18} />} />
          </div>
          <div className="health-card">
            <div className="health-icon"><ShieldCheck size={20} /></div>
            <div className="health-copy">
              <strong>Document search storage</strong>
              <span>{health ? `${health.indexed_vectors.toLocaleString()} searchable passages` : "Check whether the local index is available."}</span>
              {settings.last_indexing && <small><Clock3 size={13} /> Last upload completed {new Date(settings.last_indexing).toLocaleString()}</small>}
            </div>
            <button className="button button-secondary" disabled={checking} onClick={() => void checkStorage()}>
              {checking ? <LoaderCircle className="spin" size={16} /> : <ShieldCheck size={16} />}
              Check storage
            </button>
          </div>
          <div className="notice notice-info settings-privacy">
            <LockKeyhole size={17} />
            <span>Secrets are never displayed here. Configure Google Gemini and session keys only in the local <code>.env</code> file.</span>
          </div>
        </>
      )}
    </section>
  );
}

function SettingCard({
  label,
  value,
  icon,
  status,
}: {
  label: string;
  value: string;
  icon: ReactNode;
  status?: boolean;
}) {
  return (
    <article className="setting-card">
      <span className="setting-icon">{icon}</span>
      <div><span className="setting-label">{label}</span><strong className={status === false ? "setting-warning" : ""}>{value}</strong></div>
    </article>
  );
}

const navigation: { id: Page; label: string; icon: typeof MessageCircle }[] = [
  { id: "chat", label: "Ask HR", icon: MessageCircle },
  { id: "library", label: "Policy library", icon: Library },
];

function App() {
  const [user, setUser] = useState<User | null>(null);
  const [authenticationEnabled, setAuthenticationEnabled] = useState(true);
  const [page, setPage] = useState<Page>("chat");
  const [isLanding, setIsLanding] = useState(window.location.pathname !== "/app");
  const [loading, setLoading] = useState(true);
  const [globalError, setGlobalError] = useState("");

  useEffect(() => {
    function syncRoute() {
      const workspaceRoute = window.location.pathname === "/app";
      setIsLanding(!workspaceRoute);
      if (workspaceRoute) setPage("chat");
    }
    window.addEventListener("popstate", syncRoute);
    return () => window.removeEventListener("popstate", syncRoute);
  }, []);

  useEffect(() => {
    let active = true;
    async function openWorkspace() {
      try {
        const status = await api<{
          authentication_enabled: boolean;
        }>("/api/auth/status");
        if (!active) return;
        setAuthenticationEnabled(status.authentication_enabled);
        if (!status.authentication_enabled) {
          setUser({ username: "Local workspace", role: "admin" });
        } else {
          try {
            setUser(await api<User>("/api/auth/me"));
          } catch {
            setUser(null);
          }
        }
      } catch {
        setUser(null);
      } finally {
        if (active) setLoading(false);
      }
    }
    void openWorkspace();
    return () => {
      active = false;
    };
  }, []);

  function openWorkspace(target: Page) {
    window.history.pushState({ page: target }, "", "/app");
    setPage(target);
    setIsLanding(false);
    setGlobalError("");
  }

  function openLanding() {
    window.history.pushState({}, "", "/");
    setIsLanding(true);
    setGlobalError("");
  }

  async function signIn(username: string, password: string) {
    const signedIn = await postJson<User>("/api/auth/login", { username, password });
    setUser(signedIn);
    setPage("chat");
    setGlobalError("");
  }

  async function signOut() {
    setGlobalError("");
    try {
      await api("/api/auth/logout", { method: "POST" });
      setUser(null);
      setPage("chat");
    } catch (reason) {
      setGlobalError(messageOf(reason));
    }
  }

  if (isLanding) {
    return <LandingPage onNavigate={openWorkspace} isAdmin={user?.role === "admin"} />;
  }

  if (loading) {
    return <div className="full-loading"><Logo /><span>Opening your workspace…</span></div>;
  }
  if (!user) return <Login onLogin={signIn} />;

  const menu = user.role === "admin"
    ? [...navigation, { id: "admin" as const, label: "Administration", icon: ShieldCheck }, { id: "settings" as const, label: "Settings", icon: Settings }]
    : [...navigation, { id: "settings" as const, label: "Settings", icon: Settings }];
  const pageTitle = menu.find((item) => item.id === page)?.label ?? "Ask HR";

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <button className="brand sidebar-brand sidebar-brand-link" onClick={openLanding} aria-label="Return to PeopleDesk landing page">
          <Logo />
          <span>PeopleDesk</span>
        </button>
        <div className="workspace-label">WORKSPACE</div>
        <nav className="side-nav" aria-label="Main navigation">
          {menu.map(({ id, label, icon: Icon }) => (
            <button
              className={`nav-item${page === id ? " nav-active" : ""}`}
              key={id}
              onClick={() => {
                setPage(id);
                setGlobalError("");
              }}
            >
              <Icon size={18} strokeWidth={page === id ? 2.2 : 1.8} />
              <span>{label}</span>
              {page === id && <span className="nav-indicator" />}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="sidebar-help">
            <span className="help-icon"><CircleHelp size={17} /></span>
            <div><strong>Need a hand?</strong><span>Contact your HR team</span></div>
          </div>
          <div className="account-row">
            <span className="user-avatar">{user.username.slice(0, 1).toUpperCase()}</span>
            <div className="account-info"><strong>{user.username}</strong><span>{user.role}</span></div>
            {authenticationEnabled && (
              <button className="icon-button" aria-label="Sign out" onClick={() => void signOut()}><LogOut size={17} /></button>
            )}
          </div>
        </div>
      </aside>
      <main className="main-area">
        <header className="topbar">
          <div className="breadcrumb"><span>Workspace</span><span className="breadcrumb-divider">/</span><strong>{pageTitle}</strong></div>
          <div className="topbar-right">
            <Badge tone="green"><span className="status-dot" /> Connected</Badge>
            <span className="topbar-avatar">{user.username.slice(0, 1).toUpperCase()}</span>
          </div>
        </header>
        {globalError && <div className="notice notice-error global-error">{globalError}</div>}
        <div className={`page-content page-${page}`}>
          {page === "chat" && <Chat username={user.username} canUpload={user.role === "admin"} />}
          {page === "library" && <DocumentLibrary />}
          {page === "admin" && user.role === "admin" && <AdminPage />}
          {page === "settings" && <SettingsPage />}
        </div>
        <footer className="app-footer">
          <span><ShieldCheck size={14} /> Policy answers cite authorized documents; general guidance is labeled.</span>
          <span>PeopleDesk <span className="footer-dot">·</span> {user.role}</span>
        </footer>
      </main>
    </div>
  );
}

export default App;
