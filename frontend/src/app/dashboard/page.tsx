"use client";

import { useEffect, useState } from "react";
import { MetricsChart } from "@/components/metrics-chart";
import { HeatmapTable } from "@/components/heatmap-table";
import { ArrowUpRight } from "lucide-react";
import { fetchDashboardData } from "@/lib/dashboard/fetchRaw";
import {
    computeConversationsByDay,
    computeTimeSaved,
    computeFirstResponseSeconds,
    computeTopics,
    computeResolutionRate
} from "@/lib/dashboard/compute";

// const TENANT_ID = "demo"; // REMOVED hardcoded value

export default function DashboardPage() {
    const [loading, setLoading] = useState(true);
    // const [debugTenant, setDebugTenant] = useState<string | null>(null); // DEBUG STATE REMOVED
    const [metrics, setMetrics] = useState({
        timeSaved: { hours: 0, minutes: 0, daysEquivalency: 0 },
        resolutionRate: 0,
        responseSeconds: 0,
        conversationsByDay: [] as { name: string; value: number }[],
        topics: [] as { topic: string; count: number }[],
    });

    useEffect(() => {
        async function loadData() {
            try {
                // Get Tenant ID from localStorage (saved by Login)
                const storedTenantId = localStorage.getItem("nouva_tenant_id");
                // setDebugTenant(storedTenantId); // SET DEBUG REMOVED

                if (!storedTenantId) {
                    console.error("No tenant ID found in localStorage");
                    // Optionally redirect to login here
                    return;
                }

                console.log("[DASHBOARD] Loading data for tenant:", storedTenantId);
                const rawData = await fetchDashboardData(storedTenantId, 7);

                const convsByDay = computeConversationsByDay(rawData.messages);
                const timeSaved = computeTimeSaved(rawData.resolutionStats || []);
                const responseSeconds = computeFirstResponseSeconds(rawData.messages);
                const topics = computeTopics(rawData.messages);
                const resolutionRate = computeResolutionRate(rawData.resolutionStats || []);

                setMetrics({
                    timeSaved,
                    responseSeconds,
                    resolutionRate,
                    conversationsByDay: convsByDay,
                    topics,
                });
            } catch (error) {
                console.error("Failed to load dashboard data:", error);
            } finally {
                setLoading(false);
            }
        }

        loadData();
    }, []);

    // Formatter helpers
    const formatCurrency = (val: number) =>
        new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 }).format(val);

    const formatSeconds = (secs: number) => {
        if (secs < 60) return `${secs.toFixed(1)}s`;
        const mins = secs / 60;
        return `${mins.toFixed(1)}m`;
    };

    if (loading) {
        return <div className="p-12 text-white/50">Carregando dados...</div>;
    }

    return (
        <div className="space-y-12">
            {/* DEBUG BANNER REMOVED */}

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

            {/* Metrics Row */}
            <div className="flex flex-col md:flex-row items-start gap-8 md:gap-0">
                {/* Metric 1 - Time Saved */}
                <div className="flex-1 w-full md:pr-8 border-b md:border-b-0 border-white/[0.06] pb-6 md:pb-0">
                    <span className="text-label">Tempo Humano Poupado</span>
                    <div className="mt-3 flex items-baseline gap-3">
                        <span className="font-mono text-[42px] font-light tracking-tight text-white">
                            {metrics.timeSaved.hours}h {metrics.timeSaved.minutes}min
                        </span>
                        <div className="flex flex-col items-start">
                            <span className="text-[12px] font-medium text-emerald-400 flex items-center gap-0.5" title="Crescimento em relação à semana anterior">
                                <ArrowUpRight className="h-3 w-3" />
                                100%
                            </span>
                        </div>
                    </div>
                    <p className="text-[12px] text-[#444] mt-1">Equivalente a {metrics.timeSaved.daysEquivalency} dias de trabalho de um colaborador.</p>
                </div>

                {/* Divider */}
                <div className="hidden md:block w-px h-20 bg-gradient-to-b from-transparent via-white/10 to-transparent" />

                {/* Metric 2 - Mocked for now */}
                <div className="flex-1 w-full md:px-8 border-b md:border-b-0 border-white/[0.06] pb-6 md:pb-0">
                    <span className="text-label">Resolução IA</span>
                    <div className="mt-3 flex items-baseline gap-3">
                        <span className="font-mono text-[42px] font-light tracking-tight text-white">
                            {metrics.resolutionRate.toFixed(1)}<span className="text-[28px] text-[#555]">%</span>
                        </span>
                        <div className="flex flex-col items-start">
                            <span className="text-[12px] font-medium text-emerald-400 flex items-center gap-0.5">
                                <ArrowUpRight className="h-3 w-3" />
                                uptime
                            </span>
                        </div>
                    </div>
                    <p className="text-[12px] text-[#444] mt-1">sem handoff (30 dias)</p>
                </div>


                {/* Divider */}
                <div className="hidden md:block w-px h-20 bg-gradient-to-b from-transparent via-white/10 to-transparent" />

                {/* Metric 3 - Response Time */}
                <div className="flex-1 w-full md:pl-8">
                    <span className="text-label">Tempo Resposta</span>
                    <div className="mt-3 flex items-baseline gap-3">
                        <span className="font-mono text-[42px] font-light tracking-tight text-white">
                            {formatSeconds(metrics.responseSeconds)}
                        </span>
                        <span className="text-[12px] font-medium text-emerald-400 flex items-center gap-0.5">
                            <ArrowUpRight className="h-3 w-3" />
                            real
                        </span>
                    </div>
                    <p className="text-[12px] text-[#444] mt-1">resposta inicial média</p>
                </div>
            </div>

            {/* Charts Section - Stacked */}
            <div className="space-y-8">
                {/* Main Chart - Full Width */}
                <div className="spotlight-card p-6 md:p-8 h-[400px]">
                    <MetricsChart
                        title="Conversas por Dia"
                        data={metrics.conversationsByDay}
                        color="#6366f1"
                        glowColor="rgba(99, 102, 241, 0.25)"
                    />
                </div>

                {/* Topics Heatmap - Full Width */}
                <div className="spotlight-card p-6 md:p-8">
                    <HeatmapTable
                        title="Mapa de Tópicos (Heatmap)"
                        data={metrics.topics}
                    />
                </div>
            </div>


        </div>
    );
}
