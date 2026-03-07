"use client";

import { useState, useEffect } from "react";
import Image from "next/image";
import { useTenant } from "@/contexts/tenant-context";
import { formatDistance, format } from "date-fns";
import { ptBR } from "date-fns/locale";
import {
    RefreshCcw,
    Search,
    Package,
    ArrowRight,
    AlertCircle,
    CheckCircle2,
    Clock,
    ShoppingCart
} from "lucide-react";

interface Product {
    id: string;
    title: string;
    description: string;
    price: number | null;
    image_url: string | null;
    in_stock: boolean;
    platform: string;
    external_id: string;
    synced_at: string;
    updated_at?: string;
}

export default function ProductsPage() {
    const { tenantId } = useTenant();
    const [products, setProducts] = useState<Product[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [isSyncing, setIsSyncing] = useState(false);
    const [searchQuery, setSearchQuery] = useState("");
    const [error, setError] = useState<string | null>(null);

    const fetchProducts = async () => {
        if (!tenantId) return;

        setIsLoading(true);
        setError(null);
        try {
            const res = await fetch(`http://127.0.0.1:8000/tenant/${tenantId}/products?limit=500`);
            const data = await res.json();

            if (data.success && data.data) {
                setProducts(data.data);
            } else {
                setError(data.message || "Falha ao carregar produtos");
            }
        } catch (err) {
            console.error("Failed to fetch products:", err);
            setError("Erro de conexão ao buscar produtos");
        } finally {
            setIsLoading(false);
        }
    };

    useEffect(() => {
        fetchProducts();
    }, [tenantId]);

    const handleSync = async () => {
        if (!tenantId) return;

        setIsSyncing(true);
        setError(null);
        try {
            const res = await fetch(`http://127.0.0.1:8000/tenant/${tenantId}/products/sync`, {
                method: "POST"
            });
            const data = await res.json();

            if (data.success) {
                // Fetch the updated list
                await fetchProducts();
            } else {
                setError(data.message || "Falha ao sincronizar produtos. Verifique se a integração Shopify está configurada (Acesso a aplicativos personalizados / Token Admin).");
            }
        } catch (err) {
            console.error("Failed to sync products:", err);
            setError("Erro de conexão durante sincronização. O Shopify pode estar inacessível.");
        } finally {
            setIsSyncing(false);
        }
    };

    const filteredProducts = products.filter(p => {
        const queryRaw = searchQuery.toLowerCase();

        // Dicionário de sinônimos/traduções para a busca
        // Adicione aqui outros termos comuns se necessário
        const termMap: Record<string, string[]> = {
            "couro": ["leather"],
            "prata": ["silver"],
            "ouro": ["gold"],
            "preto": ["black"],
            "branco": ["white"],
            "azul": ["blue"],
            "vermelho": ["red"],
            "verde": ["green"],
            "pingente": ["pendant", "charm"],
            "colar": ["necklace"],
            "anel": ["ring"],
            "brinco": ["earring"],
            "pulseira": ["bracelet"],
        };

        // Gerar variação pesquisável
        let searchTerms = [queryRaw];

        // Se a pessoa digitou "couro", searchTerms vira ["couro", "leather"]
        Object.entries(termMap).forEach(([ptTerm, enTerms]) => {
            if (queryRaw.includes(ptTerm)) {
                searchTerms = [...searchTerms, ...enTerms];
            }
        });

        return searchTerms.some(query =>
            p.title.toLowerCase().includes(query) ||
            (p.external_id && p.external_id.toLowerCase().includes(query)) ||
            (p.description && p.description.toLowerCase().includes(query)) ||
            (p.platform && p.platform.toLowerCase().includes(query)) ||
            (p.price && p.price.toString().includes(query)) ||
            (p.in_stock ? "em estoque" : "esgotado").includes(query)
        );
    });

    // Calculate metadata limits
    const lastSyncDate = products.length > 0
        ? new Date(Math.max(...products.map(p => {
            const dtStr = p.updated_at || p.synced_at;
            if (!dtStr) return 0;
            // Se a data já tiver "Z" (Zulu/UTC) ou outro offset (+00:00), deixamos como está
            // Caso contrário, injetamos "Z" pra o navegador entender que a string DB é originária do UTC
            const isUTC = dtStr.endsWith("Z") || dtStr.includes("+") || dtStr.includes("-") && dtStr.indexOf("-", 10) > 10;
            const formattedDateString = isUTC ? dtStr : `${dtStr}Z`;
            return new Date(formattedDateString).getTime();
        })))
        : null;

    return (
        <div className="flex-1 space-y-8 pt-6 pb-20 max-w-7xl mx-auto w-full px-4 sm:px-6 md:px-8">
            {/* Header section  */}
            <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
                <div>
                    <h1 className="text-2xl font-semibold text-white tracking-tight">
                        Catálogo de Produtos
                    </h1>
                    <p className="text-sm text-zinc-500 mt-1 hidden md:block max-w-2xl">
                        Acompanhe todos os seus produtos sincronizados das lojas. Estes são os produtos
                        que a sua IA usa como conhecimento para vender ou responder aos clientes.
                    </p>
                </div>

                <div className="flex items-center gap-3">
                    <button
                        onClick={handleSync}
                        disabled={isSyncing || !tenantId}
                        className={`
                            px-4 py-2 flex items-center gap-2 rounded-lg text-sm font-medium
                            transition-all border shadow-lg shadow-indigo-500/10
                            ${isSyncing
                                ? "bg-white/5 border-white/10 text-white/50 cursor-not-allowed"
                                : "bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-500 hover:to-violet-500 text-white border-indigo-500/30"
                            }
                        `}
                    >
                        <RefreshCcw className={`w-4 h-4 ${isSyncing ? 'animate-spin' : ''}`} />
                        {isSyncing ? 'Sincronizando Shopify...' : 'Sincronizar Manualmente'}
                    </button>
                </div>
            </div>

            {/* Error Message */}
            {error && (
                <div className="bg-red-500/10 border border-red-500/20 text-red-400 p-4 rounded-xl flex items-start gap-3">
                    <AlertCircle className="w-5 h-5 shrink-0 mt-0.5" />
                    <div>
                        <h4 className="text-sm font-semibold">Erro Encontrado</h4>
                        <p className="text-sm text-red-500/80 mt-1">{error}</p>
                    </div>
                </div>
            )}

            {/* Stats Cards */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 lg:gap-6">
                <div className="bg-[#0f0f11] border border-white/[0.04] p-5 rounded-2xl relative overflow-hidden group">
                    <div className="absolute inset-0 bg-gradient-to-br from-indigo-500/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
                    <div className="flex items-center gap-4">
                        <div className="w-12 h-12 rounded-xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center">
                            <Package className="w-6 h-6 text-indigo-400" />
                        </div>
                        <div>
                            <p className="text-sm font-medium text-white/50">Total de Produtos</p>
                            <h3 className="text-2xl font-bold text-white tracking-tight">
                                {isLoading ? "-" : products.length}
                            </h3>
                        </div>
                    </div>
                </div>

                <div className="bg-[#0f0f11] border border-white/[0.04] p-5 rounded-2xl relative overflow-hidden group">
                    <div className="absolute inset-0 bg-gradient-to-br from-emerald-500/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
                    <div className="flex items-center gap-4">
                        <div className="w-12 h-12 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center">
                            <CheckCircle2 className="w-6 h-6 text-emerald-400" />
                        </div>
                        <div>
                            <p className="text-sm font-medium text-white/50">Em Estoque Promovidos</p>
                            <h3 className="text-2xl font-bold text-white tracking-tight">
                                {isLoading ? "-" : products.filter(p => p.in_stock).length}
                            </h3>
                        </div>
                    </div>
                </div>

                <div className="bg-[#0f0f11] border border-white/[0.04] p-5 rounded-2xl relative overflow-hidden group">
                    <div className="absolute inset-0 bg-gradient-to-br from-blue-500/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-4">
                            <div className="w-12 h-12 rounded-xl bg-blue-500/10 border border-blue-500/20 flex items-center justify-center">
                                <Clock className="w-6 h-6 text-blue-400" />
                            </div>
                            <div>
                                <p className="text-sm font-medium text-white/50">Última Sincronização</p>
                                <h3 className="text-base font-bold text-white tracking-tight mt-1">
                                    {isLoading ? "-" : lastSyncDate ? formatDistance(lastSyncDate, new Date(), { addSuffix: true, locale: ptBR }) : 'Nunca'}
                                </h3>
                                {lastSyncDate && (
                                    <p className="text-xs text-white/40 mt-1">
                                        {format(lastSyncDate, "dd/MM 'às' HH:mm")}
                                    </p>
                                )}
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            {/* Toolbar and Search */}
            <div className="flex flex-col sm:flex-row gap-4 justify-between items-center bg-[#09090b] border border-white/[0.06] p-4 rounded-xl">
                <div className="relative w-full sm:max-w-2xl">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-white/40" />
                    <input
                        type="text"
                        placeholder="Buscar por nome, id, descrição, preço, categoria ou material..."
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        className="w-full bg-[#18181b] border border-white/10 rounded-lg pl-11 pr-4 py-2 text-sm text-white placeholder:text-white/30 focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
                    />
                </div>
                <div className="text-sm text-white/40">
                    Mostrando {filteredProducts.length} itens sincronizados
                </div>
            </div>

            {/* Table */}
            <div className="bg-[#0f0f11] border border-white/[0.04] rounded-2xl overflow-hidden">
                <div className="overflow-x-auto">
                    <table className="w-full text-left border-collapse">
                        <thead>
                            <tr className="border-b border-white/[0.06] bg-white/[0.02]">
                                <th className="py-4 px-6 text-xs font-semibold text-white/50 uppercase tracking-wider">Produto</th>
                                <th className="py-4 px-6 text-xs font-semibold text-white/50 uppercase tracking-wider">Plataforma ID</th>
                                <th className="py-4 px-6 text-xs font-semibold text-white/50 uppercase tracking-wider">Preço Base</th>
                                <th className="py-4 px-6 text-xs font-semibold text-white/50 uppercase tracking-wider text-right">Status</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-white/[0.04]">
                            {isLoading ? (
                                // Loading Skeleton
                                Array.from({ length: 5 }).map((_, i) => (
                                    <tr key={i} className="animate-pulse">
                                        <td className="py-4 px-6">
                                            <div className="flex items-center gap-4">
                                                <div className="w-12 h-12 bg-white/5 rounded-lg shrink-0" />
                                                <div className="space-y-2 w-full">
                                                    <div className="h-4 bg-white/5 rounded w-3/4" />
                                                    <div className="h-3 bg-white/5 rounded w-1/2" />
                                                </div>
                                            </div>
                                        </td>
                                        <td className="py-4 px-6"><div className="h-4 bg-white/5 rounded w-24" /></td>
                                        <td className="py-4 px-6"><div className="h-4 bg-white/5 rounded w-16" /></td>
                                        <td className="py-4 px-6 flex justify-end"><div className="h-6 bg-white/5 rounded-full w-20" /></td>
                                    </tr>
                                ))
                            ) : filteredProducts.length === 0 ? (
                                // Empty State
                                <tr>
                                    <td colSpan={4} className="py-12 px-6 text-center">
                                        <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-white/5 mb-4">
                                            <ShoppingCart className="w-8 h-8 text-white/20" />
                                        </div>
                                        <h3 className="text-base font-medium text-white mb-1">Nenhum produto encontrado</h3>
                                        <p className="text-sm text-white/40 mb-4 max-w-sm mx-auto">
                                            {searchQuery
                                                ? "Sua busca não retornou nenhum resultado."
                                                : "Ainda não há produtos registrados para o seu assistente. Conecte sua loja e inicie a sincronização."}
                                        </p>
                                        {!searchQuery && (
                                            <button
                                                onClick={handleSync}
                                                className="text-indigo-400 hover:text-indigo-300 text-sm font-medium flex items-center gap-1 mx-auto"
                                            >
                                                Iniciar primeira sincronização <ArrowRight className="w-4 h-4" />
                                            </button>
                                        )}
                                    </td>
                                </tr>
                            ) : (
                                filteredProducts.map((product) => (
                                    <tr key={product.id} className="hover:bg-white/[0.02] transition-colors group">
                                        <td className="py-4 px-6">
                                            <div className="flex items-center gap-4">
                                                <div className="w-12 h-12 bg-white/5 border border-white/10 rounded-lg shrink-0 overflow-hidden relative flex items-center justify-center bg-[#18181b]">
                                                    {product.image_url ? (
                                                        <img src={product.image_url} alt={product.title} className="w-full h-full object-cover" />
                                                    ) : (
                                                        <Package className="w-5 h-5 text-white/20" />
                                                    )}
                                                </div>
                                                <div className="min-w-0">
                                                    <p className="text-sm font-medium text-white truncate max-w-[280px]">
                                                        {product.title}
                                                    </p>
                                                    <p className="text-xs text-white/40 truncate max-w-[280px] mt-0.5">
                                                        {product.description || 'Sem descrição'}
                                                    </p>
                                                </div>
                                            </div>
                                        </td>
                                        <td className="py-4 px-6">
                                            <div className="flex flex-col">
                                                <span className="text-sm font-medium text-white/80">{product.platform}</span>
                                                <span className="text-xs text-white/40 mt-0.5 font-mono">#{product.external_id}</span>
                                            </div>
                                        </td>
                                        <td className="py-4 px-6">
                                            <span className="text-sm font-semibold text-white">
                                                {product.price ? `R$ ${product.price.toFixed(2)}` : 'N/A'}
                                            </span>
                                        </td>
                                        <td className="py-4 px-6 text-right">
                                            <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border ${product.in_stock
                                                ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                                                : 'bg-red-500/10 text-red-400 border-red-500/20'
                                                }`}>
                                                <span className={`w-1.5 h-1.5 rounded-full ${product.in_stock ? 'bg-emerald-400' : 'bg-red-400'}`} />
                                                {product.in_stock ? 'Em Estoque' : 'Esgotado'}
                                            </span>
                                        </td>
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    );
}
