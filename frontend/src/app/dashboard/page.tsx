"use client";

import { StatsCard } from "@/components/stats-card";
import { MetricsChart } from "@/components/metrics-chart";
import {
    ArrowUpRight,
} from "lucide-react";

// Mock data
const conversationsData = [
    { name: "Seg", value: 120 },
    { name: "Ter", value: 145 },
    { name: "Qua", value: 132 },
    { name: "Qui", value: 178 },
    { name: "Sex", value: 156 },
    { name: "Sáb", value: 89 },
    { name: "Dom", value: 67 },
];

const resolutionData = [
    { name: "Seg", value: 85 },
    { name: "Ter", value: 88 },
    { name: "Qua", value: 82 },
    { name: "Qui", value: 91 },
    { name: "Sex", value: 87 },
    { name: "Sáb", value: 93 },
    { name: "Dom", value: 95 },
];

export default function DashboardPage() {
    return (
        <div className="space-y-12">
            {/* Header - minimal */}
            <div className="flex items-end justify-between">
                <div>
                    <h1 className="text-[28px] font-medium text-white tracking-tight">
                        Dashboard
                    </h1>
                    <p className="text-[13px] text-[#555] mt-1">
                        Visão geral · Últimos 7 dias
                    </p>
                </div>
            </div>

            {/* Metrics Row - no boxes, just typography and dividers */}
            <div className="flex flex-col md:flex-row items-start gap-8 md:gap-0">
                {/* Metric 1 */}
                <div className="flex-1 w-full md:pr-8 border-b md:border-b-0 border-white/[0.06] pb-6 md:pb-0">
                    <span className="text-label">Vendas IA</span>
                    <div className="mt-3 flex items-baseline gap-3">
                        <span className="font-mono text-[42px] font-light tracking-tight text-white">
                            R$ 847<span className="text-[28px] text-[#555]">k</span>
                        </span>
                        <span className="text-[12px] font-medium text-emerald-400 flex items-center gap-0.5">
                            <ArrowUpRight className="h-3 w-3" />
                            23.4%
                        </span>
                    </div>
                    <p className="text-[12px] text-[#444] mt-1">gerado pela IA</p>
                </div>

                {/* Divider */}
                <div className="hidden md:block w-px h-20 bg-gradient-to-b from-transparent via-white/10 to-transparent" />

                {/* Metric 2 */}
                <div className="flex-1 w-full md:px-8 border-b md:border-b-0 border-white/[0.06] pb-6 md:pb-0">
                    <span className="text-label">Resolução</span>
                    <div className="mt-3 flex items-baseline gap-3">
                        <span className="font-mono text-[42px] font-light tracking-tight text-white">
                            94.2<span className="text-[28px] text-[#555]">%</span>
                        </span>
                        <span className="text-[12px] font-medium text-emerald-400 flex items-center gap-0.5">
                            <ArrowUpRight className="h-3 w-3" />
                            3.2%
                        </span>
                    </div>
                    <p className="text-[12px] text-[#444] mt-1">meta: 90%</p>
                </div>

                {/* Divider */}
                <div className="hidden md:block w-px h-20 bg-gradient-to-b from-transparent via-white/10 to-transparent" />

                {/* Metric 3 */}
                <div className="flex-1 w-full md:pl-8">
                    <span className="text-label">Tempo Resposta</span>
                    <div className="mt-3 flex items-baseline gap-3">
                        <span className="font-mono text-[42px] font-light tracking-tight text-white">
                            1.2<span className="text-[28px] text-[#555]">s</span>
                        </span>
                        <span className="text-[12px] font-medium text-emerald-400 flex items-center gap-0.5">
                            <ArrowUpRight className="h-3 w-3" />
                            8%
                        </span>
                    </div>
                    <p className="text-[12px] text-[#444] mt-1">resposta inicial</p>
                </div>
            </div>

            {/* Charts - Asymmetric Grid */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
                {/* Main Chart - 2/3 width */}
                <div className="md:col-span-2 spotlight-card p-6 md:p-8">
                    <MetricsChart
                        title="Conversas por Dia"
                        data={conversationsData}
                        color="#6366f1"
                        glowColor="rgba(99, 102, 241, 0.25)"
                    />
                </div>

                {/* Side Chart - 1/3 width */}
                <div className="spotlight-card p-6 md:p-8">
                    <MetricsChart
                        title="Taxa de Resolução"
                        data={resolutionData}
                        color="#22c55e"
                        glowColor="rgba(34, 197, 94, 0.25)"
                    />
                </div>
            </div>

            {/* Quick Stats Row */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 pt-4">
                <div className="spotlight-card p-6 hover-lift cursor-pointer group">
                    <div className="flex items-center justify-between">
                        <span className="text-label">Agente Vendas</span>
                        <span className="h-2 w-2 rounded-full bg-emerald-400 shadow-[0_0_8px_rgba(34,197,94,0.5)]" />
                    </div>
                    <p className="font-mono text-[28px] font-light text-white mt-4 group-hover:text-indigo-300 transition-colors">89</p>
                    <p className="text-[12px] text-[#444] mt-1">conversas hoje</p>
                </div>

                <div className="spotlight-card p-6 hover-lift cursor-pointer group">
                    <div className="flex items-center justify-between">
                        <span className="text-label">Agente Suporte</span>
                        <span className="h-2 w-2 rounded-full bg-emerald-400 shadow-[0_0_8px_rgba(34,197,94,0.5)]" />
                    </div>
                    <p className="font-mono text-[28px] font-light text-white mt-4 group-hover:text-indigo-300 transition-colors">156</p>
                    <p className="text-[12px] text-[#444] mt-1">conversas hoje</p>
                </div>

                <div className="spotlight-card p-6 hover-lift cursor-pointer group">
                    <div className="flex items-center justify-between">
                        <span className="text-label">FAQ Bot</span>
                        <span className="h-2 w-2 rounded-full bg-emerald-400 shadow-[0_0_8px_rgba(34,197,94,0.5)]" />
                    </div>
                    <p className="font-mono text-[28px] font-light text-white mt-4 group-hover:text-indigo-300 transition-colors">312</p>
                    <p className="text-[12px] text-[#444] mt-1">perguntas hoje</p>
                </div>
            </div>
        </div>
    );
}
