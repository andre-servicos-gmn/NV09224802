"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "@/lib/supabase/client";
import { Loader2 } from "lucide-react";

/**
 * Auth Callback Handler
 * This page handles Supabase auth callbacks (invite, recovery, signup, etc.)
 * It detects the type of auth event and redirects appropriately.
 */
export default function AuthCallbackPage() {
    const router = useRouter();

    useEffect(() => {
        const handleAuthCallback = async () => {
            // Get hash params from URL (Supabase puts tokens here)
            const hashParams = new URLSearchParams(window.location.hash.substring(1));
            const accessToken = hashParams.get("access_token");
            const refreshToken = hashParams.get("refresh_token");
            const type = hashParams.get("type");

            console.log("Auth callback - type:", type, "has token:", !!accessToken);

            if (accessToken) {
                try {
                    // Set the session
                    const { data, error } = await supabase.auth.setSession({
                        access_token: accessToken,
                        refresh_token: refreshToken || ""
                    });

                    if (error) {
                        console.error("Session error:", error);
                        router.push("/login");
                        return;
                    }

                    // Check the type of auth event
                    if (type === "invite" || type === "signup") {
                        // New user - go to setup page to set password
                        router.push("/setup-account" + window.location.hash);
                    } else if (type === "recovery") {
                        // Password recovery - go to setup page to reset password
                        router.push("/setup-account" + window.location.hash);
                    } else {
                        // Other types (magiclink, etc.) - check if user has password set
                        // For now, redirect to dashboard
                        if (data.user) {
                            // Get tenant_id
                            const { data: userData } = await supabase
                                .from("users")
                                .select("tenant_id")
                                .eq("id", data.user.id)
                                .single();

                            if (userData?.tenant_id) {
                                localStorage.setItem("nouva_tenant_id", userData.tenant_id);
                            }
                            router.push("/dashboard");
                        } else {
                            router.push("/login");
                        }
                    }
                } catch (err) {
                    console.error("Auth callback error:", err);
                    router.push("/login");
                }
            } else {
                // No token in URL, redirect to login
                router.push("/login");
            }
        };

        handleAuthCallback();
    }, [router]);

    return (
        <div className="min-h-screen bg-[#09090b] flex items-center justify-center">
            <div className="flex flex-col items-center">
                <Loader2 className="h-8 w-8 animate-spin text-indigo-500 mb-4" />
                <p className="text-zinc-400 text-sm">Processando autenticação...</p>
            </div>
        </div>
    );
}
