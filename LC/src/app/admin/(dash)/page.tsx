import Link from "next/link";
import { connection } from "next/server";
import { getStaff, canSeeFinance } from "@/lib/auth";
import { getMonthlyPnl, getOrders, getPendingPayments, getRiderJobs } from "@/lib/data/admin";
import { Badge, Panel, PageTitle, Stat } from "@/components/admin/ui";
import { FinanceChart } from "@/components/admin/finance-chart";
import { currentMonth, monthLabel, splitProfit } from "@/lib/finance";
import { statusLabel } from "@/lib/config";
import { rs } from "@/lib/utils";

export default async function AdminOverview() {
  await connection();
  const staff = await getStaff();
  const finance = canSeeFinance(staff.role);
  const [orders, payments, jobs, pnl] = await Promise.all([getOrders(), getPendingPayments(), getRiderJobs(), finance ? getMonthlyPnl() : Promise.resolve([])]);

  const month = currentMonth();
  const thisMonth = pnl.find((r) => r.month === month) ?? pnl.at(-1);
  const split = thisMonth ? splitProfit(thisMonth.net_profit, 0) : null;
  const inWorkshop = orders.filter((o) => ["cutting", "stitching", "finishing", "quality_check"].includes(o.status)).length;
  const ready = orders.filter((o) => o.status === "ready").length;
  const balanceDue = orders.reduce((s, o) => s + Math.max(0, o.total - o.paid), 0);

  return (
    <>
      <PageTitle title={`Assalam o Alaikum, ${staff.name.split(" ")[0]}`} sub="Here's the workshop today." />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat label="Active orders" value={String(orders.length)} hint={`${inWorkshop} in workshop · ${ready} ready`} />
        <Stat label="Slips to verify" value={String(payments.length)} hint="Payment verification queue" tone={payments.length ? "warn" : "default"} />
        <Stat label="Rider jobs open" value={String(jobs.length)} hint="Pickups, deliveries & visits" />
        <Stat label="Balance to collect" value={rs(balanceDue)} hint="Across active orders" />
      </div>

      {finance && thisMonth && split && (
        <div className="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <Stat label={`Revenue · ${monthLabel(thisMonth.month)}`} value={rs(thisMonth.revenue)} />
          <Stat label="Expenses" value={rs(thisMonth.expenses)} />
          <Stat label="Net profit so far" value={rs(thisMonth.net_profit)} tone={thisMonth.net_profit >= 0 ? "good" : "bad"} />
          <Stat label="Each partner (50%)" value={rs(split.shareA)} hint="Before reserve & drawings" tone={split.shareA >= 0 ? "good" : "bad"} />
        </div>
      )}

      <div className="mt-6 grid gap-6 xl:grid-cols-[1.4fr_1fr]">
        {finance ? (
          <Panel title="Revenue, expenses & profit" action={<Link href="/admin/partnership" className="text-xs text-plum underline">Partnership</Link>}>
            <FinanceChart data={pnl} />
          </Panel>
        ) : (
          <Panel title="Today">
            <p className="text-sm text-muted">Finance is visible to partners and the accountant only.</p>
          </Panel>
        )}
        <Panel title="Latest orders" action={<Link href="/admin/orders" className="text-xs text-plum underline">All orders</Link>}>
          <ul className="divide-y divide-line">
            {orders.slice(0, 7).map((o) => (
              <li key={o.id} className="flex items-center justify-between gap-3 py-2.5 text-sm">
                <div className="min-w-0">
                  <p className="font-medium">
                    {o.order_no} <span className="font-normal text-muted">· {o.customer?.full_name}</span>
                  </p>
                  <p className="text-xs text-muted">{o.customer?.area}</p>
                </div>
                <Badge value={o.status} label={statusLabel(o.status)} />
              </li>
            ))}
          </ul>
        </Panel>
      </div>
    </>
  );
}
