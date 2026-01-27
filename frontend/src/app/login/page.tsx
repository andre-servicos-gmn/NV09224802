"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { cn } from "@/lib/utils";
import { Loader2 } from "lucide-react";
import { supabase } from "@/lib/supabase/client";

type LoginState = "BOOT" | "ASK_ID" | "WAIT_ID" | "ASK_PASS" | "WAIT_PASS" | "VERIFY" | "SUCCESS" | "FAIL";

export default function LoginPage() {
    const router = useRouter();
    const [state, setState] = useState<LoginState>("BOOT");
    const [systemMessage, setSystemMessage] = useState("");
    const [inputValue, setInputValue] = useState("");
    const [email, setEmail] = useState("");
    const inputRef = useRef<HTMLInputElement>(null);

    // Auto-focus input when needed
    useEffect(() => {
        if (state === "WAIT_ID" || state === "WAIT_PASS") {
            setTimeout(() => inputRef.current?.focus(), 100);
        }
    }, [state]);

    // State Machine Orchestrator with Cancellation
    useEffect(() => {
        let cancelled = false;

        const runTypewriter = async (text: string, nextState: LoginState | null, delay = 30) => {
            setSystemMessage("");
            setInputValue("");

            await new Promise(r => setTimeout(r, 500));
            if (cancelled) return;

            for (let i = 0; i < text.length; i++) {
                if (cancelled) return;
                setSystemMessage(prev => prev + text.charAt(i));
                await new Promise(r => setTimeout(r, delay + Math.random() * 20)); // Random typing variance
            }

            if (nextState && !cancelled) {
                setState(nextState);
            }
        };

        if (state === "BOOT") {
            runTypewriter("Sistema Nouvaris online. Identifique-se com seu e-mail.", "WAIT_ID");
        } else if (state === "ASK_PASS") {
            runTypewriter(`Olá. Chave de acesso necessaria.`, "WAIT_PASS");
        } else if (state === "VERIFY") {
            verifyCredentials();
        } else if (state === "SUCCESS") {
            runTypewriter("Acesso autorizado. Carregando ambiente...", "DONE" as LoginState);
            setTimeout(() => router.push("/dashboard"), 2500);
        } else if (state === "FAIL") {
            runTypewriter("Acesso negado. Tente novamente.", "WAIT_PASS");
        }

        return () => {
            cancelled = true;
        };
    }, [state, router]);

    const verifyCredentials = async () => {
        setSystemMessage("Verificando...");

        try {
            // 1. Try Supabase Auth
            const { data, error } = await supabase.auth.signInWithPassword({
                email: email,
                password: inputValue
            });

            if (error) {
                console.error("Auth error:", error);
                if (error.message.includes("Invalid login")) {
                    setSystemMessage("Credenciais inválidas.");
                } else {
                    setSystemMessage("Erro de autenticação.");
                }
                setState("FAIL");
                return;
            }

            if (data.user) {
                // 2. Fetch Tenant ID associated with user
                const { data: userData, error: userError } = await supabase
                    .from("users")
                    .select("tenant_id")
                    .eq("id", data.user.id)
                    .single();

                if (userData?.tenant_id) {
                    localStorage.setItem("nouva_tenant_id", userData.tenant_id);
                    setState("SUCCESS");
                } else {
                    console.error("User missing tenant:", userError);
                    setSystemMessage("Usuário sem organização.");
                    setState("FAIL");
                }
            }
        } catch (err) {
            console.error("Login exception:", err);
            setState("FAIL");
        }
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!inputValue.trim()) return;

        if (state === "WAIT_ID") {
            const input = inputValue.trim();
            // Email Validation
            const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
            if (!emailRegex.test(input)) {
                setSystemMessage("Formato de e-mail inválido.");
                return;
            }

            // Check if email exists in backend
            setSystemMessage("Verificando e-mail...");

            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 5000);

            try {
                const res = await fetch("http://127.0.0.1:8000/auth/check-email", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ email: input }),
                    signal: controller.signal
                });

                clearTimeout(timeoutId);

                if (res.ok) {
                    const data = await res.json();
                    if (!data.exists) {
                        setSystemMessage("E-mail não encontrado.");
                        return;
                    }
                }
            } catch (err) {
                clearTimeout(timeoutId);
                console.error("Check email error", err);
            }

            setEmail(input);
            setState("ASK_PASS");
        } else if (state === "WAIT_PASS" || state === "FAIL") {
            setState("VERIFY");
        }
    };

    return (
        <div
            className="min-h-screen bg-[#050505] flex flex-col items-center justify-center p-4 font-mono text-sm md:text-base relative overflow-hidden"
            onClick={() => inputRef.current?.focus()} // Click anywhere to focus
        >
            {/* Subtle Noise/Grain Overlay */}
            <div className="absolute inset-0 opacity-[0.03] pointer-events-none bg-[url('https://grainy-gradients.vercel.app/noise.svg')] brightness-100 contrast-150"></div>

            {/* Ambient Glow */}
            <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[500px] h-[500px] bg-indigo-500/5 rounded-full blur-[120px] pointer-events-none animate-pulse duration-[5000ms]"></div>

            <div className="max-w-md w-full z-10 space-y-8">

                {/* System Output Area */}
                <div className="min-h-[60px] text-center">
                    <span className="text-zinc-300 tracking-wide leading-relaxed">
                        {systemMessage}
                    </span>
                    {/* Blinking Block Cursor when System is idle/waiting */}
                    {(state === "WAIT_ID" || state === "WAIT_PASS" || state === "FAIL") && (
                        <span className="inline-block w-2 h-4 bg-indigo-500 ml-1 animate-pulse align-middle" />
                    )}
                </div>

                {/* User Input Area */}
                {(state === "WAIT_ID" || state === "WAIT_PASS" || state === "FAIL") && (
                    <form onSubmit={handleSubmit} className="relative group">
                        <input
                            ref={inputRef}
                            type={state === "WAIT_PASS" || state === "FAIL" ? "password" : "text"}
                            value={inputValue}
                            onChange={(e) => setInputValue(e.target.value)}
                            className={cn(
                                "w-full bg-transparent border-b border-zinc-800 text-center py-2 focus:outline-none focus:border-indigo-500 transition-colors",
                                "text-white placeholder:text-zinc-700",
                                state === "FAIL" && "text-red-400 border-red-500/50"
                            )}
                            placeholder={state === "WAIT_ID" ? "Digite seu e-mail..." : "********"}
                            autoComplete="off"
                            spellCheck={false}
                        />


                    </form>
                )}

                {/* Loading State Spinner */}
                {state === "VERIFY" && (
                    <div className="flex justify-center">
                        <Loader2 className="h-5 w-5 animate-spin text-zinc-600" />
                    </div>
                )}
            </div>

            {/* Footer Status */}
            <div className="absolute bottom-8 text-[10px] text-zinc-800 tracking-widest uppercase">
                Nouvaris OS v2.0 • Conexão Segura
            </div>
        </div>
    );
}
