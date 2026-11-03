import { connection } from "next/server";
import Link from "next/link";
import { requireFinance } from "@/lib/auth";
import { getCategories, getExpenses, getPartners } from "@/lib/data/admin";
import { addExpense, reviewExpense } from "@/lib/actions/admin";
import { Badge, Empty, Panel, PageTitle, Stat } from "@/components/admin/ui";
import { ActionButton, ActionForm } from "@/components/admin/controls";
import { Button } from "@/components/ui/button";
import { Input, Label, Select } from "@/components/ui/field";
import { currentMonth, monthLabel } from "@/lib/finance";
import { rs } from "@/lib/utils";

function shiftMonth(month: string, delta: number) {
  const [y, m] = month.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1 + delta, 1)).toISOString().slice(0, 7);
}

export default async function ExpensesPage({ searchParams }: PageProps<"/admin/expenses">) {
  await connection();
  await requireFinance();
  const sp = await searchParams;
  const month = typeof sp.month === "string" && /^\d{4}-\d{2}$/.test(sp.month) ? sp.month : currentMonth();
  const [expenses, categories, partners] = await Promise.all([getExpenses(month), getCategories(), getPartners()]);

  const approved = expenses.filter((e) => e.status === "approved");
  const total = approved.reduce((s, e) => s + e.amount, 0);
  const pending = expenses.filter((e) => e.status === "pending_approval");
  const byGroup = Object.entries(
    approved.reduce<Record<string, number>>((acc, e) => {
      const g = e.category?.grp ?? "Other";
      acc[g] = (acc[g] ?? 0) + e.amount;
      return acc;
    }, {}),
  ).sort((a, b) => b[1] - a[1]);
  const groups = [...new Set(categories.map((c) => c.grp))];

  return (
    <>
      <PageTitle title="Expenses" sub="Every rupee spent, with receipts. Expenses of Rs 10,000+ need the other partner's approval.">
        <div className="flex items-center gap-2 text-sm">
          <Link href={`/admin/expenses?month=${shiftMonth(month, -1)}`} className="rounded-full border border-line bg-white px-3 py-1.5">←</Link>
          <span className="min-w-36 text-center font-medium">{monthLabel(month)}</span>
          <Link href={`/admin/expenses?month=${shiftMonth(month, 1)}`} className="rounded-full border border-line bg-white px-3 py-1.5">→</Link>
        </div>
      </PageTitle>

      <div className="grid gap-4 sm:grid-cols-3">
        <Stat label="Approved expenses" value={rs(total)} />
        <Stat label="Waiting approval" value={String(pending.length)} tone={pending.length ? "warn" : "default"} hint={pending.length ? rs(pending.reduce((s, e) => s + e.amount, 0)) : undefined} />
        <Stat label="Biggest category" value={byGroup[0]?.[0] ?? "—"} hint={byGroup[0] ? rs(byGroup[0][1]) : undefined} />
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-[1.6fr_1fr]">
        <div className="space-y-6">
          {pending.length > 0 && (
            <Panel title="Needs the other partner's approval">
              <ul className="divide-y divide-line">
                {pending.map((e) => (
                  <li key={e.id} className="flex flex-wrap items-center justify-between gap-3 py-3 text-sm">
                    <span>
                      <strong>{rs(e.amount)}</strong> · {e.category?.name} · {e.vendor}
                    </span>
                    <span className="flex gap-2">
                      <ActionButton action={reviewExpense.bind(null, e.id, false)} success="Expense rejected" variant="outline">Reject</ActionButton>
                      <ActionButton action={reviewExpense.bind(null, e.id, true)} success="Expense approved">Approve</ActionButton>
                    </span>
                  </li>
                ))}
              </ul>
            </Panel>
          )}
          <Panel title={`All expenses · ${monthLabel(month)}`}>
            {expenses.length === 0 ? (
              <Empty>No expenses recorded this month.</Empty>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[560px] text-left text-sm">
                  <thead className="text-xs text-muted uppercase">
                    <tr className="border-b border-line">
                      <th className="py-2 font-semibold">Date</th>
                      <th className="py-2 font-semibold">Category</th>
                      <th className="py-2 font-semibold">Vendor / note</th>
                      <th className="py-2 font-semibold">Paid by</th>
                      <th className="py-2 text-right font-semibold">Amount</th>
                    </tr>
                  </thead>
                  <tbody>
                    {expenses.map((e) => (
                      <tr key={e.id} className="border-b border-dashed border-line">
                        <td className="py-2.5 tabular-nums">{e.spent_on.slice(5)}</td>
                        <td className="py-2.5">
                          {e.category?.name}
                          <span className="block text-xs text-muted">{e.category?.grp}</span>
                        </td>
                        <td className="py-2.5">
                          {e.vendor}
                          {e.receipt_url && (
                            <a href={e.receipt_url} target="_blank" rel="noopener noreferrer" className="ml-2 text-xs text-plum underline">receipt</a>
                          )}
                        </td>
                        <td className="py-2.5 text-xs text-muted">{e.partner?.name ?? "Business"}</td>
                        <td className="py-2.5 text-right tabular-nums">
                          {rs(e.amount)} {e.status !== "approved" && <Badge value={e.status} />}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>
        </div>

        <div className="space-y-6">
          <Panel title="Add expense">
            <ActionForm action={addExpense} success="Expense saved" className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label htmlFor="spentOn">Date</Label>
                  <Input id="spentOn" name="spentOn" type="date" defaultValue={`${month}-${month === currentMonth() ? new Date().toISOString().slice(8, 10) : "01"}`} required />
                </div>
                <div>
                  <Label htmlFor="amount">Amount (Rs)</Label>
                  <Input id="amount" name="amount" type="number" min={1} required />
                </div>
              </div>
              <div>
                <Label htmlFor="categoryId">Category</Label>
                <Select id="categoryId" name="categoryId" required defaultValue="">
                  <option value="" disabled>Choose…</option>
                  {groups.map((g) => (
                    <optgroup key={g} label={g}>
                      {categories.filter((c) => c.grp === g).map((c) => (
                        <option key={c.id} value={c.id}>{c.name}</option>
                      ))}
                    </optgroup>
                  ))}
                </Select>
              </div>
              <div>
                <Label htmlFor="vendor">Vendor / paid to</Label>
                <Input id="vendor" name="vendor" placeholder="e.g. Azam Cloth Market" />
              </div>
              <div>
                <Label htmlFor="paidByPartnerId">Paid from</Label>
                <Select id="paidByPartnerId" name="paidByPartnerId" defaultValue="">
                  <option value="">Business account / cash box</option>
                  {partners.map((p) => (
                    <option key={p.id} value={p.id}>{p.name}&rsquo;s own pocket (to be repaid)</option>
                  ))}
                </Select>
              </div>
              <div>
                <Label htmlFor="notes">Notes</Label>
                <Input id="notes" name="notes" />
              </div>
              <div>
                <Label htmlFor="receipt">Receipt photo</Label>
                <input id="receipt" name="receipt" type="file" accept="image/*,application/pdf" capture="environment" className="block w-full text-sm text-muted" />
              </div>
              <Button type="submit">Save expense</Button>
            </ActionForm>
          </Panel>

          <Panel title="Where the money went">
            <ul className="space-y-3">
              {byGroup.map(([g, amt]) => (
                <li key={g}>
                  <div className="flex justify-between text-sm">
                    <span>{g}</span>
                    <span className="tabular-nums">{rs(amt)}</span>
                  </div>
                  <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-sand">
                    <div className="h-full rounded-full bg-plum" style={{ width: `${(amt / (total || 1)) * 100}%` }} />
                  </div>
                </li>
              ))}
            </ul>
          </Panel>
        </div>
      </div>
    </>
  );
}
