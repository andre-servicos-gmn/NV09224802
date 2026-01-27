import { supabase } from '../supabase/client';
import { Conversation, Order, Message, DateRange } from './types';

export async function fetchDashboardData(tenantId: string, days = 7) {
    const endDate = new Date();
    const startDate = new Date();
    startDate.setDate(endDate.getDate() - days);

    const fromIso = startDate.toISOString();

    // 0. Use Tenant ID directly (It's already a UUID from Login/Context)
    const realTenantUuid = tenantId;
    console.log("[DEBUG] Fetching Dashboard for Tenant:", realTenantUuid);
    console.log("[DEBUG] Date Range From:", fromIso);

    // Check if it looks like a UUID to be safe?
    // if (!realTenantUuid.match(...)) { ... }

    // 1. Fetch Messages (Source of Truth for Activity)
    // We fetch ALL messages from the last 7 days for this tenant to determine "Active Conversations"
    const { data: msgs, error: msgError } = await supabase
        .from('messages')
        .select('id, conversation_id, sender_type, intent, created_at, conversations!inner(tenant_id)')
        .eq('conversations.tenant_id', realTenantUuid)
        .gte('created_at', fromIso);

    if (msgError) {
        console.error("Error fetching messages:", JSON.stringify(msgError, null, 2));
        // throw msgError; // Don't throw to see if other queries work
    } else {
        console.log("[DEBUG] Messages found:", msgs?.length);
    }
    // Cast to Message[] (ignore the inner join property in types for now)
    const messages = (msgs || []) as unknown as Message[];

    // 2. Fetch New Conversations (for 'New' metric if needed, or to keep existing logic partially)
    // We still fetch this to keep the 'conversations' count accurate as 'New Conversations'
    const { data: conversations, error: convError } = await supabase
        .from('conversations')
        .select('id, tenant_id, created_at')
        .eq('tenant_id', realTenantUuid)
        .gte('created_at', fromIso);

    if (convError) {
        console.error("Error fetching conversations:", JSON.stringify(convError, null, 2));
    } else {
        console.log("[DEBUG] Conversations found:", conversations?.length);
    }

    // 2. Fetch Orders (Restored)
    const { data: orders, error: ordersError } = await supabase
        .from('orders')
        .select('id, tenant_id, total, status, created_at')
        .eq('tenant_id', realTenantUuid)
        .gte('created_at', fromIso);

    if (ordersError) {
        console.error("Error fetching orders:", JSON.stringify(ordersError, null, 2));
    } else {
        console.log("[DEBUG] Orders found:", orders?.length);
    }

    // 3. Fetch Resolution Stats (Last 30 Days)
    const date30DaysAgo = new Date();
    date30DaysAgo.setDate(endDate.getDate() - 30);
    const fromIso30 = date30DaysAgo.toISOString();

    const { data: resolutionConvs, error: resError } = await supabase
        .from('conversations')
        .select('id, status')
        .eq('tenant_id', realTenantUuid)
        .gte('created_at', fromIso30);

    if (resError) {
        console.error("Error fetching resolution stats:", JSON.stringify(resError, null, 2));
        // Don't throw, just log and return empty
    }

    return {
        conversations: (conversations || []) as Conversation[],
        orders: (orders || []) as Order[],
        messages: messages,
        resolutionStats: (resolutionConvs || []) as { id: string, status: string }[]
    };
}
