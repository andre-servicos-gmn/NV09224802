"use client";

import { MetricsChart } from "@/components/metrics-chart";
import { HeatmapTable } from "@/components/heatmap-table";
import {
    Circle,
    ArrowUpRight,
    TrendingUp,
    ShieldCheck,
    Coins,
} from "lucide-react";

// Mock Data
const sentimentData = [
    { name: "00h", value: 82 },
    { name: "04h", value: 85 },
    { name: "08h", value: 78 },
    { name: "12h", value: 65 }, // Queda no horário de pico
    { name: "16h", value: 72 },
    { name: "20h", value: 89 },
    { name: "23h", value: 91 },
];

const topicData = [
    { topic: "Reset de Senha", count: 1245, sentiment: 95 },
    { topic: "Status do Pedido", count: 856, sentiment: 88 },
    { topic: "Reembolso / Estorno", count: 642, sentiment: 45 }, // Sentimento baixo
    { topic: "Problema no Login", count: 520, sentiment: 60 },
    { topic: "Dúvidas de Plano", count: 320, sentiment: 92 },
    { topic: "Integração API", count: 154, sentiment: 78 },
];

export default function MetricsPage() {
    return (
        <div className="space-y-8 md:space-y-12">
            {/* Header */}
            <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 md:gap-0">
                <div>
                    <h1 className="text-2xl md:text-[28px] font-medium text-white tracking-tight">
                        Métricas Avançadas
                    </h1>
                    <p className="text-[13px] text-[#555] mt-1">
                        Qualidade, economia e insights de atendimento
                    </p>
                </div>
                <div className="flex items-center gap-2 text-[12px] text-indigo-400">
                    <Circle className="h-2 w-2 fill-current" />
                    <span>Tempo Real</span>
                </div>
            </div>

            {/* Hero Metric: Deflection Rate */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 md:gap-8">
                <div className="md:col-span-2 relative overflow-hidden rounded-2xl bg-[#08080a] border border-white/[0.06] p-6 md:p-8">
                    <div className="absolute top-0 right-0 w-64 h-64 bg-emerald-500/10 blur-[100px] pointer-events-none" />

                    <div className="relative z-10 flex flex-col md:flex-row md:items-start justify-between gap-8 md:gap-0">
                        <div>
                            <div className="flex items-center gap-2 mb-4">
                                <ShieldCheck className="h-5 w-5 text-emerald-400" />
                                <span className="text-label text-emerald-400/80">Taxa de Deflexão Real</span>
                            </div>

                            <div className="flex items-baseline gap-4">
                                <span className="text-[56px] md:text-[64px] font-light tracking-tighter text-white">
                                    84.2%
                                </span>
                                <span className="text-sm font-medium text-emerald-400 flex items-center gap-1 bg-emerald-500/10 px-2 py-1 rounded-full border border-emerald-500/20">
                                    <ArrowUpRight className="h-3 w-3" />
                                    +5.4%
                                </span>
                            </div>

                            <p className="max-w-full md:max-w-[80%] text-[14px] text-zinc-500 mt-4 leading-relaxed">
                                De todos os tickets abertos, a Inteligência Artificial resolveu <strong className="text-zinc-200">84.2%</strong> totalmente sozinha, sem intervenção humana.
                            </p>
                        </div>

                        <div className="md:text-right pt-4 md:pt-0 border-t md:border-t-0 border-white/[0.06]">
                            <div className="flex items-center gap-2 mb-2 md:justify-end">
                                <Coins className="h-4 w-4 text-[#eab308]" />
                                <span className="text-label text-[#eab308]">Economia Estimada</span>
                            </div>
                            <p className="text-[32px] font-light text-white tracking-tight">R$ 14.5k</p>
                            <p className="text-[12px] text-zinc-600">neste mês</p>
                        </div>
                    </div>
                </div>

                {/* Secondary Stat: TMA */}
                <div className="rounded-2xl bg-[#08080a] border border-white/[0.06] p-6 md:p-8 flex flex-col justify-center">
                    <span className="text-label mb-4">Tempo de Resolução (TMA)</span>
                    <div className="flex items-baseline gap-2">
                        <span className="text-[48px] font-light text-white tracking-tighter">1m 12s</span>
                    </div>
                    <div className="mt-4 p-3 rounded-lg bg-white/[0.03] text-[12px] text-zinc-400">
                        <div className="flex justify-between mb-1">
                            <span>Humano</span>
                            <span>12m 30s</span>
                        </div>
                        <div className="w-full h-1 bg-zinc-800 rounded-full overflow-hidden">
                            <div className="w-full h-full bg-zinc-600" />
                        </div>

                        <div className="flex justify-between mt-3 mb-1">
                            <span className="text-indigo-400">IA Nouva</span>
                            <span className="text-indigo-400">1m 12s</span>
                        </div>
                        <div className="w-full h-1 bg-zinc-800 rounded-full overflow-hidden">
                            <div className="w-[10%] h-full bg-indigo-500" />
                        </div>
                    </div>
                </div>
            </div>

            {/* Content Grid */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 md:gap-8">
                {/* Sentiment Chart */}
                <div className="spotlight-card p-6 md:p-8">
                    <div className="flex items-center justify-between mb-6">
                        <div>
                            <h3 className="text-label flex items-center gap-2">
                                <TrendingUp className="h-4 w-4 text-indigo-400" />
                                Análise de Sentimento (CSAT)
                            </h3>
                            <p className="text-[12px] text-zinc-500 mt-1">Humor médio do cliente durante a conversa</p>
                        </div>
                        <div className="text-right">
                            <span className="text-2xl font-light text-white">78/100</span>
                        </div>
                    </div>

                    <div className="h-[250px] -ml-4">
                        <MetricsChart
                            title="Sentimento Hoje"
                            data={sentimentData}
                            color="#818cf8"
                            glowColor="rgba(129, 140, 248, 0.2)"
                        />
                    </div>

                    <div className="mt-4 p-3 rounded-lg border border-amber-500/20 bg-amber-500/5 flex items-start gap-3">
                        <div className="h-1.5 w-1.5 rounded-full bg-amber-500 mt-1.5 shrink-0" />
                        <p className="text-[12px] text-amber-200/80">
                            <strong>Insight:</strong> Queda de sentimento detectada às 12h. Tópico correlacionado: "Reembolso". Sugerimos revisar o prompt para ser mais empático em negativas de estorno.
                        </p>
                    </div>
                </div>

                {/* Topic Heatmap */}
                <div className="spotlight-card p-6 md:p-8">
                    <HeatmapTable
                        title="Mapa de Tópicos (Heatmap)"
                        data={topicData}
                    />
                </div>
            </div>
        </div>
    );
}
