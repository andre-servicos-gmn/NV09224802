"use client";

import { useState } from "react";
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
} from "lucide-react";
import { cn } from "@/lib/utils";

// Mock data
const mockAgents = [
    {
        id: "sales",
        name: "Consultor de Vendas",
        role: "Vendas",
        status: "active",
        model: "GPT-4 Turbo",
        prompt: "Você é um consultor de vendas experiente e persuasivo da Nouva. Seu objetivo é entender as necessidades do cliente e oferecer a melhor solução de IA para o negócio dele. Seja profissional, mas amigável. Sempre foque no ROI.",
        files: ["catalogo_produtos_2024.pdf", "precos_q1.pdf"],
    },
    {
        id: "support",
        name: "Suporte Técnico N1",
        role: "Suporte",
        status: "active",
        model: "Claude 3.5 Sonnet",
        prompt: "Você é um especialista em suporte técnico nível 1. Ajude os usuários a resolver problemas básicos de configuração e acesso. Seja paciente e didático. Se não souber a resposta, escale para o humano.",
        files: ["manual_usuario.pdf", "troubleshooting_guide.pdf"],
    },
    {
        id: "faq",
        name: "FAQ Bot",
        role: "Info",
        status: "inactive",
        model: "GPT-3.5 Turbo",
        prompt: "Você responde apenas perguntas frequentes baseadas na base de conhecimento. Seja direto e conciso.",
        files: ["faq_site.pdf"],
    },
];

export default function AgentsPage() {
    const [selectedAgentId, setSelectedAgentId] = useState(mockAgents[0].id);
    const [agents, setAgents] = useState(mockAgents);
    const [chatInput, setChatInput] = useState("");
    const [chatHistory, setChatHistory] = useState([
        { role: "agent", content: "Olá! Como posso ajudar você hoje?" },
    ]);
    const [activeTab, setActiveTab] = useState<"list" | "config" | "chat">("list");

    const selectedAgent = agents.find((a) => a.id === selectedAgentId) || agents[0];

    const toggleAgentStatus = (id: string) => {
        setAgents(agents.map(agent => {
            if (agent.id === id) {
                return { ...agent, status: agent.status === "active" ? "inactive" : "active" };
            }
            return agent;
        }));
    };

    const handleAgentSelect = (id: string) => {
        setSelectedAgentId(id);
        if (window.innerWidth < 768) {
            setActiveTab("config");
        }
    };

    const handleSendMessage = () => {
        if (!chatInput.trim()) return;

        const newHistory = [...chatHistory, { role: "user", content: chatInput }];
        setChatHistory(newHistory);
        setChatInput("");

        // Simulate response
        setTimeout(() => {
            setChatHistory([
                ...newHistory,
                { role: "agent", content: "Esta é uma resposta simulada do agente baseada no seu input." }
            ]);
        }, 1000);
    };

    return (
        <div className="h-[calc(100vh-140px)] md:h-[calc(100vh-120px)] flex flex-col md:flex-row gap-6 relative">

            {/* Mobile Tab Navigation */}
            <div className="md:hidden flex items-center p-1 bg-white/[0.03] border border-white/[0.06] rounded-lg mb-2 shrink-0">
                <button
                    onClick={() => setActiveTab("list")}
                    className={cn(
                        "flex-1 py-1.5 text-[13px] font-medium rounded-md transition-all",
                        activeTab === "list" ? "bg-indigo-500 text-white shadow-sm" : "text-zinc-500"
                    )}
                >
                    Agentes
                </button>
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

            {/* Left Sidebar: Agent List */}
            <div className={cn(
                "w-full md:w-[280px] shrink-0 flex flex-col gap-4 transition-all",
                activeTab === "list" ? "flex" : "hidden md:flex"
            )}>
                <div className="flex items-center justify-between px-2">
                    <h2 className="text-sm font-medium text-zinc-400">Seus Agentes</h2>
                    <Button variant="ghost" size="icon" className="h-8 w-8 text-zinc-400">
                        <Bot className="h-4 w-4" />
                    </Button>
                </div>

                <div className="space-y-2 overflow-y-auto no-scrollbar md:pr-2 pb-20 md:pb-0">
                    {agents.map((agent) => (
                        <div
                            key={agent.id}
                            onClick={() => handleAgentSelect(agent.id)}
                            className={cn(
                                "group relative p-3 rounded-xl border transition-all cursor-pointer hover:shadow-lg",
                                selectedAgentId === agent.id
                                    ? "bg-[#161618] border-indigo-500/20 shadow-[0_4px_20px_-4px_rgba(99,102,241,0.1)]"
                                    : "bg-[#0b0b0d] border-transparent hover:border-white/[0.06] hover:bg-[#121214]"
                            )}
                        >
                            <div className="flex items-center justify-between mb-2">
                                <span className={cn(
                                    "text-[10px] uppercase font-bold tracking-wider px-1.5 py-0.5 rounded-md",
                                    selectedAgentId === agent.id
                                        ? "bg-indigo-500/10 text-indigo-400"
                                        : "bg-white/[0.04] text-zinc-500"
                                )}>
                                    {agent.role}
                                </span>
                                <div className={cn(
                                    "h-2 w-2 rounded-full shadow-[0_0_8px_rgba(0,0,0,0.5)]",
                                    agent.status === "active" ? "bg-emerald-500 shadow-emerald-500/20" : "bg-zinc-700"
                                )} />
                            </div>
                            <h3 className={cn(
                                "font-medium text-sm mb-1",
                                selectedAgentId === agent.id ? "text-white" : "text-zinc-400 group-hover:text-zinc-200"
                            )}>
                                {agent.name}
                            </h3>
                            <p className="text-[11px] text-zinc-600 truncate">
                                {agent.model}
                            </p>
                        </div>
                    ))}

                    <button className="w-full py-3 rounded-xl border border-dashed border-zinc-800 text-zinc-600 text-sm font-medium hover:bg-white/[0.02] hover:border-zinc-700 hover:text-zinc-400 transition-all flex items-center justify-center gap-2">
                        + Novo Agente
                    </button>
                </div>
            </div>

            {/* Middle: Configuration */}
            <div className={cn(
                "flex-1 min-w-0 flex-col gap-6 overflow-y-auto md:pr-2 pb-20 md:pb-0",
                activeTab === "config" ? "flex" : "hidden md:flex"
            )}>
                {/* Header */}
                <div className="flex items-center justify-between p-1">
                    <div>
                        <h1 className="text-xl md:text-2xl font-semibold text-white tracking-tight">{selectedAgent.name}</h1>
                        <p className="text-sm text-zinc-500 flex items-center gap-2 mt-1">
                            <span className="w-2 h-2 rounded-full bg-indigo-500"></span>
                            {selectedAgent.model}
                        </p>
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
                        <Button variant="outline" size="icon" className="h-9 w-9 border-white/[0.06] bg-transparent text-zinc-400 hover:text-white">
                            <Settings2 className="h-4 w-4" />
                        </Button>
                    </div>
                </div>

                {/* Prompt Section */}
                <Card>
                    <CardHeader className="pb-4">
                        <div className="flex items-center justify-between">
                            <div>
                                <CardTitle className="flex items-center gap-2">
                                    <Sparkles className="h-3 w-3 text-indigo-400" />
                                    Prompt do Sistema
                                </CardTitle>
                                <CardDescription className="mt-1">
                                    Defina a personalidade, tom de voz e regras de comportamento.
                                </CardDescription>
                            </div>
                        </div>
                    </CardHeader>
                    <CardContent>
                        <textarea
                            className="w-full h-[200px] bg-[#050505] border border-zinc-800 rounded-lg p-4 text-sm text-zinc-300 focus:outline-none focus:border-indigo-500/50 focus:ring-1 focus:ring-indigo-500/20 resize-none font-mono leading-relaxed"
                            defaultValue={selectedAgent.prompt}
                        />
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
                            <Button variant="outline" size="sm" className="h-8 text-xs border-dashed border-zinc-700 bg-transparent hover:bg-zinc-900">
                                <Upload className="h-3 w-3 mr-2" />
                                Upload PDF
                            </Button>
                        </div>
                    </CardHeader>
                    <CardContent>
                        <div className="space-y-2">
                            {selectedAgent.files.map((file, i) => (
                                <div key={i} className="flex items-center justify-between p-3 rounded-lg bg-[#050505] border border-zinc-800 group hover:border-zinc-700 transition-colors">
                                    <div className="flex items-center gap-3">
                                        <div className="h-8 w-8 rounded bg-indigo-500/10 flex items-center justify-center">
                                            <FileText className="h-4 w-4 text-indigo-400" />
                                        </div>
                                        <div>
                                            <p className="text-sm font-medium text-zinc-300 truncate max-w-[150px] md:max-w-none">{file}</p>
                                            <p className="text-[10px] text-zinc-600 uppercase tracking-wider">Processado</p>
                                        </div>
                                    </div>
                                    <Button variant="ghost" size="icon" className="h-8 w-8 text-zinc-600 hover:text-red-400 hover:bg-red-400/10 opacity-0 group-hover:opacity-100 transition-all">
                                        <Trash2 className="h-4 w-4" />
                                    </Button>
                                </div>
                            ))}
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
