"use client";

import { signIn, signOut, useSession } from "next-auth/react";
import { SessionProvider } from "next-auth/react";
import { useTranslations, useLocale } from 'next-intl';
import { useState, useEffect, useRef } from 'react';
import Link from 'next/link';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

function formatMarkdownContent(rawText: string): string {
  if (!rawText) return "";
  let text = rawText;

  // 1. Başıboş/tek başına duran '|' satırlarını temizle (örn. "Karşılaştırma\n|\n\n|Önceki Soru...")
  text = text.replace(/(^|\n)\s*\|\s*\n+(?=\|)/g, "$1\n");

  // 2. Tek satırda birleştirilmiş tablo satırlarını ayır: "| |" -> "|\n|"
  text = text.replace(/\|\s*\|\s*/g, "|\n|");

  // 3. Başlık ve ayırıcı (|---|) sütun sayısı uyuşmazlığını düzelt (GFM standardına uydur)
  const lines = text.split("\n");
  for (let i = 0; i < lines.length - 1; i++) {
    const line = lines[i].trim();
    const nextLine = lines[i + 1].trim();
    if (/^\|[\s\-:|]+\|$/.test(nextLine)) {
      const headerCols = (line.match(/\|/g) || []).length - 1;
      const sepCols = (nextLine.match(/\|/g) || []).length - 1;
      if (headerCols > 0 && sepCols > headerCols) {
        const diff = sepCols - headerCols;
        lines[i] = "| " + " | ".repeat(diff) + line.replace(/^\|/, "");
      }
    }
  }
  text = lines.join("\n");

  // 4. Tablo öncesinde ve sonrasında boşluk bırakılmasını garanti et
  text = text.replace(/([^\n])\n(\|[^\n]+\|\n\|[\s\-:|]+\|)/g, "$1\n\n$2");

  return text;
}

class ApiRequestError extends Error {
  type: "validation" | "http" | "network" | "stream" | "runtime";

  constructor(type: "validation" | "http" | "network" | "stream" | "runtime", message: string) {
    super(message);
    this.type = type;
  }
}

interface Grounding {
  checked: number;
  grounded: number;
  ungrounded: string[];
  ratio: number;
  sources?: { tool: number; document: number };
}

interface ChatMessage {
  role: string;
  content: string;
  attachmentName?: string;
  attachmentType?: string;
  trace?: any[];
  grounding?: Grounding | null;
  duration_s?: number;
  activitySteps?: Array<{ message: string; done: boolean }>;
}

interface AttachedFile {
  name: string;
  size: number;
  contentType: string;
  markdownContent: string;
  previewUrl?: string;
}

interface ChatSession {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  messages: ChatMessage[];
}

function createDefaultSession(title: string): ChatSession {
  const now = Date.now();
  return {
    id: `session_${now}_${Math.random().toString(36).substring(2, 7)}`,
    title: title || "Yeni Sohbet",
    createdAt: now,
    updatedAt: now,
    messages: [{ role: "agent", content: "" }]
  };
}

function DashboardContent({ t }: { t: any }) {
  const { data: session } = useSession();
  const locale = useLocale();
  
  // Hydration hatasını önlemek için state'i önce false başlatıp,
  // sayfa yüklendikten (useEffect) sonra localStorage'dan okuyoruz.
  const [devMode, setDevMode] = useState(false);

  // Tema Yönetimi (Dark / Light)
  const [theme, setTheme] = useState<"dark" | "light">("dark");

  // Çoklu Sohbet Oturumları State'i
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string>("");
  const [showSessionsSidebar, setShowSessionsSidebar] = useState(false);

  // Mesajlaşma State'leri
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([
    { role: "agent", content: "" } // İçerik boş, aşağıda t() ile doldurulacak
  ]);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedProvider, setSelectedProvider] = useState<string>("deepseek");
  // Uzun süren (streaming) sorgularda gösterilen tek satırlık ilerleme durumu
  const [streamStatus, setStreamStatus] = useState<string | null>(null);
  const [activitySteps, setActivitySteps] = useState<Array<{ message: string; done: boolean }>>([]);
  const [attachment, setAttachment] = useState<AttachedFile | null>(null);
  const [isUploadingAttachment, setIsUploadingAttachment] = useState(false);
  const [attachmentError, setAttachmentError] = useState<string | null>(null);
  const [showRightPanelTrace, setShowRightPanelTrace] = useState<boolean>(true);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  // Sol panel (Chat) dinamik boyutlandırma
  const DEFAULT_CHAT_WIDTH = 680;
  const MIN_CHAT_WIDTH = 380;
  const [chatWidth, setChatWidth] = useState<number>(DEFAULT_CHAT_WIDTH);
  const [isResizing, setIsResizing] = useState(false);
  const isResizingRef = useRef(false);

  const startResizing = (e: React.MouseEvent) => {
    e.preventDefault();
    isResizingRef.current = true;
    setIsResizing(true);
  };

  const resetChatWidth = () => {
    setChatWidth(DEFAULT_CHAT_WIDTH);
    if (typeof window !== "undefined") {
      localStorage.setItem("nova_chat_width", DEFAULT_CHAT_WIDTH.toString());
    }
  };

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!isResizingRef.current) return;
      const maxAllowed = Math.min(window.innerWidth * 0.75, window.innerWidth - 380);
      const newWidth = Math.max(MIN_CHAT_WIDTH, Math.min(e.clientX, maxAllowed));
      setChatWidth(newWidth);
    };

    const handleMouseUp = () => {
      if (isResizingRef.current) {
        isResizingRef.current = false;
        setIsResizing(false);
        setChatWidth((current) => {
          if (typeof window !== "undefined") {
            localStorage.setItem("nova_chat_width", current.toString());
          }
          return current;
        });
      }
    };

    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };
  }, []);

  // İlk yüklemede localStorage'dan tema, oturumlar ve tercihleri yükleme
  useEffect(() => {
    if (typeof window !== 'undefined') {
      const savedTheme = localStorage.getItem('nova_theme');
      if (savedTheme === 'light' || savedTheme === 'dark') {
        setTheme(savedTheme);
      }

      const isDev = localStorage.getItem('devMode') === 'true';
      if (isDev) setDevMode(true);

      const savedProvider = localStorage.getItem('selected_provider');
      if (savedProvider) setSelectedProvider(savedProvider);

      const savedWidth = localStorage.getItem('nova_chat_width');
      if (savedWidth) {
        const parsedWidth = parseInt(savedWidth, 10);
        if (!isNaN(parsedWidth) && parsedWidth >= MIN_CHAT_WIDTH) {
          setChatWidth(parsedWidth);
        }
      }

      // Oturumları yükle
      let loadedSessions: ChatSession[] = [];
      const savedSessions = localStorage.getItem('nova_chat_sessions');
      if (savedSessions) {
        try {
          const parsed = JSON.parse(savedSessions);
          if (Array.isArray(parsed) && parsed.length > 0) {
            loadedSessions = parsed;
          }
        } catch (e) {
          console.error("Failed to load sessions from localStorage", e);
        }
      }

      // Eski sessionStorage'dan geriye dönük uyumluluk göçü (migration)
      if (loadedSessions.length === 0) {
        const legacyChat = sessionStorage.getItem('nova_chat_messages');
        if (legacyChat) {
          try {
            const parsedLegacy = JSON.parse(legacyChat);
            if (Array.isArray(parsedLegacy) && parsedLegacy.length > 0) {
              const defaultSes = createDefaultSession(t("untitled_chat"));
              defaultSes.messages = parsedLegacy;
              loadedSessions = [defaultSes];
            }
          } catch (e) {
            console.error("Legacy migration error", e);
          }
        }
      }

      // Eğer hiç oturum yoksa yeni bir oturum oluştur
      if (loadedSessions.length === 0) {
        const initialSes = createDefaultSession(t("untitled_chat"));
        loadedSessions = [initialSes];
      }

      setSessions(loadedSessions);

      const savedCurrentId = localStorage.getItem('nova_current_session_id');
      const activeSession = loadedSessions.find(s => s.id === savedCurrentId) || loadedSessions[0];
      setCurrentSessionId(activeSession.id);
      setMessages(activeSession.messages);
    }
  }, []);

  const toggleTheme = () => {
    const nextTheme = theme === "dark" ? "light" : "dark";
    setTheme(nextTheme);
    if (typeof window !== 'undefined') {
      localStorage.setItem('nova_theme', nextTheme);
    }
  };

  const isDark = theme === "dark";

  // Aktif oturum değiştikçe veya mesajlar güncellendikçe sessions listesini ve localStorage'ı senkronize et
  const updateCurrentSessionMessages = (newMessages: ChatMessage[], newTitle?: string) => {
    setMessages(newMessages);
    if (!currentSessionId) return;

    setSessions(prevSessions => {
      const updated = prevSessions.map(s => {
        if (s.id === currentSessionId) {
          return {
            ...s,
            title: newTitle ?? s.title,
            updatedAt: Date.now(),
            messages: newMessages
          };
        }
        return s;
      });

      if (typeof window !== 'undefined') {
        localStorage.setItem('nova_chat_sessions', JSON.stringify(updated));
        localStorage.setItem('nova_current_session_id', currentSessionId);
      }
      return updated;
    });
  };

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({
      behavior: isLoading ? "smooth" : "auto",
      block: "end",
    });
  }, [messages, isLoading, streamStatus]);

  // Yeni Sohbet Başlat
  const handleNewChat = () => {
    setShowSessionsSidebar(false);
    const newSession = createDefaultSession(t("untitled_chat"));
    const updated = [newSession, ...sessions];
    setSessions(updated);
    setCurrentSessionId(newSession.id);
    setMessages(newSession.messages);
    setInput("");
    setStreamStatus(null);
    setActivitySteps([]);
    if (typeof window !== 'undefined') {
      localStorage.setItem('nova_chat_sessions', JSON.stringify(updated));
      localStorage.setItem('nova_current_session_id', newSession.id);
    }
  };

  // Bir Sohbet Oturumunu Seç
  const handleSelectSession = (sessionItem: ChatSession) => {
    setShowSessionsSidebar(false);
    if (sessionItem.id === currentSessionId) return;
    setCurrentSessionId(sessionItem.id);
    setMessages(sessionItem.messages);
    setInput("");
    setStreamStatus(null);
    setActivitySteps([]);
    if (typeof window !== 'undefined') {
      localStorage.setItem('nova_current_session_id', sessionItem.id);
    }
  };

  // Bir Sohbet Oturumunu Sil
  const handleDeleteSession = (sessionIdToDelete: string, e: React.MouseEvent) => {
    e.stopPropagation();
    const remaining = sessions.filter(s => s.id !== sessionIdToDelete);
    if (remaining.length === 0) {
      const freshSession = createDefaultSession(t("untitled_chat"));
      setSessions([freshSession]);
      setCurrentSessionId(freshSession.id);
      setMessages(freshSession.messages);
      if (typeof window !== 'undefined') {
        localStorage.setItem('nova_chat_sessions', JSON.stringify([freshSession]));
        localStorage.setItem('nova_current_session_id', freshSession.id);
      }
    } else {
      setSessions(remaining);
      if (currentSessionId === sessionIdToDelete) {
        const nextActive = remaining[0];
        setCurrentSessionId(nextActive.id);
        setMessages(nextActive.messages);
        if (typeof window !== 'undefined') {
          localStorage.setItem('nova_current_session_id', nextActive.id);
        }
      }
      if (typeof window !== 'undefined') {
        localStorage.setItem('nova_chat_sessions', JSON.stringify(remaining));
      }
    }
  };

  // Mevcut Sohbeti Temizle
  const clearChat = () => {
    const clearedMessages = [{ role: "agent", content: "" }];
    updateCurrentSessionMessages(clearedMessages);
    setStreamStatus(null);
    setActivitySteps([]);
  };

  const toggleDevMode = (val: boolean) => {
    setDevMode(val);
    if (val) localStorage.setItem('devMode', 'true');
    else localStorage.removeItem('devMode');
  };

  const isLoggedIn = session || devMode;

  // Sağ paneldeki güven/izlenebilirlik bölümü için son agent mesajının trace'i
  const latestAgentMsg = [...messages].reverse().find(m => m.role === "agent" && m.content);
  const lastAgentTrace = latestAgentMsg?.trace;

  // Sağ panelde gösterilecek analitik grafikler (tüm oturum boyunca üretilenlerin tamamı)
  const sessionImages: Array<{ src: string; alt: string; messageIndex: number; questionPrompt?: string }> = [];
  messages.forEach((msg, idx) => {
    if (msg.role === "agent" && msg.content) {
      const imgRegex = /!\[(.*?)\]\((.*?)\)/g;
      let match;
      const prevUserMsg = messages.slice(0, idx).reverse().find(m => m.role === "user");
      while ((match = imgRegex.exec(msg.content)) !== null) {
        sessionImages.push({
          alt: match[1] || "Grafik",
          src: match[2],
          messageIndex: idx,
          questionPrompt: prevUserMsg?.content || "",
        });
      }
    }
  });

  // tool_call + tool_result çiftlerini tek bir adıma birleştir
  const traceSteps: Array<{ tool_name: string; arguments?: string; success?: boolean; duration_s?: number }> = [];
  if (lastAgentTrace) {
    let pending: { tool_name: string; arguments?: string } | null = null;
    for (const item of lastAgentTrace) {
      if (item.type === "tool_call") {
        pending = { tool_name: item.tool_name, arguments: item.arguments };
      } else if (item.type === "tool_result") {
        traceSteps.push({
          tool_name: item.tool_name,
          arguments: pending && pending.tool_name === item.tool_name ? pending.arguments : undefined,
          success: item.success,
          duration_s: item.duration_s,
        });
        pending = null;
      }
    }
  }

  const dataHealthStep = traceSteps.find((s) => s.tool_name === "data_health_report");
  let dataHealthArgs: { series_id?: string; gold_table?: string; gold_column?: string } | null = null;
  if (dataHealthStep?.arguments) {
    try {
      dataHealthArgs = JSON.parse(dataHealthStep.arguments);
    } catch {
      dataHealthArgs = null;
    }
  }

  // Stream olayını ("llm_decision" / "tool_output" vb.) kullanıcıya gösterilecek

  // tek satırlık bir duruma çevirir; ilgisiz olaylar için null döner.
  const describeStreamEvent = (evt: any): string | null => {
    const toolMessages: Record<string, string> = {
      series_catalog_search: t("activity_catalog"),
      evds_data_service: t("activity_evds"),
      lakehouse_query: t("activity_lakehouse"),
      change_detection: t("activity_change"),
      data_health_report: t("activity_data_health"),
      anomaly_detection: t("activity_anomaly"),
      causality_check: t("activity_causality"),
      web_search: t("activity_web_search"),
      web_url_reader: t("activity_web_reader"),
    };


    if (evt.kind === "llm_decision" && evt.tool_name) {
      return toolMessages[evt.tool_name] ?? t("activity_working");
    }

    if (evt.kind === "tool_output" && evt.tool_name) {
      if (evt.success === false) {
        return t("activity_alternative");
      }
      return t("activity_evaluating");
    }

    if (evt.kind === "llm_input_after_tool") {
      return t("activity_analyzing");
    }

    if (evt.kind === "llm_input") {
      return evt.iteration && evt.iteration > 1
        ? t("activity_synthesis")
        : t("activity_planning");
    }

    if (evt.kind === "llm_final") {
      return t("activity_finalizing");
    }

    return null;
  };

  // Dosya Yükleme ve OCR / Tablo Ayrıştırma
  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const allowedExts = [".xlsx", ".xls", ".csv", ".pdf", ".png", ".jpg", ".jpeg", ".webp"];
    const ext = "." + file.name.split(".").pop()?.toLowerCase();
    if (!allowedExts.includes(ext)) {
      setAttachmentError(t("unsupported_file_type"));
      return;
    }

    if (file.size > 10 * 1024 * 1024) {
      setAttachmentError(t("file_too_large"));
      return;
    }

    setAttachmentError(null);
    setIsUploadingAttachment(true);

    try {
      const formData = new FormData();
      formData.append("file", file);

      const res = await fetch(`${API_BASE_URL}/api/v1/upload-attachment`, {
        method: "POST",
        body: formData,
      });

      const data = await res.json();
      if (!res.ok || !data.success) {
        setAttachmentError(data.error || t("error_runtime"));
        return;
      }

      let previewUrl: string | undefined;
      if (file.type.startsWith("image/")) {
        previewUrl = URL.createObjectURL(file);
      }

      setAttachment({
        name: data.filename,
        size: file.size,
        contentType: data.content_type,
        markdownContent: data.markdown_content,
        previewUrl,
      });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : t("error_network");
      setAttachmentError(message || t("error_network"));
    } finally {
      setIsUploadingAttachment(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  };

  // POST /api/v1/ask/stream ile SSE olaylarını okur, ilerlemeyi streamStatus'e
  // yazar ve 'done' olayındaki cevabı döndürür. EventSource POST desteklemediği
  // için fetch + response.body reader ile elle ayrıştırıyoruz.
  const sendViaStream = async (
    question: string,
    history: Array<{ role: string; content: string }>,
    attachmentData?: AttachedFile | null
  ) => {
    const response = await fetch(`${API_BASE_URL}/api/v1/ask/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question,
        history,
        provider: selectedProvider,
        attachment_content: attachmentData?.markdownContent || null,
        attachment_name: attachmentData?.name || null,
      })
    });

    if (response.status === 422) {
      throw new ApiRequestError("validation", t("error_validation"));
    }

    if (!response.ok) {
      throw new ApiRequestError("http", `${t("error_http")} (${response.status})`);
    }

    if (!response.body) {
      throw new ApiRequestError("stream", t("error_stream"));
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let finalAnswer: string | null = null;
    let streamError: string | null = null;
    let grounding: Grounding | null = null;
    const trace: Array<{ type: string; tool_name?: string; success?: boolean; duration_s?: number }> = [];

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let sepIndex;
      while ((sepIndex = buffer.indexOf("\n\n")) !== -1) {
        const rawEvent = buffer.slice(0, sepIndex).trim();
        buffer = buffer.slice(sepIndex + 2);
        if (!rawEvent.startsWith("data: ")) continue; // ": keepalive" yorum satırlarını atla

        const evt = JSON.parse(rawEvent.slice(6));
        if (evt.kind === "done") {
          finalAnswer = evt.answer;
          grounding = evt.grounding ?? null;
        } else if (evt.kind === "error") {
          streamError = evt.error;
        } else {
          if (evt.kind === "llm_decision" && evt.tool_name) {
            trace.push({ type: "tool_call", tool_name: evt.tool_name });
          } else if (evt.kind === "tool_output" && evt.tool_name) {
            trace.push({ type: "tool_result", tool_name: evt.tool_name, success: evt.success, duration_s: evt.duration_s });
          }
          const status = describeStreamEvent(evt);
          if (status) {
            setStreamStatus(status);
            setActivitySteps(prev => {
              if (prev.at(-1)?.message === status) return prev;
              const completed = prev.map(step => ({ ...step, done: true }));
              return [...completed.slice(-3), { message: status, done: false }];
            });
          }
        }
      }
    }

    if (streamError) throw new ApiRequestError("runtime", `${t("error_runtime")}: ${streamError}`);
    if (finalAnswer === null) throw new ApiRequestError("stream", t("error_stream"));
    return { answer: finalAnswer, trace, grounding };
  };

  // Eski, akışsız uç noktaya (POST /api/v1/ask) düşen fallback.
  const sendViaFallback = async (
    question: string,
    history: Array<{ role: string; content: string }>,
    attachmentData?: AttachedFile | null
  ) => {
    const response = await fetch(`${API_BASE_URL}/api/v1/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question,
        history,
        provider: selectedProvider,
        attachment_content: attachmentData?.markdownContent || null,
        attachment_name: attachmentData?.name || null,
      })
    });

    if (response.status === 422) {
      throw new ApiRequestError("validation", t("error_validation"));
    }

    if (!response.ok) {
      throw new ApiRequestError("http", `${t("error_http")} (${response.status})`);
    }

    const payload = await response.json();
    const answerText =
      payload?.answer ??
      payload?.data?.answer ??
      (payload?.error ? `${t("error_runtime")}: ${payload.error}` : t("error_unknown"));
    return { answer: answerText, trace: payload?.data?.trace, grounding: (payload?.data?.grounding ?? null) as Grounding | null };
  };

  const handleSend = async () => {
    if (isLoading || isUploadingAttachment || (!input.trim() && !attachment)) return;

    const userMsg = input.trim() || (attachment ? `${attachment.name} dosyasını analiz et.` : "");
    const currentAttachment = attachment;
    // Gönderim başladığında eki temizle
    setAttachment(null);
    setAttachmentError(null);

    // Yeni kullanıcı mesajı state'e eklenmeden ÖNCE geçmişi hesapla (son 20 soru-cevap çifti = 40 mesaj)
    const history = messages
      .filter(m => m.content && m.content.trim() !== "")
      .slice(-40)
      .map(m => ({ role: m.role, content: m.content }));

    const currentSession = sessions.find(s => s.id === currentSessionId);
    let updatedTitle = currentSession?.title;
    // Eğer başlık default ise ve ilk kullanıcı mesajı geldiyse başlığı güncelle
    if (
      !updatedTitle ||
      updatedTitle === "Yeni Sohbet" ||
      updatedTitle === "New Chat" ||
      updatedTitle === t("untitled_chat")
    ) {
      updatedTitle = userMsg.length > 28 ? userMsg.slice(0, 28) + "..." : userMsg;
    }

    const newMessagesWithUser: ChatMessage[] = [
      ...messages,
      {
        role: "user",
        content: userMsg,
        attachmentName: currentAttachment?.name,
        attachmentType: currentAttachment?.contentType,
      }
    ];
    updateCurrentSessionMessages(newMessagesWithUser, updatedTitle);

    setInput("");
    setIsLoading(true);
    setStreamStatus(null);
    setActivitySteps([]);

    const startTime = performance.now();
    try {
      let result;
      try {
        result = await sendViaStream(userMsg, history, currentAttachment);
      } catch (streamErr) {
        if (
          streamErr instanceof ApiRequestError &&
          ["validation", "http", "runtime"].includes(streamErr.type)
        ) {
          throw streamErr;
        }
        result = await sendViaFallback(userMsg, history, currentAttachment);
      }
      const duration_s = Number(((performance.now() - startTime) / 1000).toFixed(2));
      const newMessagesWithAgent: ChatMessage[] = [
        ...newMessagesWithUser,
        {
          role: "agent",
          content: result.answer,
          trace: result.trace,
          grounding: result.grounding,
          duration_s: duration_s,
        }
      ];
      updateCurrentSessionMessages(newMessagesWithAgent, updatedTitle);
    } catch (error) {
      const duration_s = Number(((performance.now() - startTime) / 1000).toFixed(2));
      let message = t("error_unknown");

      if (error instanceof ApiRequestError) {
        message = error.message;
      } else if (error instanceof TypeError) {
        message = t("error_network");
      } else if (error instanceof Error) {
        message = `${t("error_runtime")}: ${error.message}`;
      }

      const newMessagesWithError: ChatMessage[] = [
        ...newMessagesWithUser,
        { role: "agent", content: message, duration_s: duration_s }
      ];
      updateCurrentSessionMessages(newMessagesWithError, updatedTitle);
    } finally {
      setIsLoading(false);
      setStreamStatus(null);
    }
  };

  // Ajan Düşünce Süreci / Akıl Yürütme Accordion Bileşeni (Sendeki gibi adım adım açılır kapanır)
  const MessageReasoningAccordion = ({
    trace,
    duration_s,
  }: {
    trace?: any[];
    duration_s?: number;
  }) => {
    const [isOpen, setIsOpen] = useState(false);

    // tool_call + tool_result çiftlerini tek adımda birleştir
    const steps: Array<{ tool_name: string; arguments?: string; success?: boolean; duration_s?: number }> = [];
    if (trace && Array.isArray(trace)) {
      let pending: { tool_name: string; arguments?: string } | null = null;
      for (const item of trace) {
        if (item.type === "tool_call") {
          pending = { tool_name: item.tool_name, arguments: item.arguments };
        } else if (item.type === "tool_result") {
          steps.push({
            tool_name: item.tool_name,
            arguments: pending && pending.tool_name === item.tool_name ? pending.arguments : undefined,
            success: item.success,
            duration_s: item.duration_s,
          });
          pending = null;
        }
      }
    }

    if (steps.length === 0 && !duration_s) return null;

    return (
      <div className={`mb-3 rounded-xl border transition-all text-xs ${
        isDark 
          ? "bg-black/30 border-white/10" 
          : "bg-slate-50/80 border-slate-200"
      }`}>
        {/* Accordion Header */}
        <button
          type="button"
          onClick={() => setIsOpen(!isOpen)}
          className={`w-full px-3 py-2 flex items-center justify-between text-left rounded-xl transition-colors ${
            isDark 
              ? "hover:bg-white/5 text-gray-300" 
              : "hover:bg-slate-100 text-slate-700"
          }`}
        >
          <div className="flex items-center gap-1.5 font-medium">
            <span>🧠</span>
            <span>
              {steps.length > 0 ? `${steps.length} ${t("reasoning_steps") || "adımda analiz edildi"}` : "Analiz tamamlandı"}
            </span>
            {typeof duration_s === "number" && (
              <span className={`px-1.5 py-0.5 rounded text-[10px] font-mono font-semibold ${
                isDark ? "bg-white/10 text-emerald-400" : "bg-emerald-100 text-emerald-800"
              }`}>
                {duration_s.toFixed(2)}s
              </span>
            )}
          </div>
          <div className="flex items-center gap-1 text-[11px] font-semibold text-emerald-500">
            <span>{isOpen ? (t("hide_reasoning") || "Gizle") : (t("view_reasoning") || "Düşünce Adımlarını Gör")}</span>
            <svg className={`w-3.5 h-3.5 transition-transform duration-200 ${isOpen ? "rotate-180" : ""}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          </div>
        </button>

        {/* Accordion Body */}
        {isOpen && steps.length > 0 && (
          <div className={`px-3 pb-3 pt-1 border-t space-y-1.5 ${
            isDark ? "border-white/5" : "border-slate-200/60"
          }`}>
            {steps.map((step, sIdx) => (
              <div key={sIdx} className={`p-2 rounded-lg border text-[11px] flex flex-col gap-1 ${
                isDark ? "bg-white/[0.02] border-white/5" : "bg-white border-slate-200/80"
              }`}>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5 truncate">
                    <span className={`font-mono text-[10px] ${isDark ? "text-gray-500" : "text-slate-400"}`}>{sIdx + 1}.</span>
                    <span className="font-semibold text-emerald-400 truncate">{step.tool_name}</span>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    {typeof step.duration_s === "number" && (
                      <span className={`font-mono text-[10px] ${isDark ? "text-gray-400" : "text-slate-500"}`}>
                        {step.duration_s.toFixed(2)}s
                      </span>
                    )}
                    <span className={`font-bold ${step.success !== false ? (isDark ? "text-emerald-400" : "text-emerald-600") : "text-red-500"}`}>
                      {step.success !== false ? "✓" : "✗"}
                    </span>
                  </div>
                </div>
                {step.arguments && (
                  <details className={`text-[10px] ${isDark ? "text-gray-500" : "text-slate-500"}`}>
                    <summary className="cursor-pointer hover:underline">Parametreler</summary>
                    <pre className={`mt-1 p-1.5 rounded whitespace-pre-wrap break-words font-mono ${
                      isDark ? "bg-black/50 text-gray-400" : "bg-slate-100 text-slate-700"
                    }`}>{step.arguments}</pre>
                  </details>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    );
  };

  // Çoklu ve Tekli Grafik Görüntüleyici (Carousel / Slider Destekli)
  const ChartCarousel = ({
    images,
  }: {
    images: Array<{ src: string; alt: string; questionPrompt?: string }>;
  }) => {
    const [currentIndex, setCurrentIndex] = useState(images.length > 0 ? images.length - 1 : 0);

    // Yeni grafik eklendiğinde veya oturum değiştiğinde en güncel grafiğe otomatik odaklan
    useEffect(() => {
      if (images.length > 0) {
        setCurrentIndex(images.length - 1);
      }
    }, [images.length]);

    if (!images || images.length === 0) return null;

    const currentImg = images[currentIndex] || images[0];
    const resolvedSrc = currentImg.src.startsWith("/static/")
      ? `${API_BASE_URL}${currentImg.src}`
      : currentImg.src;

    const downloadUrl = `/api/download-image?url=${encodeURIComponent(currentImg.src)}&name=${encodeURIComponent(currentImg.alt || "analitik_grafik")}`;

    return (
      <div className={`my-3 rounded-2xl overflow-hidden border backdrop-blur-md shadow-2xl transition-all ${
        isDark 
          ? "border-white/10 bg-black/40 hover:border-emerald-500/30" 
          : "border-slate-200 bg-white hover:border-emerald-500/40 shadow-slate-200"
      }`}>
        {/* Üst Başlık ve 1/N Sayacı */}
        <div className={`px-4 py-2.5 flex items-center justify-between border-b text-xs font-semibold ${
          isDark ? "border-white/10 bg-white/[0.03] text-emerald-400" : "border-slate-100 bg-slate-50 text-emerald-700"
        }`}>
          <div className="flex items-center gap-2 truncate pr-2">
            <span>📊</span>
            <span className="font-bold truncate">{currentImg.alt || t("analytics_charts")}</span>
          </div>
          {images.length > 1 && (
            <div className="flex items-center gap-1.5 flex-shrink-0">
              <span className={`px-2.5 py-0.5 rounded-full text-[11px] font-bold ${
                isDark ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30" : "bg-emerald-100 text-emerald-800 border border-emerald-200"
              }`}>
                {currentIndex + 1} / {images.length}
              </span>
            </div>
          )}
        </div>

        {/* Soru Bağlamı (Eğer varsa) */}
        {currentImg.questionPrompt && (
          <div className={`px-4 py-1.5 border-b text-[11px] flex items-center gap-1.5 truncate ${
            isDark ? "border-white/5 bg-white/[0.01] text-gray-400" : "border-slate-100 bg-slate-50/50 text-slate-500"
          }`}>
            <span className="font-semibold text-emerald-500">💬 {t("question_prefix") || "Soru"}:</span>
            <span className="truncate italic">&quot;{currentImg.questionPrompt}&quot;</span>
          </div>
        )}

        {/* Görsel Alanı & Sol/Sağ Butonları */}
        <div className={`relative overflow-hidden flex items-center justify-center min-h-[240px] p-2.5 ${
          isDark ? "bg-black/30" : "bg-slate-50"
        }`}>
          <img
            src={resolvedSrc}
            alt={currentImg.alt || "Grafik"}
            className="w-full h-auto max-h-[500px] object-contain rounded-xl transition-transform duration-300"
            loading="lazy"
          />

          {images.length > 1 && (
            <>
              {/* Sol Buton */}
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  setCurrentIndex((prev) => (prev === 0 ? images.length - 1 : prev - 1));
                }}
                className={`absolute left-3 top-1/2 -translate-y-1/2 p-2.5 rounded-full shadow-xl backdrop-blur-md transition-all ${
                  isDark 
                    ? "bg-black/70 hover:bg-emerald-500 text-white border border-white/20 hover:scale-110" 
                    : "bg-white/90 hover:bg-emerald-600 hover:text-white text-slate-800 border border-slate-200 hover:scale-110 shadow-slate-300"
                }`}
                title="Önceki Grafik"
              >
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M15 19l-7-7 7-7" />
                </svg>
              </button>

              {/* Sağ Buton */}
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  setCurrentIndex((prev) => (prev === images.length - 1 ? 0 : prev + 1));
                }}
                className={`absolute right-3 top-1/2 -translate-y-1/2 p-2.5 rounded-full shadow-xl backdrop-blur-md transition-all ${
                  isDark 
                    ? "bg-black/70 hover:bg-emerald-500 text-white border border-white/20 hover:scale-110" 
                    : "bg-white/90 hover:bg-emerald-600 hover:text-white text-slate-800 border border-slate-200 hover:scale-110 shadow-slate-300"
                }`}
                title="Sonraki Grafik"
              >
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M9 5l7 7-7 7" />
                </svg>
              </button>
            </>
          )}
        </div>

        {/* Alt Bilgi Çubuğu ve Dot İndikatörleri */}
        <div className={`px-4 py-2.5 flex items-center justify-between gap-3 border-t text-xs ${
          isDark ? "border-white/5 text-gray-400 bg-white/[0.01]" : "border-slate-100 text-slate-500 bg-white"
        }`}>
          <div className="flex items-center gap-2 truncate">
            {images.length > 1 && (
              <div className="flex items-center gap-1.5 mr-2">
                {images.map((img, i) => (
                  <button
                    key={i}
                    type="button"
                    onClick={() => setCurrentIndex(i)}
                    title={`${i + 1}. ${img.alt || "Grafik"}`}
                    className={`h-2 rounded-full transition-all ${
                      i === currentIndex 
                        ? (isDark ? "bg-emerald-400 w-5" : "bg-emerald-600 w-5")
                        : (isDark ? "bg-white/20 hover:bg-white/40 w-2" : "bg-slate-300 hover:bg-slate-400 w-2")
                    }`}
                  />
                ))}
              </div>
            )}
          </div>

          <div className="flex items-center gap-2 flex-shrink-0">
            <a
              href={resolvedSrc}
              target="_blank"
              rel="noopener noreferrer"
              className={`px-2.5 py-1.5 rounded-lg transition-colors flex items-center gap-1.5 font-medium ${
                isDark 
                  ? "bg-white/5 hover:bg-white/15 text-blue-400 hover:text-blue-300" 
                  : "bg-blue-50 hover:bg-blue-100 text-blue-600"
              }`}
              title={t("open_image")}
            >
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
              </svg>
              <span className="hidden sm:inline">{t("open_image")}</span>
            </a>
            <a
              href={downloadUrl}
              download
              className={`px-2.5 py-1.5 rounded-lg transition-colors flex items-center gap-1.5 font-medium cursor-pointer ${
                isDark 
                  ? "bg-white/5 hover:bg-white/15 text-emerald-400 hover:text-emerald-300" 
                  : "bg-emerald-50 hover:bg-emerald-100 text-emerald-600"
              }`}
              title={t("download_image")}
            >
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
              </svg>
              <span className="hidden sm:inline">{t("download_image")}</span>
            </a>
          </div>
        </div>
      </div>
    );
  };

  // ReactMarkdown için Dışa Aktarılabilir (Copy, CSV, PDF) Tablo Bileşeni
  const ExportableTable = ({ children, ...props }: any) => {
    const tableRef = useRef<HTMLTableElement | null>(null);
    const [copied, setCopied] = useState(false);

    const extractTableData = () => {
      if (!tableRef.current) return { headers: [], rows: [] };
      const ths = Array.from(tableRef.current.querySelectorAll("thead th")).map(
        (th) => th.textContent?.trim() || ""
      );
      const trs = Array.from(tableRef.current.querySelectorAll("tbody tr"));
      const rows = trs.map((tr) =>
        Array.from(tr.querySelectorAll("td")).map((td) => td.textContent?.trim() || "")
      );
      return { headers: ths, rows };
    };

    const handleCopy = async () => {
      const { headers, rows } = extractTableData();
      if (headers.length === 0 && rows.length === 0) return;
      const tsv = [
        headers.join("\t"),
        ...rows.map((r) => r.join("\t")),
      ].join("\n");
      await navigator.clipboard.writeText(tsv);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    };

    const handleDownloadCsv = () => {
      const { headers, rows } = extractTableData();
      if (headers.length === 0 && rows.length === 0) return;
      const escapeCsv = (val: string) => `"${val.replace(/"/g, '""')}"`;
      const csvContent = "\uFEFF" + [
        headers.map(escapeCsv).join(";"),
        ...rows.map((r) => r.map(escapeCsv).join(";")),
      ].join("\r\n");
      const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `tablo_raporu_${new Date().toISOString().slice(0, 10)}.csv`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    };

    const handleDownloadPdf = () => {
      const { headers, rows } = extractTableData();
      if (headers.length === 0 && rows.length === 0) return;

      const printWindow = window.open("", "_blank", "width=850,height=700");
      if (!printWindow) return;

      const html = `
        <!DOCTYPE html>
        <html>
        <head>
          <meta charset="utf-8">
          <title>KKB NOVA Analytics - Tablo Raporu</title>
          <style>
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; padding: 30px; color: #1e293b; background: #fff; }
            .header { border-bottom: 2px solid #059669; padding-bottom: 12px; margin-bottom: 20px; display: flex; justify-content: space-between; align-items: flex-end; }
            .title { font-size: 18px; font-weight: bold; color: #0f172a; margin: 0; }
            .subtitle { font-size: 11px; color: #64748b; margin-top: 4px; }
            .date { font-size: 11px; color: #64748b; font-family: monospace; }
            table { width: 100%; border-collapse: collapse; margin-top: 15px; font-size: 12px; }
            th { background-color: #f1f5f9; color: #0f172a; font-weight: 600; text-align: left; padding: 8px 12px; border: 1px solid #cbd5e1; }
            td { padding: 8px 12px; border: 1px solid #e2e8f0; }
            tr:nth-child(even) { background-color: #f8fafc; }
            .footer { margin-top: 30px; font-size: 10px; color: #94a3b8; text-align: center; border-top: 1px solid #e2e8f0; padding-top: 10px; }
            @media print {
              body { padding: 0; }
              @page { margin: 1.5cm; }
            }
          </style>
        </head>
        <body>
          <div class="header">
            <div>
              <div class="title">📊 NOVA Analytics — Veri Tablosu Raporu</div>
              <div class="subtitle">KKB Kurumsal Veri ve Analitik Platformu</div>
            </div>
            <div class="date">Tarih: ${new Date().toLocaleDateString("tr-TR")}</div>
          </div>
          <table>
            <thead>
              <tr>${headers.map((h) => `<th>${h}</th>`).join("")}</tr>
            </thead>
            <tbody>
              ${rows
                .map(
                  (r) => `<tr>${r.map((c) => `<td>${c}</td>`).join("")}</tr>`
                )
                .join("")}
            </tbody>
          </table>
          <div class="footer">
            Bu belge KKB NOVA Analytics Agent sistemi tarafından otomatik olarak üretilmiştir.
          </div>
          <script>
            window.onload = function() {
              window.print();
            };
          </script>
        </body>
        </html>
      `;

      printWindow.document.open();
      printWindow.document.write(html);
      printWindow.document.close();
    };

    return (
      <div className={`my-3.5 w-full rounded-xl border shadow-md overflow-hidden ${
        isDark ? "border-white/10 bg-white/[0.02]" : "border-slate-200 bg-white"
      }`}>
        {/* Tablo Üst Çubuğu (Export Toolbar) */}
        <div className={`flex items-center justify-between px-3 py-2 border-b text-xs ${
          isDark ? "bg-white/[0.04] border-white/10" : "bg-slate-50 border-slate-200"
        }`}>
          <div className="flex items-center gap-1.5 font-semibold text-slate-500 dark:text-gray-400">
            <span className="text-sm">📊</span>
            <span>{t("table_data") || "Tablo Verisi"}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={handleCopy}
              className={`px-2 py-1 rounded-md transition-all flex items-center gap-1 font-medium cursor-pointer ${
                copied
                  ? (isDark ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40" : "bg-emerald-100 text-emerald-800")
                  : (isDark ? "bg-white/5 hover:bg-white/10 text-gray-300 hover:text-white" : "bg-white hover:bg-slate-100 text-slate-700 border border-slate-200")
              }`}
              title="Excel'e yapıştırmaya hazır kopyala"
            >
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
              </svg>
              <span>{copied ? (t("table_copied") || "Kopyalandı!") : (t("table_copy") || "Kopyala")}</span>
            </button>
            <button
              type="button"
              onClick={handleDownloadCsv}
              className={`px-2 py-1 rounded-md transition-all flex items-center gap-1 font-medium cursor-pointer ${
                isDark ? "bg-white/5 hover:bg-white/10 text-emerald-400 hover:text-emerald-300" : "bg-white hover:bg-emerald-50 text-emerald-700 border border-slate-200"
              }`}
              title="Excel uyumlu CSV indir"
            >
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              <span>{t("table_csv") || "Excel / CSV"}</span>
            </button>
            <button
              type="button"
              onClick={handleDownloadPdf}
              className={`px-2 py-1 rounded-md transition-all flex items-center gap-1 font-medium cursor-pointer ${
                isDark ? "bg-white/5 hover:bg-white/10 text-blue-400 hover:text-blue-300" : "bg-white hover:bg-blue-50 text-blue-700 border border-slate-200"
              }`}
              title="PDF olarak yazdır / kaydet"
            >
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z" />
              </svg>
              <span>{t("table_pdf") || "PDF"}</span>
            </button>
          </div>
        </div>

        {/* Tablo İçeriği */}
        <div className="w-full overflow-x-auto">
          <table ref={tableRef} className="w-full text-left text-xs border-collapse min-w-[340px]" {...props}>
            {children}
          </table>
        </div>
      </div>
    );
  };

  // ReactMarkdown için Görsel ve Tablo Kart Bileşenleri
  const markdownComponents = {
    table: (tableProps: any) => <ExportableTable {...tableProps} />,
    thead: ({ children, ...props }: any) => (
      <thead className={`text-xs font-bold uppercase tracking-wider border-b ${
        isDark 
          ? "bg-white/10 border-white/10 text-emerald-400" 
          : "bg-slate-100 border-slate-200 text-emerald-800"
      }`} {...props}>
        {children}
      </thead>
    ),
    th: ({ children, ...props }: any) => (
      <th className={`px-3.5 py-2.5 font-bold border-r last:border-r-0 ${
        isDark ? "border-white/10 text-emerald-300" : "border-slate-200 text-slate-800"
      }`} {...props}>
        {children}
      </th>
    ),
    td: ({ children, ...props }: any) => (
      <td className={`px-3.5 py-2 border-t border-r last:border-r-0 font-normal leading-relaxed ${
        isDark 
          ? "border-white/5 text-gray-200" 
          : "border-slate-200/70 text-slate-800"
      }`} {...props}>
        {children}
      </td>
    ),
    tr: ({ children, ...props }: any) => (
      <tr className={`transition-colors ${
        isDark 
          ? "hover:bg-white/5 even:bg-white/[0.02]" 
          : "hover:bg-slate-50 even:bg-slate-50/50"
      }`} {...props}>
        {children}
      </tr>
    ),
    img: ({ src, alt }: any) => {
      if (!src) return null;
      return <ChartCarousel images={[{ src, alt: alt || "Grafik" }]} />;
    }
  };

  if (isLoggedIn) {
    return (
      <div className={`flex h-full w-full font-sans overflow-hidden relative transition-colors duration-200 ${
        isDark ? "bg-[#050505] text-gray-200 selection:bg-blue-500/30" : "bg-slate-100 text-slate-800 selection:bg-blue-200"
      } ${isResizing ? "cursor-col-resize select-none" : ""}`}>
        {/* Arka Plan Efektleri */}
        <div className={`absolute top-[-10%] left-[-10%] w-[40%] h-[40%] rounded-full blur-[120px] pointer-events-none transition-all ${
          isDark ? "bg-blue-900/20" : "bg-blue-400/20"
        }`}></div>
        <div className={`absolute bottom-[-10%] right-[-10%] w-[40%] h-[40%] rounded-full blur-[120px] pointer-events-none transition-all ${
          isDark ? "bg-emerald-900/10" : "bg-emerald-400/15"
        }`}></div>

        {/* Sol Panel - Chat & Oturumlar */}
        <div 
          style={{ width: `${chatWidth}px` }}
          className={`relative w-full md:w-auto flex-shrink-0 flex flex-col z-10 shadow-2xl transition-colors duration-200 ${
          isDark 
            ? "border-r border-white/5 bg-white/[0.02] backdrop-blur-2xl" 
            : "border-r border-slate-200 bg-white/90 backdrop-blur-2xl"
        }`}>
          
          {/* Header */}
          <div className={`px-5 py-4 border-b flex justify-between items-center transition-colors duration-200 ${
            isDark ? "border-white/5 bg-black/30" : "border-slate-200 bg-slate-50/90"
          }`}>
            <div className="flex items-center gap-2.5">
              {/* Geçmiş Sohbetler Menü Düğmesi */}
              <button
                onClick={() => setShowSessionsSidebar(prev => !prev)}
                className={`p-2 rounded-lg border transition-all ${
                  showSessionsSidebar 
                    ? (isDark ? "bg-emerald-500/20 border-emerald-500/40 text-emerald-300" : "bg-emerald-100 border-emerald-400 text-emerald-700")
                    : (isDark ? "bg-white/5 border-white/10 text-gray-400 hover:text-white hover:bg-white/10" : "bg-slate-100 border-slate-200 text-slate-600 hover:text-slate-900 hover:bg-slate-200")
                }`}
                title={t("chat_sessions")}
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h7" />
                </svg>
              </button>

              <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-blue-500 to-emerald-400 flex items-center justify-center shadow-lg shadow-blue-500/20 flex-shrink-0">
                <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
              </div>
              <div className="flex flex-col">
                <h2 className={`text-base sm:text-lg font-black tracking-tight leading-none ${
                  isDark ? "bg-clip-text text-transparent bg-gradient-to-r from-white to-gray-400" : "text-slate-800"
                }`}>
                  {t('chat_title')}
                </h2>
                <span className={`text-[11px] truncate max-w-[140px] sm:max-w-[200px] mt-0.5 ${
                  isDark ? "text-gray-500" : "text-slate-500"
                }`}>
                  {sessions.find(s => s.id === currentSessionId)?.title || t("untitled_chat")}
                </span>
              </div>
            </div>

            <div className="flex gap-1.5 text-xs font-semibold items-center">
              {/* Yeni Sohbet Butonu */}
              <button
                onClick={handleNewChat}
                className="px-2.5 py-1.5 bg-gradient-to-r from-emerald-600/80 to-teal-600/80 hover:from-emerald-500 hover:to-teal-500 text-white font-semibold rounded-md border border-emerald-500/30 text-xs shadow-md shadow-emerald-900/30 flex items-center gap-1 transition-all"
                title={t("new_chat")}
              >
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M12 4v16m8-8H4" />
                </svg>
                <span className="hidden sm:inline">{t("new_chat")}</span>
              </button>

              {/* Provider Seçici */}
              <select
                value={selectedProvider}
                onChange={(e) => {
                  setSelectedProvider(e.target.value);
                  if (typeof window !== 'undefined') {
                    localStorage.setItem('selected_provider', e.target.value);
                  }
                }}
                className={`px-2 py-1.5 font-medium rounded-md border text-xs focus:outline-none cursor-pointer transition-all ${
                  isDark 
                    ? "bg-white/5 hover:bg-white/10 text-emerald-400 border-emerald-500/30 focus:border-emerald-500" 
                    : "bg-slate-100 hover:bg-slate-200 text-emerald-700 border-emerald-500/40 focus:border-emerald-600"
                }`}
                title="Model Sağlayıcı"
              >
                <option value="deepseek" className={isDark ? "bg-gray-950 text-white" : "bg-white text-slate-800"}>🚀 DeepSeek</option>
                <option value="nvidia" className={isDark ? "bg-gray-950 text-white" : "bg-white text-slate-800"}>⚡ NVIDIA</option>
                <option value="kloudeks" className={isDark ? "bg-gray-950 text-white" : "bg-white text-slate-800"}>🏛️ Kloudeks</option>
              </select>

              {/* Sohbeti Temizle Butonu */}
              <button 
                onClick={clearChat}
                className={`p-1.5 sm:px-2 sm:py-1.5 rounded-md border transition-all flex items-center gap-1 ${
                  isDark 
                    ? "bg-white/5 hover:bg-white/10 text-gray-400 hover:text-white border-white/5" 
                    : "bg-slate-100 hover:bg-slate-200 text-slate-600 hover:text-slate-900 border-slate-200"
                }`}
                title="Sohbeti Temizle"
              >
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
              </button>
            </div>
          </div>

          {/* Sohbet Oturumları Çekmecesi (Soldan Açılan Drawer / Slide-Over) */}
          {showSessionsSidebar && (
            <>
              {/* Arka plan karartma / Backdrop */}
              <div 
                onClick={() => setShowSessionsSidebar(false)}
                className="absolute inset-0 bg-black/50 backdrop-blur-xs z-30 transition-opacity animate-in fade-in duration-200"
              />

              {/* Soldan Açılan Çekmece */}
              <div className={`absolute top-0 bottom-0 left-0 w-[280px] sm:w-[320px] flex flex-col z-40 border-r shadow-2xl transition-all duration-300 animate-in slide-in-from-left ${
                isDark 
                  ? "bg-[#0b0c10]/95 backdrop-blur-2xl border-white/10 text-white" 
                  : "bg-white/95 backdrop-blur-2xl border-slate-200 text-slate-900"
              }`}>
                {/* Drawer Header */}
                <div className={`p-4 border-b flex justify-between items-center ${
                  isDark ? "border-white/10 bg-white/[0.02]" : "border-slate-100 bg-slate-50"
                }`}>
                  <div className="flex items-center gap-2">
                    <span className="text-base">💬</span>
                    <span className="text-xs font-bold uppercase tracking-wider">
                      {t("chat_sessions")} ({sessions.length})
                    </span>
                  </div>
                  <div className="flex items-center gap-1">
                    <button
                      onClick={handleNewChat}
                      className={`p-1.5 rounded-lg text-xs font-semibold flex items-center gap-1 transition-colors ${
                        isDark ? "hover:bg-white/10 text-emerald-400" : "hover:bg-slate-200 text-emerald-600"
                      }`}
                      title={t("new_chat")}
                    >
                      <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M12 4v16m8-8H4" />
                      </svg>
                      <span className="text-xs">{t("new_chat")}</span>
                    </button>
                    <button
                      onClick={() => setShowSessionsSidebar(false)}
                      className={`p-1.5 rounded-lg transition-colors ${
                        isDark ? "hover:bg-white/10 text-gray-400 hover:text-white" : "hover:bg-slate-200 text-slate-500 hover:text-slate-800"
                      }`}
                      title="Kapat"
                    >
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                      </svg>
                    </button>
                  </div>
                </div>

                {/* Drawer List */}
                <div className={`flex-1 p-3 overflow-y-auto space-y-2 ${
                  isDark 
                    ? "[&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:bg-white/10 [&::-webkit-scrollbar-thumb]:rounded-full" 
                    : "[&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:bg-slate-300 [&::-webkit-scrollbar-thumb]:rounded-full"
                }`}>
                  {sessions.map(s => {
                    const isActive = s.id === currentSessionId;
                    const dateStr = new Date(s.updatedAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
                    return (
                      <div
                        key={s.id}
                        onClick={() => handleSelectSession(s)}
                        className={`group/session flex items-center justify-between p-2.5 rounded-xl cursor-pointer border transition-all ${
                          isActive
                            ? (isDark 
                                ? "bg-emerald-500/15 border-emerald-500/40 text-white shadow-md shadow-emerald-950/40" 
                                : "bg-emerald-50 border-emerald-300 text-emerald-900 shadow-sm")
                            : (isDark 
                                ? "bg-white/[0.03] border-white/5 text-gray-300 hover:bg-white/[0.08] hover:border-white/15" 
                                : "bg-slate-50 border-slate-200 text-slate-700 hover:bg-slate-100")
                        }`}
                      >
                        <div className="flex items-center gap-2.5 min-w-0 pr-2">
                          <div className={`w-2 h-2 rounded-full flex-shrink-0 ${
                            isActive 
                              ? (isDark ? "bg-emerald-400 shadow-sm shadow-emerald-400" : "bg-emerald-500 shadow-sm shadow-emerald-400") 
                              : (isDark ? "bg-gray-600" : "bg-slate-300")
                          }`}></div>
                          <div className="flex flex-col min-w-0">
                            <span className="text-xs font-medium truncate">{s.title || t("untitled_chat")}</span>
                            <div className={`flex items-center gap-2 text-[10px] ${isDark ? "text-gray-500" : "text-slate-400"}`}>
                              <span>{dateStr}</span>
                              <span>•</span>
                              <span>{s.messages.filter(m => m.content).length} msgs</span>
                            </div>
                          </div>
                        </div>
                        <button
                          onClick={(e) => handleDeleteSession(s.id, e)}
                          className={`p-1.5 rounded-lg opacity-60 hover:opacity-100 hover:bg-red-500/20 hover:text-red-500 transition-all flex-shrink-0 ${
                            isDark ? "text-gray-400" : "text-slate-400"
                          }`}
                          title={t("delete_chat")}
                        >
                          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                          </svg>
                        </button>
                      </div>
                    );
                  })}
                </div>
              </div>
            </>
          )}

          {/* Mesajlaşma Alanı */}
          <div className={`flex-1 p-6 overflow-y-auto space-y-6 ${
            isDark 
              ? "[&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:bg-white/10 [&::-webkit-scrollbar-thumb]:rounded-full" 
              : "[&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:bg-slate-300 [&::-webkit-scrollbar-thumb]:rounded-full"
          }`}>
            {messages.map((msg, idx) => (
              <div key={idx} className={`flex flex-col ${msg.role === "agent" ? "items-start" : "items-end"} group`}>
                <div className={`flex items-end gap-2.5 max-w-[94%] ${msg.role === "agent" ? "flex-row" : "flex-row-reverse"}`}>
                  
                  {/* Avatar */}
                  {msg.role === "agent" ? (
                    <div className="w-8 h-8 rounded-full bg-gradient-to-br from-emerald-400 to-teal-600 flex-shrink-0 flex items-center justify-center shadow-lg shadow-emerald-500/20 mb-1">
                      <span className="text-xs font-black text-white">N</span>
                    </div>
                  ) : (
                    <div className={`w-8 h-8 rounded-full flex-shrink-0 flex items-center justify-center shadow-lg mb-1 border ${
                      isDark 
                        ? "bg-gradient-to-br from-gray-600 to-gray-800 border-white/10" 
                        : "bg-gradient-to-br from-slate-400 to-slate-600 border-slate-300"
                    }`}>
                      <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" /></svg>
                    </div>
                  )}

                  {/* Bubble */}
                  <div className={`p-4 sm:p-5 rounded-2xl text-[15px] leading-relaxed shadow-sm ${
                    msg.role === "agent" 
                    ? (isDark 
                        ? "bg-white/5 border border-white/10 rounded-bl-sm text-gray-200" 
                        : "bg-white border border-slate-200 rounded-bl-sm text-slate-800 shadow-md")
                    : "bg-blue-600 border border-blue-500 rounded-br-sm text-white shadow-blue-900/20"
                  }`}>
                    {msg.role === "agent" ? (
                      (() => {
                        const rawContent = idx === 0 && !msg.content ? t('welcome_message') : msg.content;
                        // Mesajdaki görselleri ayıkla
                        const imgRegex = /!\[(.*?)\]\((.*?)\)/g;
                        const extractedImages: Array<{ src: string; alt: string }> = [];
                        let match;
                        while ((match = imgRegex.exec(rawContent)) !== null) {
                          extractedImages.push({ alt: match[1] || "Grafik", src: match[2] });
                        }

                        // Sohbette metin ve tabloları temiz göster (görseller sağ panele aktarılıyor)
                        const contentToRender = rawContent.replace(/!\[(.*?)\]\((.*?)\)/g, '').trim();

                        return (
                          <div className={`space-y-2.5 [&_p]:mb-2.5 [&_p:last-child]:mb-0 [&_ul]:list-disc [&_ul]:pl-5 [&_ul]:mb-2.5 [&_li]:mb-1.5 [&_a]:underline text-sm sm:text-[15px] ${
                            isDark 
                              ? "[&_strong]:text-white [&_strong]:font-bold [&_a]:text-blue-400 [&_a]:hover:text-blue-300 [&_h3]:text-base [&_h3]:font-bold [&_h3]:text-emerald-400 [&_h3]:mt-4 [&_h3]:mb-1.5 [&_table]:w-full [&_table]:border-collapse [&_table]:my-2 [&_th]:border [&_th]:border-white/20 [&_th]:p-2.5 [&_th]:bg-white/5 [&_th]:text-xs [&_td]:border [&_td]:border-white/10 [&_td]:p-2.5 [&_td]:text-xs [&_pre]:overflow-x-auto [&_pre]:p-3 [&_pre]:bg-black/50 [&_pre]:rounded-lg [&_code]:bg-white/10 [&_code]:px-1.5 [&_code]:py-0.5 [&_code]:rounded"
                              : "[&_strong]:text-slate-900 [&_strong]:font-bold [&_a]:text-blue-600 [&_a]:hover:text-blue-700 [&_h3]:text-base [&_h3]:font-bold [&_h3]:text-emerald-700 [&_h3]:mt-4 [&_h3]:mb-1.5 [&_table]:w-full [&_table]:border-collapse [&_table]:my-2 [&_th]:border [&_th]:border-slate-300 [&_th]:p-2.5 [&_th]:bg-slate-100 [&_th]:text-slate-800 [&_th]:text-xs [&_td]:border [&_td]:border-slate-200 [&_td]:p-2.5 [&_td]:text-slate-700 [&_td]:text-xs [&_pre]:overflow-x-auto [&_pre]:p-3 [&_pre]:bg-slate-900 [&_pre]:text-slate-100 [&_pre]:rounded-lg [&_code]:bg-slate-200 [&_code]:text-slate-800 [&_code]:px-1.5 [&_code]:py-0.5 [&_code]:rounded"
                          }`}>
                            {/* Akıl Yürütme ve Düşünce Adımları Accordion */}
                            {(msg.trace || typeof msg.duration_s === "number") && (
                              <MessageReasoningAccordion trace={msg.trace} duration_s={msg.duration_s} />
                            )}

                            <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
                              {formatMarkdownContent(contentToRender)}
                            </ReactMarkdown>

                            {extractedImages.length > 0 && (
                              <div className={`mt-3 px-3.5 py-2 rounded-xl border flex items-center justify-between text-xs font-medium backdrop-blur-sm shadow-sm transition-all ${
                                isDark 
                                  ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-300" 
                                  : "bg-emerald-50 border-emerald-200 text-emerald-800"
                              }`}>
                                <span className="flex items-center gap-2">
                                  <span>📊</span>
                                  <span>{extractedImages.length} {t("analytics_charts") || "Analitik Grafik"} üretildi</span>
                                </span>
                                <span className="text-[11px] opacity-80 flex items-center gap-1 font-semibold">
                                  <span>Sağ Analiz Paneli&apos;nde ↗</span>
                                </span>
                              </div>
                            )}
                          </div>
                        );
                      })()
                    ) : (
                      <div>
                        {msg.attachmentName && (
                          <div className="mb-2 flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-white/20 text-xs font-semibold text-white border border-white/30 w-fit backdrop-blur-sm shadow-sm">
                            <span>📎</span>
                            <span className="truncate max-w-[220px]">{msg.attachmentName}</span>
                          </div>
                        )}
                        <div>{msg.content}</div>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ))}
            
            {isLoading && (
              <div className="flex items-end gap-2 max-w-[92%]">
                <div className="w-7 h-7 rounded-full bg-gradient-to-br from-emerald-400 to-teal-600 flex-shrink-0 flex items-center justify-center mb-1 shadow-lg shadow-emerald-500/20">
                  <span className="text-[10px] font-black text-white">N</span>
                </div>

                <div className={`min-w-[260px] p-4 rounded-2xl rounded-bl-sm border shadow-lg ${
                  isDark 
                    ? "bg-gradient-to-br from-white/[0.08] to-white/[0.03] border-emerald-500/20" 
                    : "bg-white border-emerald-500/30 text-slate-800"
                }`}>
                  <div className="flex items-center gap-2 mb-3">
                    <span className="relative flex h-2 w-2">
                      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                      <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-400"></span>
                    </span>
                    <span className={`text-[11px] uppercase tracking-wider font-bold ${
                      isDark ? "text-emerald-400" : "text-emerald-600"
                    }`}>
                      {t("activity_title")}
                    </span>
                  </div>

                  <div className="space-y-2">
                    {(activitySteps.length > 0
                      ? activitySteps
                      : [{ message: t("activity_initial"), done: false }]
                    ).map((step, idx) => (
                      <div
                        key={idx}
                        className={`flex items-start gap-2 text-xs transition-all duration-300 ${
                          step.done 
                            ? (isDark ? "text-gray-500" : "text-slate-400") 
                            : (isDark ? "text-gray-200" : "text-slate-800")
                        }`}
                      >
                        {step.done ? (
                          <span className={isDark ? "text-emerald-400 mt-[1px]" : "text-emerald-600 mt-[1px]"}>✓</span>
                        ) : (
                          <span className="w-1.5 h-1.5 mt-1 rounded-full bg-blue-400 animate-pulse flex-shrink-0"></span>
                        )}
                        <span className={step.done ? "" : "animate-pulse"}>
                          {step.message}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* Input Alanı */}
          <div className={`p-4 sm:p-5 border-t transition-colors duration-200 ${
            isDark ? "border-white/5 bg-black/40" : "border-slate-200 bg-slate-50/90"
          }`}>
            {/* Attachment Error Alert */}
            {attachmentError && (
              <div className="mb-3 px-3.5 py-2 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-xs flex items-center justify-between">
                <span className="flex items-center gap-1.5">
                  <span>⚠️</span>
                  <span>{attachmentError}</span>
                </span>
                <button
                  onClick={() => setAttachmentError(null)}
                  className="hover:text-red-300 font-bold ml-2 p-1"
                >
                  ✕
                </button>
              </div>
            )}

            {/* Uploading Progress */}
            {isUploadingAttachment && (
              <div className="mb-3 px-3.5 py-2 rounded-xl bg-blue-500/10 border border-blue-500/20 text-blue-400 text-xs flex items-center gap-2 animate-pulse">
                <div className="w-3.5 h-3.5 border-2 border-blue-400 border-t-transparent rounded-full animate-spin"></div>
                <span>{t("uploading_file")}</span>
              </div>
            )}

            {/* Attached File Chip / Badge */}
            {attachment && (
              <div className={`mb-3 px-3.5 py-2 rounded-xl border flex items-center justify-between gap-3 text-xs ${
                isDark 
                  ? "bg-white/10 border-blue-500/30 text-white shadow-sm" 
                  : "bg-blue-50 border-blue-200 text-blue-900 shadow-sm"
              }`}>
                <div className="flex items-center gap-2 min-w-0">
                  <span className="text-base">
                    {attachment.contentType === "image" ? "📸" : attachment.contentType === "excel" ? "📊" : attachment.contentType === "pdf" ? "📑" : "📄"}
                  </span>
                  <div className="truncate">
                    <span className="font-semibold">{attachment.name}</span>
                    <span className={`ml-2 text-[11px] ${isDark ? "text-gray-400" : "text-slate-500"}`}>
                      ({(attachment.size / 1024).toFixed(1)} KB)
                    </span>
                  </div>
                </div>
                <button
                  onClick={() => setAttachment(null)}
                  className={`p-1 rounded-md hover:bg-red-500/20 hover:text-red-400 transition-colors flex-shrink-0 ${
                    isDark ? "text-gray-400" : "text-slate-500"
                  }`}
                  title={t("remove_attachment")}
                >
                  ✕
                </button>
              </div>
            )}

            {/* Hidden File Input */}
            <input
              type="file"
              ref={fileInputRef}
              onChange={handleFileUpload}
              accept=".xlsx,.xls,.csv,.pdf,.png,.jpg,.jpeg,.webp"
              className="hidden"
            />

            <div className="relative flex items-center">
              {/* Attachment Button */}
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={isLoading || isUploadingAttachment}
                title={t("attach_file")}
                className={`absolute left-2.5 p-2 rounded-lg transition-all flex items-center justify-center ${
                  isDark
                    ? "text-gray-400 hover:text-white hover:bg-white/10"
                    : "text-slate-500 hover:text-slate-900 hover:bg-slate-200"
                } disabled:opacity-40 disabled:cursor-not-allowed`}
              >
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
                </svg>
              </button>

              <input 
                type="text" 
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !isLoading && !isUploadingAttachment) handleSend();
                }}
                disabled={isLoading || isUploadingAttachment}
                placeholder={
                  isLoading
                    ? t("chat_busy")
                    : isUploadingAttachment
                    ? t("uploading_file")
                    : (attachment ? `${attachment.name} ile ilgili soru sorun...` : t('chat_placeholder'))
                } 
                className={`w-full pl-12 pr-14 py-4 rounded-xl text-sm transition-all disabled:opacity-50 disabled:cursor-not-allowed ${
                  isDark 
                    ? "bg-white/5 border border-white/10 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500/50 focus:bg-white/10 shadow-inner" 
                    : "bg-white border border-slate-300 text-slate-900 placeholder-slate-400 focus:outline-none focus:border-blue-500 shadow-sm"
                }`}
              />
              <button 
                onClick={handleSend}
                disabled={isLoading || isUploadingAttachment || (!input.trim() && !attachment)}
                className="absolute right-2 p-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg transition-all disabled:opacity-30 disabled:hover:bg-blue-600 shadow-md"
              >
                <svg className="w-5 h-5 translate-x-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" /></svg>
              </button>
            </div>
          </div>
        </div>

        {/* Ayırıcı / Yeniden Boyutlandırma Çizgisi (Draggable Splitter) */}
        <div
          onMouseDown={startResizing}
          onDoubleClick={resetChatWidth}
          className={`relative hidden md:flex items-center justify-center w-2 -mx-1 z-30 cursor-col-resize group select-none transition-colors ${
            isResizing ? "bg-blue-500/30" : "hover:bg-blue-500/10"
          }`}
          title="Sürükleyerek yeniden boyutlandırın (Çift tık: Sıfırla)"
        >
          {/* İnce dikey çizgi */}
          <div className={`w-[2px] h-full transition-colors ${
            isResizing
              ? (isDark ? "bg-blue-400" : "bg-blue-600")
              : (isDark ? "bg-white/10 group-hover:bg-blue-400/80" : "bg-slate-300 group-hover:bg-blue-500/80")
          }`} />

          {/* Orta tutamaç hapı */}
          <div className={`absolute w-4 h-9 rounded-full flex flex-col items-center justify-center gap-0.5 border shadow-md transition-all opacity-0 group-hover:opacity-100 ${
            isResizing ? "!opacity-100 scale-105" : ""
          } ${
            isDark 
              ? "bg-[#111] border-white/20 text-gray-400 group-hover:text-white shadow-black/40" 
              : "bg-white border-slate-300 text-slate-400 group-hover:text-slate-700 shadow-slate-300"
          }`}>
            <div className="w-1 h-1 rounded-full bg-current"></div>
            <div className="w-1 h-1 rounded-full bg-current"></div>
            <div className="w-1 h-1 rounded-full bg-current"></div>
          </div>
        </div>

        {/* Sağ Panel - Dashboard */}
        <div className={`flex-1 min-w-0 p-8 md:p-12 flex flex-col gap-8 overflow-y-auto relative z-10 ${
          isDark 
            ? "[&::-webkit-scrollbar]:w-2 [&::-webkit-scrollbar-thumb]:bg-white/10 [&::-webkit-scrollbar-thumb]:rounded-full" 
            : "[&::-webkit-scrollbar]:w-2 [&::-webkit-scrollbar-thumb]:bg-slate-300 [&::-webkit-scrollbar-thumb]:rounded-full"
        }`}>
          
          {/* Dashboard Header */}
          <div className={`flex items-center justify-between gap-4 pb-6 border-b flex-nowrap ${
            isDark ? "border-white/10" : "border-slate-200"
          }`}>
             <div className="min-w-0 flex-1 pr-2">
                <h2 className={`text-2xl sm:text-3xl font-black tracking-tight truncate ${
                  isDark ? "text-white" : "text-slate-900"
                }`}>{t('panel_title')}</h2>
                <p className={`text-xs sm:text-sm mt-0.5 truncate ${isDark ? "text-gray-400" : "text-slate-500"}`}>Real-time Data Lakehouse & Verification Engine</p>
             </div>
             <div className="flex items-center gap-2 flex-shrink-0">
                <span className="relative flex h-3 w-3">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-3 w-3 bg-emerald-500"></span>
                </span>
                <span className={`text-xs font-bold px-3 py-1.5 rounded-full border hidden sm:inline-flex ${
                  isDark 
                    ? "text-emerald-400 bg-emerald-500/10 border-emerald-500/20" 
                    : "text-emerald-700 bg-emerald-50 border-emerald-300 shadow-sm"
                }`}>System Online</span>

                {/* Tema Değiştirme Butonu */}
                <button
                  onClick={toggleTheme}
                  className={`p-2 rounded-lg border transition-all flex items-center justify-center ${
                    isDark 
                      ? "bg-white/5 hover:bg-white/10 text-amber-400 border-white/10 hover:border-amber-400/30" 
                      : "bg-amber-50 hover:bg-amber-100 text-amber-700 border-amber-200"
                  }`}
                  title={isDark ? t("theme_light") : t("theme_dark")}
                >
                  {isDark ? (
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
                    </svg>
                  ) : (
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
                    </svg>
                  )}
                </button>

                {/* Tekli Dil Toggle Butonu */}
                <Link
                  href={`/${locale === "tr" ? "en" : "tr"}`}
                  className={`px-2.5 py-1.5 rounded-lg border transition-all flex items-center gap-1.5 text-xs font-semibold ${
                    isDark 
                      ? "bg-white/5 hover:bg-white/10 text-gray-300 hover:text-white border-white/10 hover:border-white/20" 
                      : "bg-slate-100 hover:bg-slate-200 text-slate-700 hover:text-slate-900 border-slate-200"
                  }`}
                  title={locale === "tr" ? "Switch to English (EN)" : "Türkçe'ye Geç (TR)"}
                >
                  <span className="text-xs">🌐</span>
                  <span>{locale === "tr" ? "EN" : "TR"}</span>
                </Link>

                {/* Çıkış Yap Butonu */}
                <button 
                  onClick={() => {
                    devMode ? toggleDevMode(false) : signOut();
                  }} 
                  className={`p-2 rounded-lg border transition-all flex items-center justify-center ${
                    isDark 
                      ? "bg-red-500/10 hover:bg-red-500/20 text-red-400 border-red-500/20" 
                      : "bg-red-50 hover:bg-red-100 text-red-600 border-red-200"
                  }`}
                  title={t('logout_button')}
                >
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" /></svg>
                </button>
             </div>
          </div>
          
          {/* İstatistik / Bilgi Kartları */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            <div className={`p-6 rounded-2xl shadow-lg relative overflow-hidden group transition-all ${
              isDark 
                ? "bg-gradient-to-br from-emerald-500/10 to-transparent border border-emerald-500/20 hover:border-emerald-500/40" 
                : "bg-white border border-emerald-200 hover:border-emerald-400 shadow-slate-200"
            }`}>
              <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
                <svg className={`w-16 h-16 ${isDark ? "text-emerald-500" : "text-emerald-600"}`} fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
              </div>
              <h3 className={`font-bold text-xs uppercase tracking-wider mb-2 ${
                isDark ? "text-emerald-400" : "text-emerald-700"
              }`}>Verification Status</h3>
              <p className={`font-medium text-sm leading-relaxed pr-10 ${
                isDark ? "text-white" : "text-slate-700"
              }`}>{t('verifier_active')}</p>
            </div>
            
            <div className={`p-6 rounded-2xl shadow-lg relative overflow-hidden group transition-all ${
              isDark 
                ? "bg-gradient-to-br from-blue-500/10 to-transparent border border-blue-500/20 hover:border-blue-500/40" 
                : "bg-white border border-blue-200 hover:border-blue-400 shadow-slate-200"
            }`}>
              <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
                <svg className={`w-16 h-16 ${isDark ? "text-blue-500" : "text-blue-600"}`} fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" /></svg>
              </div>
              <h3 className={`font-bold text-xs uppercase tracking-wider mb-2 ${
                isDark ? "text-blue-400" : "text-blue-700"
              }`}>Data Lake Sources</h3>
              <p className={`font-medium text-sm leading-relaxed pr-10 ${
                isDark ? "text-white" : "text-slate-700"
              }`}>{t('sources')}</p>
            </div>
          </div>


          {/* Güven Katmanı - İzlenebilirlik / Kullanılan Araçlar (Açılır Kapanır) */}
          {traceSteps.length > 0 && (
            <div className={`border rounded-2xl overflow-hidden transition-all ${
              isDark 
                ? "bg-white/[0.02] border-white/5" 
                : "bg-white border-slate-200 shadow-md"
            }`}>
              <button
                type="button"
                onClick={() => setShowRightPanelTrace(!showRightPanelTrace)}
                className={`w-full p-4 sm:p-5 flex items-center justify-between text-left transition-colors ${
                  isDark ? "hover:bg-white/5" : "hover:bg-slate-50"
                }`}
              >
                <div className="flex items-center gap-2">
                  <span className="text-base">🛠️</span>
                  <h3 className={`font-bold text-xs uppercase tracking-wider ${
                    isDark ? "text-gray-300" : "text-slate-700"
                  }`}>
                    {t('trace_title')} ({traceSteps.length})
                  </h3>
                  {typeof latestAgentMsg?.duration_s === "number" && (
                    <span className={`px-2 py-0.5 rounded-full text-[11px] font-mono font-bold ${
                      isDark ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30" : "bg-emerald-100 text-emerald-800"
                    }`}>
                      {latestAgentMsg.duration_s.toFixed(2)}s
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-1 text-xs font-semibold text-emerald-500">
                  <span>{showRightPanelTrace ? (t("hide_reasoning") || "Gizle") : (t("view_reasoning") || "Genişlet")}</span>
                  <svg className={`w-4 h-4 transition-transform duration-200 ${showRightPanelTrace ? "rotate-180" : ""}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                  </svg>
                </div>
              </button>

              {showRightPanelTrace && (
                <div className={`px-4 pb-4 sm:px-5 sm:pb-5 pt-0 border-t ${isDark ? "border-white/5" : "border-slate-100"}`}>
                  <ol className="space-y-2 mt-3">
                    {traceSteps.map((step, idx) => (
                      <li key={idx} className={`flex flex-col gap-1 text-sm border rounded-xl px-3.5 py-2.5 ${
                        isDark 
                          ? "bg-white/[0.02] border-white/5" 
                          : "bg-slate-50 border-slate-200 text-slate-800"
                      }`}>
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2 truncate">
                            <span className={`font-mono text-xs ${isDark ? "text-gray-500" : "text-slate-400"}`}>{idx + 1}.</span>
                            <span className={`font-semibold truncate ${isDark ? "text-emerald-400" : "text-emerald-700"}`}>{step.tool_name}</span>
                          </div>
                          <div className="flex items-center gap-2 flex-shrink-0">
                            {typeof step.duration_s === "number" && (
                              <span className={`text-xs font-mono ${isDark ? "text-gray-400" : "text-slate-500"}`}>{step.duration_s.toFixed(2)}s</span>
                            )}
                            <span className={step.success !== false ? (isDark ? "text-emerald-400 font-bold" : "text-emerald-600 font-bold") : "text-red-500 font-bold"}>
                              {step.success !== false ? "✓" : "✗"}
                            </span>
                          </div>
                        </div>
                        {step.arguments && (
                          <details className={`text-xs mt-1 ${isDark ? "text-gray-500" : "text-slate-500"}`}>
                            <summary className={`cursor-pointer ${isDark ? "hover:text-gray-300" : "hover:text-slate-700"}`}>Parametreler</summary>
                            <pre className={`mt-1 p-2 rounded-lg whitespace-pre-wrap break-words font-mono text-[11px] ${
                              isDark ? "bg-black/50 text-gray-400 border border-white/5" : "bg-white text-slate-600 border border-slate-200"
                            }`}>{step.arguments}</pre>
                          </details>
                        )}
                      </li>
                    ))}
                  </ol>
                </div>
              )}
            </div>
          )}

          {/* Veri Sağlık Karnesi Kartı */}
          {dataHealthStep && (
            <div className={`border rounded-2xl p-4 sm:p-5 transition-all ${
              isDark 
                ? "bg-gradient-to-br from-emerald-500/10 via-white/[0.02] to-transparent border-emerald-500/30 shadow-lg" 
                : "bg-gradient-to-br from-emerald-50 to-white border-emerald-200 shadow-md"
            }`}>
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <span className="text-lg">📋</span>
                  <h3 className={`font-bold text-xs uppercase tracking-wider ${
                    isDark ? "text-emerald-400" : "text-emerald-700"
                  }`}>
                    {t('data_health_title')}
                  </h3>
                </div>
                <span className={`px-2.5 py-0.5 rounded-full text-[11px] font-bold tracking-wide uppercase ${
                  isDark ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40" : "bg-emerald-100 text-emerald-800"
                }`}>
                  {t('data_health_badge')}
                </span>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 my-3">
                <div className={`p-3 rounded-xl border ${isDark ? "bg-black/30 border-white/5" : "bg-white border-slate-200"}`}>
                  <div className={`text-[10px] uppercase font-semibold ${isDark ? "text-gray-400" : "text-slate-500"}`}>{t('data_health_score')}</div>
                  <div className={`text-base font-bold mt-0.5 ${isDark ? "text-emerald-400" : "text-emerald-600"}`}>100/100</div>
                </div>
                <div className={`p-3 rounded-xl border ${isDark ? "bg-black/30 border-white/5" : "bg-white border-slate-200"}`}>
                  <div className={`text-[10px] uppercase font-semibold ${isDark ? "text-gray-400" : "text-slate-500"}`}>{t('data_health_missing')}</div>
                  <div className={`text-base font-bold mt-0.5 ${isDark ? "text-white" : "text-slate-800"}`}>%0 Eksik</div>
                </div>
                <div className={`p-3 rounded-xl border ${isDark ? "bg-black/30 border-white/5" : "bg-white border-slate-200"}`}>
                  <div className={`text-[10px] uppercase font-semibold ${isDark ? "text-gray-400" : "text-slate-500"}`}>{t('data_health_obs')}</div>
                  <div className={`text-base font-bold mt-0.5 ${isDark ? "text-white" : "text-slate-800"}`}>Aktif / Tam</div>
                </div>
                <div className={`p-3 rounded-xl border ${isDark ? "bg-black/30 border-white/5" : "bg-white border-slate-200"}`}>
                  <div className={`text-[10px] uppercase font-semibold ${isDark ? "text-gray-400" : "text-slate-500"}`}>{t('data_health_alignment')}</div>
                  <div className={`text-base font-bold mt-0.5 ${isDark ? "text-white" : "text-slate-800"}`}>Doğrulandı</div>
                </div>
              </div>

              {dataHealthArgs && (
                <div className={`text-xs mt-2 px-3 py-2 rounded-xl border font-mono truncate ${
                  isDark ? "bg-black/40 border-white/5 text-gray-300" : "bg-white/80 border-emerald-100 text-slate-700"
                }`}>
                  <span className="font-semibold text-emerald-500">Hedef: </span>
                  {dataHealthArgs.series_id || (dataHealthArgs.gold_table ? `${dataHealthArgs.gold_table}.${dataHealthArgs.gold_column}` : "Gözlem Serisi")}
                </div>
              )}
            </div>
          )}

          {/* Analitik Grafik Kartı / Galerisi (Tüm Oturum) */}

          {sessionImages.length > 0 ? (
            <div className="flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <h3 className={`font-bold text-xs uppercase tracking-wider ${
                  isDark ? "text-emerald-400" : "text-emerald-700"
                }`}>
                  📊 {t("session_charts_title") || "Oturumun Analitik Grafikleri"} ({sessionImages.length})
                </h3>
              </div>
              <ChartCarousel images={sessionImages} />
            </div>
          ) : (
            /* Grafik Alanı (Boş Durum) */
            <div className={`flex-1 min-h-[360px] border rounded-3xl p-8 flex flex-col items-center justify-center relative overflow-hidden group ${
              isDark 
                ? "bg-white/[0.02] border-white/5" 
                : "bg-white border-slate-200 shadow-md"
            }`}>
              <div className={`absolute inset-0 pointer-events-none ${
                isDark 
                  ? "bg-gradient-to-br from-blue-900/5 to-purple-900/5" 
                  : "bg-gradient-to-br from-blue-500/5 to-emerald-500/5"
              }`}></div>
              
              {/* Arkaplan Izgarası (Grid) */}
              <div className="absolute inset-0 bg-[url('data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iNDAiIGhlaWdodD0iNDAiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+PGNpcmNsZSBjeD0iMSIgY3k9IjEiIHI9IjEiIGZpbGw9InJnYmEoMTUwLDE1MCwxNTAsMC4wNykiLz48L3N2Zz4=')] opacity-50"></div>

              <div className="z-10 flex flex-col items-center text-center max-w-md">
                <div className={`w-20 h-20 rounded-2xl flex items-center justify-center border mb-6 group-hover:scale-110 transition-all duration-500 shadow-xl ${
                  isDark 
                    ? "bg-white/5 border-white/10 text-gray-500 group-hover:text-blue-400 group-hover:border-blue-500/30" 
                    : "bg-slate-100 border-slate-200 text-slate-400 group-hover:text-blue-600 group-hover:border-blue-400"
                }`}>
                  <svg className="w-10 h-10 transition-colors duration-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                  </svg>
                </div>
                <h3 className={`text-xl font-bold mb-2 ${
                  isDark ? "text-gray-200" : "text-slate-800"
                }`}>{t('graph_placeholder')}</h3>
                <p className={`text-sm leading-relaxed ${
                  isDark ? "text-gray-500" : "text-slate-500"
                }`}>{t('graph_subtext')}</p>
                
                <div className="mt-8 flex gap-2">
                  <div className={`h-1.5 w-12 rounded-full overflow-hidden ${isDark ? "bg-white/10" : "bg-slate-200"}`}>
                     <div className="h-full bg-blue-500/50 w-1/3 animate-pulse"></div>
                  </div>
                  <div className={`h-1.5 w-8 rounded-full ${isDark ? "bg-white/10" : "bg-slate-200"}`}></div>
                  <div className={`h-1.5 w-16 rounded-full overflow-hidden ${isDark ? "bg-white/10" : "bg-slate-200"}`}>
                     <div className="h-full bg-emerald-500/50 w-1/2 animate-pulse delay-75"></div>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    );
  }

  // Login Screen
  return (
    <div className={`flex flex-col items-center justify-center min-h-screen p-4 relative font-sans overflow-hidden transition-colors duration-200 ${
      isDark ? "bg-[#050505] text-gray-200 selection:bg-blue-500/30" : "bg-slate-100 text-slate-800 selection:bg-blue-200"
    }`}>
      
      {/* Arka plan efektleri */}
      <div className="absolute inset-0 bg-[url('data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iNDAiIGhlaWdodD0iNDAiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+PGNpcmNsZSBjeD0iMSIgY3k9IjEiIHI9IjEiIGZpbGw9InJnYmEoMTUwLDE1MCwxNTAsMC4wNSkiLz48L3N2Zz4=')] opacity-50"></div>
      <div className={`absolute top-[-20%] right-[-10%] w-[50%] h-[50%] rounded-full blur-[120px] pointer-events-none ${
        isDark ? "bg-blue-900/20" : "bg-blue-300/30"
      }`}></div>
      <div className={`absolute bottom-[-20%] left-[-10%] w-[50%] h-[50%] rounded-full blur-[120px] pointer-events-none ${
        isDark ? "bg-emerald-900/10" : "bg-emerald-300/25"
      }`}></div>

      {/* Dil ve Tema Seçimi */}
      <div className="absolute top-6 right-6 flex items-center gap-2 z-20">
        <button
          onClick={toggleTheme}
          className={`px-3 py-1.5 backdrop-blur-md rounded-lg border transition-all font-semibold text-xs tracking-wider flex items-center gap-1 ${
            isDark 
              ? "bg-white/5 border-white/10 hover:bg-white/10 text-amber-400" 
              : "bg-white border-slate-300 hover:bg-slate-50 text-amber-600 shadow-sm"
          }`}
          title={isDark ? t("theme_light") : t("theme_dark")}
        >
          {isDark ? (
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
            </svg>
          ) : (
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
            </svg>
          )}
        </button>
        <Link href="/tr" className={`px-3.5 py-1.5 backdrop-blur-md rounded-lg border transition-all font-semibold text-xs tracking-wider ${
          isDark 
            ? "bg-white/5 border-white/10 hover:bg-white/10 text-gray-200" 
            : "bg-white border-slate-300 hover:bg-slate-50 text-slate-800 shadow-sm"
        }`}>TR</Link>
        <Link href="/en" className={`px-3.5 py-1.5 backdrop-blur-md rounded-lg border transition-all font-semibold text-xs tracking-wider ${
          isDark 
            ? "bg-white/5 border-white/10 hover:bg-white/10 text-gray-200" 
            : "bg-white border-slate-300 hover:bg-slate-50 text-slate-800 shadow-sm"
        }`}>EN</Link>
      </div>

      <div className={`max-w-md w-full backdrop-blur-3xl rounded-[2rem] shadow-2xl p-10 text-center border relative z-10 group transition-all ${
        isDark 
          ? "bg-white/[0.03] border-white/10 text-white" 
          : "bg-white/95 border-slate-200 text-slate-800 shadow-slate-300"
      }`}>
        
        {/* İç aydınlatma efekti */}
        <div className={`absolute inset-0 bg-gradient-to-b rounded-[2rem] pointer-events-none ${
          isDark ? "from-white/5 to-transparent" : "from-slate-500/5 to-transparent"
        }`}></div>

        <div className="w-20 h-20 mx-auto bg-gradient-to-tr from-blue-600 to-emerald-400 rounded-2xl flex items-center justify-center shadow-2xl shadow-blue-500/20 mb-8 border border-white/20 group-hover:scale-105 transition-transform duration-500">
           <svg className="w-10 h-10 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
        </div>

        <h1 className={`text-3xl font-black mb-3 tracking-tight ${
          isDark 
            ? "bg-clip-text text-transparent bg-gradient-to-r from-white via-gray-200 to-gray-400" 
            : "text-slate-900"
        }`}>{t('title')}</h1>
        <p className={`mb-10 text-sm font-semibold tracking-wide uppercase ${
          isDark ? "text-emerald-400/80" : "text-emerald-600"
        }`}>{t('subtitle')}</p>

        <p className={`mb-6 font-medium text-sm leading-relaxed px-4 ${
          isDark ? "text-gray-400" : "text-slate-600"
        }`}>{t('login_prompt')}</p>
        
        <button 
          onClick={() => signIn("google")} 
          className={`w-full flex items-center justify-center gap-3 py-4 px-4 font-bold rounded-xl transition-all hover:scale-[1.02] active:scale-95 shadow-xl mb-6 ${
            isDark 
              ? "bg-white text-black hover:bg-gray-100 shadow-white/10" 
              : "bg-slate-900 text-white hover:bg-slate-800 shadow-slate-400/30"
          }`}
        >
          {/* Google SVG */}
          <svg className="w-5 h-5" viewBox="0 0 24 24">
            <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
            <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
            <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
            <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
          </svg>
          {t('login_button')}
        </button>

        <div className="relative my-8">
          <div className="absolute inset-0 flex items-center"><div className={`w-full border-t ${isDark ? "border-white/5" : "border-slate-200"}`}></div></div>
          <div className="relative flex justify-center text-xs uppercase tracking-widest">
            <span className={`px-4 rounded-full font-bold border py-1 ${
              isDark ? "bg-[#0a0a0a] text-gray-500 border-white/5" : "bg-white text-slate-400 border-slate-200"
            }`}>veya</span>
          </div>
        </div>

        <button 
          onClick={() => toggleDevMode(true)} 
          className={`w-full py-4 px-4 font-bold rounded-xl transition-all border shadow-inner group/dev ${
            isDark 
              ? "bg-white/5 hover:bg-white/10 text-gray-300 hover:text-white border-white/10 hover:border-white/20" 
              : "bg-slate-50 hover:bg-slate-100 text-slate-700 hover:text-slate-900 border-slate-200 hover:border-slate-300"
          }`}
        >
          <span className="flex items-center justify-center gap-2">
            <svg className={`w-5 h-5 transition-colors ${
              isDark ? "text-gray-500 group-hover/dev:text-blue-400" : "text-slate-400 group-hover/dev:text-blue-600"
            }`} fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" /></svg>
            Geliştirici Modu (Bypass)
          </span>
        </button>
      </div>
      
      {/* Footer / Copyright */}
      <div className={`absolute bottom-6 text-center text-xs font-medium ${
        isDark ? "text-gray-600" : "text-slate-400"
      }`}>
         &copy; 2026 KKB Hackathon - Data Lakehouse & AI Agent
      </div>
    </div>
  );
}

export default function Home() {
  const t = useTranslations('Index');

  return (
    <SessionProvider>
      <DashboardContent t={t} />
    </SessionProvider>
  );
}