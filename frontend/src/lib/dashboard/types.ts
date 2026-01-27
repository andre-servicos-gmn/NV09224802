export interface Conversation {
    id: string;
    tenant_id: string;
    created_at: string;
}

export interface Order {
    id: string;
    tenant_id: string;
    total: number;
    status: string;
    created_at: string;
}

export interface Message {
    id: string;
    conversation_id: string;
    sender_type: 'user' | 'agent' | 'system';
    intent?: string;
    created_at: string;
}

export interface DateRange {
    from: Date;
    to: Date;
}
