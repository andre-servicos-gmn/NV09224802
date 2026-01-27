"use client";

import { createContext, useContext, useState, useEffect, ReactNode, useCallback } from "react";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import { supabase } from "@/lib/supabase/client";

interface TenantContextType {
    logoUrl: string | null;
    companyName: string;
    tenantId: string;
    userId: string | null;
    userEmail: string | null;
    userName: string | null;
    refreshSettings: () => Promise<void>;
    refreshUser: () => Promise<void>;
    logout: () => void;
}

const TenantContext = createContext<TenantContextType | null>(null);

export function useTenant() {
    const context = useContext(TenantContext);
    if (!context) {
        throw new Error("useTenant must be used within TenantProvider");
    }
    return context;
}

export function TenantProvider({ children }: { children: ReactNode }) {
    const [logoUrl, setLogoUrl] = useState<string | null>(null);
    const [companyName, setCompanyName] = useState("Nouva");
    const [tenantId, setTenantId] = useState<string | null>(null);
    const [userId, setUserId] = useState<string | null>(null);
    const [userEmail, setUserEmail] = useState<string | null>(null);
    const [userName, setUserName] = useState<string | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const router = useRouter();

    useEffect(() => {
        // Load tenant ID from storage and get user from Supabase
        const initAuth = async () => {
            const stored = localStorage.getItem("nouva_tenant_id");
            if (stored) {
                setTenantId(stored);

                // Get current user from Supabase session
                const { data: { user } } = await supabase.auth.getUser();
                if (user) {
                    setUserId(user.id);
                    setUserEmail(user.email || null);
                    setUserName(user.user_metadata?.name || null);

                    // Also fetch name from users table (more up-to-date)
                    try {
                        const { data } = await supabase.from("users").select("name").eq("id", user.id).single();
                        if (data?.name) {
                            setUserName(data.name);
                        }
                    } catch (e) {
                        console.error("Failed to fetch user name:", e);
                    }
                }
            } else {
                // Not authenticated, redirect to login
                router.push("/login");
            }
            setIsLoading(false);
        };
        initAuth();
    }, [router]);

    const logout = useCallback(async () => {
        localStorage.removeItem("nouva_tenant_id");
        await supabase.auth.signOut();
        setTenantId(null);
        setUserId(null);
        setUserEmail(null);
        setUserName(null);
        router.push("/login");
    }, [router]);

    const refreshSettings = useCallback(async () => {
        if (!tenantId) return;
        try {
            const res = await fetch(`http://127.0.0.1:8000/tenant/${tenantId}`);
            if (res.ok) {
                const data = await res.json();
                if (data.success && data.data) {
                    // Always set logoUrl - to the value or null if not present
                    setLogoUrl(data.data.settings?.logo_url || null);
                    if (data.data.name) {
                        setCompanyName(data.data.name);
                    }
                }
            }
        } catch (error) {
            console.error("Failed to fetch tenant settings:", error);
        }
    }, [tenantId]);

    const refreshUser = useCallback(async () => {
        if (!userId) return;
        try {
            const { data } = await supabase.from("users").select("name").eq("id", userId).single();
            if (data?.name) {
                setUserName(data.name);
            }
        } catch (error) {
            console.error("Failed to refresh user:", error);
        }
    }, [userId]);

    useEffect(() => {
        refreshSettings();
    }, [refreshSettings, tenantId]); // Refresh when tenantId changes

    if (isLoading) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-black">
                <Loader2 className="h-8 w-8 animate-spin text-zinc-500" />
            </div>
        );
    }

    // Protection: If no tenantId, don't render children (redirecting...)
    if (!tenantId) return null;

    return (
        <TenantContext.Provider value={{ logoUrl, companyName, tenantId, userId, userEmail, userName, refreshSettings, refreshUser, logout }}>
            {children}
        </TenantContext.Provider>
    );
}
