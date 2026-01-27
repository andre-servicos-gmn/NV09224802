"use client";

import { createContext, useContext, useState, useCallback, ReactNode, useEffect } from "react";
import { cn } from "@/lib/utils";
import { CheckCircle, XCircle, X } from "lucide-react";

interface Toast {
    id: string;
    type: "success" | "error";
    message: string;
    isExiting?: boolean;
}

interface ToastContextType {
    showToast: (type: "success" | "error", message: string) => void;
}

const ToastContext = createContext<ToastContextType | null>(null);

export function useToast() {
    const context = useContext(ToastContext);
    if (!context) {
        throw new Error("useToast must be used within ToastProvider");
    }
    return context;
}

export function ToastProvider({ children }: { children: ReactNode }) {
    const [toasts, setToasts] = useState<Toast[]>([]);

    const showToast = useCallback((type: "success" | "error", message: string) => {
        const id = crypto.randomUUID();
        setToasts(prev => [...prev, { id, type, message, isExiting: false }]);

        // Start exit animation after 3.5 seconds
        setTimeout(() => {
            setToasts(prev => prev.map(t => t.id === id ? { ...t, isExiting: true } : t));
        }, 3500);

        // Remove from DOM after animation completes
        setTimeout(() => {
            setToasts(prev => prev.filter(t => t.id !== id));
        }, 4000);
    }, []);

    const dismissToast = useCallback((id: string) => {
        // Start exit animation
        setToasts(prev => prev.map(t => t.id === id ? { ...t, isExiting: true } : t));
        // Remove after animation
        setTimeout(() => {
            setToasts(prev => prev.filter(t => t.id !== id));
        }, 300);
    }, []);

    return (
        <ToastContext.Provider value={{ showToast }}>
            {children}

            {/* Toast Container */}
            <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-3 pointer-events-none">
                {toasts.map(toast => (
                    <div
                        key={toast.id}
                        className={cn(
                            "flex items-center gap-3 px-4 py-3 rounded-xl shadow-2xl border backdrop-blur-md pointer-events-auto",
                            "transition-all duration-300 ease-out",
                            toast.isExiting
                                ? "opacity-0 translate-x-8 scale-95"
                                : "opacity-100 translate-x-0 scale-100 animate-toast-enter",
                            toast.type === "success"
                                ? "bg-emerald-950/80 border-emerald-500/40 text-emerald-400"
                                : "bg-red-950/80 border-red-500/40 text-red-400"
                        )}
                        style={{
                            boxShadow: toast.type === "success"
                                ? "0 0 30px rgba(16, 185, 129, 0.15)"
                                : "0 0 30px rgba(239, 68, 68, 0.15)"
                        }}
                    >
                        <div className={cn(
                            "shrink-0 p-1 rounded-full",
                            toast.type === "success" ? "bg-emerald-500/20" : "bg-red-500/20"
                        )}>
                            {toast.type === "success" ? (
                                <CheckCircle className="h-4 w-4" />
                            ) : (
                                <XCircle className="h-4 w-4" />
                            )}
                        </div>
                        <span className="text-sm font-medium text-zinc-100 max-w-[280px]">
                            {toast.message}
                        </span>
                        <button
                            onClick={() => dismissToast(toast.id)}
                            className="ml-1 p-1.5 rounded-lg hover:bg-white/10 transition-colors duration-200"
                        >
                            <X className="h-3.5 w-3.5 text-zinc-400 hover:text-zinc-200 transition-colors" />
                        </button>
                    </div>
                ))}
            </div>

            {/* Keyframe animation styles */}
            <style jsx global>{`
                @keyframes toast-enter {
                    0% {
                        opacity: 0;
                        transform: translateX(100%) scale(0.9);
                    }
                    100% {
                        opacity: 1;
                        transform: translateX(0) scale(1);
                    }
                }
                .animate-toast-enter {
                    animation: toast-enter 0.4s cubic-bezier(0.16, 1, 0.3, 1);
                }
            `}</style>
        </ToastContext.Provider>
    );
}

