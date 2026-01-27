"use client";

import React, { useState, useRef } from "react";
import { Button } from "@/components/ui/button";
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from "@/components/ui/card";
import {
    Bot,
    MoreVertical,
    Upload,
    FileText,
    Send,
    Trash2,
    Power,
    Sparkles,
    Settings2,
    MessageSquare,
    Loader2,
    X,
    AlertTriangle,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useToast } from "@/components/ui/toast";
import { useTenant } from "@/contexts/tenant-context";

// Agent data (no mock files - loaded from Supabase)
const initialAgents = [
    {
        id: "sales",
        name: "Consultor de Vendas",
        role: "Vendas",
        status: "active",
        model: "GPT-4 Turbo",
        prompt: "Você é um consultor de vendas experiente e persuasivo da Nouva. Seu objetivo é entender as necessidades do cliente e oferecer a melhor solução de IA para o negócio dele. Seja profissional, mas amigável. Sempre foque no ROI.",
        personalityId: "professional",
    },
    {
        id: "support",
        name: "Suporte Técnico N1",
        role: "Suporte",
        status: "active",
        model: "Claude 3.5 Sonnet",
        prompt: "Você é um especialista em suporte técnico nível 1. Ajude os usuários a resolver problemas básicos de configuração e acesso. Seja paciente e didático. Se não souber a resposta, escale para o humano.",
        personalityId: "friendly",
    },
    {
        id: "faq",
        name: "FAQ Bot",
        role: "Info",
        status: "inactive",
        model: "GPT-3.5 Turbo",
        prompt: "Você responde apenas perguntas frequentes baseadas na base de conhecimento. Seja direto e conciso.",
        personalityId: "direct",
    },
];

// Mapping from backend brand_voice to frontend personalityId
const BRAND_VOICE_MAP: Record<string, string> = {
    "profissional": "professional",
    "amigavel": "friendly",
    "conversacional": "conversational",
    "direto": "direct",
    // Reverse mapping for safety
    "professional": "professional",
    "friendly": "friendly",
    "conversational": "conversational",
    "direct": "direct"
};

interface KnowledgeFile {
    filename: string;
    chunks: number;
    category: string;
}

export default function AgentsPage() {
    const [selectedAgentId, setSelectedAgentId] = useState(initialAgents[0].id);
    const [agents, setAgents] = useState(initialAgents);
    const [chatInput, setChatInput] = useState("");
    const [chatHistory, setChatHistory] = useState<{ role: string, content: string }[]>([]);
    const [activeTab, setActiveTab] = useState<"config" | "chat">("config");
    const [isUploading, setIsUploading] = useState(false);
    const [deletingFile, setDeletingFile] = useState<string | null>(null);
    const [knowledgeFiles, setKnowledgeFiles] = useState<KnowledgeFile[]>([]);
    const [isLoadingFiles, setIsLoadingFiles] = useState(true);
    const [showDeactivateConfirm, setShowDeactivateConfirm] = useState(false);
    const [pendingDeactivateId, setPendingDeactivateId] = useState<string | null>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);
    const { showToast } = useToast();
    const { tenantId } = useTenant();

    // Fetch knowledge base files on mount
    const fetchKnowledgeFiles = async () => {
        try {
            const res = await fetch(`http://127.0.0.1:8000/list-knowledge?tenant_id=${tenantId}`);
            if (res.ok) {
                const data = await res.json();
                if (data.success) {
                    setKnowledgeFiles(data.files);
                }
            }
        } catch (error) {
            console.error("Failed to fetch knowledge files:", error);
        } finally {
            setIsLoadingFiles(false);
        }
    };

    // Fetch tenant settings (status and personality)
    const fetchTenantSettings = async () => {
        try {
            const res = await fetch(`http://127.0.0.1:8000/tenant/${tenantId}`);
            if (res.ok) {
                const data = await res.json();
                if (data.success && data.data) {
                    const { active, brand_voice } = data.data;
                    const personalityId = BRAND_VOICE_MAP[brand_voice] || "professional";

                    // Update agents state to reflect real settings
                    setAgents(prev => prev.map(a => ({
                        ...a,
                        status: active ? "active" : "inactive",
                        personalityId: personalityId
                    })));
                }
            }
        } catch (error) {
            console.error("Failed to fetch tenant settings:", error);
        }
    };

    // biome-ignore lint/correctness/useExhaustiveDependencies: run once on mount
    React.useEffect(() => {
        if (tenantId) {
            fetchKnowledgeFiles();
            fetchTenantSettings();
        }
    }, [tenantId]);

    const selectedAgent = agents.find((a) => a.id === selectedAgentId) || agents[0];

    const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
        const file = event.target.files?.[0];
        if (!file) return;

        setIsUploading(true);
        const formData = new FormData();
        formData.append("file", file);
        formData.append("file", file);
        formData.append("tenant_id", tenantId);
        formData.append("category", "manual");

        try {
            const res = await fetch("http://127.0.0.1:8000/upload", {
                method: "POST",
                body: formData,
            });

            if (!res.ok) {
                const errData = await res.json();
                console.error("Upload Error:", errData);
                showToast("error", errData.detail || "Erro no upload");
                return;
            }

            const data = await res.json();
            console.log("Upload success:", data);

            // Refresh the files list from backend
            await fetchKnowledgeFiles();

            showToast("success", `Arquivo processado! ${data.chunks_created} chunks criados.`);
        } catch (error) {
            console.error("Upload failed:", error);
            showToast("error", "Falha no upload. Backend offline?");
        } finally {
            setIsUploading(false);
            // Reset file input
            if (fileInputRef.current) {
                fileInputRef.current.value = "";
            }
        }
    };

    const handleDeleteFile = async (filename: string) => {
        setDeletingFile(filename);

        try {
            const res = await fetch("http://127.0.0.1:8000/delete-knowledge", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    filename: filename,
                    tenant_id: tenantId
                })
            });

            const data = await res.json();

            if (!res.ok || !data.success) {
                showToast("error", data.message || "Erro ao excluir arquivo");
                return;
            }

            // Refresh the files list from backend
            await fetchKnowledgeFiles();

            showToast("success", `${filename} removido (${data.deleted_count} chunks)`);
        } catch (error) {
            console.error("Delete failed:", error);
            showToast("error", "Falha ao excluir. Backend offline?");
        } finally {
            setDeletingFile(null);
        }
    };

    const toggleAgentStatus = async (id: string) => {
        const agent = agents.find(a => a.id === id);
        if (!agent) return;

        const newStatus = agent.status === "active" ? false : true;

        // If deactivating, show confirmation dialog
        if (!newStatus) {
            setPendingDeactivateId(id);
            setShowDeactivateConfirm(true);
            return;
        }

        // Activating - proceed directly
        await performStatusChange(id, true);
    };

    const performStatusChange = async (id: string, newStatus: boolean) => {
        // Optimistic update
        setAgents(agents.map(a => a.id === id ? { ...a, status: newStatus ? "active" : "inactive" } : a));

        try {
            const res = await fetch("http://127.0.0.1:8000/update-tenant", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    tenant_id: tenantId,
                    active: newStatus
                })
            });

            if (!res.ok) {
                throw new Error("Failed to update status");
            }

            const data = await res.json();
            if (data.success) {
                showToast("success", `Agente ${newStatus ? "ativado" : "desativado"} com sucesso`);
            } else {
                throw new Error(data.message);
            }
        } catch (error) {
            console.error("Failed to update status:", error);
            showToast("error", "Erro ao atualizar status do agente");
            // Revert optimistic update
            setAgents(agents.map(a => a.id === id ? { ...a, status: !newStatus ? "active" : "inactive" } : a));
        }
    };

    const confirmDeactivate = async () => {
        if (pendingDeactivateId) {
            await performStatusChange(pendingDeactivateId, false);
        }
        setShowDeactivateConfirm(false);
        setPendingDeactivateId(null);
    };

    const cancelDeactivate = () => {
        setShowDeactivateConfirm(false);
        setPendingDeactivateId(null);
    };

    const handleAgentSelect = (id: string) => {
        setSelectedAgentId(id);
        if (window.innerWidth < 768) {
            setActiveTab("config");
        }
    };

    const handleSendMessage = async () => {
        if (!chatInput.trim()) return;

        const userMsg = { role: "user", content: chatInput };
        const newHistory = [...chatHistory, userMsg];
        setChatHistory(newHistory);
        setChatInput("");

        // Use sessionId from localStorage or create new one
        let sessionId = localStorage.getItem("playground_session_id");
        if (!sessionId) {
            sessionId = crypto.randomUUID().replace(/-/g, '');
            localStorage.setItem("playground_session_id", sessionId);
        }

        try {
            const res = await fetch("http://127.0.0.1:8000/chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    message: userMsg.content,
                    session_id: sessionId,
                    tenant_id: tenantId, // Dynamic Tenant
                    personality_id: (selectedAgent as any).personalityId || "professional",
                    is_playground: true // Bypass agent status check
                })
            });

            if (!res.ok) {
                const errData = await res.json();
                console.error("API Error Response:", errData);
                throw new Error(errData.detail || "API Error");
            }

            const data = await res.json();
            setChatHistory(prev => [...prev, { role: "agent", content: data.response }]);
        } catch (error) {
            console.error("Fetch error:", error);
            setChatHistory(prev => [...prev, { role: "agent", content: `Erro: ${(error as any).message}` }]);
        }
    };

    return (
        <div className="h-[calc(100vh-140px)] md:h-[calc(100vh-120px)] flex flex-col md:flex-row gap-6 relative">

            {/* Deactivate Confirmation Modal */}
            {showDeactivateConfirm && (
                <div
                    className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4 transition-opacity duration-300"
                    style={{ animation: 'fadeIn 0.2s ease-out' }}
                >
                    <div
                        className="bg-[#111113] border border-white/[0.08] rounded-2xl max-w-md w-full shadow-2xl"
                        style={{ animation: 'slideUp 0.3s ease-out' }}
                    >
                        <div className="p-6">
                            <div className="flex items-center gap-3 mb-4">
                                <div className="h-10 w-10 rounded-full bg-amber-500/10 flex items-center justify-center">
                                    <AlertTriangle className="h-5 w-5 text-amber-500" />
                                </div>
                                <h3 className="text-lg font-semibold text-white">Desativar Agente</h3>
                            </div>
                            <p className="text-sm text-zinc-400 leading-relaxed">
                                Ao desativar este agente, ele será desligado em <span className="text-zinc-200 font-medium">todos os canais integrados</span> onde está conectado (WhatsApp, Telegram, etc).
                            </p>
                            <p className="text-sm text-zinc-500 mt-3">
                                O Playground desta página continuará funcionando normalmente para testes.
                            </p>
                        </div>
                        <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-white/[0.06] bg-white/[0.02]">
                            <Button
                                variant="outline"
                                size="sm"
                                onClick={cancelDeactivate}
                                className="border-zinc-700 text-zinc-300 hover:bg-zinc-800"
                            >
                                Cancelar
                            </Button>
                            <Button
                                size="sm"
                                onClick={confirmDeactivate}
                                className="bg-red-600 hover:bg-red-500 text-white"
                            >
                                Desativar
                            </Button>
                        </div>
                    </div>
                </div>
            )}

            {/* Mobile Tab Navigation */}
            <div className="md:hidden flex items-center p-1 bg-white/[0.03] border border-white/[0.06] rounded-lg mb-2 shrink-0">

                <button
                    onClick={() => setActiveTab("config")}
                    className={cn(
                        "flex-1 py-1.5 text-[13px] font-medium rounded-md transition-all",
                        activeTab === "config" ? "bg-indigo-500 text-white shadow-sm" : "text-zinc-500"
                    )}
                >
                    Config
                </button>
                <button
                    onClick={() => setActiveTab("chat")}
                    className={cn(
                        "flex-1 py-1.5 text-[13px] font-medium rounded-md transition-all",
                        activeTab === "chat" ? "bg-indigo-500 text-white shadow-sm" : "text-zinc-500"
                    )}
                >
                    Chat
                </button>
            </div>



            {/* Middle: Configuration */}
            <div className={cn(
                "flex-1 min-w-0 flex-col gap-6 overflow-y-auto md:pr-2 pb-20 md:pb-0",
                "flex-1 min-w-0 flex-col gap-6 overflow-y-auto md:pr-2 pb-20 md:pb-0",
                activeTab === "config" ? "flex" : "hidden md:flex"
            )}>
                {/* Header */}
                <div className="flex items-center justify-between p-1">
                    <div>
                        <h1 className="text-xl md:text-2xl font-semibold text-white tracking-tight">{selectedAgent.name}</h1>
                    </div>

                    <div className="flex items-center gap-2 md:gap-3">
                        <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-white/[0.03] border border-white/[0.06]">
                            <span className="text-xs font-medium text-zinc-400 hidden sm:block">Status</span>
                            <button
                                onClick={() => toggleAgentStatus(selectedAgent.id)}
                                className={cn(
                                    "w-9 h-5 rounded-full p-0.5 transition-colors relative",
                                    selectedAgent.status === "active" ? "bg-emerald-500/20" : "bg-zinc-800"
                                )}
                            >
                                <div className={cn(
                                    "w-4 h-4 rounded-full shadow-sm transition-all transform",
                                    selectedAgent.status === "active" ? "translate-x-4 bg-emerald-500" : "translate-x-0 bg-zinc-500"
                                )} />
                            </button>
                        </div>
                    </div>
                </div>

                {/* Personality Section */}
                <Card>
                    <CardHeader className="pb-4">
                        <div className="flex items-center justify-between">
                            <div>
                                <CardTitle className="flex items-center gap-2">
                                    <Sparkles className="h-3 w-3 text-indigo-400" />
                                    Personalidade do Agente
                                </CardTitle>
                                <CardDescription className="mt-1">
                                    Escolha o tom de voz e estilo de comunicação do agente.
                                </CardDescription>
                            </div>
                        </div>
                    </CardHeader>
                    <CardContent>
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                            {[
                                {
                                    id: "professional",
                                    label: "Profissional",
                                    description: "Formal, eficiente e focado em resultados.",
                                    prompt: "Você é um assistente profissional e corporativo. Use linguagem formal, seja objetivo e priorize a eficiência. Evite gírias ou emojis excessivos."
                                },
                                {
                                    id: "friendly",
                                    label: "Simpático",
                                    description: "Amigável, acolhedor e usa emojis.",
                                    prompt: "Você é um assistente super amigável e acolhedor! Use emojis 😊, seja empático e faça o cliente se sentir especial. Use linguagem casual mas respeitosa."
                                },
                                {
                                    id: "conversational",
                                    label: "Conversacional",
                                    description: "Natural, como uma conversa no WhatsApp.",
                                    prompt: "Aja como se estivesse conversando com um amigo no WhatsApp. Seja natural, use frases curtas e diretas. Pode usar gírias leves se apropriado ao contexto."
                                },
                                {
                                    id: "direct",
                                    label: "Direto",
                                    description: "Respostas curtas e direto ao ponto.",
                                    prompt: "Seja extremamente conciso. Responda apenas o que foi perguntado, sem enrolação ou cumprimentos desnecessários. Foco total na informação."
                                }
                            ].map((personality) => (
                                <button
                                    key={personality.id}
                                    onClick={async () => {
                                        // Optimistic update
                                        setAgents(agents.map(a =>
                                            a.id === selectedAgentId ? { ...a, prompt: personality.prompt, personalityId: personality.id } : a
                                        ));

                                        try {
                                            const res = await fetch("http://127.0.0.1:8000/update-tenant", {
                                                method: "POST",
                                                headers: { "Content-Type": "application/json" },
                                                body: JSON.stringify({
                                                    tenant_id: tenantId,
                                                    brand_voice: personality.id
                                                })
                                            });

                                            if (!res.ok) throw new Error("Backend error");

                                            showToast("success", `Personalidade alterada para: ${personality.label}`);
                                        } catch (error) {
                                            console.error("Failed to update personality:", error);
                                            showToast("error", "Erro ao salvar personalidade");
                                        }
                                    }}
                                    className={cn(
                                        "flex flex-col items-start p-4 rounded-xl border transition-all text-left relative overflow-hidden group",
                                        (selectedAgent as any).personalityId === personality.id
                                            ? "bg-indigo-500/10 border-indigo-500/50 ring-1 ring-indigo-500/20"
                                            : "bg-[#050505] border-zinc-800 hover:border-zinc-700 hover:bg-zinc-900/50"
                                    )}
                                >
                                    <div className={cn(
                                        "absolute top-0 right-0 w-16 h-16 bg-gradient-to-br from-indigo-500/10 to-transparent blur-xl transition-opacity",
                                        (selectedAgent as any).personalityId === personality.id ? "opacity-100" : "opacity-0"
                                    )} />

                                    <span className={cn(
                                        "text-sm font-medium mb-1 relative z-10",
                                        (selectedAgent as any).personalityId === personality.id ? "text-indigo-400" : "text-zinc-200 group-hover:text-white"
                                    )}>
                                        {personality.label}
                                    </span>
                                    <span className="text-xs text-zinc-500 leading-relaxed relative z-10 group-hover:text-zinc-400">
                                        {personality.description}
                                    </span>
                                </button>
                            ))}
                        </div>
                    </CardContent>
                </Card>

                {/* RAG Section */}
                <Card>
                    <CardHeader className="pb-4">
                        <div className="flex items-center justify-between">
                            <div>
                                <CardTitle className="flex items-center gap-2">
                                    <FileText className="h-3 w-3 text-indigo-400" />
                                    Base de Conhecimento (RAG)
                                </CardTitle>
                                <CardDescription className="mt-1">
                                    Documentos que o agente utilizará para responder perguntas.
                                </CardDescription>
                            </div>
                            <input
                                type="file"
                                ref={fileInputRef}
                                onChange={handleFileUpload}
                                accept=".pdf,.docx,.doc,.txt"
                                className="hidden"
                            />
                            <Button
                                variant="outline"
                                size="sm"
                                className="h-8 text-xs border-dashed border-zinc-700 bg-transparent hover:bg-zinc-900"
                                onClick={() => fileInputRef.current?.click()}
                                disabled={isUploading}
                            >
                                {isUploading ? (
                                    <>
                                        <Loader2 className="h-3 w-3 mr-2 animate-spin" />
                                        Processando...
                                    </>
                                ) : (
                                    <>
                                        <Upload className="h-3 w-3 mr-2" />
                                        Upload Arquivo
                                    </>
                                )}
                            </Button>
                        </div>
                    </CardHeader>
                    <CardContent>
                        <div className="space-y-2">
                            {isLoadingFiles ? (
                                <div className="flex items-center justify-center py-4">
                                    <Loader2 className="h-5 w-5 animate-spin text-zinc-500" />
                                </div>
                            ) : knowledgeFiles.length === 0 ? (
                                <p className="text-sm text-zinc-500 text-center py-4">Nenhum arquivo carregado</p>
                            ) : (
                                knowledgeFiles.map((file, i) => (
                                    <div key={file.filename} className="flex items-center justify-between p-3 rounded-lg bg-[#050505] border border-zinc-800 group hover:border-zinc-700 transition-colors">
                                        <div className="flex items-center gap-3">
                                            <div className="h-8 w-8 rounded bg-indigo-500/10 flex items-center justify-center">
                                                <FileText className="h-4 w-4 text-indigo-400" />
                                            </div>
                                            <div>
                                                <p className="text-sm font-medium text-zinc-300 truncate max-w-[150px] md:max-w-none">{file.filename}</p>
                                                <p className="text-[10px] text-zinc-600 uppercase tracking-wider">{file.chunks} chunks</p>
                                            </div>
                                        </div>
                                        <Button
                                            variant="ghost"
                                            size="icon"
                                            className="h-8 w-8 text-zinc-600 hover:text-red-400 hover:bg-red-400/10 opacity-0 group-hover:opacity-100 transition-all"
                                            onClick={() => handleDeleteFile(file.filename)}
                                            disabled={deletingFile === file.filename}
                                        >
                                            {deletingFile === file.filename ? (
                                                <Loader2 className="h-4 w-4 animate-spin" />
                                            ) : (
                                                <Trash2 className="h-4 w-4" />
                                            )}
                                        </Button>
                                    </div>
                                ))
                            )}
                        </div>
                    </CardContent>
                </Card>
            </div>

            {/* Right: Playground */}
            <div className={cn(
                "w-full md:w-[360px] shrink-0 flex-col bg-[#0b0b0d] border border-white/[0.06] rounded-2xl overflow-hidden shadow-2xl transition-all",
                activeTab === "chat" ? "flex h-full" : "hidden md:flex"
            )}>
                <div className="h-12 border-b border-white/[0.06] flex items-center justify-between px-4 bg-[#111113]">
                    <div className="flex items-center gap-2">
                        <MessageSquare className="h-4 w-4 text-indigo-400" />
                        <span className="text-xs font-medium text-zinc-300 text-sm">Playground</span>
                    </div>
                    <span className="text-[10px] text-zinc-600 uppercase tracking-wider px-2 py-0.5 rounded bg-white/[0.03]">
                        Preview
                    </span>
                </div>

                {/* Chat Messages */}
                <div className="flex-1 p-4 overflow-y-auto space-y-4 bg-[#0b0b0d]">
                    {chatHistory.map((msg, idx) => (
                        <div key={idx} className={cn(
                            "flex gap-3 text-sm animate-in slide-in-from-bottom-2 duration-300",
                            msg.role === "user" ? "flex-row-reverse" : ""
                        )}>
                            <div className={cn(
                                "flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold mt-1",
                                msg.role === "agent" ? "bg-indigo-500 text-white" : "bg-zinc-700 text-zinc-300"
                            )}>
                                {msg.role === "agent" ? "A" : "U"}
                            </div>
                            <div className={cn(
                                "rounded-2xl px-4 py-2.5 max-w-[85%] leading-relaxed",
                                msg.role === "agent"
                                    ? "bg-[#161618] text-zinc-300 border border-white/[0.04] rounded-tl-none"
                                    : "bg-indigo-600 text-white rounded-tr-none shadow-lg shadow-indigo-500/10"
                            )}>
                                {msg.content}
                            </div>
                        </div>
                    ))}
                </div>

                {/* Input Area */}
                <div className="p-4 bg-[#111113] border-t border-white/[0.06]">
                    <div className="relative">
                        <input
                            type="text"
                            value={chatInput}
                            onChange={(e) => setChatInput(e.target.value)}
                            onKeyDown={(e) => e.key === 'Enter' && handleSendMessage()}
                            placeholder="Teste seu agente..."
                            className="w-full bg-[#050505] border border-zinc-800 text-sm text-white rounded-xl pl-4 pr-10 py-3 focus:outline-none focus:border-indigo-500/50 focus:ring-1 focus:ring-indigo-500/20 placeholder:text-zinc-600"
                        />
                        <button
                            onClick={handleSendMessage}
                            className="absolute right-2 top-1/2 -translate-y-1/2 h-7 w-7 flex items-center justify-center rounded-lg bg-indigo-500 text-white hover:bg-indigo-600 transition-colors"
                        >
                            <Send className="h-3.5 w-3.5" />
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
}
