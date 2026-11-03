import { Suspense } from "react";
import type { Metadata } from "next";
import Link from "next/link";
import { LogOut } from "lucide-react";
import { Logo } from "@/components/brand/logo";
import { AdminNav } from "@/components/admin/nav";
import { getStaff, canSeeFinance } from "@/lib/auth";
import { signOut } from "@/lib/actions/admin";

export const metadata: Metadata = { title: "Admin", robots: { index: false } };

async function Sidebar() {
  const staff = await getStaff();
  return (
    <>
      <AdminNav showFinance={canSeeFinance(staff.role)} />
      <div className="mt-auto hidden border-t border-ivory/10 px-5 py-4 lg:block">
        <p className="text-sm text-ivory">{staff.name}</p>
        <p className="text-xs text-ivory/50 capitalize">{staff.role}</p>
        <form action={signOut}>
          <button className="mt-3 inline-flex items-center gap-2 text-xs text-ivory/60 hover:text-ivory">
            <LogOut className="size-3.5" /> Sign out
          </button>
        </form>
      </div>
    </>
  );
}

async function PreviewBanner() {
  const staff = await getStaff();
  if (!staff.preview) return null;
  return (
    <div className="mb-6 rounded-[var(--radius-md)] border border-gold/40 bg-gold/10 px-4 py-3 text-sm text-[#7a5b26]">
      Preview mode — showing sample data. Add your Supabase keys to <code>.env.local</code> and run the migration to go live.
    </div>
  );
}

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-[#f4efe7] lg:grid lg:grid-cols-[248px_1fr]">
      <aside className="sticky top-0 z-30 flex flex-col bg-plum py-4 text-ivory lg:h-screen lg:py-6">
        <Link href="/admin" className="mb-4 px-5 lg:mb-8">
          <Logo light />
        </Link>
        <Suspense fallback={<div className="h-10" />}>
          <Sidebar />
        </Suspense>
      </aside>
      <div className="min-w-0 px-4 py-8 sm:px-8 lg:px-10">
        <Suspense fallback={null}>
          <PreviewBanner />
        </Suspense>
        {children}
      </div>
    </div>
  );
}
