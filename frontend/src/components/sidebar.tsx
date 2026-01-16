"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
    LayoutDashboard,
    Settings,
    BarChart3,
    Bot,
    Search,
    Bell,
    Menu,
    X,
} from "lucide-react";
import { cn } from "@/lib/utils";

const navigation = [
    { name: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
    { name: "Agentes", href: "/dashboard/agents", icon: Bot },
    { name: "Métricas", href: "/dashboard/metrics", icon: BarChart3 },
    { name: "Config", href: "/dashboard/settings", icon: Settings },
];

export function Sidebar() {
    const pathname = usePathname();

    const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

    return (
        <header className="fixed top-0 left-0 right-0 z-50 h-16 bg-[#050505]/80 backdrop-blur-md border-b border-white/[0.06]">
            <div className="h-full max-w-[1600px] mx-auto px-4 md:px-6 flex items-center justify-between gap-4 md:gap-8">
                {/* Left Section: Logo & Mobile Menu Button */}
                <div className="flex items-center gap-3">
                    <button
                        onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
                        className="md:hidden p-2 text-white/70 hover:text-white"
                    >
                        {isMobileMenuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
                    </button>

                    <div className="flex items-center gap-3">
                        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-500/10 border border-indigo-500/20">
                            <span className="text-sm font-bold text-indigo-400">N</span>
                        </div>
                        <span className="text-base font-semibold text-white tracking-tight hidden sm:block">
                            Nouva
                        </span>
                    </div>
                </div>

                {/* Desktop Navigation */}
                <nav className="hidden md:flex items-center gap-1">
                    {navigation.map((item) => {
                        const isActive = pathname === item.href;
                        return (
                            <Link
                                key={item.name}
                                href={item.href}
                                className={cn(
                                    "flex items-center gap-2 px-3 py-1.5 rounded-md transition-all duration-200",
                                    isActive
                                        ? "bg-white/[0.08] text-white"
                                        : "text-white/40 hover:text-white hover:bg-white/[0.04]"
                                )}
                            >
                                <item.icon
                                    className={cn(
                                        "h-4 w-4",
                                        isActive ? "text-indigo-400" : "currentColor"
                                    )}
                                />
                                <span className="text-[13px] font-medium tracking-tight">{item.name}</span>
                            </Link>
                        );
                    })}
                </nav>

                {/* Right Actions */}
                <div className="flex items-center gap-2 md:gap-4">
                    {/* Search - Mobile: Icon only, Desktop: Input */}
                    <div className="relative group">
                        <Search className="md:absolute md:left-3 md:top-1/2 md:-translate-y-1/2 h-5 w-5 md:h-3.5 md:w-3.5 text-white/50 md:text-white/30 group-focus-within:text-indigo-400 transition-colors cursor-pointer md:cursor-default" />
                        <input
                            type="text"
                            placeholder="Buscar..."
                            className="hidden md:block w-48 h-8 pl-9 pr-3 rounded-md bg-white/[0.03] border border-white/[0.06] text-[12px] text-white placeholder:text-white/20 focus:outline-none focus:border-indigo-500/30 focus:bg-white/[0.05] transition-all"
                        />
                    </div>

                    <div className="hidden md:block h-4 w-[1px] bg-white/[0.06]" />

                    {/* Notifications */}
                    <button className="flex items-center justify-center h-8 w-8 rounded-full hover:bg-white/[0.03] transition-all text-white/40 hover:text-white">
                        <Bell className="h-5 w-5 md:h-4 md:w-4" />
                    </button>

                    {/* User */}
                    <button className="flex items-center gap-2 pr-1 pl-1 py-1 rounded-full border border-transparent hover:bg-white/[0.03] transition-all">
                        <div className="h-7 w-7 rounded-full bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center text-[10px] font-bold text-white shadow-sm shadow-indigo-500/20">
                            U
                        </div>
                    </button>
                </div>
            </div>

            {/* Mobile Menu Overlay */}
            {isMobileMenuOpen && (
                <div className="absolute top-16 left-0 right-0 bg-[#050505] border-b border-white/[0.06] p-4 md:hidden flex flex-col gap-2 shadow-2xl animate-in slide-in-from-top-2">
                    {navigation.map((item) => {
                        const isActive = pathname === item.href;
                        return (
                            <Link
                                key={item.name}
                                href={item.href}
                                onClick={() => setIsMobileMenuOpen(false)}
                                className={cn(
                                    "flex items-center gap-3 px-4 py-3 rounded-xl transition-all duration-200",
                                    isActive
                                        ? "bg-indigo-500/10 text-white"
                                        : "text-white/60 hover:text-white hover:bg-white/[0.04]"
                                )}
                            >
                                <item.icon
                                    className={cn(
                                        "h-5 w-5",
                                        isActive ? "text-indigo-400" : "currentColor"
                                    )}
                                />
                                <span className="text-[15px] font-medium">{item.name}</span>
                            </Link>
                        );
                    })}
                </div>
            )}
        </header>
    );
}
