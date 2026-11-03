import { connection } from "next/server";
import { requireFinance } from "@/lib/auth";
import { getMonthlyPnl, getPartners, getPartnerTxns, getSettlement } from "@/lib/data/admin";
import { addPartnerTxn } from "@/lib/actions/admin";
import { Badge, Panel, PageTitle } from "@/components/admin/ui";
import { ActionForm } from "@/components/admin/controls";
import { FinanceChart } from "@/components/admin/finance-chart";
import { SettlementCalculator } from "@/components/admin/settlement-calculator";
import { Button } from "@/components/ui/button";
import { Input, Label, Select } from "@/components/ui/field";
import { currentMonth, monthLabel } from "@/lib/finance";
import { rs } from "@/lib/utils";

export default async function PartnershipPage() {
  await connection();
  await requireFinance();
  const month = currentMonth();
  const [pnl, partners, txns, settlement] = await Promise.all([getMonthlyPnl(), getPartners(), getPartnerTxns(), getSettlement(month)]);
  const row = pnl.find((r) => r.month === month) ?? { month, revenue: 0, expenses: 0, net_profit: 0 };

  const [a, b] = partners;
  const ledger = partners.map((p) => {
    const mine = txns.filter((t) => t.partner_id === p.id);
    const sum = (type: string) => mine.filter((t) => t.type === type).reduce((s, t) => s + t.amount, 0);
    const drawingsThisMonth = mine.filter((t) => t.type === "drawing" && t.happened_on.startsWith(month)).reduce((s, t) => s + t.amount, 0);
    const balance = sum("capital") + sum("profit_share") + sum("reimbursement") - sum("loss_share") - sum("drawing");
    return { partner: p, capital: sum("capital"), profit: sum("profit_share") - sum("loss_share"), reimb: sum("reimbursement"), drawings: sum("drawing"), drawingsThisMonth, balance };
  });

  return (
    <>
      <PageTitle title="Partnership · 50 / 50" sub="Net profit after all expenses, split equally between the Tech & Online partner and the Stitching partner." />

      <Panel title={`Settlement · ${monthLabel(month)}`} action={settlement && <Badge value={settlement.status} />}>
        {a && b ? (
          <SettlementCalculator
            month={month}
            revenue={row.revenue}
            expenses={row.expenses}
            partnerA={{ name: a.name, drawings: ledger[0].drawingsThisMonth }}
            partnerB={{ name: b.name, drawings: ledger[1].drawingsThisMonth }}
            status={settlement ? (settlement.status === "closed" ? "closed" : "draft") : "open"}
            initialReserve={settlement && row.net_profit > 0 ? Math.round((settlement.reserve * 100) / row.net_profit) : 10}
          />
        ) : (
          <p className="text-sm text-muted">Add both partners in Supabase (`partners` table) to start.</p>
        )}
      </Panel>

      <div className="mt-6 grid gap-6 xl:grid-cols-[1.5fr_1fr]">
        <Panel title="Partner ledgers (all time)">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[560px] text-left text-sm">
              <thead className="text-xs text-muted uppercase">
                <tr className="border-b border-line">
                  <th className="py-2 font-semibold">Partner</th>
                  <th className="py-2 text-right font-semibold">Capital</th>
                  <th className="py-2 text-right font-semibold">Profit share</th>
                  <th className="py-2 text-right font-semibold">Repaid expenses</th>
                  <th className="py-2 text-right font-semibold">Drawings</th>
                  <th className="py-2 text-right font-semibold">Balance</th>
                </tr>
              </thead>
              <tbody>
                {ledger.map((l) => (
                  <tr key={l.partner.id} className="border-b border-dashed border-line">
                    <td className="py-3">
                      {l.partner.name}
                      <span className="block text-xs text-muted">{l.partner.role === "tech_online" ? "Website, leads, marketing" : "Workshop, stitching, quality"}</span>
                    </td>
                    <td className="py-3 text-right tabular-nums">{rs(l.capital)}</td>
                    <td className="py-3 text-right tabular-nums">{rs(l.profit)}</td>
                    <td className="py-3 text-right tabular-nums">{rs(l.reimb)}</td>
                    <td className="py-3 text-right tabular-nums">−{rs(l.drawings)}</td>
                    <td className="py-3 text-right font-semibold tabular-nums">{rs(l.balance)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-8">
            <FinanceChart data={pnl} />
          </div>
        </Panel>

        <Panel title="Record capital or drawing">
          <ActionForm action={addPartnerTxn} success="Saved to partner ledger" className="space-y-4">
            <div>
              <Label htmlFor="partnerId">Partner</Label>
              <Select id="partnerId" name="partnerId" required>
                {partners.map((p) => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </Select>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label htmlFor="type">Type</Label>
                <Select id="type" name="type" defaultValue="drawing">
                  <option value="drawing">Drawing / advance taken</option>
                  <option value="capital">Capital put in</option>
                </Select>
              </div>
              <div>
                <Label htmlFor="amount">Amount</Label>
                <Input id="amount" name="amount" type="number" min={1} required />
              </div>
            </div>
            <div>
              <Label htmlFor="happenedOn">Date</Label>
              <Input id="happenedOn" name="happenedOn" type="date" defaultValue={new Date().toISOString().slice(0, 10)} required />
            </div>
            <div>
              <Label htmlFor="notes">Notes</Label>
              <Input id="notes" name="notes" />
            </div>
            <Button type="submit">Save</Button>
          </ActionForm>
          <h3 className="mt-8 mb-3 font-sans text-sm font-semibold tracking-normal">Recent ledger entries</h3>
          <ul className="divide-y divide-line text-sm">
            {txns.slice(0, 8).map((t) => (
              <li key={t.id} className="flex justify-between gap-3 py-2">
                <span>
                  <span className="capitalize">{t.type.replace("_", " ")}</span>
                  <span className="block text-xs text-muted">
                    {partners.find((p) => p.id === t.partner_id)?.name} · {t.happened_on}
                  </span>
                </span>
                <span className="tabular-nums">{rs(t.amount)}</span>
              </li>
            ))}
          </ul>
        </Panel>
      </div>
    </>
  );
}
