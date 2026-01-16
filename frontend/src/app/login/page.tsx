"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { cn } from "@/lib/utils";
import { Loader2 } from "lucide-react";

type LoginState = "BOOT" | "ASK_ID" | "WAIT_ID" | "ASK_PASS" | "WAIT_PASS" | "VERIFY" | "SUCCESS" | "FAIL";

export default function LoginPage() {
    const router = useRouter();
    const [state, setState] = useState<LoginState>("BOOT");
    const [systemMessage, setSystemMessage] = useState("");
    const [inputValue, setInputValue] = useState("");
    const [username, setUsername] = useState("");
    const inputRef = useRef<HTMLInputElement>(null);

    // Auto-focus input when needed
    useEffect(() => {
        if (state === "WAIT_ID" || state === "WAIT_PASS") {
            setTimeout(() => inputRef.current?.focus(), 100);
        }
    }, [state]);

    // Typewriter Effect Logic
    const typeMessage = async (text: string, nextState: LoginState, delay = 30) => {
        setSystemMessage("");
        setInputValue(""); // Clear user input

        await new Promise(r => setTimeout(r, 500)); // Initial pause

        for (let i = 0; i < text.length; i++) {
            setSystemMessage(prev => prev + text.charAt(i));
            await new Promise(r => setTimeout(r, delay + Math.random() * 20)); // Random typing variance
        }

        setState(nextState);
    };

    // State Machine Orchestrator
    useEffect(() => {
        if (state === "BOOT") {
            typeMessage("Sistema Nouvaris online. Identifique-se.", "WAIT_ID");
        } else if (state === "ASK_PASS") {
            typeMessage(`Olá, ${username}. Chave de acesso necessaria.`, "WAIT_PASS");
        } else if (state === "VERIFY") {
            verifyCredentials();
        } else if (state === "SUCCESS") {
            typeMessage("Acesso autorizado. Carregando ambiente...", "DONE" as LoginState);
            setTimeout(() => router.push("/dashboard"), 2500);
        } else if (state === "FAIL") {
            typeMessage("Acesso negado. Tente novamente.", "WAIT_PASS");
        }
    }, [state]);

    const verifyCredentials = async () => {
        setSystemMessage("Verificando...");
        await new Promise(r => setTimeout(r, 1500)); // Fake network delay

        if (inputValue === "nouva") {
            setState("SUCCESS");
        } else {
            setState("FAIL");
        }
    };

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        if (!inputValue.trim()) return;

        if (state === "WAIT_ID") {
            setUsername(inputValue.trim());
            setState("ASK_PASS");
        } else if (state === "WAIT_PASS" || state === "FAIL") { // Allow retry from FAIL state
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
                            placeholder={state === "WAIT_ID" ? "Digite seu usuário..." : "********"}
                            autoComplete="off"
                            spellCheck={false}
                        />

                        {/* Hint for Password */}
                        {(state === "WAIT_PASS" || state === "FAIL") && (
                            <p className="absolute -bottom-8 left-0 right-0 text-center text-[10px] text-zinc-700 transition-opacity opacity-0 group-focus-within:opacity-100">
                                Dica: <span className="text-zinc-600">nouva</span>
                            </p>
                        )}
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
