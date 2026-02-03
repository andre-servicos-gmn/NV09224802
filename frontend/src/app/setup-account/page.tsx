"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { cn } from "@/lib/utils";
import { Loader2, Check, AlertCircle } from "lucide-react";
import { supabase } from "@/lib/supabase/client";

type SetupState = "LOADING" | "FORM" | "SAVING" | "SUCCESS" | "ERROR";

export default function SetupAccountPage() {
    const router = useRouter();
    const [state, setState] = useState<SetupState>("LOADING");
    const [name, setName] = useState("");
    const [password, setPassword] = useState("");
    const [confirmPassword, setConfirmPassword] = useState("");
    const [error, setError] = useState("");
    const [userEmail, setUserEmail] = useState("");
    const nameInputRef = useRef<HTMLInputElement>(null);

    // Handle Supabase invite token on mount
    useEffect(() => {
        const handleInviteToken = async () => {
            // Check URL hash for access token (Supabase puts it there for magic links/invites)
            const hashParams = new URLSearchParams(window.location.hash.substring(1));
            const accessToken = hashParams.get("access_token");
            const refreshToken = hashParams.get("refresh_token");
            const type = hashParams.get("type");

            console.log("Hash params:", { accessToken: !!accessToken, type });

            if (accessToken && (type === "invite" || type === "recovery" || type === "signup")) {
                try {
                    // Set the session with the tokens from URL
                    const { data, error } = await supabase.auth.setSession({
                        access_token: accessToken,
                        refresh_token: refreshToken || ""
                    });

                    if (error) {
                        console.error("Error setting session:", error);
                        setError("Token inválido ou expirado. Solicite um novo convite.");
                        setState("ERROR");
                        return;
                    }

                    if (data.user) {
                        setUserEmail(data.user.email || "");
                        // Clear the hash from URL for cleaner look
                        window.history.replaceState(null, "", "/setup-account");
                        setState("FORM");
                        setTimeout(() => nameInputRef.current?.focus(), 100);
                    }
                } catch (err) {
                    console.error("Token handling error:", err);
                    setError("Erro ao processar convite.");
                    setState("ERROR");
                }
            } else {
                // Check if already authenticated
                const { data: { session } } = await supabase.auth.getSession();
                if (session?.user) {
                    setUserEmail(session.user.email || "");
                    setState("FORM");
                    setTimeout(() => nameInputRef.current?.focus(), 100);
                } else {
                    setError("Nenhum convite encontrado. Use o link do email de convite.");
                    setState("ERROR");
                }
            }
        };

        handleInviteToken();
    }, []);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError("");

        // Validation
        if (!name.trim()) {
            setError("Digite seu nome.");
            return;
        }
        if (password.length < 6) {
            setError("Senha deve ter pelo menos 6 caracteres.");
            return;
        }
        if (password !== confirmPassword) {
            setError("As senhas não conferem.");
            return;
        }

        setState("SAVING");

        try {
            // 1. Update password in Supabase Auth
            const { error: updateError } = await supabase.auth.updateUser({
                password: password
            });

            if (updateError) {
                console.error("Password update error:", updateError);
                setError("Erro ao definir senha: " + updateError.message);
                setState("FORM");
                return;
            }

            // 2. Get current user
            const { data: { user } } = await supabase.auth.getUser();

            if (!user) {
                setError("Usuário não encontrado.");
                setState("FORM");
                return;
            }

            // 3. Ensure user exists in public.users table and update name
            // This will create the user if not exists, fetching tenant_id from auth metadata
            // Try to get tenant_id from user metadata or localStorage as fallback
            const metaTenantId = user.user_metadata?.tenant_id;
            const storedTenantId = localStorage.getItem("nouva_tenant_id");
            const tenantIdToSend = metaTenantId || storedTenantId || undefined;

            console.log("Ensure user - tenant sources:", {
                metaTenantId,
                storedTenantId,
                sending: tenantIdToSend
            });

            const response = await fetch("http://127.0.0.1:8000/ensure-user", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    user_id: user.id,
                    email: user.email || "",
                    name: name.trim(),
                    tenant_id: tenantIdToSend
                })
            });

            const ensureResult = await response.json();

            if (!response.ok || !ensureResult.success) {
                console.error("Ensure user failed:", ensureResult);
                setError("Erro ao criar perfil: " + (ensureResult.message || "Erro desconhecido"));
                setState("FORM");
                return;
            }

            // 4. Get tenant_id from the ensure-user response
            const tenantId = ensureResult.data?.tenant_id;

            if (tenantId) {
                localStorage.setItem("nouva_tenant_id", tenantId);
            }

            setState("SUCCESS");

            // Redirect to dashboard after success animation
            setTimeout(() => {
                router.push("/dashboard");
            }, 2000);

        } catch (err) {
            console.error("Setup error:", err);
            setError("Erro ao criar conta. Tente novamente.");
            setState("FORM");
        }
    };

    return (
        <div className="min-h-screen bg-[#09090b] flex items-center justify-center p-4">
            <div className="w-full max-w-md">
                {/* Logo/Brand */}
                <div className="text-center mb-8">
                    <h1 className="text-3xl font-bold text-white tracking-tight">Nouva</h1>
                    <p className="text-zinc-500 text-sm mt-2">Configure sua conta</p>
                </div>

                {/* Card */}
                <div className="bg-[#111113] border border-white/[0.08] rounded-2xl p-8 shadow-2xl">

                    {/* Loading State */}
                    {state === "LOADING" && (
                        <div className="flex flex-col items-center justify-center py-12">
                            <Loader2 className="h-8 w-8 animate-spin text-indigo-500 mb-4" />
                            <p className="text-zinc-400 text-sm">Verificando convite...</p>
                        </div>
                    )}

                    {/* Error State */}
                    {state === "ERROR" && (
                        <div className="flex flex-col items-center justify-center py-8">
                            <div className="h-16 w-16 rounded-full bg-red-500/10 flex items-center justify-center mb-4">
                                <AlertCircle className="h-8 w-8 text-red-400" />
                            </div>
                            <p className="text-red-400 text-sm text-center mb-6">{error}</p>
                            <button
                                onClick={() => router.push("/login")}
                                className="text-indigo-400 hover:text-indigo-300 text-sm underline"
                            >
                                Ir para login
                            </button>
                        </div>
                    )}

                    {/* Form State */}
                    {state === "FORM" && (
                        <form onSubmit={handleSubmit} className="space-y-6">
                            <div className="text-center mb-6">
                                <p className="text-zinc-400 text-sm">
                                    Bem-vindo! Complete seu cadastro para <span className="text-white">{userEmail}</span>
                                </p>
                            </div>

                            {error && (
                                <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-3">
                                    <p className="text-red-400 text-sm">{error}</p>
                                </div>
                            )}

                            <div className="space-y-2">
                                <label className="text-xs font-medium text-zinc-400">Seu Nome</label>
                                <input
                                    ref={nameInputRef}
                                    type="text"
                                    value={name}
                                    onChange={(e) => setName(e.target.value)}
                                    placeholder="Digite seu nome completo"
                                    className="w-full bg-zinc-900/50 border border-white/[0.08] rounded-lg px-4 py-3 text-white placeholder:text-zinc-600 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500/50 transition-all"
                                />
                            </div>

                            <div className="space-y-2">
                                <label className="text-xs font-medium text-zinc-400">Senha</label>
                                <input
                                    type="password"
                                    value={password}
                                    onChange={(e) => setPassword(e.target.value)}
                                    placeholder="Mínimo 6 caracteres"
                                    className="w-full bg-zinc-900/50 border border-white/[0.08] rounded-lg px-4 py-3 text-white placeholder:text-zinc-600 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500/50 transition-all"
                                />
                            </div>

                            <div className="space-y-2">
                                <label className="text-xs font-medium text-zinc-400">Confirmar Senha</label>
                                <input
                                    type="password"
                                    value={confirmPassword}
                                    onChange={(e) => setConfirmPassword(e.target.value)}
                                    placeholder="Digite a senha novamente"
                                    className="w-full bg-zinc-900/50 border border-white/[0.08] rounded-lg px-4 py-3 text-white placeholder:text-zinc-600 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500/50 transition-all"
                                />
                            </div>

                            <button
                                type="submit"
                                className="w-full bg-indigo-600 hover:bg-indigo-500 text-white font-medium py-3 rounded-lg transition-all flex items-center justify-center gap-2"
                            >
                                Criar Conta
                            </button>
                        </form>
                    )}

                    {/* Saving State */}
                    {state === "SAVING" && (
                        <div className="flex flex-col items-center justify-center py-12">
                            <Loader2 className="h-8 w-8 animate-spin text-indigo-500 mb-4" />
                            <p className="text-zinc-400 text-sm">Criando sua conta...</p>
                        </div>
                    )}

                    {/* Success State */}
                    {state === "SUCCESS" && (
                        <div className="flex flex-col items-center justify-center py-8">
                            <div className="h-16 w-16 rounded-full bg-emerald-500/10 flex items-center justify-center mb-4 animate-in zoom-in duration-300">
                                <Check className="h-8 w-8 text-emerald-400" />
                            </div>
                            <p className="text-emerald-400 text-sm font-medium mb-2">Conta criada com sucesso!</p>
                            <p className="text-zinc-500 text-xs">Redirecionando para o painel...</p>
                        </div>
                    )}
                </div>

                {/* Footer */}
                <p className="text-center text-zinc-600 text-xs mt-8">
                    © 2026 Nouva. Todos os direitos reservados.
                </p>
            </div>
        </div>
    );
}
