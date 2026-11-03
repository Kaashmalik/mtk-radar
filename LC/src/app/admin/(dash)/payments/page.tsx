import { getStaff } from "@/lib/auth";
import { getPendingPayments } from "@/lib/data/admin";
import { recordPayment, rejectPayment, verifyPayment } from "@/lib/actions/admin";
import { Empty, Panel, PageTitle } from "@/components/admin/ui";
import { ActionButton, ActionForm } from "@/components/admin/controls";
import { Button } from "@/components/ui/button";
import { Input, Label, Select } from "@/components/ui/field";
import { rs } from "@/lib/utils";

export default async function PaymentsPage() {
  await getStaff();
  const payments = await getPendingPayments();

  return (
    <>
      <PageTitle title="Payment slips" sub="Check each slip against your bank / wallet statement before approving." />
      <div className="grid gap-6 xl:grid-cols-[1.6fr_1fr]">
        <Panel title={`Waiting for verification (${payments.length})`}>
          {payments.length === 0 ? (
            <Empty>All slips verified. 🎉</Empty>
          ) : (
            <ul className="divide-y divide-line">
              {payments.map((p) => (
                <li key={p.id} className="flex flex-wrap items-center justify-between gap-4 py-4">
                  <div className="min-w-0 text-sm">
                    <p className="font-semibold">
                      {p.order?.order_no} · {rs(p.amount)} <span className="font-normal text-muted capitalize">({p.kind})</span>
                    </p>
                    <p className="text-muted">
                      <span className="capitalize">{p.method}</span> · {p.sender_name ?? "—"} {p.txn_id && `· Txn ${p.txn_id}`} · via {p.submitted_via}
                    </p>
                    <p className="text-xs text-muted">Order total {rs(p.order?.total ?? 0)} · {new Date(p.created_at).toLocaleString("en-PK")}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    {p.proof_url ? (
                      <a href={p.proof_url} target="_blank" rel="noopener noreferrer" className="text-xs text-plum underline">
                        View slip
                      </a>
                    ) : (
                      <span className="text-xs text-muted">No slip image</span>
                    )}
                    <ActionButton action={rejectPayment.bind(null, p.id, "Slip unclear or amount not received")} success="Slip rejected — ask the customer to resend" variant="outline" confirm="Reject this slip?">
                      Reject
                    </ActionButton>
                    <ActionButton action={verifyPayment.bind(null, p.id)} success="Payment verified — order confirmed">
                      Approve
                    </ActionButton>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <Panel title="Record a payment">
          <p className="mb-4 text-sm text-muted">For slips received on WhatsApp, or cash collected by a rider or at the shop.</p>
          <ActionForm action={recordPayment} success="Payment recorded" className="space-y-4">
            <div>
              <Label htmlFor="orderNo">Order #</Label>
              <Input id="orderNo" name="orderNo" placeholder="LC-1042" required />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label htmlFor="method">Method</Label>
                <Select id="method" name="method" defaultValue="cash_rider">
                  <option value="cash_rider">Cash to rider</option>
                  <option value="cash_shop">Cash at shop</option>
                  <option value="bank">Bank</option>
                  <option value="jazzcash">JazzCash</option>
                  <option value="easypaisa">Easypaisa</option>
                  <option value="raast">Raast</option>
                </Select>
              </div>
              <div>
                <Label htmlFor="amount">Amount</Label>
                <Input id="amount" name="amount" type="number" min={1} required />
              </div>
            </div>
            <div>
              <Label htmlFor="txnId">Transaction ID</Label>
              <Input id="txnId" name="txnId" />
            </div>
            <div>
              <Label htmlFor="slip">Slip image</Label>
              <input id="slip" name="slip" type="file" accept="image/*,application/pdf" className="block w-full text-sm text-muted" />
            </div>
            <Button type="submit">Save payment</Button>
          </ActionForm>
        </Panel>
      </div>
    </>
  );
}
