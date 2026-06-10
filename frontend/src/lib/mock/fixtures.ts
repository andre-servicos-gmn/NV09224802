/**
 * Fixtures de mock pra screenshots. Ativadas via NEXT_PUBLIC_MOCK=true.
 *
 * Quando MOCK_ENABLED, as páginas Dashboard e Conversations retornam estes
 * dados em vez de chamar o backend — não precisa de uvicorn nem dados reais
 * no Supabase. Pra desativar: NEXT_PUBLIC_MOCK=false (ou remover) + restart.
 */

export const MOCK_ENABLED = process.env.NEXT_PUBLIC_MOCK === "true";

// Helper: ISO string relativa a agora (pra horários sempre "recentes" nas prints)
const minsAgo = (m: number) => new Date(Date.now() - m * 60_000).toISOString();
const hoursAgo = (h: number) => new Date(Date.now() - h * 3_600_000).toISOString();

// ─── Dashboard (overview/métricas) ───────────────────────────────────

export const MOCK_DASHBOARD_METRICS = {
    revenue: 12847,
    avgTicket: 284,
    resolutionRate: 87.3,
    responseSeconds: 4.2,
    conversationsByDay: [
        { name: "Seg", value: 34 },
        { name: "Ter", value: 41 },
        { name: "Qua", value: 38 },
        { name: "Qui", value: 52 },
        { name: "Sex", value: 61 },
        { name: "Sáb", value: 47 },
        { name: "Dom", value: 29 },
    ],
    topics: [
        { topic: "Rastreamento de pedido", count: 84 },
        { topic: "Busca de produto", count: 72 },
        { topic: "Formas de pagamento", count: 53 },
        { topic: "Troca / devolução", count: 38 },
        { topic: "Prazo de entrega", count: 31 },
        { topic: "Disponibilidade de estoque", count: 27 },
        { topic: "Desconto / cupom", count: 19 },
    ],
};

// ─── Conversations ────────────────────────────────────────────────────

export interface MockConversation {
    id: string;
    tenant_id: string;
    session_id: string;
    channel: string;
    status: string;
    domain: string | null;
    frustration_level: number;
    push_name: string | null;
    created_at: string;
    updated_at: string | null;
}

export interface MockMessage {
    id: string;
    conversation_id: string;
    sender_type: "user" | "agent" | "system";
    content: string;
    intent: string | null;
    domain: string | null;
    metadata: Record<string, unknown> | null;
    created_at: string;
}

const TENANT = "demo";

export const MOCK_CONVERSATIONS: MockConversation[] = [
    {
        id: "conv-001", tenant_id: TENANT, session_id: "5511954499030", channel: "whatsapp",
        status: "active", domain: "sales", frustration_level: 0, push_name: "André Tudorov",
        created_at: minsAgo(8), updated_at: minsAgo(2),
    },
    {
        id: "conv-002", tenant_id: TENANT, session_id: "5511987654321", channel: "whatsapp",
        status: "active", domain: "support", frustration_level: 1, push_name: "Mariana Costa",
        created_at: minsAgo(23), updated_at: minsAgo(5),
    },
    {
        id: "conv-003", tenant_id: TENANT, session_id: "5521991234567", channel: "whatsapp",
        status: "handoff", domain: "support", frustration_level: 3, push_name: "Carlos Eduardo",
        created_at: minsAgo(47), updated_at: minsAgo(12),
    },
    {
        id: "conv-004", tenant_id: TENANT, session_id: "5531996543210", channel: "whatsapp",
        status: "human_active", domain: "support", frustration_level: 2, push_name: "Juliana Almeida",
        created_at: hoursAgo(2), updated_at: minsAgo(34),
    },
    {
        id: "conv-005", tenant_id: TENANT, session_id: "5511933221100", channel: "web",
        status: "active", domain: "sales", frustration_level: 0, push_name: "Pedro Henrique",
        created_at: hoursAgo(3), updated_at: minsAgo(40),
    },
    {
        id: "conv-006", tenant_id: TENANT, session_id: "5547988776655", channel: "whatsapp",
        status: "handoff", domain: "sales", frustration_level: 4, push_name: "Fernanda Lima",
        created_at: hoursAgo(4), updated_at: hoursAgo(1),
    },
    {
        id: "conv-007", tenant_id: TENANT, session_id: "5511944556677", channel: "whatsapp",
        status: "closed", domain: "sales", frustration_level: 0, push_name: "Ricardo Souza",
        created_at: hoursAgo(20), updated_at: hoursAgo(19),
    },
    {
        id: "conv-008", tenant_id: TENANT, session_id: "5562981122334", channel: "whatsapp",
        status: "closed", domain: "support", frustration_level: 1, push_name: "Beatriz Santos",
        created_at: hoursAgo(26), updated_at: hoursAgo(25),
    },
    {
        id: "conv-009", tenant_id: TENANT, session_id: "5511955667788", channel: "web",
        status: "closed", domain: "store_qa", frustration_level: 0, push_name: "Lucas Martins",
        created_at: hoursAgo(30), updated_at: hoursAgo(29),
    },
];

export const MOCK_MESSAGES: Record<string, MockMessage[]> = {
    "conv-001": [
        { id: "m1", conversation_id: "conv-001", sender_type: "user", content: "oi, queria ver corrente de prata", intent: "search_product", domain: "sales", metadata: null, created_at: minsAgo(8) },
        { id: "m2", conversation_id: "conv-001", sender_type: "agent", content: "Oi, André! 😊 Temos sim. Achei estas opções de corrente de prata:\n\n*Corrente Veneziana Prata 925* — R$ 189,90\n*Corrente Cadeado Prata 925* — R$ 234,90\n\nQuer ver os detalhes de alguma?", intent: "search_product", domain: "sales", metadata: { action: "search_products" }, created_at: minsAgo(7) },
        { id: "m3", conversation_id: "conv-001", sender_type: "user", content: "a primeira, qual o tamanho?", intent: "select_variant", domain: "sales", metadata: null, created_at: minsAgo(4) },
        { id: "m4", conversation_id: "conv-001", sender_type: "agent", content: "A Veneziana vem em 45cm e 60cm. As duas em prata 925 com garantia. Quer que eu já te mande o link pra finalizar?", intent: "select_variant", domain: "sales", metadata: { action: "get_product_variants" }, created_at: minsAgo(2) },
    ],
    "conv-003": [
        { id: "m1", conversation_id: "conv-003", sender_type: "user", content: "cadê meu pedido?? já faz uma semana", intent: "order_status", domain: "support", metadata: null, created_at: minsAgo(47) },
        { id: "m2", conversation_id: "conv-003", sender_type: "agent", content: "Poxa, Carlos, sinto muito pela demora. Me passa o número do pedido que eu verifico agora.", intent: "order_status", domain: "support", metadata: null, created_at: minsAgo(46) },
        { id: "m3", conversation_id: "conv-003", sender_type: "user", content: "1042. e é a terceira vez que pergunto isso", intent: "provide_order_id", domain: "support", metadata: null, created_at: minsAgo(40) },
        { id: "m4", conversation_id: "conv-003", sender_type: "user", content: "isso é um absurdo, quero falar com alguém de verdade", intent: "order_complaint", domain: "support", metadata: null, created_at: minsAgo(13) },
        { id: "m5", conversation_id: "conv-003", sender_type: "agent", content: "Entendo totalmente sua frustração. Vou te transferir agora pra um atendente humano resolver isso pessoalmente. Um momento.", intent: "order_complaint", domain: "support", metadata: { action: "escalate_handoff", handoff_reason: "high_frustration" }, created_at: minsAgo(12) },
        { id: "m6", conversation_id: "conv-003", sender_type: "system", content: "Conversa transferida para atendimento humano.", intent: null, domain: null, metadata: { event: "handoff" }, created_at: minsAgo(12) },
    ],
    "conv-007": [
        { id: "m1", conversation_id: "conv-007", sender_type: "user", content: "vocês têm fone bluetooth?", intent: "search_product", domain: "sales", metadata: null, created_at: hoursAgo(20) },
        { id: "m2", conversation_id: "conv-007", sender_type: "agent", content: "Temos sim, Ricardo! O *Fone Bluetooth TWS Pro* tá saindo por R$ 149,90 com frete grátis. Quer levar?", intent: "search_product", domain: "sales", metadata: { action: "search_products" }, created_at: hoursAgo(20) },
        { id: "m3", conversation_id: "conv-007", sender_type: "user", content: "quero sim! como pago?", intent: "payment_question", domain: "sales", metadata: null, created_at: hoursAgo(20) },
        { id: "m4", conversation_id: "conv-007", sender_type: "agent", content: "Perfeito! Aqui está o link pra finalizar — pode pagar no Pix, cartão ou boleto:\nhttps://loja.exemplo.com/checkout/tws-pro\n\nQualquer dúvida é só chamar 😉", intent: "payment_question", domain: "sales", metadata: { action: "generate_checkout_link" }, created_at: hoursAgo(19) },
        { id: "m5", conversation_id: "conv-007", sender_type: "system", content: "Conversa encerrada.", intent: null, domain: null, metadata: { event: "closed" }, created_at: hoursAgo(19) },
    ],
};

/** Filtra conversas mock pelo tab atual (active/handoff/closed). */
export function mockConversationsForTab(tab: string): MockConversation[] {
    if (tab === "active") {
        return MOCK_CONVERSATIONS.filter(
            (c) => c.status === "active" || c.status === "human_active"
        );
    }
    if (tab === "handoff") {
        return MOCK_CONVERSATIONS.filter((c) => c.status === "handoff");
    }
    if (tab === "closed") {
        return MOCK_CONVERSATIONS.filter((c) => c.status === "closed");
    }
    return MOCK_CONVERSATIONS;
}
