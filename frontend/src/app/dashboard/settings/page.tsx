"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
    CardFooter,
} from "@/components/ui/card";
import {
    User,
    Building,
    CreditCard,
    Users,
    Mail,
    Shield,
    Check,
    Upload,
    LogOut,
    X,
    Trash2,
} from "lucide-react";
import { useRef, useEffect } from "react";
import { cn } from "@/lib/utils";
import { useToast } from "@/components/ui/toast";
import { Loader2 } from "lucide-react";
import { useTenant } from "@/contexts/tenant-context";
import { Dialog } from "@/components/ui/dialog";

const tabs = [
    { id: "general", label: "Geral", icon: Building },
    { id: "team", label: "Equipe", icon: Users },
];

export default function SettingsPage() {
    const [activeTab, setActiveTab] = useState("general");
    const { logoUrl, companyName, userEmail, userName, userId, refreshSettings, refreshUser, logout, tenantId } = useTenant();
    const [isUploading, setIsUploading] = useState(false);
    const [isSavingName, setIsSavingName] = useState(false);
    const [isSavingUserName, setIsSavingUserName] = useState(false);
    const [companyNameInput, setCompanyNameInput] = useState("");
    const [userNameInput, setUserNameInput] = useState("");
    const fileInputRef = useRef<HTMLInputElement>(null);
    const [usageStats, setUsageStats] = useState({
        conversations: 0,
        max_conversations: 1500,
        storage: "0 B",
        max_storage: "500 MB",
        team: 0 // Will be updated from API
    });
    const { showToast } = useToast();

    // Invite modal state
    const [showInviteModal, setShowInviteModal] = useState(false);
    const [inviteEmail, setInviteEmail] = useState("");
    const [inviteName, setInviteName] = useState("");
    const [isInviting, setIsInviting] = useState(false);
    const [inviteResult, setInviteResult] = useState<{ password?: string; email?: string } | null>(null);

    // Delete confirmation modal state
    const [showDeleteModal, setShowDeleteModal] = useState(false);
    const [deleteTarget, setDeleteTarget] = useState<{ id: string; name: string } | null>(null);
    const [isDeleting, setIsDeleting] = useState(false);
    const [deleteConfirmationText, setDeleteConfirmationText] = useState("");

    // Initialize company name input from context
    useEffect(() => {
        if (companyName) {
            setCompanyNameInput(companyName);
        }
    }, [companyName]);

    // Initialize user name input from context
    useEffect(() => {
        if (userName) {
            setUserNameInput(userName);
        }
    }, [userName]);

    useEffect(() => {
        const fetchUsage = async () => {
            try {
                const res = await fetch(`http://127.0.0.1:8000/tenant/${tenantId}/usage`);
                if (res.ok) {
                    const data = await res.json();
                    if (data.success && data.data) {
                        setUsageStats(data.data);
                    }
                }
            } catch (error) {
                console.error("Failed to fetch usage stats:", error);
            }
        };
        fetchUsage();
    }, [tenantId]);

    // Team members state and fetch
    interface TeamMember {
        id: string;
        email: string;
        name: string;
        role: string;
        status: string;
    }
    const [teamMembers, setTeamMembers] = useState<TeamMember[]>([]);
    const [isLoadingTeam, setIsLoadingTeam] = useState(false);

    const fetchTeam = async () => {
        if (!tenantId) return;
        setIsLoadingTeam(true);
        try {
            const res = await fetch(`http://127.0.0.1:8000/tenant/${tenantId}/team`);
            if (res.ok) {
                const data = await res.json();
                if (data.success && data.data?.members) {
                    setTeamMembers(data.data.members);
                    // Update team count in usage stats
                    setUsageStats(prev => ({ ...prev, team: data.data.members.length }));
                }
            }
        } catch (error) {
            console.error("Failed to fetch team members:", error);
        } finally {
            setIsLoadingTeam(false);
        }
    };

    // Refresh team data when switching to team tab
    useEffect(() => {
        if (activeTab === "team") {
            fetchTeam();
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [activeTab, tenantId]);

    // Fetch team count on initial load for usage stats
    useEffect(() => {
        if (tenantId) {
            fetchTeam();
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [tenantId]);

    // Removed local fetch effect as context handles it

    const handleLogoUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
        const file = event.target.files?.[0];
        if (!file) return;

        setIsUploading(true);
        const formData = new FormData();
        formData.append("file", file);
        formData.append("tenant_id", tenantId);

        try {
            const res = await fetch("http://127.0.0.1:8000/upload-logo", {
                method: "POST",
                body: formData,
            });

            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || "Erro no upload");

            if (data.success && data.data?.logo_url) {
                await refreshSettings(); // Update global context
                showToast("success", "Logo atualizada com sucesso!");
            }
        } catch (error) {
            console.error("Upload failed:", error);
            showToast("error", "Erro ao atualizar logo.");
        } finally {
            setIsUploading(false);
            if (fileInputRef.current) fileInputRef.current.value = "";
        }
    };

    const handleLogoRemove = async () => {
        setIsUploading(true);
        try {
            const res = await fetch("http://127.0.0.1:8000/remove-logo", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ tenant_id: tenantId }),
            });

            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || "Erro ao remover");

            if (data.success) {
                await refreshSettings();
                showToast("success", "Logo removida com sucesso!");
            }
        } catch (error) {
            console.error("Remove failed:", error);
            showToast("error", "Erro ao remover logo.");
        } finally {
            setIsUploading(false);
        }
    };

    const handleSaveCompanyName = async () => {
        if (!companyNameInput.trim()) {
            showToast("error", "Nome da empresa não pode estar vazio.");
            return;
        }

        setIsSavingName(true);
        try {
            const res = await fetch("http://127.0.0.1:8000/update-tenant", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    tenant_id: tenantId,
                    name: companyNameInput.trim()
                }),
            });

            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || "Erro ao salvar");

            if (data.success) {
                await refreshSettings();
                showToast("success", "Nome da empresa atualizado!");
            }
        } catch (error) {
            console.error("Save name failed:", error);
            showToast("error", "Erro ao salvar nome da empresa.");
        } finally {
            setIsSavingName(false);
        }
    };

    const handleSaveUserName = async () => {
        if (!userNameInput.trim()) {
            showToast("error", "Nome não pode estar vazio.");
            return;
        }
        if (!userId) {
            showToast("error", "Usuário não encontrado.");
            return;
        }

        setIsSavingUserName(true);
        try {
            const res = await fetch("http://127.0.0.1:8000/update-user", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    user_id: userId,
                    name: userNameInput.trim()
                }),
            });

            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || "Erro ao salvar");

            if (data.success) {
                await refreshUser();
                showToast("success", "Seu nome foi atualizado!");
            }
        } catch (error) {
            console.error("Save user name failed:", error);
            showToast("error", "Erro ao salvar nome.");
        } finally {
            setIsSavingUserName(false);
        }
    };

    const handleInvite = async () => {
        if (!inviteEmail.trim()) {
            showToast("error", "Email é obrigatório.");
            return;
        }

        setIsInviting(true);
        setInviteResult(null);
        try {
            const res = await fetch("http://127.0.0.1:8000/invite-team-member", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    tenant_id: tenantId,
                    email: inviteEmail.trim(),
                    name: inviteName.trim() || undefined
                }),
            });

            const data = await res.json();

            if (!res.ok) {
                throw new Error(data.detail || "Erro ao convidar");
            }

            if (data.success) {
                setInviteResult({ password: data.data?.password, email: inviteEmail });
                showToast("success", "Membro convidado com sucesso!");
                fetchTeam(); // Refresh team list
            } else {
                showToast("error", data.message || "Erro ao convidar membro.");
            }
        } catch (error) {
            console.error("Invite failed:", error);
            showToast("error", (error as Error).message || "Erro ao convidar membro.");
        } finally {
            setIsInviting(false);
        }
    };

    const closeInviteModal = () => {
        setShowInviteModal(false);
        setInviteEmail("");
        setInviteName("");
        setInviteResult(null);
    };

    const handleDeleteUser = (userId: string, userName: string) => {
        setDeleteTarget({ id: userId, name: userName });
        setShowDeleteModal(true);
    };

    const confirmDelete = async () => {
        if (!deleteTarget) return;

        setIsDeleting(true);
        try {
            const res = await fetch("http://127.0.0.1:8000/delete-user", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    user_id: deleteTarget.id,
                    tenant_id: tenantId
                }),
            });

            const data = await res.json();

            if (!res.ok) {
                throw new Error(data.detail || "Erro ao remover usuário");
            }

            if (data.success) {
                showToast("success", data.message || "Usuário removido com sucesso!");
                fetchTeam(); // Refresh team list
            } else {
                showToast("error", data.message || "Erro ao remover usuário.");
            }
        } catch (error) {
            console.error("Delete user failed:", error);
            showToast("error", (error as Error).message || "Erro ao remover usuário.");
        } finally {
            setIsDeleting(false);
            setShowDeleteModal(false);
            setDeleteTarget(null);
            setDeleteConfirmationText("");
        }
    };

    return (
        <div className="flex flex-col md:flex-row gap-8 min-h-[calc(100vh-120px)]">
            {/* Sidebar Navigation */}
            <aside className="w-full md:w-[240px] shrink-0">
                <div className="sticky top-24 space-y-1">
                    <h2 className="px-4 text-xs font-semibold text-zinc-500 uppercase tracking-wider mb-2">
                        Configurações
                    </h2>

                    {/* Mobile Horizontal Scroll */}
                    <div className="flex md:flex-col overflow-x-auto md:overflow-visible gap-1 pb-2 md:pb-0">
                        {tabs.map((tab) => {
                            const isActive = activeTab === tab.id;
                            const Icon = tab.icon;
                            return (
                                <button
                                    key={tab.id}
                                    onClick={() => setActiveTab(tab.id)}
                                    className={cn(
                                        "flex items-center gap-3 px-4 py-2 text-sm font-medium rounded-lg transition-all whitespace-nowrap md:whitespace-normal flex-1 md:flex-none",
                                        isActive
                                            ? "bg-indigo-500/10 text-indigo-400"
                                            : "text-zinc-400 hover:text-zinc-200 hover:bg-white/[0.03]"
                                    )}
                                >
                                    <Icon className="h-4 w-4" />
                                    {tab.label}
                                </button>
                            );
                        })}
                    </div>
                </div>
            </aside>

            {/* Main Content Area */}
            <main className="flex-1 max-w-4xl space-y-6">

                {/* GENERAL TAB */}
                {activeTab === "general" && (
                    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
                        <div>
                            <h1 className="text-2xl font-semibold text-white tracking-tight">Geral</h1>
                            <p className="text-sm text-zinc-500 mt-1">Gerencie as informações da sua conta e organização.</p>
                        </div>

                        {/* Organization Profile */}
                        <Card>
                            <CardHeader>
                                <CardTitle className="text-base">Perfil da Organização</CardTitle>
                                <CardDescription>Como sua empresa aparece no sistema.</CardDescription>
                            </CardHeader>
                            <CardContent className="space-y-4">
                                <div className="flex items-center gap-6">
                                    <div className="h-20 w-20 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-2xl font-bold text-white shadow-lg shadow-indigo-500/20 overflow-hidden relative">
                                        {logoUrl ? (
                                            // // biome-ignore lint/a11y/useAltText: <explanation>
                                            <img src={logoUrl} alt="Organization Logo" className="h-full w-full object-cover" />
                                        ) : (
                                            "N"
                                        )}
                                        {isUploading && (
                                            <div className="absolute inset-0 bg-black/50 flex items-center justify-center">
                                                <Loader2 className="h-6 w-6 animate-spin text-white" />
                                            </div>
                                        )}
                                    </div>
                                    <div className="space-y-2">
                                        <input
                                            type="file"
                                            ref={fileInputRef}
                                            onChange={handleLogoUpload}
                                            accept="image/png, image/jpeg, image/webp"
                                            className="hidden"
                                        />
                                        <div className="flex gap-2">
                                            <Button
                                                variant="outline"
                                                size="sm"
                                                className="h-9"
                                                onClick={() => fileInputRef.current?.click()}
                                                disabled={isUploading}
                                            >
                                                <Upload className="h-3.5 w-3.5 mr-2" />
                                                {isUploading ? "Enviando..." : "Alterar Logo"}
                                            </Button>
                                            {logoUrl && (
                                                <Button
                                                    variant="outline"
                                                    size="sm"
                                                    className="h-9 text-red-400 border-red-500/30 hover:bg-red-500/10"
                                                    onClick={handleLogoRemove}
                                                    disabled={isUploading}
                                                >
                                                    Remover
                                                </Button>
                                            )}
                                        </div>
                                        <p className="text-xs text-zinc-500">Recomendado: 400x400px, PNG ou JPG.</p>
                                    </div>
                                </div>
                                <div className="grid gap-4 md:grid-cols-2">
                                    <div className="space-y-2">
                                        <label className="text-xs font-medium text-zinc-400">Nome da Empresa</label>
                                        <Input
                                            value={companyNameInput}
                                            onChange={(e) => setCompanyNameInput(e.target.value)}
                                            placeholder="Nome da sua empresa"
                                        />
                                    </div>
                                    <div className="hidden">
                                        {/* Website field removed */}
                                    </div>
                                </div>
                            </CardContent>
                            <CardFooter className="border-t border-white/[0.06] py-3 bg-white/[0.01]">
                                <Button
                                    size="sm"
                                    className="bg-indigo-600 hover:bg-indigo-500 text-white ml-auto"
                                    onClick={handleSaveCompanyName}
                                    disabled={isSavingName}
                                >
                                    {isSavingName ? "Salvando..." : "Salvar Alterações"}
                                </Button>
                            </CardFooter>
                        </Card>

                        {/* Personal Profile */}
                        <Card>
                            <CardHeader>
                                <CardTitle className="text-base">Seu Perfil</CardTitle>
                                <CardDescription>Suas informações pessoais de acesso.</CardDescription>
                            </CardHeader>
                            <CardContent className="space-y-4">
                                <div className="grid gap-4 md:grid-cols-2">
                                    <div className="space-y-2">
                                        <label className="text-xs font-medium text-zinc-400">Nome Completo</label>
                                        <Input
                                            value={userNameInput}
                                            onChange={(e) => setUserNameInput(e.target.value)}
                                            placeholder="Seu nome"
                                        />
                                    </div>
                                    <div className="space-y-2">
                                        <label className="text-xs font-medium text-zinc-400">Email</label>
                                        <Input value={userEmail || ""} disabled className="opacity-50" />
                                    </div>
                                </div>
                            </CardContent>
                            <CardFooter className="border-t border-white/[0.06] py-3 bg-white/[0.01]">
                                <Button
                                    size="sm"
                                    className="bg-indigo-600 hover:bg-indigo-500 text-white ml-auto"
                                    onClick={handleSaveUserName}
                                    disabled={isSavingUserName}
                                >
                                    {isSavingUserName ? "Salvando..." : "Salvar Alterações"}
                                </Button>
                            </CardFooter>
                        </Card>

                        {/* Usage Stats (Moved from Billing) */}
                        <Card>
                            <CardHeader>
                                <CardTitle className="text-base">Uso do Workspace</CardTitle>
                            </CardHeader>
                            <CardContent className="space-y-6">
                                <div className="space-y-2">
                                    <div className="flex justify-between text-xs">
                                        <span className="text-zinc-400">Conversas / Mês</span>
                                        <span className="text-white">{usageStats.conversations} / {usageStats.max_conversations.toLocaleString()}</span>
                                    </div>
                                    <div className="h-2 w-full bg-zinc-800 rounded-full overflow-hidden">
                                        <div
                                            className="h-full bg-indigo-500 transition-all duration-1000"
                                            style={{ width: `${Math.min((usageStats.conversations / usageStats.max_conversations) * 100, 100)}%` }}
                                        />
                                    </div>
                                </div>

                                <div className="space-y-2">
                                    <div className="flex justify-between text-xs">
                                        <span className="text-zinc-400">Armazenamento (RAG)</span>
                                        <span className="text-white">{usageStats.storage} / {usageStats.max_storage}</span>
                                    </div>
                                    <div className="h-2 w-full bg-zinc-800 rounded-full overflow-hidden">
                                        <div className="h-full bg-violet-600 w-[5%] transition-all duration-1000" />
                                    </div>
                                </div>

                                <div className="space-y-2">
                                    <div className="flex justify-between text-xs">
                                        <span className="text-zinc-400">Membros da Equipe</span>
                                        <span className="text-white">{usageStats.team} / Illimitado</span>
                                    </div>
                                    <div className="h-2 w-full bg-zinc-800 rounded-full overflow-hidden">
                                        <div className="h-full bg-emerald-500 w-[5%] transition-all duration-1000" />
                                    </div>
                                </div>
                            </CardContent>
                        </Card>
                    </div>
                )
                }

                {/* TEAM TAB */}
                {
                    activeTab === "team" && (
                        <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
                            <div className="flex items-center justify-between">
                                <div>
                                    <h1 className="text-2xl font-semibold text-white tracking-tight">Equipe</h1>
                                    <p className="text-sm text-zinc-500 mt-1">Gerencie quem tem acesso ao workspace.</p>
                                </div>
                                <Button
                                    className="bg-indigo-600 hover:bg-indigo-500"
                                    onClick={() => setShowInviteModal(true)}
                                >
                                    <Users className="h-4 w-4 mr-2" />
                                    Convidar Membro
                                </Button>
                            </div>

                            <Card>
                                <CardContent className="p-0">
                                    {isLoadingTeam ? (
                                        <div className="flex items-center justify-center p-8">
                                            <span className="text-zinc-500 text-sm">Carregando equipe...</span>
                                        </div>
                                    ) : teamMembers.length === 0 ? (
                                        <div className="flex items-center justify-center p-8">
                                            <span className="text-zinc-500 text-sm">Nenhum membro encontrado</span>
                                        </div>
                                    ) : (
                                        teamMembers.map((member) => (
                                            <div key={member.id} className="flex items-center justify-between p-4 border-b last:border-0 border-white/[0.06] hover:bg-white/[0.02] transition-colors">
                                                <div className="flex items-center gap-3">
                                                    <div className="h-10 w-10 rounded-full bg-zinc-800 flex items-center justify-center text-zinc-400 font-medium text-sm">
                                                        {member.name.substring(0, 2).toUpperCase()}
                                                    </div>
                                                    <div>
                                                        <p className="text-sm font-medium text-white">{member.name}</p>
                                                        <p className="text-[11px] text-zinc-500">{member.email}</p>
                                                    </div>
                                                </div>
                                                <div className="flex items-center gap-4">
                                                    <span className="text-xs text-zinc-400 bg-white/[0.05] px-2 py-1 rounded-md border border-white/[0.05]">
                                                        {member.role}
                                                    </span>
                                                    <span className={cn(
                                                        "text-[10px] font-medium px-2 py-1 rounded-full",
                                                        member.status === "Ativo" ? "bg-emerald-500/10 text-emerald-400" : "bg-amber-500/10 text-amber-400"
                                                    )}>
                                                        {member.status}
                                                    </span>
                                                    <button
                                                        onClick={() => handleDeleteUser(member.id, member.name)}
                                                        className="p-2 text-zinc-500 hover:text-red-400 hover:bg-red-500/10 rounded-lg transition-colors"
                                                        title="Remover membro"
                                                    >
                                                        <Trash2 className="h-4 w-4" />
                                                    </button>
                                                </div>
                                            </div>
                                        ))
                                    )}
                                </CardContent>
                            </Card>
                        </div>
                    )
                }

                {/* Logout Button */}
                <div className="mt-12 border-t border-white/[0.06] pt-8 flex justify-end">
                    <Button
                        variant="destructive"
                        onClick={logout}
                        className="bg-red-500/10 hover:bg-red-500/20 text-red-500 border border-red-500/20"
                    >
                        <LogOut className="h-4 w-4 mr-2" />
                        Sair da Conta
                    </Button>
                </div>
            </main >

            {/* Invite Modal */}
            <Dialog
                open={showInviteModal}
                onClose={closeInviteModal}
                title="Convidar Membro"
            >
                {!inviteResult ? (
                    <>
                        <p className="text-sm text-zinc-400 mb-6">
                            Digite o email do novo membro. O sistema enviará um convite automaticamente.
                        </p>

                        <div className="space-y-2">
                            <label className="text-xs font-medium text-zinc-400">Email</label>
                            <Input
                                type="email"
                                value={inviteEmail}
                                onChange={(e) => setInviteEmail(e.target.value)}
                                placeholder="email@exemplo.com"
                            />
                        </div>

                        <div className="flex gap-3 mt-6">
                            <Button
                                variant="outline"
                                className="flex-1 border-white/[0.08]"
                                onClick={closeInviteModal}
                            >
                                Cancelar
                            </Button>
                            <Button
                                className="flex-1 bg-indigo-600 hover:bg-indigo-500"
                                onClick={handleInvite}
                                disabled={isInviting || !inviteEmail.trim()}
                            >
                                {isInviting ? "Convidando..." : "Enviar Convite"}
                            </Button>
                        </div>
                    </>
                ) : (
                    <>
                        <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-lg p-4 mb-4">
                            <p className="text-sm text-emerald-400 font-medium">✓ Convite enviado com sucesso!</p>
                        </div>

                        <p className="text-sm text-zinc-400 mb-4">
                            Um email de convite foi enviado para <span className="text-white">{inviteResult.email}</span>
                        </p>

                        <Button
                            className="w-full bg-indigo-600 hover:bg-indigo-500"
                            onClick={closeInviteModal}
                        >
                            Fechar
                        </Button>
                    </>
                )}
            </Dialog>

            {/* Delete Confirmation Modal */}
            <Dialog
                open={showDeleteModal}
                onClose={() => {
                    setShowDeleteModal(false);
                    setDeleteTarget(null);
                    setDeleteConfirmationText("");
                }}
                title="Remover Membro"
            >
                <div className="text-center">
                    <div className="h-16 w-16 rounded-full bg-red-500/10 flex items-center justify-center mx-auto mb-4">
                        <Trash2 className="h-8 w-8 text-red-400" />
                    </div>
                    <p className="text-zinc-400 text-sm mb-2">
                        Tem certeza que deseja remover
                    </p>
                    <p className="text-white font-medium text-lg mb-6">
                        {deleteTarget?.name}?
                    </p>
                    <p className="text-zinc-500 text-xs mb-4">
                        Esta ação não pode ser desfeita. O usuário perderá acesso ao sistema.
                    </p>

                    <div className="mb-6 space-y-2 text-left">
                        <label className="text-xs text-zinc-400">
                            Digite <span className="text-red-400 font-bold">DELETAR</span> para confirmar:
                        </label>
                        <Input
                            value={deleteConfirmationText}
                            onChange={(e) => setDeleteConfirmationText(e.target.value)}
                            placeholder="DELETAR"
                            className="text-center font-mono border-red-500/20 focus:border-red-500/50"
                        />
                    </div>

                    <div className="flex gap-3">
                        <Button
                            variant="outline"
                            className="flex-1 border-white/[0.08]"
                            onClick={() => {
                                setShowDeleteModal(false);
                                setDeleteTarget(null);
                                setDeleteConfirmationText("");
                            }}
                            disabled={isDeleting}
                        >
                            Cancelar
                        </Button>
                        <Button
                            className="flex-1 bg-red-600 hover:bg-red-500 disabled:opacity-50 disabled:cursor-not-allowed"
                            onClick={confirmDelete}
                            disabled={isDeleting || deleteConfirmationText !== "DELETAR"}
                        >
                            {isDeleting ? "Removendo..." : "Remover"}
                        </Button>
                    </div>
                </div>
            </Dialog>
        </div >
    );
}

function FileText({ className }: { className?: string }) {
    return (
        <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            className={className}
        >
            <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z" />
            <polyline points="14 2 14 8 20 8" />
            <line x1="16" x2="8" y1="13" y2="13" />
            <line x1="16" x2="8" y1="17" y2="17" />
            <line x1="10" x2="8" y1="9" y2="9" />
        </svg>
    );
}
