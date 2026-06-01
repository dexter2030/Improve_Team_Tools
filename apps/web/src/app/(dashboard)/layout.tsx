import { Sidebar } from "@/components/sidebar";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-1 min-h-screen">
      <Sidebar />
      <main className="flex-1 overflow-x-hidden">
        <div className="max-w-7xl mx-auto px-8 py-8">{children}</div>
      </main>
    </div>
  );
}
