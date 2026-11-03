"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion } from "motion/react";
import { Bike, ClipboardList, HandCoins, Image as ImageIcon, Inbox, LayoutDashboard, Receipt, Shirt, Star, TicketPercent, Users } from "lucide-react";
import { cn } from "@/lib/utils";

const items = [
  { href: "/admin", label: "Overview", icon: LayoutDashboard },
  { href: "/admin/orders", label: "Orders", icon: ClipboardList },
  { href: "/admin/payments", label: "Payment slips", icon: HandCoins },
  { href: "/admin/riders", label: "Dispatch & riders", icon: Bike },
  { href: "/admin/inquiries", label: "Inquiries", icon: Inbox },
  { href: "/admin/reviews", label: "Reviews & gallery", icon: Star },
  { href: "/admin/designs", label: "Lookbook designs", icon: Shirt },
  { href: "/admin/media", label: "Site media", icon: ImageIcon },
  { href: "/admin/coupons", label: "Coupons", icon: TicketPercent, finance: true },
  { href: "/admin/expenses", label: "Expenses", icon: Receipt, finance: true },
  { href: "/admin/partnership", label: "Partnership 50/50", icon: Users, finance: true },
];

export function AdminNav({ showFinance }: { showFinance: boolean }) {
  const pathname = usePathname();
  return (
    <nav className="flex gap-1 overflow-x-auto px-3 lg:flex-col lg:overflow-visible" aria-label="Admin">
      {items
        .filter((i) => showFinance || !i.finance)
        .map(({ href, label, icon: Icon }) => {
          const active = href === "/admin" ? pathname === href : pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "relative flex shrink-0 items-center gap-3 rounded-[var(--radius-md)] px-3 py-2.5 text-sm transition-colors",
                active ? "text-ivory" : "text-ivory/60 hover:text-ivory",
              )}
            >
              {active && (
                <motion.span
                  layoutId="admin-nav"
                  className="absolute inset-0 rounded-[var(--radius-md)] bg-ivory/10"
                  transition={{ type: "spring", stiffness: 380, damping: 32 }}
                />
              )}
              <Icon className="relative size-4" strokeWidth={1.6} />
              <span className="relative">{label}</span>
            </Link>
          );
        })}
    </nav>
  );
}
