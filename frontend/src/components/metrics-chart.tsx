"use client";

import {
    AreaChart,
    Area,
    XAxis,
    YAxis,
    Tooltip,
    ResponsiveContainer,
} from "recharts";

interface MetricsChartProps {
    title: string;
    data: { name: string; value: number }[];
    color?: string;
    glowColor?: string;
}

export function MetricsChart({
    title,
    data,
    color = "#6366f1",
    glowColor = "rgba(99, 102, 241, 0.3)"
}: MetricsChartProps) {
    return (
        <div className="relative">
            {/* Glow effect under chart */}
            <div
                className="absolute bottom-0 left-1/2 -translate-x-1/2 w-3/4 h-24 blur-3xl opacity-40 pointer-events-none"
                style={{ background: glowColor }}
            />

            <div className="relative">
                <span className="text-label">{title}</span>

                <div className="mt-6 h-[220px] w-full">
                    <ResponsiveContainer width="100%" height="100%">
                        <AreaChart
                            data={data}
                            margin={{ top: 8, right: 0, left: -24, bottom: 0 }}
                        >
                            <defs>
                                <linearGradient id={`gradient-${title.replace(/\s/g, '')}`} x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="0%" stopColor={color} stopOpacity={0.25} />
                                    <stop offset="100%" stopColor={color} stopOpacity={0} />
                                </linearGradient>
                            </defs>
                            <XAxis
                                dataKey="name"
                                stroke="transparent"
                                fontSize={11}
                                tickLine={false}
                                axisLine={false}
                                tick={{ fill: '#444' }}
                                dy={12}
                            />
                            <YAxis
                                stroke="transparent"
                                fontSize={11}
                                tickLine={false}
                                axisLine={false}
                                tick={{ fill: '#444' }}
                                dx={-8}
                            />
                            <Tooltip
                                contentStyle={{
                                    backgroundColor: "rgba(10, 10, 10, 0.95)",
                                    border: "1px solid rgba(255,255,255,0.1)",
                                    borderRadius: "8px",
                                    color: "#fff",
                                    fontSize: "12px",
                                    backdropFilter: "blur(8px)",
                                    boxShadow: "0 20px 40px -12px rgba(0,0,0,0.6)",
                                }}
                                labelStyle={{ color: "#666", fontSize: "11px", marginBottom: "4px" }}
                                cursor={{ stroke: 'rgba(255,255,255,0.05)', strokeWidth: 1 }}
                            />
                            <Area
                                type="monotone"
                                dataKey="value"
                                stroke={color}
                                strokeWidth={2}
                                fill={`url(#gradient-${title.replace(/\s/g, '')})`}
                                dot={false}
                                activeDot={{
                                    r: 4,
                                    fill: color,
                                    stroke: '#0a0a0a',
                                    strokeWidth: 2,
                                }}
                            />
                        </AreaChart>
                    </ResponsiveContainer>
                </div>
            </div>
        </div>
    );
}
