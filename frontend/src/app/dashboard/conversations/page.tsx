"use client";

import { useState, useEffect, useRef } from "react";
import { useTenant } from "@/contexts/tenant-context";
import { useToast } from "@/components/ui/toast";
import { Dialog } from "@/components/ui/dialog";
import {
    Search,
    Send,
    X,
    User,
    Bot,
    AlertCircle,
    Clock,
    MessageSquare,
    Phone,
    Loader2,
    Pause,
    Play,
    ChevronLeft,
    ChevronRight
} from "lucide-react";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

interface Conversation {
    id: string;
    tenant_id: string;
    session_id: string;
    channel: string;
    status: string;
    domain: string | null;
    frustration_level: number;
    push_name: string | null;
    created_at: string;
    updated_at: string | null;
}

interface Message {
    id: string;
    conversation_id: string;
    sender_type: "user" | "agent" | "system";
    content: string;
    intent: string | null;
    domain: string | null;
    metadata: Record<string, unknown> | null;
    created_at: string;
}

type Tab = "active" | "handoff" | "closed";
type PageSize = 30 | 50 | 100;

export default function ConversationsPage() {
    const { tenantId } = useTenant();
    const { showToast } = useToast();

    const [tab, setTab] = useState<Tab>("active");
    const [pageSize, setPageSize] = useState<PageSize>(50);
    const [page, setPage] = useState(1);
    const [hasMore, setHasMore] = useState(false);
    const [searchQuery, setSearchQuery] = useState("");
    const [conversations, setConversations] = useState<Conversation[]>([]);
    const [selectedConversation, setSelectedConversation] = useState<Conversation | null>(null);
    const [messages, setMessages] = useState<Message[]>([]);
    const [messageInput, setMessageInput] = useState("");

    const [loadingConversations, setLoadingConversations] = useState(false);
    const [loadingMessages, setLoadingMessages] = useState(false);
    const [sendingMessage, setSendingMessage] = useState(false);
    const [closingConversation, setClosingConversation] = useState(false);
    const [pausingAgent, setPausingAgent] = useState(false);

    const [showCloseDialog, setShowCloseDialog] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const messagesEndRef = useRef<HTMLDivElement>(null);

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    };

    // Fetch conversations
    const fetchConversations = async (pageNum: number = page) => {
        if (!tenantId) return;

        setLoadingConversations(true);
        setError(null);

        try {
            const offset = (pageNum - 1) * pageSize;
            const res = await fetch(`${BACKEND_URL}/conversations?tenant_id=${tenantId}&tab=${tab}&limit=${pageSize}&offset=${offset}`);
            if (!res.ok) throw new Error("Failed to fetch conversations");
            const data = await res.json();
            setConversations(data.data || []);
            setHasMore(data.has_more || false);
        } catch (err) {
            setError("Erro ao carregar conversas");
            showToast("error", "Erro ao carregar conversas");
        } finally {
            setLoadingConversations(false);
        }
    };

    // Fetch messages for selected conversation
    const fetchMessages = async (conversationId: string) => {
        setLoadingMessages(true);

        try {
            const res = await fetch(`${BACKEND_URL}/conversations/${conversationId}/messages`);
            if (!res.ok) throw new Error("Failed to fetch messages");
            const data = await res.json();
            setMessages(data.data || []);
            setTimeout(scrollToBottom, 100);
        } catch (err) {
            showToast("error", "Erro ao carregar mensagens");
            setMessages([]);
        } finally {
            setLoadingMessages(false);
        }
    };

    // Send message
    const handleSendMessage = async () => {
        if (!selectedConversation || !messageInput.trim()) return;

        setSendingMessage(true);

        try {
            const res = await fetch(`${BACKEND_URL}/conversations/${selectedConversation.id}/send-message`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ content: messageInput })
            });

            const data = await res.json();

            if (data.success && data.message) {
                setMessages(prev => [...prev, data.message]);
                setMessageInput("");
                setTimeout(scrollToBottom, 100);
            } else {
                showToast("error", data.error || "Erro ao enviar mensagem");
            }
        } catch (err) {
            showToast("error", "Erro ao enviar mensagem");
        } finally {
            setSendingMessage(false);
        }
    };

    // Close conversation
    const handleCloseConversation = async () => {
        if (!selectedConversation) return;

        setClosingConversation(true);

        try {
            const res = await fetch(`${BACKEND_URL}/conversations/${selectedConversation.id}/close`, {
                method: "POST"
            });

            if (!res.ok) throw new Error("Failed to close");

            showToast("success", "Handoff finalizado");
            setShowCloseDialog(false);
            setSelectedConversation(prev => prev ? { ...prev, status: "active" } : null);

            // Refresh messages to get system message from DB
            fetchMessages(selectedConversation.id);
            fetchConversations();
        } catch (err) {
            showToast("error", "Erro ao finalizar handoff");
        } finally {
            setClosingConversation(false);
        }
    };

    // Pause agent (manual handoff)
    const handlePauseAgent = async () => {
        if (!selectedConversation) return;

        setPausingAgent(true);

        try {
            const res = await fetch(`${BACKEND_URL}/conversations/${selectedConversation.id}/pause`, {
                method: "POST"
            });

            if (!res.ok) throw new Error("Failed to pause");

            showToast("success", "Agente pausado");
            setSelectedConversation(prev => prev ? { ...prev, status: "human_active" } : null);

            // Refresh messages to get system message from DB
            fetchMessages(selectedConversation.id);
            fetchConversations();
        } catch (err) {
            showToast("error", "Erro ao pausar agente");
        } finally {
            setPausingAgent(false);
        }
    };

    // Reset page when tab or pageSize changes
    useEffect(() => {
        setPage(1);
    }, [tab, pageSize]);

    // Load conversations on mount and when params change
    useEffect(() => {
        fetchConversations(page);
    }, [tenantId, tab, pageSize, page]);

    // Load messages when conversation selected
    useEffect(() => {
        if (selectedConversation) {
            fetchMessages(selectedConversation.id);
        } else {
            setMessages([]);
        }
    }, [selectedConversation?.id]);

    // Filter conversations by search
    const filteredConversations = conversations.filter(conv => {
        const displayName = (conv.push_name || conv.session_id).toLowerCase();
        const query = searchQuery.toLowerCase();
        return displayName.includes(query) ||
            conv.channel.toLowerCase().includes(query) ||
            conv.status.toLowerCase().includes(query);
    });

    const formatTime = (dateStr: string) => {
        const date = new Date(dateStr);
        return date.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
    };

    const formatDate = (dateStr: string) => {
        const date = new Date(dateStr);
        return date.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
    };

    const getStatusColor = (status: string) => {
        switch (status) {
            case "active": return "bg-green-500/20 text-green-400";
            case "handoff": return "bg-yellow-500/20 text-yellow-400";
            case "human_active": return "bg-blue-500/20 text-blue-400";
            case "closed": return "bg-zinc-500/20 text-zinc-400";
            default: return "bg-zinc-500/20 text-zinc-400";
        }
    };

    const getStatusLabel = (status: string) => {
        switch (status) {
            case "active": return "Ativo";
            case "handoff": return "Aguardando";
            case "human_active": return "Humano";
            case "closed": return "Encerrado";
            default: return status;
        }
    };

    const isClosed = selectedConversation?.status === "closed";

    return (
        <div className="flex h-[calc(100dvh-120px)] bg-[#050505] rounded-xl overflow-hidden">
            {/* Left Column - Conversations List */}
            <div className="w-80 min-w-[320px] border-r border-white/[0.06] flex flex-col">
                {/* Tabs */}
                <div className="p-3 border-b border-white/[0.06]">
                    <div className="flex gap-1 p-1 bg-white/[0.03] rounded-lg">
                        <button
                            onClick={() => setTab("active")}
                            className={`flex-1 py-2 px-2 text-xs font-medium rounded-md transition-all ${tab === "active"
                                ? "bg-green-500/20 text-green-400"
                                : "text-zinc-400 hover:text-white"
                                }`}
                        >
                            Ativos
                        </button>
                        <button
                            onClick={() => setTab("handoff")}
                            className={`flex-1 py-2 px-2 text-xs font-medium rounded-md transition-all ${tab === "handoff"
                                ? "bg-yellow-500/20 text-yellow-400"
                                : "text-zinc-400 hover:text-white"
                                }`}
                        >
                            Handoffs
                        </button>
                        <button
                            onClick={() => setTab("closed")}
                            className={`flex-1 py-2 px-2 text-xs font-medium rounded-md transition-all ${tab === "closed"
                                ? "bg-zinc-500/20 text-zinc-400"
                                : "text-zinc-400 hover:text-white"
                                }`}
                        >
                            Fechados
                        </button>
                    </div>
                </div>

                {/* Search */}
                <div className="p-3 border-b border-white/[0.06]">
                    <div className="relative">
                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-zinc-500" />
                        <input
                            type="text"
                            placeholder="Buscar conversa..."
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                            className="w-full pl-9 pr-4 py-2 bg-white/[0.03] border border-white/[0.06] rounded-lg text-sm text-white placeholder:text-zinc-500 focus:outline-none focus:border-indigo-500/50"
                        />
                    </div>
                </div>

                {/* Pagination Controls */}
                <div className="px-3 py-2 border-b border-white/[0.06] flex items-center justify-between">
                    <div className="flex items-center gap-1">
                        <button
                            onClick={() => setPage(p => Math.max(1, p - 1))}
                            disabled={page === 1}
                            className="p-1 text-zinc-400 hover:text-white disabled:opacity-30 disabled:hover:text-zinc-400"
                        >
                            <ChevronLeft className="h-4 w-4" />
                        </button>
                        <span className="text-xs text-zinc-400 min-w-[60px] text-center">Pág {page}</span>
                        <button
                            onClick={() => setPage(p => p + 1)}
                            disabled={!hasMore}
                            className="p-1 text-zinc-400 hover:text-white disabled:opacity-30 disabled:hover:text-zinc-400"
                        >
                            <ChevronRight className="h-4 w-4" />
                        </button>
                    </div>
                    <div className="flex gap-1">
                        {([30, 50, 100] as PageSize[]).map(size => (
                            <button
                                key={size}
                                onClick={() => setPageSize(size)}
                                className={`px-2 py-1 text-xs rounded ${pageSize === size ? "bg-indigo-500/20 text-indigo-400" : "text-zinc-400 hover:text-white"}`}
                            >
                                {size}
                            </button>
                        ))}
                    </div>
                </div>

                {/* Conversations List */}
                <div className="flex-1 overflow-y-auto">
                    {loadingConversations ? (
                        <div className="flex items-center justify-center h-32">
                            <Loader2 className="h-6 w-6 text-zinc-500 animate-spin" />
                        </div>
                    ) : error ? (
                        <div className="flex flex-col items-center justify-center h-32 text-zinc-500 gap-2">
                            <AlertCircle className="h-6 w-6" />
                            <span className="text-sm">{error}</span>
                        </div>
                    ) : filteredConversations.length === 0 ? (
                        <div className="flex flex-col items-center justify-center h-32 text-zinc-500 gap-2">
                            <MessageSquare className="h-6 w-6" />
                            <span className="text-sm">Nenhuma conversa encontrada</span>
                        </div>
                    ) : (
                        filteredConversations.map((conv) => (
                            <button
                                key={conv.id}
                                onClick={() => setSelectedConversation(conv)}
                                className={`w-full p-3 border-b border-white/[0.04] text-left transition-all hover:bg-white/[0.03] ${selectedConversation?.id === conv.id ? "bg-white/[0.06]" : ""
                                    }`}
                            >
                                <div className="flex items-start justify-between gap-2">
                                    <div className="flex-1 min-w-0">
                                        <div className="flex items-center gap-2">
                                            <User className="h-3 w-3 text-zinc-500" />
                                            <span className="text-sm font-medium text-white truncate">
                                                {conv.push_name || conv.session_id.slice(0, 12) + "..."}
                                            </span>
                                        </div>
                                        <div className="flex items-center gap-2 mt-1">
                                            <span className={`text-xs px-2 py-0.5 rounded-full ${getStatusColor(conv.status)}`}>
                                                {getStatusLabel(conv.status)}
                                            </span>
                                            <span className="text-xs text-zinc-500">{conv.channel}</span>
                                        </div>
                                    </div>
                                    <div className="text-xs text-zinc-500 flex items-center gap-1">
                                        <Clock className="h-3 w-3" />
                                        {formatDate(conv.created_at)}
                                    </div>
                                </div>
                            </button>
                        ))
                    )}
                </div>
            </div>

            {/* Right Column - Chat */}
            <div className="flex-1 flex flex-col">
                {!selectedConversation ? (
                    <div className="flex-1 flex items-center justify-center text-zinc-500">
                        <div className="text-center">
                            <MessageSquare className="h-12 w-12 mx-auto mb-3 opacity-50" />
                            <p>Selecione uma conversa</p>
                        </div>
                    </div>
                ) : (
                    <>
                        {/* Chat Header */}
                        <div className="p-4 border-b border-white/[0.06] flex items-center justify-between">
                            <div className="flex items-center gap-3">
                                <div className="h-10 w-10 rounded-full bg-indigo-500/20 flex items-center justify-center">
                                    <User className="h-5 w-5 text-indigo-400" />
                                </div>
                                <div>
                                    <div className="text-white font-medium">{selectedConversation.push_name || selectedConversation.session_id.slice(0, 16) + "..."}</div>
                                    <div className="flex items-center gap-2 text-xs text-zinc-400">
                                        <span className={`px-2 py-0.5 rounded-full ${getStatusColor(selectedConversation.status)}`}>
                                            {getStatusLabel(selectedConversation.status)}
                                        </span>
                                        <span>{selectedConversation.channel}</span>
                                        {selectedConversation.domain && <span>• {selectedConversation.domain}</span>}
                                    </div>
                                </div>
                            </div>
                            <div className="flex items-center gap-2">
                                {/* In Handoff tab: show Finalizar button */}
                                {(selectedConversation.status === "handoff" || selectedConversation.status === "human_active") && (
                                    <button
                                        onClick={() => setShowCloseDialog(true)}
                                        className="px-4 py-2 text-sm font-medium text-green-400 hover:text-green-300 hover:bg-green-500/10 rounded-lg transition-all flex items-center gap-2"
                                    >
                                        <Play className="h-4 w-4" />
                                        Finalizar
                                    </button>
                                )}
                                {/* In General tab (active status): show Pausar button */}
                                {selectedConversation.status === "active" && (
                                    <button
                                        onClick={handlePauseAgent}
                                        disabled={pausingAgent}
                                        className="px-4 py-2 text-sm font-medium text-orange-400 hover:text-orange-300 hover:bg-orange-500/10 rounded-lg transition-all flex items-center gap-2 disabled:opacity-50"
                                    >
                                        {pausingAgent ? <Loader2 className="h-4 w-4 animate-spin" /> : <Pause className="h-4 w-4" />}
                                        Pausar Agente
                                    </button>
                                )}
                                <button
                                    onClick={() => setSelectedConversation(null)}
                                    className="p-2 text-zinc-400 hover:text-white rounded-lg hover:bg-white/[0.05] transition-all"
                                >
                                    <X className="h-5 w-5" />
                                </button>
                            </div>
                        </div>

                        {/* Messages */}
                        <div className="flex-1 overflow-y-auto p-4 space-y-4">
                            {loadingMessages ? (
                                <div className="flex items-center justify-center h-32">
                                    <Loader2 className="h-6 w-6 text-zinc-500 animate-spin" />
                                </div>
                            ) : messages.length === 0 ? (
                                <div className="flex flex-col items-center justify-center h-32 text-zinc-500">
                                    <MessageSquare className="h-8 w-8 mb-2 opacity-50" />
                                    <span className="text-sm">Ainda não há mensagens nesta conversa</span>
                                </div>
                            ) : (
                                messages.map((msg) => {
                                    const isHuman = msg.sender_type === "agent" && (msg.metadata as any)?.sent_by === "human_agent";
                                    return (
                                        <div
                                            key={msg.id}
                                            className={`flex gap-3 ${msg.sender_type === "agent" ? "flex-row-reverse" : ""
                                                }`}
                                        >
                                            <div className={`h-8 w-8 rounded-full flex items-center justify-center flex-shrink-0 ${msg.sender_type === "user"
                                                ? "bg-zinc-700"
                                                : isHuman
                                                    ? "bg-emerald-500/20"
                                                    : msg.sender_type === "agent"
                                                        ? "bg-indigo-500/20"
                                                        : "bg-yellow-500/20"
                                                }`}>
                                                {msg.sender_type === "user" ? (
                                                    <User className="h-4 w-4 text-zinc-300" />
                                                ) : isHuman ? (
                                                    <User className="h-4 w-4 text-emerald-400" />
                                                ) : msg.sender_type === "agent" ? (
                                                    <Bot className="h-4 w-4 text-indigo-400" />
                                                ) : (
                                                    <AlertCircle className="h-4 w-4 text-yellow-400" />
                                                )}
                                            </div>
                                            <div className={`max-w-[70%] ${msg.sender_type === "agent" ? "text-right" : ""
                                                }`}>
                                                <div className={`px-4 py-2 rounded-2xl text-sm ${msg.sender_type === "user"
                                                    ? "bg-white/[0.06] text-white rounded-tl-sm"
                                                    : isHuman
                                                        ? "bg-emerald-500/20 text-white rounded-tr-sm"
                                                        : msg.sender_type === "agent"
                                                            ? "bg-indigo-500/20 text-white rounded-tr-sm"
                                                            : "bg-yellow-500/10 text-yellow-200 rounded-tl-sm italic"
                                                    }`}>
                                                    {msg.content}
                                                </div>
                                                <div className={`text-xs text-zinc-500 mt-1 ${msg.sender_type === "agent" ? "text-right" : ""
                                                    }`}>
                                                    {formatTime(msg.created_at)}
                                                    {isHuman && <span className="ml-1 text-emerald-500/50">• Atendente</span>}
                                                </div>
                                            </div>
                                        </div>
                                    );
                                })
                            )}
                            <div ref={messagesEndRef} />
                        </div>

                        {/* Input */}
                        <div className="p-4 border-t border-white/[0.06]">
                            {isClosed ? (
                                <div className="text-center text-sm text-zinc-500 py-3">
                                    Conversa encerrada. Não é possível enviar mensagens.
                                </div>
                            ) : (
                                <div className="flex gap-3">
                                    <input
                                        type="text"
                                        placeholder="Digite sua mensagem..."
                                        value={messageInput}
                                        onChange={(e) => setMessageInput(e.target.value)}
                                        onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleSendMessage()}
                                        disabled={sendingMessage}
                                        className="flex-1 px-4 py-3 bg-white/[0.03] border border-white/[0.06] rounded-xl text-white placeholder:text-zinc-500 focus:outline-none focus:border-indigo-500/50 disabled:opacity-50"
                                    />
                                    <button
                                        onClick={handleSendMessage}
                                        disabled={!messageInput.trim() || sendingMessage}
                                        className="px-4 py-3 bg-indigo-500 hover:bg-indigo-600 disabled:opacity-50 disabled:hover:bg-indigo-500 rounded-xl transition-all flex items-center gap-2"
                                    >
                                        {sendingMessage ? (
                                            <Loader2 className="h-5 w-5 text-white animate-spin" />
                                        ) : (
                                            <Send className="h-5 w-5 text-white" />
                                        )}
                                    </button>
                                </div>
                            )}
                        </div>
                    </>
                )}
            </div>

            {/* Close Confirmation Dialog */}
            <Dialog open={showCloseDialog} onClose={() => setShowCloseDialog(false)} title="Finalizar Handoff">
                <p className="text-zinc-400 mb-6">
                    Ao finalizar, o agente voltará a responder automaticamente esta conversa.
                </p>
                <div className="flex gap-3 justify-end">
                    <button
                        onClick={() => setShowCloseDialog(false)}
                        className="px-4 py-2 text-sm font-medium text-zinc-400 hover:text-white rounded-lg transition-all"
                    >
                        Cancelar
                    </button>
                    <button
                        onClick={handleCloseConversation}
                        disabled={closingConversation}
                        className="px-4 py-2 text-sm font-medium bg-green-500 hover:bg-green-600 text-white rounded-lg transition-all disabled:opacity-50 flex items-center gap-2"
                    >
                        {closingConversation && <Loader2 className="h-4 w-4 animate-spin" />}
                        Finalizar
                    </button>
                </div>
            </Dialog>
        </div>
    );
}
