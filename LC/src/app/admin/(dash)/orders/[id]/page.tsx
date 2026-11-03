import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, MessageCircle } from "lucide-react";
import { getStaff } from "@/lib/auth";
import { getOrderDetail, getRiders } from "@/lib/data/admin";
import { addFinishedPhoto, assignRider, createRiderJob, receiveFabric, rescheduleJob, setPromisedDate, updateOrderStatus } from "@/lib/actions/admin";
import { Badge, Panel, PageTitle } from "@/components/admin/ui";
import { ActionForm, StatusSelect } from "@/components/admin/controls";
import { InlineDate } from "@/components/admin/inline-date";
import { Button } from "@/components/ui/button";
import { Input, Label, Select } from "@/components/ui/field";
import { addons, designOptions, garments, orderStatuses, pickupSlots, statusLabel } from "@/lib/config";
import { rs } from "@/lib/utils";

const allStatuses = [...orderStatuses, { value: "alteration", label: "Alteration" }, { value: "completed", label: "Completed" }, { value: "cancelled", label: "Cancelled" }] as const;

function optionLabel(key: string, value: unknown) {
  if (key === "addons" && Array.isArray(value)) return value.map((v) => addons.find((a) => a.value === v)?.label ?? v).join(", ") || "—";
  const group = designOptions.find((g) => g.key === key);
  return group?.options.find((o) => o.value === value)?.label ?? String(value);
}

export default async function OrderDetailPage({ params }: PageProps<"/admin/orders/[id]">) {
  await getStaff();
  const { id } = await params;
  const [order, riders] = await Promise.all([getOrderDetail(id), getRiders()]);
  if (!order) notFound();

  const due = Math.max(0, order.total - order.paid);
  const c = order.customer;
  const riderOptions = [{ value: "", label: "Unassigned" }, ...riders.filter((r) => r.is_active).map((r) => ({ value: r.id, label: r.full_name }))];

  return (
    <>
      <Link href="/admin/orders" className="mb-4 inline-flex items-center gap-1 text-sm text-muted hover:text-plum">
        <ArrowLeft className="size-4" /> Orders
      </Link>
      <PageTitle title={order.order_no} sub={`Placed ${new Date(order.created_at).toLocaleString("en-PK")} · ${order.tier} · ${order.fabric_method.replace("_", " ")}`}>
        <div className="w-56">
          <StatusSelect value={order.status} options={allStatuses} onChange={updateOrderStatus.bind(null, order.id)} success="Status updated — customer notified" />
        </div>
      </PageTitle>

      <div className="grid gap-6 xl:grid-cols-[1.5fr_1fr]">
        <div className="space-y-6">
          <Panel title="What to stitch">
            {order.items.map((item) => (
              <div key={item.id} className="space-y-4">
                <p className="font-display text-xl text-plum">
                  {garments.find((g) => g.slug === item.garment_slug)?.name ?? item.garment_slug} × {item.qty}
                  <span className="ml-2 font-sans text-sm text-muted">{rs(item.price)} each</span>
                </p>
                <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm sm:grid-cols-3">
                  {Object.entries(item.options).map(([k, v]) => (
                    <div key={k}>
                      <dt className="text-xs text-muted capitalize">{k}</dt>
                      <dd>{optionLabel(k, v)}</dd>
                    </div>
                  ))}
                </dl>
                <div className="rounded-[var(--radius-md)] bg-cream/70 p-4">
                  <p className="text-xs font-semibold tracking-wider text-muted uppercase">Measurements</p>
                  <dl className="mt-2 grid grid-cols-2 gap-x-6 gap-y-1.5 text-sm sm:grid-cols-4">
                    {Object.entries(item.measurement_snapshot)
                      .filter(([, v]) => v !== null && v !== "")
                      .map(([k, v]) => (
                        <div key={k}>
                          <dt className="text-xs text-muted capitalize">{k.replace(/_/g, " ")}</dt>
                          <dd className={k === "notes" ? "font-medium" : "font-medium capitalize"}>{k === "notes" ? String(v) : String(v).replace(/_/g, " ")}</dd>
                        </div>
                      ))}
                  </dl>
                </div>
                {item.reference_images.length > 0 && (
                  <div className="flex flex-wrap gap-2">
                    {item.reference_images.map((src) => (
                      <a key={src} href={src} target="_blank" rel="noopener noreferrer">
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img src={src} alt="Customer reference" className="size-24 rounded-[var(--radius-md)] object-cover" />
                      </a>
                    ))}
                  </div>
                )}
              </div>
            ))}
            {order.notes && <p className="mt-4 border-l-2 border-gold pl-3 text-sm">{order.notes}</p>}
          </Panel>

          <Panel title="Timeline & handovers">
            <ol className="space-y-3 border-l border-line pl-5 text-sm">
              {[...order.history.map((h) => ({ at: h.created_at, label: h.from_status === h.to_status ? h.note ?? "" : statusLabel(h.to_status), note: h.from_status === h.to_status ? null : h.note, photo: h.photo_url })),
                ...order.custody.map((e) => ({ at: e.created_at, label: `Custody: ${e.event.replace(/_/g, " ")}`, note: e.note, photo: e.photo_url }))]
                .sort((a, b) => a.at.localeCompare(b.at))
                .map((e, i) => (
                  <li key={i} className="relative">
                    <span className="absolute top-1.5 -left-[24px] size-2 rounded-full bg-gold" />
                    <p className="font-medium">{e.label}</p>
                    <p className="text-xs text-muted">
                      {new Date(e.at).toLocaleString("en-PK")} {e.note && `· ${e.note}`}
                    </p>
                    {e.photo && (
                      <a href={e.photo} target="_blank" rel="noopener noreferrer" className="text-xs text-plum underline">
                        View photo
                      </a>
                    )}
                  </li>
                ))}
            </ol>
          </Panel>

          <div className="grid gap-6 md:grid-cols-2">
            <Panel title="Fabric received at warehouse">
              <ActionForm action={receiveFabric} success="Fabric logged — production can start" className="space-y-3">
                <input type="hidden" name="orderId" value={order.id} />
                <input name="photo" type="file" accept="image/*" capture="environment" className="block w-full text-sm text-muted" />
                <Input name="note" placeholder="Pieces, length, condition, rack/bin…" />
                <Button type="submit" size="sm">Log fabric intake</Button>
              </ActionForm>
            </Panel>
            <Panel title="Finished suit photo">
              <ActionForm action={addFinishedPhoto} success="Photo saved" className="space-y-3">
                <input type="hidden" name="orderId" value={order.id} />
                <input name="photo" type="file" accept="image/*" capture="environment" required className="block w-full text-sm text-muted" />
                {order.showcase_consent ? (
                  <>
                    <label className="flex items-center gap-2 text-sm">
                      <input type="checkbox" name="publish" className="accent-[var(--color-plum)]" /> Publish to “Stitched by Laraib”
                    </label>
                    <Input name="title" placeholder="Title, e.g. Chiffon party wear" />
                    <Input name="tags" placeholder="Tags, comma separated" />
                  </>
                ) : (
                  <p className="text-xs text-muted">Customer did not consent to showcase — photo stays private.</p>
                )}
                <Button type="submit" size="sm">Save photo</Button>
              </ActionForm>
            </Panel>
          </div>
        </div>

        <div className="space-y-6">
          <Panel title="Customer">
            {c && (
              <div className="space-y-1 text-sm">
                <p className="font-semibold">{c.full_name}</p>
                <p>
                  <a href={`tel:${c.phone}`} className="text-plum underline">{c.phone}</a>
                  <a
                    href={`https://wa.me/${c.phone.replace(/\D/g, "")}?text=${encodeURIComponent(`Assalam o Alaikum, update on your order ${order.order_no}:`)}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="ml-3 inline-flex items-center gap-1 text-[#1f7a4d]"
                  >
                    <MessageCircle className="size-3.5" /> WhatsApp
                  </a>
                </p>
                <p className="text-muted">
                  {c.address} {c.area && `· ${c.area}`} {order.zone_code && `· Zone ${order.zone_code}`}
                </p>
                {c.landmark && <p className="text-xs text-muted">Landmark: {c.landmark}</p>}
              </div>
            )}
          </Panel>

          <Panel title="Money">
            <dl className="space-y-1.5 text-sm">
              <div className="flex justify-between"><dt className="text-muted">Stitching</dt><dd>{rs(order.subtotal)}</dd></div>
              {order.urgency_fee > 0 && <div className="flex justify-between"><dt className="text-muted">Urgency</dt><dd>{rs(order.urgency_fee)}</dd></div>}
              {order.delivery_fee > 0 && <div className="flex justify-between"><dt className="text-muted">Pickup & delivery</dt><dd>{rs(order.delivery_fee)}</dd></div>}
              <div className="flex justify-between border-t border-line pt-1.5 font-semibold"><dt>Total</dt><dd>{rs(order.total)}</dd></div>
              <div className="flex justify-between"><dt className="text-muted">Paid</dt><dd className="text-success">{rs(order.paid)}</dd></div>
              <div className="flex justify-between"><dt className="text-muted">Balance due</dt><dd className={due ? "text-wine" : ""}>{rs(due)}</dd></div>
            </dl>
            <ul className="mt-4 space-y-2 border-t border-line pt-3 text-xs">
              {order.payments.map((p) => (
                <li key={p.id} className="flex items-center justify-between gap-2">
                  <span className="capitalize">{p.method.replace("_", " ")} · {p.kind}</span>
                  <span className="flex items-center gap-2">
                    {rs(p.amount)} <Badge value={p.status} />
                  </span>
                </li>
              ))}
            </ul>
          </Panel>

          <Panel title="Delivery promise">
            <div className="flex items-center justify-between gap-3 text-sm">
              <span className="text-muted">Promised date</span>
              <InlineDate value={order.promised_date} onSave={setPromisedDate.bind(null, order.id)} />
            </div>
          </Panel>

          <Panel title="Rider jobs">
            <ul className="space-y-3">
              {order.jobs.map((j) => (
                <li key={j.id} className="rounded-[var(--radius-md)] border border-line p-3 text-sm">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold capitalize">{j.type.replace("_", " ")}</span>
                    <Badge value={j.status} />
                  </div>
                  <p className="mt-1 text-xs text-muted">
                    {j.slot ?? "Any time"} {j.cash_to_collect > 0 && `· collect ${rs(j.cash_to_collect)}`}
                  </p>
                  {!["done"].includes(j.status) && (
                    <div className="mt-2 grid grid-cols-2 gap-2">
                      <StatusSelect value={j.rider_id ?? ""} options={riderOptions} onChange={assignRider.bind(null, j.id)} />
                      <InlineDate value={j.scheduled_date} onSave={rescheduleJob.bind(null, j.id)} />
                    </div>
                  )}
                </li>
              ))}
            </ul>
            <details className="mt-4">
              <summary className="cursor-pointer text-sm text-plum">+ New rider job</summary>
              <ActionForm action={createRiderJob} success="Rider job created" className="mt-3 space-y-3">
                <input type="hidden" name="orderId" value={order.id} />
                <div className="grid grid-cols-2 gap-2">
                  <Select name="type" defaultValue="delivery">
                    <option value="pickup">Pickup</option>
                    <option value="delivery">Delivery</option>
                    <option value="measurement">Measurement visit</option>
                    <option value="alteration_return">Alteration pickup</option>
                  </Select>
                  <Input name="date" type="date" required />
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <Select name="slot" defaultValue={pickupSlots[1]}>
                    {pickupSlots.map((s) => <option key={s}>{s}</option>)}
                  </Select>
                  <Select name="riderId" defaultValue="">
                    {riderOptions.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
                  </Select>
                </div>
                <div>
                  <Label htmlFor="cash">Cash to collect</Label>
                  <Input id="cash" name="cash" type="number" min={0} defaultValue={due} />
                </div>
                <Input name="notes" placeholder="Notes for the rider" />
                <Button type="submit" size="sm">Create job</Button>
              </ActionForm>
            </details>
          </Panel>
        </div>
      </div>
    </>
  );
}
