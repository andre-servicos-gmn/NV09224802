"use client";

import { cn } from "@/lib/utils";

interface HeatmapTableProps {
    title: string;
    data: {
        topic: string;
        count: number;
        sentiment: number; // 0-100 (0=bad, 100=good)
    }[];
}

export function HeatmapTable({ title, data }: HeatmapTableProps) {
    // Find max value to calculate intensity
    const maxCount = Math.max(...data.map(d => d.count));

    return (
        <div className="space-y-4">
            <h3 className="text-label">{title}</h3>

            <div className="bg-white/[0.02] border border-white/[0.06] rounded-xl overflow-hidden">
                <div className="grid grid-cols-12 gap-4 border-b border-white/[0.06] bg-white/[0.02] px-6 py-3 text-[11px] font-medium uppercase tracking-wider text-zinc-500">
                    <div className="col-span-6">Tópico</div>
                    <div className="col-span-3 text-right">Volume</div>
                    <div className="col-span-3 text-right">Sentimento</div>
                </div>

                <div className="divide-y divide-white/[0.04]">
                    {data.map((item, idx) => {
                        const intensity = (item.count / maxCount) * 100;

                        return (
                            <div key={idx} className="grid grid-cols-12 gap-4 px-6 py-3.5 items-center hover:bg-white/[0.02] transition-colors">
                                <div className="col-span-6 flex items-center gap-3">
                                    <span className="text-[13px] font-medium text-zinc-200">
                                        {item.topic}
                                    </span>
                                </div>

                                <div className="col-span-3">
                                    <div className="flex items-center justify-end gap-3">
                                        <span className="text-[12px] text-zinc-400 font-mono">
                                            {item.count}
                                        </span>
                                        {/* Volume Bar */}
                                        <div className="w-16 h-1.5 rounded-full bg-zinc-800 overflow-hidden">
                                            <div
                                                className="h-full bg-indigo-500"
                                                style={{ width: `${intensity}%` }}
                                            />
                                        </div>
                                    </div>
                                </div>

                                <div className="col-span-3 flex items-center justify-end gap-2">
                                    <span className={cn(
                                        "text-[12px] font-mono",
                                        item.sentiment >= 80 ? "text-emerald-400" :
                                            item.sentiment >= 50 ? "text-amber-400" : "text-rose-400"
                                    )}>
                                        {item.sentiment}%
                                    </span>
                                    {/* Sentiment Dot */}
                                    <div className={cn(
                                        "w-2 h-2 rounded-full",
                                        item.sentiment >= 80 ? "bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.4)]" :
                                            item.sentiment >= 50 ? "bg-amber-500 shadow-[0_0_8px_rgba(245,158,11,0.4)]" : "bg-rose-500 shadow-[0_0_8px_rgba(244,63,94,0.4)]"
                                    )} />
                                </div>
                            </div>
                        );
                    })}
                </div>
            </div>
        </div>
    );
}
