import { Conversation, Order, Message } from './types';

// Helper to get day name (Seg, Ter, etc.)
function getDayName(dateStr: string): string {
    const date = new Date(dateStr);
    const days = ['Dom', 'Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb'];
    return days[date.getDay()];
}

// Modified to use MESSAGES activity instead of Conversation creation date
export function computeConversationsByDay(messages: Message[]) {
    // Initialize last 7 days map
    const last7Days = new Map<string, number>();
    const today = new Date();

    // Fill map with 0 for last 7 days in order
    const result: { name: string; value: number; dateKey: string }[] = [];
    for (let i = 6; i >= 0; i--) {
        const d = new Date();
        d.setDate(today.getDate() - i);
        const dayName = daysHelper(d.getDay());
        result.push({ name: dayName, value: 0, dateKey: d.toDateString() });
    }

    // Aggregate by Active Day (Message Activity)
    // We use a Set to count unique conversation_id per day
    const activeConvsPerDay = new Map<string, Set<string>>();

    messages.forEach(m => {
        const mDate = new Date(m.created_at).toDateString();
        if (!activeConvsPerDay.has(mDate)) {
            activeConvsPerDay.set(mDate, new Set());
        }
        activeConvsPerDay.get(mDate)?.add(m.conversation_id);
    });

    // Match with result array
    result.forEach(r => {
        if (activeConvsPerDay.has(r.dateKey)) {
            r.value = activeConvsPerDay.get(r.dateKey)?.size || 0;
        }
    });

    // Return clean structure
    return result.map(({ name, value }) => ({ name, value }));
}

function daysHelper(dayIndex: number) {
    const days = ['Dom', 'Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb'];
    return days[dayIndex];
}

export function computeRevenueAndTicket(orders: Order[]) {
    // Filter for paid/completed orders if possible, else all > 0
    // Filter for paid/completed orders
    const validOrders = orders.filter(o => {
        const total = Number(o.total);
        return (o.status === 'paid' || o.status === 'completed' || (total > 0 && o.status !== 'cancelled'));
    });

    const revenue = validOrders.reduce((sum, o) => sum + Number(o.total), 0);
    const count = validOrders.length;
    const avgTicket = count > 0 ? revenue / count : 0;

    return { revenue, count, avgTicket };
}

export function computeFirstResponseSeconds(messages: Message[]) {
    // Group by conversation
    const byConv: Record<string, Message[]> = {};
    messages.forEach(m => {
        if (!byConv[m.conversation_id]) byConv[m.conversation_id] = [];
        byConv[m.conversation_id].push(m);
    });

    let totalSeconds = 0;
    let count = 0;

    Object.values(byConv).forEach(msgs => {
        // Sort by time
        msgs.sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime());

        const firstUser = msgs.find(m => m.sender_type === 'user');
        if (!firstUser) return;

        // Find first agent msg AFTER user msg
        const firstAgent = msgs.find(m => m.sender_type === 'agent' && new Date(m.created_at) > new Date(firstUser.created_at));

        if (firstAgent) {
            const diff = (new Date(firstAgent.created_at).getTime() - new Date(firstUser.created_at).getTime()) / 1000;
            if (diff < 3600 * 24) { // Ignore outliers > 24h
                totalSeconds += diff;
                count++;
            }
        }
    });

    return count > 0 ? totalSeconds / count : 0;
}

export function computeTopics(messages: Message[]) {
    const topicCounts: Record<string, number> = {};

    messages.forEach(m => {
        if (m.intent && m.intent !== 'unknown') {
            topicCounts[m.intent] = (topicCounts[m.intent] || 0) + 1;
        }
    });

    // Sort by count desc
    return Object.entries(topicCounts)
        .map(([topic, count]) => ({ topic, count }))
        .sort((a, b) => b.count - a.count)
        .slice(0, 5); // Start with top 5
}

export function computeResolutionRate(conversations: { status: string }[]) {
    if (!conversations || conversations.length === 0) return 0;

    const total = conversations.length;
    // Resolved = Status is NOT 'handoff'
    // This assumes 'active', 'closed', etc are considered "handled by AI" 
    // until explicitly marked as handoff
    const resolved = conversations.filter(c => c.status !== 'handoff').length;

    return (resolved / total) * 100;
}
