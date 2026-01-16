"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
    CardFooter,
} from "@/components/ui/card";
import {
    User,
    Building,
    CreditCard,
    Users,
    Mail,
    Shield,
    Check,
    Upload,
    LogOut,
} from "lucide-react";
import { cn } from "@/lib/utils";

const tabs = [
    { id: "general", label: "Geral", icon: Building },
    { id: "team", label: "Equipe", icon: Users },
    { id: "billing", label: "Faturamento", icon: CreditCard },
];

export default function SettingsPage() {
    const [activeTab, setActiveTab] = useState("general");

    return (
        <div className="flex flex-col md:flex-row gap-8 min-h-[calc(100vh-120px)]">
            {/* Sidebar Navigation */}
            <aside className="w-full md:w-[240px] shrink-0">
                <div className="sticky top-24 space-y-1">
                    <h2 className="px-4 text-xs font-semibold text-zinc-500 uppercase tracking-wider mb-2">
                        Configurações
                    </h2>

                    {/* Mobile Horizontal Scroll */}
                    <div className="flex md:flex-col overflow-x-auto md:overflow-visible gap-1 pb-2 md:pb-0">
                        {tabs.map((tab) => {
                            const isActive = activeTab === tab.id;
                            const Icon = tab.icon;
                            return (
                                <button
                                    key={tab.id}
                                    onClick={() => setActiveTab(tab.id)}
                                    className={cn(
                                        "flex items-center gap-3 px-4 py-2 text-sm font-medium rounded-lg transition-all whitespace-nowrap md:whitespace-normal flex-1 md:flex-none",
                                        isActive
                                            ? "bg-indigo-500/10 text-indigo-400"
                                            : "text-zinc-400 hover:text-zinc-200 hover:bg-white/[0.03]"
                                    )}
                                >
                                    <Icon className="h-4 w-4" />
                                    {tab.label}
                                </button>
                            );
                        })}
                    </div>
                </div>
            </aside>

            {/* Main Content Area */}
            <main className="flex-1 max-w-4xl space-y-6">

                {/* GENERAL TAB */}
                {activeTab === "general" && (
                    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
                        <div>
                            <h1 className="text-2xl font-semibold text-white tracking-tight">Geral</h1>
                            <p className="text-sm text-zinc-500 mt-1">Gerencie as informações da sua conta e organização.</p>
                        </div>

                        {/* Organization Profile */}
                        <Card>
                            <CardHeader>
                                <CardTitle className="text-base">Perfil da Organização</CardTitle>
                                <CardDescription>Como sua empresa aparece no sistema.</CardDescription>
                            </CardHeader>
                            <CardContent className="space-y-4">
                                <div className="flex items-center gap-6">
                                    <div className="h-20 w-20 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-2xl font-bold text-white shadow-lg shadow-indigo-500/20">
                                        N
                                    </div>
                                    <div className="space-y-2">
                                        <Button variant="outline" size="sm" className="h-9">
                                            <Upload className="h-3.5 w-3.5 mr-2" />
                                            Alterar Logo
                                        </Button>
                                        <p className="text-xs text-zinc-500">Recomendado: 400x400px, PNG ou JPG.</p>
                                    </div>
                                </div>
                                <div className="grid gap-4 md:grid-cols-2">
                                    <div className="space-y-2">
                                        <label className="text-xs font-medium text-zinc-400">Nome da Empresa</label>
                                        <Input defaultValue="Nouvaris Tecnologia" />
                                    </div>
                                    <div className="space-y-2">
                                        <label className="text-xs font-medium text-zinc-400">Website</label>
                                        <Input defaultValue="https://nouvaris.com" />
                                    </div>
                                </div>
                            </CardContent>
                            <CardFooter className="border-t border-white/[0.06] py-3 bg-white/[0.01]">
                                <Button size="sm" className="bg-indigo-600 hover:bg-indigo-500 text-white ml-auto">
                                    Salvar Alterações
                                </Button>
                            </CardFooter>
                        </Card>

                        {/* Personal Profile */}
                        <Card>
                            <CardHeader>
                                <CardTitle className="text-base">Seu Perfil</CardTitle>
                                <CardDescription>Suas informações pessoais de acesso.</CardDescription>
                            </CardHeader>
                            <CardContent className="space-y-4">
                                <div className="grid gap-4 md:grid-cols-2">
                                    <div className="space-y-2">
                                        <label className="text-xs font-medium text-zinc-400">Nome Completo</label>
                                        <Input defaultValue="Admin User" />
                                    </div>
                                    <div className="space-y-2">
                                        <label className="text-xs font-medium text-zinc-400">Email</label>
                                        <Input defaultValue="admin@nouvaris.com" disabled className="opacity-50" />
                                    </div>
                                </div>
                            </CardContent>
                        </Card>
                    </div>
                )}

                {/* TEAM TAB */}
                {activeTab === "team" && (
                    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
                        <div className="flex items-center justify-between">
                            <div>
                                <h1 className="text-2xl font-semibold text-white tracking-tight">Equipe</h1>
                                <p className="text-sm text-zinc-500 mt-1">Gerencie quem tem acesso ao workspace.</p>
                            </div>
                            <Button className="bg-indigo-600 hover:bg-indigo-500">
                                <Users className="h-4 w-4 mr-2" />
                                Convidar Membro
                            </Button>
                        </div>

                        <Card>
                            <CardContent className="p-0">
                                {[
                                    { name: "Admin User", email: "admin@nouvaris.com", role: "Proprietário", status: "Ativo" },
                                    { name: "Lucas Dev", email: "lucas@nouvaris.com", role: "Admin", status: "Ativo" },
                                    { name: "Sarah Design", email: "sarah@nouvaris.com", role: "Editor", status: "Pendente" },
                                ].map((member, i) => (
                                    <div key={i} className="flex items-center justify-between p-4 border-b last:border-0 border-white/[0.06] hover:bg-white/[0.02] transition-colors">
                                        <div className="flex items-center gap-3">
                                            <div className="h-10 w-10 rounded-full bg-zinc-800 flex items-center justify-center text-zinc-400 font-medium text-sm">
                                                {member.name.substring(0, 2).toUpperCase()}
                                            </div>
                                            <div>
                                                <p className="text-sm font-medium text-white">{member.name}</p>
                                                <p className="text-[11px] text-zinc-500">{member.email}</p>
                                            </div>
                                        </div>
                                        <div className="flex items-center gap-4">
                                            <span className="text-xs text-zinc-400 bg-white/[0.05] px-2 py-1 rounded-md border border-white/[0.05]">
                                                {member.role}
                                            </span>
                                            <span className={cn(
                                                "text-[10px] font-medium px-2 py-1 rounded-full",
                                                member.status === "Ativo" ? "bg-emerald-500/10 text-emerald-400" : "bg-amber-500/10 text-amber-400"
                                            )}>
                                                {member.status}
                                            </span>
                                            <Button variant="ghost" size="icon" className="h-8 w-8 text-zinc-500 hover:text-red-400">
                                                <LogOut className="h-4 w-4" />
                                            </Button>
                                        </div>
                                    </div>
                                ))}
                            </CardContent>
                        </Card>
                    </div>
                )}

                {/* BILLING TAB */}
                {activeTab === "billing" && (
                    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
                        <div>
                            <h1 className="text-2xl font-semibold text-white tracking-tight">Faturamento</h1>
                            <p className="text-sm text-zinc-500 mt-1">Detalhes do seu plano e uso de recursos.</p>
                        </div>

                        <div className="grid gap-6 md:grid-cols-2">
                            {/* Current Plan */}
                            <Card className="border-indigo-500/20 bg-indigo-500/[0.03]">
                                <CardHeader>
                                    <div className="flex items-start justify-between">
                                        <div>
                                            <CardTitle className="text-indigo-400">Plano Enterprise</CardTitle>
                                            <CardDescription>Cobrança mensal</CardDescription>
                                        </div>
                                        <span className="bg-indigo-500 text-white text-[10px] font-bold px-2 py-1 rounded uppercase tracking-wider">
                                            Ativo
                                        </span>
                                    </div>
                                </CardHeader>
                                <CardContent>
                                    <div className="text-3xl font-light text-white mb-1">R$ 899,00<span className="text-sm text-zinc-500 font-normal">/mês</span></div>
                                    <p className="text-xs text-zinc-400">Próxima cobrança em 01 Fev, 2026</p>
                                </CardContent>
                                <CardFooter>
                                    <Button variant="outline" className="w-full border-indigo-500/30 text-indigo-300 hover:text-white hover:bg-indigo-500">
                                        Gerenciar Assinatura
                                    </Button>
                                </CardFooter>
                            </Card>

                            {/* Usage Stats (Mock) */}
                            <Card>
                                <CardHeader>
                                    <CardTitle className="text-base">Uso do Workspace</CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-6">
                                    <div className="space-y-2">
                                        <div className="flex justify-between text-xs">
                                            <span className="text-zinc-400">Mensagens IA / Mês</span>
                                            <span className="text-white">14.5k / 50k</span>
                                        </div>
                                        <div className="h-2 w-full bg-zinc-800 rounded-full overflow-hidden">
                                            <div className="h-full bg-indigo-500 w-[29%]" />
                                        </div>
                                    </div>

                                    <div className="space-y-2">
                                        <div className="flex justify-between text-xs">
                                            <span className="text-zinc-400">Armazenamento (RAG)</span>
                                            <span className="text-white">2.1 GB / 10 GB</span>
                                        </div>
                                        <div className="h-2 w-full bg-zinc-800 rounded-full overflow-hidden">
                                            <div className="h-full bg-violet-600 w-[21%]" />
                                        </div>
                                    </div>

                                    <div className="space-y-2">
                                        <div className="flex justify-between text-xs">
                                            <span className="text-zinc-400">Membros da Equipe</span>
                                            <span className="text-white">5 / Illimitado</span>
                                        </div>
                                        <div className="h-2 w-full bg-zinc-800 rounded-full overflow-hidden">
                                            <div className="h-full bg-emerald-500 w-[5%]" />
                                        </div>
                                    </div>
                                </CardContent>
                            </Card>
                        </div>

                        <Card>
                            <CardHeader>
                                <CardTitle className="text-base">Histórico de Faturas</CardTitle>
                            </CardHeader>
                            <CardContent className="p-0">
                                {[
                                    { date: "01 Jan, 2026", amount: "R$ 899,00", status: "Pago" },
                                    { date: "01 Dez, 2025", amount: "R$ 899,00", status: "Pago" },
                                    { date: "01 Nov, 2025", amount: "R$ 899,00", status: "Pago" },
                                ].map((invoice, i) => (
                                    <div key={i} className="flex items-center justify-between p-4 border-b last:border-0 border-white/[0.06]">
                                        <div className="flex items-center gap-3">
                                            <div className="h-8 w-8 rounded bg-white/[0.05] flex items-center justify-center">
                                                <FileText className="h-4 w-4 text-zinc-400" />
                                            </div>
                                            <div>
                                                <p className="text-sm font-medium text-zinc-300">Fatura Mensal</p>
                                                <p className="text-[10px] text-zinc-500">{invoice.date}</p>
                                            </div>
                                        </div>
                                        <div className="flex items-center gap-4">
                                            <span className="text-sm font-medium text-white">{invoice.amount}</span>
                                            <div className="flex items-center gap-1 text-[10px] font-bold text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded uppercase tracking-wider">
                                                <Check className="h-3 w-3" />
                                                {invoice.status}
                                            </div>
                                            <Button variant="ghost" size="icon" className="h-8 w-8 text-zinc-500">
                                                <Upload className="h-4 w-4 rotate-180" /> {/* Download icon shim */}
                                            </Button>
                                        </div>
                                    </div>
                                ))}
                            </CardContent>
                        </Card>
                    </div>
                )}
            </main>
        </div>
    );
}

function FileText({ className }: { className?: string }) {
    return (
        <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            className={className}
        >
            <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z" />
            <polyline points="14 2 14 8 20 8" />
            <line x1="16" x2="8" y1="13" y2="13" />
            <line x1="16" x2="8" y1="17" y2="17" />
            <line x1="10" x2="8" y1="9" y2="9" />
        </svg>
    );
}
