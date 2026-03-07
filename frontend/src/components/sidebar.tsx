"use client";

import { useState } from "react";
import Link from "next/link";
import Image from "next/image";
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
    MessageSquare,
    ShoppingBag,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useTenant } from "@/contexts/tenant-context";

const navigation = [
    { name: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
    { name: "Conversas", href: "/dashboard/conversations", icon: MessageSquare },
    { name: "Produtos", href: "/dashboard/products", icon: ShoppingBag },
    { name: "Agentes", href: "/dashboard/agents", icon: Bot },
    { name: "Config", href: "/dashboard/settings", icon: Settings },
];

export function Sidebar() {
    const pathname = usePathname();
    const { logoUrl, companyName } = useTenant();

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
                        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-500/10 border border-indigo-500/20 overflow-hidden">
                            <Image
                                src="/nouvaris-icon.jpeg"
                                alt="Logo"
                                width={32}
                                height={32}
                                className="h-full w-full object-cover"
                            />
                        </div>
                        <span className="text-base font-semibold text-white tracking-tight hidden sm:block">
                            {companyName}
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
                {/* Right Actions - Cleaned up */}
                <div className="flex items-center gap-2 md:gap-4">
                    {/* User Profile Only */}
                    <button className="flex items-center gap-2 pr-1 pl-1 py-1 rounded-full border border-transparent hover:bg-white/[0.03] transition-all">
                        <div className="h-7 w-7 rounded-full bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center text-[10px] font-bold text-white shadow-sm shadow-indigo-500/20 overflow-hidden">
                            {logoUrl ? (
                                // // biome-ignore lint/a11y/useAltText: <explanation>
                                <img src={logoUrl} alt="User" className="h-full w-full object-cover" />
                            ) : (
                                "U"
                            )}
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
