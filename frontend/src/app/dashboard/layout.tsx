import { Sidebar } from "@/components/sidebar";

export default function DashboardLayout({
    children,
}: {
    children: React.ReactNode;
}) {
    return (
        <div className="min-h-screen relative">
            {/* Ambient glow orbs - living background */}
            <div className="ambient-orb ambient-orb-primary" />
            <div className="ambient-orb ambient-orb-secondary" />

            <Sidebar />
            <main className="min-h-screen relative z-10 pt-20 px-4 md:px-12 pb-10">
                <div className="mx-auto max-w-7xl">
                    {children}
                </div>
            </main>
        </div>
    );
}
