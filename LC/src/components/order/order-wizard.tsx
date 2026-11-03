"use client";
import { useEffect, useMemo, useState, useSyncExternalStore, useTransition } from "react";
import { useSearchParams } from "next/navigation";
import { AnimatePresence, motion } from "motion/react";
import { toast } from "sonner";
import { ArrowLeft, ArrowRight, Check, Copy, ImagePlus, MessageCircle, Upload } from "lucide-react";
import {
  addons,
  benchmarkBrands,
  designOptions,
  garments,
  measurementMethods,
  paymentAccounts,
  pickupSlots,
  selfMeasureFields,
  standardSizes,
  tiers,
  whatsappLink,
  zones,
  type MeasurementMethod,
} from "@/lib/config";
import { estimateDelivery, formatDay, quote, type Coupon, type OrderSelection } from "@/lib/pricing";
import { checkCoupon, createOrder } from "@/lib/actions/public";
import { compressFormData } from "@/lib/client-image";
import type { SiteMedia } from "@/lib/media";
import { AnimatedNumber } from "@/components/motion/counter";
import { MediaImage } from "@/components/brand/media-image";
import { Button, ButtonLink } from "@/components/ui/button";
import { Input, Label, Select, Textarea } from "@/components/ui/field";
import { cn, rs } from "@/lib/utils";

const steps = ["Design", "Measurements", "Pickup & delivery", "Details & payment"] as const;

type State = OrderSelection & {
  measurementMethod: MeasurementMethod;
  measurement: Record<string, string>;
  savedProfileId: string;
  profileName: string;
  area: string;
  address: string;
  landmark: string;
  pickupDate: string;
  pickupSlot: string;
  name: string;
  phone: string;
  email: string;
  notes: string;
  paymentMethod: "bank" | "jazzcash" | "easypaisa" | "raast" | "whatsapp";
  txnId: string;
  showcaseConsent: boolean;
};

function Chip({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        "relative rounded-full border px-4 py-2 text-sm transition-colors duration-300",
        active ? "border-plum text-ivory" : "border-line text-ink hover:border-plum/50",
      )}
    >
      {active && (
        <motion.span className="absolute inset-0 rounded-full bg-plum" initial={{ scale: 0.8, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} />
      )}
      <span className="relative">{children}</span>
    </button>
  );
}

function CopyRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3 py-1.5 text-sm">
      <span className="text-muted">{label}</span>
      <button
        type="button"
        className="inline-flex items-center gap-2 font-medium tabular-nums text-ink hover:text-plum"
        onClick={() => {
          navigator.clipboard?.writeText(value.replace(/\s/g, ""));
          toast.success(`${label} copied`);
        }}
      >
        {value} <Copy className="size-3.5 text-muted" />
      </button>
    </div>
  );
}

export type WizardCustomer = {
  name: string;
  phone: string;
  email: string | null;
  area: string | null;
  address: string | null;
  profiles: { id: string; name: string; source: string; fit: string }[];
} | null;

const DRAFT_KEY = "laraib-order-draft";
const noopSubscribe = () => () => {};
function readDraft() {
  try {
    return localStorage.getItem(DRAFT_KEY);
  } catch {
    return null;
  }
}

export function OrderWizard({ customer, media }: { customer: WizardCustomer; media: SiteMedia }) {
  const params = useSearchParams();
  const initialGarment = garments.some((g) => g.slug === params.get("garment")) ? params.get("garment")! : "simple";
  // a Lookbook design arrives as ?garment=…&neckline=…&sleeves=…&look=Title
  const initialOptions = Object.fromEntries(
    designOptions.map((g) => {
      const fromLook = params.get(g.key);
      return [g.key, g.options.some((o) => o.value === fromLook) ? fromLook! : g.options[0].value];
    }),
  );
  const look = params.get("look")?.slice(0, 120) ?? "";

  const savedDraft = useSyncExternalStore(noopSubscribe, readDraft, () => null);
  const [draftHandled, setDraftHandled] = useState(Boolean(look));
  const [coupon, setCoupon] = useState<{ coupon: Coupon; label: string } | null>(null);
  const [couponInput, setCouponInput] = useState("");
  const [checkingCoupon, startCouponCheck] = useTransition();

  const [step, setStep] = useState(0);
  const [dir, setDir] = useState(1);
  const [pending, startTransition] = useTransition();
  const [slip, setSlip] = useState<File | null>(null);
  const [references, setReferences] = useState<File[]>([]);
  const [done, setDone] = useState<{ orderNo: string; total: number; advance: number; pickupCode: string | null } | null>(null);

  const [s, setS] = useState<State>({
    garment: initialGarment,
    options: initialOptions,
    addons: [],
    qty: 1,
    tier: "standard",
    fabricMethod: "rider_pickup",
    zone: "A",
    measurementMethod: "standard_size",
    measurement: { size: "M", fit: "regular" },
    savedProfileId: customer?.profiles[0]?.id ?? "",
    profileName: "Me",
    area: customer?.area ?? "",
    address: customer?.address ?? "",
    landmark: "",
    pickupDate: "",
    pickupSlot: pickupSlots[0],
    name: customer?.name ?? "",
    phone: customer?.phone.replace(/^\+92/, "0") ?? "",
    email: customer?.email ?? "",
    notes: "",
    paymentMethod: "bank",
    txnId: "",
    showcaseConsent: true,
  });
  const set = <K extends keyof State>(key: K, value: State[K]) => setS((prev) => ({ ...prev, [key]: value }));
  const setM = (key: string, value: string) => setS((prev) => ({ ...prev, measurement: { ...prev.measurement, [key]: value } }));

  const price = useMemo(() => quote(s, coupon?.coupon ?? null), [s, coupon]);
  const garmentIndex = garments.findIndex((g) => g.slug === s.garment);
  // computed once on mount so the pickup calendar starts tomorrow
  const [minDate] = useState(() => new Date(Date.now() + 86400000).toISOString().slice(0, 10));
  const estimate = estimateDelivery(s, s.fabricMethod === "rider_pickup" && s.pickupDate ? s.pickupDate : minDate);

  // Autosave once the customer is past the first step (files are not saved).
  useEffect(() => {
    if (step === 0 || done) return;
    try {
      localStorage.setItem(DRAFT_KEY, JSON.stringify({ ...s, txnId: "", savedAt: Date.now() }));
    } catch {}
  }, [s, step, done]);

  function restoreDraft() {
    try {
      const draft = JSON.parse(savedDraft ?? "{}") as Partial<State>;
      setS((prev) => ({ ...prev, ...draft, savedProfileId: prev.savedProfileId, name: draft.name || prev.name, phone: draft.phone || prev.phone }));
      toast.success("Your saved order is back");
    } catch {}
    setDraftHandled(true);
  }

  function applyCoupon() {
    if (!couponInput.trim()) return;
    startCouponCheck(async () => {
      const res = await checkCoupon(couponInput, price.subtotal);
      if (!res.ok) return void toast.error(res.error);
      setCoupon(res.data);
      toast.success(`${res.data.coupon.code} applied — ${res.data.label}`);
    });
  }

  function validate(): string | null {
    if (step === 1 && s.savedProfileId) return null;
    if (step === 1 && s.measurementMethod === "self") {
      const missing = selfMeasureFields.find((f) => !s.measurement[f.key]);
      if (missing) return `Please enter your ${missing.label.toLowerCase()}`;
    }
    if (step === 1 && s.measurementMethod === "brand_match" && !s.measurement.brand) return "Please choose your usual brand";
    if (step === 2 && s.fabricMethod === "rider_pickup") {
      if (!s.area || !s.address) return "Please add your area and full address for pickup";
      if (!s.pickupDate) return "Please choose a pickup date";
    }
    if (step === 3) {
      if (s.name.trim().length < 2) return "Please enter your name";
      if (!/^(\+92|0)?3\d{2}[\s-]?\d{7}$/.test(s.phone.trim())) return "Enter a valid mobile number, e.g. 0300 1234567";
    }
    return null;
  }

  function go(delta: number) {
    if (delta > 0) {
      const err = validate();
      if (err) return toast.error(err);
    }
    setDir(delta);
    setStep((v) => Math.min(Math.max(v + delta, 0), steps.length - 1));
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function submit() {
    const err = validate();
    if (err) return toast.error(err);
    const fd = new FormData();
    const { zone, savedProfileId, ...rest } = s;
    const website = (document.getElementById("website") as HTMLInputElement | null)?.value ?? "";
    fd.set(
      "payload",
      JSON.stringify({
        ...rest,
        zone: s.fabricMethod === "rider_pickup" ? zone : undefined,
        savedProfileId: savedProfileId || undefined,
        couponCode: coupon?.coupon.code,
        look: look || undefined,
        website,
      }),
    );
    if (slip) fd.set("slip", slip);
    references.forEach((f) => fd.append("references", f));
    startTransition(async () => {
      const res = await createOrder(await compressFormData(fd));
      if (!res.ok) return void toast.error(res.error);
      try {
        localStorage.removeItem(DRAFT_KEY);
      } catch {}
      setDone(res.data);
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  }

  if (done) {
    const msg = `Assalam o Alaikum, payment slip for order ${done.orderNo}, amount ${rs(done.advance)}.`;
    return (
      <motion.div initial={{ opacity: 0, y: 30 }} animate={{ opacity: 1, y: 0 }} className="mx-auto max-w-2xl py-10 text-center">
        <motion.div
          initial={{ scale: 0 }}
          animate={{ scale: 1 }}
          transition={{ type: "spring", stiffness: 200, damping: 14, delay: 0.2 }}
          className="mx-auto grid size-20 place-items-center rounded-full bg-plum text-ivory"
        >
          <Check className="size-9" />
        </motion.div>
        <p className="eyebrow mt-8">Order received</p>
        <h2 className="font-display mt-3 text-5xl text-plum">{done.orderNo}</h2>
        <p className="mx-auto mt-5 max-w-md text-muted">
          {slip || s.txnId
            ? "We're verifying your payment slip. You'll get a WhatsApp confirmation with your pickup details shortly."
            : `Your slot is reserved for 24 hours. Please transfer the advance of ${rs(done.advance)} and send us the slip.`}
        </p>
        {done.pickupCode && (
          <div className="mx-auto mt-8 max-w-xs rounded-[var(--radius-lg)] bg-plum p-6 text-ivory">
            <p className="text-xs tracking-[0.2em] text-ivory/60 uppercase">Pickup handover code</p>
            <p className="font-display mt-2 text-5xl tracking-[0.3em] text-gold-soft">{done.pickupCode}</p>
            <p className="mt-3 text-xs text-ivory/70">Give this code to the Laraib rider when they collect your fabric. It&rsquo;s also on the Track order page.</p>
          </div>
        )}
        <div className="mt-10 flex flex-wrap justify-center gap-3">
          {!slip && (
            <a href={whatsappLink(msg)} target="_blank" rel="noopener noreferrer" className="inline-flex h-14 items-center gap-2 rounded-full bg-[#1f7a4d] px-8 text-white">
              <MessageCircle className="size-4" /> Send slip on WhatsApp
            </a>
          )}
          <ButtonLink href="/track" variant="outline" size="lg">
            Track this order
          </ButtonLink>
        </div>
      </motion.div>
    );
  }

  return (
    <div className="grid gap-10 lg:grid-cols-[1fr_380px]">
      <div>
        {savedDraft && !draftHandled && step === 0 && (
          <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} className="mb-8 flex flex-wrap items-center justify-between gap-3 rounded-[var(--radius-md)] border border-gold/40 bg-gold/10 px-5 py-4 text-sm">
            <span>You have an unfinished order saved on this device.</span>
            <span className="flex gap-2">
              <Button size="sm" variant="ghost" onClick={() => setDraftHandled(true)}>
                Start fresh
              </Button>
              <Button size="sm" onClick={restoreDraft}>
                Continue it
              </Button>
            </span>
          </motion.div>
        )}

        {/* progress */}
        <ol className="mb-10 grid grid-cols-4 gap-2">
          {steps.map((label, i) => (
            <li key={label}>
              <div className="h-1 overflow-hidden rounded-full bg-line">
                <motion.div className="h-full bg-plum" initial={false} animate={{ width: i <= step ? "100%" : "0%" }} transition={{ duration: 0.6 }} />
              </div>
              <p className={cn("mt-2 hidden text-xs sm:block", i === step ? "font-semibold text-plum" : "text-muted")}>
                {i + 1}. {label}
              </p>
            </li>
          ))}
        </ol>

        <AnimatePresence mode="wait" custom={dir}>
          <motion.div
            key={step}
            custom={dir}
            initial={{ opacity: 0, x: dir * 40 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: dir * -40 }}
            transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
          >
            {step === 0 && (
              <div className="space-y-10">
                <section>
                  <h2 className="text-3xl text-plum">What are we stitching?</h2>
                  <div className="mt-6 grid gap-3 sm:grid-cols-2">
                    {garments.map((g) => (
                      <button
                        key={g.slug}
                        type="button"
                        onClick={() => set("garment", g.slug)}
                        className={cn(
                          "rounded-[var(--radius-md)] border p-5 text-left transition-all duration-300",
                          s.garment === g.slug ? "border-plum bg-plum/[0.04] shadow-[inset_0_0_0_1px_var(--color-plum)]" : "border-line hover:border-plum/40",
                        )}
                      >
                        <div className="flex items-center justify-between">
                          <p className="font-semibold">{g.name}</p>
                          <p className="text-sm text-muted">from {rs(g.basePrice)}</p>
                        </div>
                        <p className="mt-1 text-sm text-muted">{g.blurb}</p>
                      </button>
                    ))}
                  </div>
                </section>

                {designOptions.map((group) => (
                  <section key={group.key}>
                    <h3 className="text-xl text-plum">{group.label}</h3>
                    <div className="mt-4 flex flex-wrap gap-2">
                      {group.options.map((o) => (
                        <Chip key={o.value} active={s.options[group.key] === o.value} onClick={() => set("options", { ...s.options, [group.key]: o.value })}>
                          {o.label}
                          {o.price > 0 && <span className="ml-1.5 opacity-60">+{o.price}</span>}
                        </Chip>
                      ))}
                    </div>
                  </section>
                ))}

                <section>
                  <h3 className="text-xl text-plum">Add-ons</h3>
                  <div className="mt-4 flex flex-wrap gap-2">
                    {addons.map((a) => (
                      <Chip
                        key={a.value}
                        active={s.addons.includes(a.value)}
                        onClick={() => set("addons", s.addons.includes(a.value) ? s.addons.filter((x) => x !== a.value) : [...s.addons, a.value])}
                      >
                        {a.label} <span className="ml-1.5 opacity-60">+{a.price}</span>
                      </Chip>
                    ))}
                  </div>
                </section>

                <section className="grid gap-6 sm:grid-cols-2">
                  <div>
                    <Label htmlFor="qty">Number of suits</Label>
                    <Input id="qty" type="number" min={1} max={20} value={s.qty} onChange={(e) => set("qty", Math.max(1, Number(e.target.value) || 1))} />
                  </div>
                  <div>
                    <Label>Reference pictures (“make it like this”)</Label>
                    <label className="flex h-12 cursor-pointer items-center gap-2 rounded-[var(--radius-md)] border border-dashed border-line px-4 text-sm text-muted hover:border-plum">
                      <ImagePlus className="size-4" />
                      {references.length ? `${references.length} picture(s) added` : "Upload up to 4 pictures"}
                      <input type="file" accept="image/*" multiple className="sr-only" onChange={(e) => setReferences(Array.from(e.target.files ?? []).slice(0, 4))} />
                    </label>
                  </div>
                </section>
              </div>
            )}

            {step === 1 && (
              <div className="space-y-8">
                <h2 className="text-3xl text-plum">How should we take your measurements?</h2>
                {customer && customer.profiles.length > 0 && (
                  <section>
                    <p className="eyebrow">Your saved profiles</p>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {customer.profiles.map((p) => (
                        <Chip key={p.id} active={s.savedProfileId === p.id} onClick={() => set("savedProfileId", p.id)}>
                          {p.name} <span className="ml-1 opacity-60 capitalize">· {p.source.replace(/_/g, " ")}</span>
                        </Chip>
                      ))}
                      <Chip active={!s.savedProfileId} onClick={() => set("savedProfileId", "")}>
                        New measurements
                      </Chip>
                    </div>
                  </section>
                )}
                {s.savedProfileId ? (
                  <div>
                    <Label htmlFor="fitNotesSaved">Changes for this order (optional)</Label>
                    <Input id="fitNotesSaved" value={s.measurement.notes ?? ""} onChange={(e) => setM("notes", e.target.value)} placeholder="e.g. 1 inch longer shirt this time" />
                  </div>
                ) : (
                <>
                {customer && (
                  <div className="max-w-xs">
                    <Label htmlFor="profileName">Save these measurements as</Label>
                    <Input id="profileName" value={s.profileName} onChange={(e) => set("profileName", e.target.value)} placeholder="Me, Ammi, Sister…" />
                  </div>
                )}
                <div className="grid gap-3 sm:grid-cols-2">
                  {measurementMethods.map((m) => (
                    <button
                      key={m.value}
                      type="button"
                      onClick={() => set("measurementMethod", m.value)}
                      className={cn(
                        "relative rounded-[var(--radius-md)] border p-5 text-left transition-all duration-300",
                        s.measurementMethod === m.value ? "border-plum bg-plum/[0.04] shadow-[inset_0_0_0_1px_var(--color-plum)]" : "border-line hover:border-plum/40",
                      )}
                    >
                      {m.badge && <span className="absolute top-4 right-4 text-[0.65rem] font-semibold tracking-wider text-gold uppercase">{m.badge}</span>}
                      <p className="font-semibold">{m.title}</p>
                      <p className="mt-1 text-sm text-muted">{m.desc}</p>
                    </button>
                  ))}
                </div>

                <motion.div key={s.measurementMethod} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="rounded-[var(--radius-lg)] bg-cream/70 p-6">
                  {s.measurementMethod === "standard_size" && (
                    <div className="space-y-5">
                      <div>
                        <Label>Your size</Label>
                        <div className="flex flex-wrap gap-2">
                          {standardSizes.map((sz) => (
                            <Chip key={sz} active={s.measurement.size === sz} onClick={() => setM("size", sz)}>
                              {sz}
                            </Chip>
                          ))}
                        </div>
                      </div>
                      <FitPicker value={s.measurement.fit} onChange={(v) => setM("fit", v)} />
                    </div>
                  )}
                  {s.measurementMethod === "brand_match" && (
                    <div className="grid gap-5 sm:grid-cols-2">
                      <div>
                        <Label htmlFor="brand">Brand you usually wear</Label>
                        <Select id="brand" value={s.measurement.brand ?? ""} onChange={(e) => setM("brand", e.target.value)}>
                          <option value="">Choose a brand</option>
                          {benchmarkBrands.map((b) => (
                            <option key={b}>{b}</option>
                          ))}
                        </Select>
                      </div>
                      <div>
                        <Label htmlFor="brandSize">Your size there</Label>
                        <Select id="brandSize" value={s.measurement.size ?? "M"} onChange={(e) => setM("size", e.target.value)}>
                          {standardSizes.map((sz) => (
                            <option key={sz}>{sz}</option>
                          ))}
                        </Select>
                      </div>
                      <div className="sm:col-span-2">
                        <FitPicker value={s.measurement.fit} onChange={(v) => setM("fit", v)} />
                      </div>
                      <p className="text-xs text-muted sm:col-span-2">Brand names are used only for size comparison; we are not affiliated with them.</p>
                    </div>
                  )}
                  {s.measurementMethod === "self" && (
                    <div className="grid gap-4 sm:grid-cols-2">
                      {selfMeasureFields.map((f) => (
                        <div key={f.key}>
                          <Label htmlFor={f.key}>
                            {f.label} <span className="font-normal text-muted">(inches)</span>
                          </Label>
                          <Input
                            id={f.key}
                            inputMode="decimal"
                            value={s.measurement[f.key] ?? ""}
                            onChange={(e) => setM(f.key, e.target.value.replace(/[^\d.]/g, ""))}
                            placeholder={f.hint}
                          />
                        </div>
                      ))}
                    </div>
                  )}
                  {s.measurementMethod === "home_visit" && (
                    <p className="text-sm text-muted">
                      A trained Laraib measurer (female staff by default) will visit at your pickup slot. We&rsquo;ll measure and collect your fabric in the same visit. Family members can be measured too — mention them in the notes.
                    </p>
                  )}
                  {s.measurementMethod === "sample_suit" && (
                    <p className="text-sm text-muted">
                      Keep a suit that fits you well ready with your fabric. Our rider tags it with a QR code; the master tailor copies it and it comes back with your order.
                    </p>
                  )}
                  {s.measurementMethod === "video_call" && (
                    <p className="text-sm text-muted">After you order, we&rsquo;ll WhatsApp you to book a 10-minute video call and guide you through each measurement.</p>
                  )}
                  <div className="mt-5">
                    <Label htmlFor="fitNotes">Fit notes (optional)</Label>
                    <Input id="fitNotes" value={s.measurement.notes ?? ""} onChange={(e) => setM("notes", e.target.value)} placeholder="e.g. sleeves 1 inch longer, loose at the waist" />
                  </div>
                </motion.div>
                </>
                )}
              </div>
            )}

            {step === 2 && (
              <div className="space-y-10">
                <section>
                  <h2 className="text-3xl text-plum">How will your fabric reach us?</h2>
                  <div className="mt-6 grid gap-3 sm:grid-cols-3">
                    {[
                      { v: "rider_pickup", t: "Laraib rider pickup", d: "We collect & return to your door" },
                      { v: "dropoff", t: "Drop off at studio", d: "Garhi Shahu, free" },
                      { v: "courier", t: "Courier it to us", d: "For customers outside Lahore" },
                    ].map((o) => (
                      <button
                        key={o.v}
                        type="button"
                        onClick={() => set("fabricMethod", o.v as State["fabricMethod"])}
                        className={cn(
                          "rounded-[var(--radius-md)] border p-5 text-left transition-all",
                          s.fabricMethod === o.v ? "border-plum shadow-[inset_0_0_0_1px_var(--color-plum)]" : "border-line hover:border-plum/40",
                        )}
                      >
                        <p className="font-semibold">{o.t}</p>
                        <p className="mt-1 text-sm text-muted">{o.d}</p>
                      </button>
                    ))}
                  </div>
                </section>

                {s.fabricMethod === "rider_pickup" && (
                  <motion.section initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} className="space-y-5 overflow-hidden">
                    <div>
                      <Label htmlFor="area">Your area</Label>
                      <Select
                        id="area"
                        value={s.area}
                        onChange={(e) => {
                          const zone = zones.find((z) => z.areas.includes(e.target.value));
                          setS((prev) => ({ ...prev, area: e.target.value, zone: zone?.code ?? prev.zone }));
                        }}
                      >
                        <option value="">Choose your area</option>
                        {zones.map((z) => (
                          <optgroup key={z.code} label={`Zone ${z.code} · ${z.name} — ${rs(z.fee)}/trip`}>
                            {z.areas.map((a) => (
                              <option key={a}>{a}</option>
                            ))}
                          </optgroup>
                        ))}
                      </Select>
                      {s.zone === "C" && s.area && <p className="mt-2 text-xs text-muted">Zone C pickups run on Tuesdays and Fridays.</p>}
                    </div>
                    <div>
                      <Label htmlFor="address">Full address</Label>
                      <Textarea id="address" className="min-h-20" value={s.address} onChange={(e) => set("address", e.target.value)} placeholder="House #, street, block" />
                    </div>
                    <div>
                      <Label htmlFor="landmark">Nearest landmark</Label>
                      <Input id="landmark" value={s.landmark} onChange={(e) => set("landmark", e.target.value)} placeholder="e.g. near the mosque / park" />
                    </div>
                    <div className="grid gap-5 sm:grid-cols-2">
                      <div>
                        <Label htmlFor="pickupDate">Pickup date</Label>
                        <Input id="pickupDate" type="date" min={minDate} value={s.pickupDate} onChange={(e) => set("pickupDate", e.target.value)} />
                      </div>
                      <div>
                        <Label htmlFor="slot">Time slot</Label>
                        <Select id="slot" value={s.pickupSlot} onChange={(e) => set("pickupSlot", e.target.value)}>
                          {pickupSlots.map((p) => (
                            <option key={p}>{p}</option>
                          ))}
                        </Select>
                      </div>
                    </div>
                  </motion.section>
                )}

                <section>
                  <h3 className="text-xl text-plum">Delivery speed</h3>
                  <div className="mt-4 grid gap-3 sm:grid-cols-3">
                    {tiers.map((t) => (
                      <button
                        key={t.value}
                        type="button"
                        onClick={() => set("tier", t.value)}
                        className={cn(
                          "rounded-[var(--radius-md)] border p-5 text-left transition-all",
                          s.tier === t.value ? "border-plum shadow-[inset_0_0_0_1px_var(--color-plum)]" : "border-line hover:border-plum/40",
                        )}
                      >
                        <p className="font-semibold">{t.label}</p>
                        <p className="text-sm text-muted">{t.days}</p>
                        <p className="mt-2 text-sm">{t.fee ? `+${rs(t.fee)} / suit` : "Included"}</p>
                      </button>
                    ))}
                  </div>
                </section>
              </div>
            )}

            {step === 3 && (
              <div className="space-y-10">
                <section className="space-y-5">
                  <h2 className="text-3xl text-plum">Your details</h2>
                  <div className="grid gap-5 sm:grid-cols-2">
                    <div>
                      <Label htmlFor="name">Full name</Label>
                      <Input id="name" autoComplete="name" value={s.name} onChange={(e) => set("name", e.target.value)} />
                    </div>
                    <div>
                      <Label htmlFor="phone">WhatsApp number</Label>
                      <Input id="phone" inputMode="tel" autoComplete="tel" placeholder="0300 1234567" value={s.phone} onChange={(e) => set("phone", e.target.value)} />
                    </div>
                  </div>
                  <div>
                    <Label htmlFor="notes">Anything else? (optional)</Label>
                    <Textarea id="notes" className="min-h-20" value={s.notes} onChange={(e) => set("notes", e.target.value)} />
                  </div>
                </section>

                <section>
                  <h2 className="text-3xl text-plum">Pay the advance</h2>
                  <p className="mt-2 text-muted">
                    Transfer <strong className="text-ink">{rs(price.advance)}</strong> (50%) to any account below. Write your name in the transfer note. The balance is paid to our rider on delivery.
                  </p>
                  <div className="mt-6 flex flex-wrap gap-2">
                    {[...paymentAccounts.map((a) => ({ v: a.type, l: a.label })), { v: "whatsapp", l: "I'll send the slip on WhatsApp" }].map((o) => (
                      <Chip key={o.v} active={s.paymentMethod === o.v} onClick={() => set("paymentMethod", o.v as State["paymentMethod"])}>
                        {o.l}
                      </Chip>
                    ))}
                  </div>

                  {s.paymentMethod !== "whatsapp" ? (
                    <motion.div key={s.paymentMethod} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="mt-6 space-y-6">
                      {paymentAccounts
                        .filter((a) => a.type === s.paymentMethod)
                        .map((a) => (
                          <div key={a.type} className="rounded-[var(--radius-lg)] border border-line bg-white/60 p-6">
                            <p className="eyebrow">{a.label}</p>
                            <div className="mt-4 divide-y divide-dashed divide-line">
                              <CopyRow label="Account title" value={a.title} />
                              {a.bank && <CopyRow label="Bank" value={a.bank} />}
                              <CopyRow label={a.type === "bank" ? "Account no." : "Number"} value={a.number} />
                              {a.iban && <CopyRow label="IBAN" value={a.iban} />}
                              <CopyRow label="Amount" value={String(price.advance)} />
                            </div>
                          </div>
                        ))}
                      <div className="grid gap-5 sm:grid-cols-2">
                        <div>
                          <Label>Upload payment slip / screenshot</Label>
                          <label
                            className={cn(
                              "flex h-12 cursor-pointer items-center gap-2 rounded-[var(--radius-md)] border border-dashed px-4 text-sm transition-colors",
                              slip ? "border-success text-success" : "border-line text-muted hover:border-plum",
                            )}
                          >
                            {slip ? <Check className="size-4" /> : <Upload className="size-4" />}
                            <span className="truncate">{slip ? slip.name : "Choose image or PDF"}</span>
                            <input type="file" accept="image/*,application/pdf" capture="environment" className="sr-only" onChange={(e) => setSlip(e.target.files?.[0] ?? null)} />
                          </label>
                        </div>
                        <div>
                          <Label htmlFor="txn">Transaction ID (optional)</Label>
                          <Input id="txn" value={s.txnId} onChange={(e) => set("txnId", e.target.value)} />
                        </div>
                      </div>
                      <p className="text-xs text-muted">You can also place the order now and send the slip within 24 hours.</p>
                    </motion.div>
                  ) : (
                    <p className="mt-6 rounded-[var(--radius-md)] bg-cream p-5 text-sm text-muted">
                      After placing the order you&rsquo;ll get a button that opens WhatsApp with your order number and amount filled in.
                    </p>
                  )}
                </section>

                <section>
                  <Label htmlFor="coupon">Coupon code</Label>
                  {coupon ? (
                    <div className="flex h-12 items-center justify-between rounded-[var(--radius-md)] border border-success/40 bg-success/5 px-4 text-sm">
                      <span className="text-success">
                        <Check className="mr-1 inline size-4" /> {coupon.coupon.code} · {coupon.label}
                      </span>
                      <button type="button" className="text-muted underline" onClick={() => setCoupon(null)}>
                        Remove
                      </button>
                    </div>
                  ) : (
                    <div className="flex gap-2">
                      <Input id="coupon" value={couponInput} onChange={(e) => setCouponInput(e.target.value.toUpperCase())} placeholder="e.g. EID10" className="uppercase" />
                      <Button type="button" variant="outline" onClick={applyCoupon} disabled={checkingCoupon}>
                        {checkingCoupon ? "…" : "Apply"}
                      </Button>
                    </div>
                  )}
                </section>

                {/* honeypot — hidden from people, bots fill it */}
                <input id="website" name="website" tabIndex={-1} autoComplete="off" aria-hidden className="absolute -left-[9999px] h-0 w-0 opacity-0" />

                <label className="flex cursor-pointer items-start gap-3 text-sm text-muted">
                  <input type="checkbox" className="mt-1 size-4 accent-[var(--color-plum)]" checked={s.showcaseConsent} onChange={(e) => set("showcaseConsent", e.target.checked)} />
                  Laraib Creative may photograph my finished suit (no faces) for the “Stitched by Laraib” gallery.
                </label>
              </div>
            )}
          </motion.div>
        </AnimatePresence>

        <div className="mt-12 flex items-center justify-between border-t border-line pt-6">
          <Button variant="ghost" onClick={() => go(-1)} disabled={step === 0} className={step === 0 ? "invisible" : ""}>
            <ArrowLeft className="size-4" /> Back
          </Button>
          {step < steps.length - 1 ? (
            <Button size="lg" onClick={() => go(1)}>
              Continue <ArrowRight className="size-4" />
            </Button>
          ) : (
            <Button size="lg" onClick={submit} disabled={pending}>
              {pending ? "Placing order…" : "Place order"}
            </Button>
          )}
        </div>
      </div>

      {/* live summary */}
      <aside className="lg:sticky lg:top-28 lg:self-start">
        <div className="overflow-hidden rounded-[var(--radius-lg)] border border-line bg-white/60">
          <div className="relative aspect-[16/10] overflow-hidden">
            <AnimatePresence mode="wait">
              <motion.div key={s.garment} className="h-full" initial={{ opacity: 0, scale: 1.04 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.5 }}>
                <MediaImage src={media[`service.${s.garment}`]?.url} alt={garments[Math.max(garmentIndex, 0)].name} sizes="380px" tone={garmentIndex} />
              </motion.div>
            </AnimatePresence>
            {look && <span className="absolute bottom-3 left-3 max-w-[85%] truncate rounded-full bg-ivory/95 px-3 py-1 text-xs text-plum">Look: {look}</span>}
          </div>
          <div className="space-y-3 p-6 text-sm">
            <p className="font-display text-xl text-plum">
              {garments[Math.max(garmentIndex, 0)].name} × {s.qty}
            </p>
            <p className="text-xs text-muted">
              {designOptions
                .map((g) => g.options.find((o) => o.value === s.options[g.key])?.label)
                .filter(Boolean)
                .join(" · ")}
            </p>
            <Row label="Stitching" value={rs(price.subtotal)} />
            {price.discount > 0 && <Row label={`Coupon ${coupon?.coupon.code}`} value={`−${rs(price.discount)}`} />}
            {price.urgencyFee > 0 && <Row label="Urgency" value={rs(price.urgencyFee)} />}
            {s.fabricMethod === "rider_pickup" && <Row label="Pickup & delivery" value={price.deliveryFee ? rs(price.deliveryFee) : "Free"} />}
            <div className="stitch-rule my-2" />
            <div className="flex items-baseline justify-between">
              <span className="font-semibold">Total</span>
              <span className="font-display text-3xl text-plum">
                <AnimatedNumber value={price.total} prefix="Rs " />
              </span>
            </div>
            <Row label="Advance to pay now (50%)" value={rs(price.advance)} />
            <div className="mt-2 flex items-center justify-between rounded-[var(--radius-md)] bg-cream px-4 py-3">
              <span className="text-xs text-muted">
                Estimated delivery
                <span className="block text-[0.7rem]">{tiers.find((t) => t.value === s.tier)?.label} · Sundays off</span>
              </span>
              <AnimatePresence mode="wait">
                <motion.span key={estimate} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }} className="font-display text-lg text-plum">
                  {formatDay(estimate)}
                </motion.span>
              </AnimatePresence>
            </div>
          </div>
        </div>
      </aside>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-4">
      <span className="text-muted">{label}</span>
      <span className="tabular-nums">{value}</span>
    </div>
  );
}

function FitPicker({ value, onChange }: { value?: string; onChange: (v: string) => void }) {
  return (
    <div>
      <Label>Preferred fit</Label>
      <div className="flex flex-wrap gap-2">
        {[
          ["slim", "Slim"],
          ["regular", "Regular"],
          ["comfort", "Comfort (loose)"],
        ].map(([v, l]) => (
          <Chip key={v} active={(value ?? "regular") === v} onClick={() => onChange(v)}>
            {l}
          </Chip>
        ))}
      </div>
    </div>
  );
}
