import { requireFinance } from "@/lib/auth";
import { getCoupons } from "@/lib/data/admin";
import { saveCoupon, setCouponActive } from "@/lib/actions/admin";
import { Badge, Empty, Panel, PageTitle } from "@/components/admin/ui";
import { ActionButton, ActionForm } from "@/components/admin/controls";
import { Button } from "@/components/ui/button";
import { Input, Label, Select } from "@/components/ui/field";
import { rs } from "@/lib/utils";

export default async function CouponsPage() {
  await requireFinance();
  const coupons = await getCoupons();
  return (
    <>
      <PageTitle title="Coupons" sub="Discounts come off the stitching price (not delivery or urgency). Every use is counted, so limits are exact." />
      <div className="grid gap-6 xl:grid-cols-[1.5fr_1fr]">
        <Panel title="All coupons">
          {coupons.length === 0 ? (
            <Empty>No coupons yet.</Empty>
          ) : (
            <ul className="divide-y divide-line">
              {coupons.map((c) => (
                <li key={c.code} className="flex flex-wrap items-center justify-between gap-3 py-3 text-sm">
                  <div>
                    <p className="font-semibold tracking-wider">
                      {c.code} {!c.is_active && <Badge value="inactive" />}
                    </p>
                    <p className="text-xs text-muted">
                      {c.kind === "percent" ? `${c.value}% off` : `${rs(c.value)} off`}
                      {c.max_discount && ` (max ${rs(c.max_discount)})`} · min order {rs(c.min_order)}
                      {c.ends_on && ` · until ${c.ends_on}`} · used {c.used_count}
                      {c.usage_limit && ` / ${c.usage_limit}`}
                    </p>
                    {c.description && <p className="text-xs text-muted">{c.description}</p>}
                  </div>
                  <ActionButton action={setCouponActive.bind(null, c.code, !c.is_active)} success="Updated" variant="outline">
                    {c.is_active ? "Pause" : "Activate"}
                  </ActionButton>
                </li>
              ))}
            </ul>
          )}
        </Panel>
        <Panel title="Create or update a coupon">
          <ActionForm action={saveCoupon} success="Coupon saved" className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Code</Label>
                <Input name="code" required placeholder="EID10" className="uppercase" />
              </div>
              <div>
                <Label>Type</Label>
                <Select name="kind" defaultValue="percent">
                  <option value="percent">Percent off</option>
                  <option value="flat">Flat Rs off</option>
                </Select>
              </div>
              <div>
                <Label>Value</Label>
                <Input name="value" type="number" min={1} required />
              </div>
              <div>
                <Label>Max discount (Rs)</Label>
                <Input name="maxDiscount" type="number" min={1} />
              </div>
              <div>
                <Label>Min order (Rs)</Label>
                <Input name="minOrder" type="number" min={0} defaultValue={0} />
              </div>
              <div>
                <Label>Usage limit</Label>
                <Input name="usageLimit" type="number" min={1} />
              </div>
              <div>
                <Label>Starts</Label>
                <Input name="startsOn" type="date" />
              </div>
              <div>
                <Label>Ends</Label>
                <Input name="endsOn" type="date" />
              </div>
            </div>
            <div>
              <Label>Note</Label>
              <Input name="description" placeholder="e.g. Eid campaign on Instagram" />
            </div>
            <Button type="submit">Save coupon</Button>
          </ActionForm>
        </Panel>
      </div>
    </>
  );
}
