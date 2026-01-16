import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { LucideIcon } from "lucide-react";

interface StatsCardProps {
    title: string;
    value: string | number;
    description?: string;
    icon: LucideIcon;
    trend?: {
        value: number;
        isPositive: boolean;
    };
    className?: string;
}

export function StatsCard({
    title,
    value,
    description,
    icon: Icon,
    trend,
    className,
}: StatsCardProps) {
    return (
        <Card className={cn("overflow-hidden", className)}>
            <CardContent className="p-7">
                {/* Label row */}
                <div className="flex items-center justify-between mb-4">
                    <span className="text-[11px] font-medium uppercase tracking-[0.05em] text-zinc-500">
                        {title}
                    </span>
                    <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-500/10">
                        <Icon className="h-4 w-4 text-indigo-400" />
                    </div>
                </div>

                {/* Value row */}
                <div className="flex items-baseline gap-3">
                    <span className="text-[32px] font-medium tracking-tight text-zinc-100">
                        {value}
                    </span>
                    {trend && (
                        <span
                            className={cn(
                                "text-[12px] font-medium",
                                trend.isPositive ? "text-emerald-400" : "text-rose-400"
                            )}
                        >
                            {trend.isPositive ? "+" : ""}{trend.value}%
                        </span>
                    )}
                </div>

                {/* Description */}
                {description && (
                    <p className="mt-1.5 text-[13px] text-zinc-600">{description}</p>
                )}
            </CardContent>
        </Card>
    );
}
