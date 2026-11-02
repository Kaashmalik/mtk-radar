import type { Product } from '@/data/products';
import { Bell, Camera, Download, Heart, Pause, Play, Search, ShieldAlert, ShoppingBag, Star, TrendingUp, Users } from 'lucide-react';

/* Coded UI previews of each product. Pure markup + CSS so they stay crisp at any size. */

function BrowserFrame({ url, accent, children }: { url: string; accent: string; children: React.ReactNode }) {
  return (
    <div className="overflow-hidden rounded-2xl border border-line bg-elevated shadow-float">
      <div className="flex items-center gap-3 border-b border-line bg-muted px-4 py-2.5">
        <div className="flex gap-1.5">
          <span className="size-2.5 rounded-full bg-[#ff5f57]" />
          <span className="size-2.5 rounded-full bg-[#febc2e]" />
          <span className="size-2.5 rounded-full bg-[#28c840]" />
        </div>
        <div className="flex min-w-0 flex-1 items-center gap-2 rounded-md bg-elevated px-3 py-1 text-[11px] text-fg-subtle">
          <span className="size-1.5 shrink-0 rounded-full" style={{ background: accent }} />
          <span className="truncate">{url}</span>
        </div>
      </div>
      <div className="text-[11px] leading-tight">{children}</div>
    </div>
  );
}

function Sidebar({ accent, items, active = 0 }: { accent: string; items: string[]; active?: number }) {
  return (
    <div className="hidden w-32 shrink-0 space-y-1 border-r border-line p-3 sm:block">
      {items.map((it, i) => (
        <div
          key={it}
          className="rounded-md px-2 py-1.5 font-medium"
          style={i === active ? { background: `${accent}1f`, color: accent } : { color: 'var(--fg-subtle)' }}
        >
          {it}
        </div>
      ))}
    </div>
  );
}

function Kpi({ label, value, delta, accent }: { label: string; value: string; delta?: string; accent: string }) {
  return (
    <div className="rounded-lg border border-line p-2.5">
      <p className="text-fg-subtle">{label}</p>
      <p className="mt-1 font-display text-base font-bold">{value}</p>
      {delta && (
        <p className="mt-0.5 flex items-center gap-1 font-semibold" style={{ color: accent }}>
          <TrendingUp className="size-3" /> {delta}
        </p>
      )}
    </div>
  );
}

function Bars({ values, accent }: { values: number[]; accent: string }) {
  return (
    <div className="flex h-24 items-end gap-1.5">
      {values.map((v, i) => (
        <div
          key={i}
          className="grow-bar flex-1 rounded-t"
          style={{
            height: `${v}%`,
            background: i === values.length - 1 ? accent : `${accent}55`,
            animationDelay: `${i * 60}ms`,
          }}
        />
      ))}
    </div>
  );
}

function InstalEaseDemo({ accent }: { accent: string }) {
  const rows = [
    ['Ali Traders', 'Samsung A55', 'Rs 8,500', 'Paid'],
    ['Usman K.', 'Haier AC 1.5T', 'Rs 12,000', 'Due'],
    ['Sana B.', 'Dawlance Fridge', 'Rs 6,200', 'Overdue'],
  ];
  return (
    <BrowserFrame url="instalease.mtkcodex.site/dashboard" accent={accent}>
      <div className="flex">
        <Sidebar accent={accent} items={['Dashboard', 'Contracts', 'Customers', 'Payments', 'Reports']} />
        <div className="min-w-0 flex-1 space-y-3 p-3">
          <div className="grid grid-cols-3 gap-2">
            <Kpi label="Collected" value="Rs 4.2M" delta="+18%" accent={accent} />
            <Kpi label="Active contracts" value="1,284" delta="+42" accent={accent} />
            <Kpi label="Recovery rate" value="96.4%" accent={accent} />
          </div>
          <div className="rounded-lg border border-line p-3">
            <p className="mb-2 font-semibold">Monthly collections</p>
            <Bars values={[38, 52, 45, 61, 58, 72, 66, 84, 79, 92]} accent={accent} />
          </div>
          <div className="overflow-hidden rounded-lg border border-line">
            {rows.map((r) => (
              <div key={r[0]} className="grid grid-cols-4 gap-2 border-b border-line px-3 py-2 last:border-0">
                <span className="truncate font-medium">{r[0]}</span>
                <span className="truncate text-fg-subtle">{r[1]}</span>
                <span>{r[2]}</span>
                <span
                  className="justify-self-start rounded-full px-2 py-0.5 font-semibold"
                  style={{
                    color: r[3] === 'Paid' ? '#16a34a' : r[3] === 'Due' ? '#d97706' : '#dc2626',
                    background: r[3] === 'Paid' ? '#16a34a1a' : r[3] === 'Due' ? '#d977061a' : '#dc26261a',
                  }}
                >
                  {r[3]}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </BrowserFrame>
  );
}

function DairyDemo({ accent }: { accent: string }) {
  const pts = [30, 42, 38, 55, 50, 64, 60, 72, 70, 82, 78, 90];
  const path = pts.map((v, i) => `${i === 0 ? 'M' : 'L'} ${(i / (pts.length - 1)) * 300} ${100 - v}`).join(' ');
  return (
    <BrowserFrame url="dairy.mtkcodex.site/farm/overview" accent={accent}>
      <div className="flex">
        <Sidebar accent={accent} items={['Overview', 'Herd', 'Milk log', 'Health', 'Finance']} />
        <div className="min-w-0 flex-1 space-y-3 p-3">
          <div className="grid grid-cols-3 gap-2">
            <Kpi label="Today's milk" value="2,140 L" delta="+6.2%" accent={accent} />
            <Kpi label="Animals" value="312" accent={accent} />
            <Kpi label="Avg / cow" value="14.8 L" delta="+0.9" accent={accent} />
          </div>
          <div className="rounded-lg border border-line p-3">
            <div className="mb-2 flex items-center justify-between">
              <p className="font-semibold">Milk production · 12 weeks</p>
              <span className="rounded-full px-2 py-0.5 font-semibold" style={{ background: `${accent}1f`, color: accent }}>
                IoT synced
              </span>
            </div>
            <svg viewBox="0 0 300 100" className="h-24 w-full" preserveAspectRatio="none" aria-hidden>
              <path d={`${path} L 300 100 L 0 100 Z`} fill={`${accent}22`} />
              <path d={path} fill="none" stroke={accent} strokeWidth="2.5" vectorEffect="non-scaling-stroke" />
            </svg>
          </div>
          <div className="grid grid-cols-2 gap-2">
            {[
              ['Vaccination due', '14 animals', '#f59e0b'],
              ['Expected calving', '6 this week', accent],
            ].map(([t, v, c]) => (
              <div key={t} className="flex items-center gap-2 rounded-lg border border-line p-2.5">
                <span className="size-2 rounded-full" style={{ background: c }} />
                <span className="text-fg-subtle">{t}</span>
                <span className="ml-auto font-semibold">{v}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </BrowserFrame>
  );
}

function EduDemo({ accent }: { accent: string }) {
  return (
    <BrowserFrame url="greenfield.mtkedu.app/admin" accent={accent}>
      <div className="flex">
        <Sidebar accent={accent} items={['Dashboard', 'Students', 'Attendance', 'Exams', 'Fees']} active={0} />
        <div className="min-w-0 flex-1 space-y-3 p-3">
          <div className="grid grid-cols-3 gap-2">
            <Kpi label="Students" value="2,086" accent={accent} />
            <Kpi label="Attendance" value="94.7%" delta="+2.1%" accent={accent} />
            <Kpi label="Fees collected" value="88%" accent={accent} />
          </div>
          <div className="grid grid-cols-[auto_1fr] items-center gap-4 rounded-lg border border-line p-3">
            <div
              className="grid size-20 place-items-center rounded-full"
              style={{ background: `conic-gradient(${accent} 0 82%, var(--bg-muted) 82% 100%)` }}
            >
              <div className="grid size-14 place-items-center rounded-full bg-elevated font-display text-sm font-bold">82%</div>
            </div>
            <div className="space-y-1.5">
              <p className="font-semibold">AI insight</p>
              <p className="text-fg-muted">
                23 students in Grade 9 are trending below 60% in Mathematics. Suggested: remedial sessions before mid-terms.
              </p>
            </div>
          </div>
          <div className="space-y-1.5 rounded-lg border border-line p-3">
            {[
              ['Grade 10-A', 97],
              ['Grade 9-B', 91],
              ['Grade 8-C', 86],
            ].map(([c, v]) => (
              <div key={c} className="flex items-center gap-2">
                <span className="w-16 shrink-0 text-fg-subtle">{c}</span>
                <div className="h-1.5 flex-1 rounded-full bg-muted">
                  <div className="h-full rounded-full" style={{ width: `${v}%`, background: accent }} />
                </div>
                <span className="w-8 text-right font-semibold">{v}%</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </BrowserFrame>
  );
}

function SslDemo({ accent }: { accent: string }) {
  const balls = ['1', '4', '•', '6', 'W', '2'];
  return (
    <BrowserFrame url="ssl.mtkcodex.site/live/final" accent={accent}>
      <div className="space-y-3 p-3">
        <div className="rounded-xl p-4 text-white" style={{ background: `linear-gradient(135deg, ${accent}, #7c2d12)` }}>
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-1.5 rounded-full bg-white/20 px-2 py-0.5 font-bold">
              <span className="pulse-dot size-1.5 rounded-full bg-white text-white" /> LIVE
            </span>
            <span className="opacity-80">Final · Over 17.4</span>
          </div>
          <div className="mt-3 grid grid-cols-[1fr_auto_1fr] items-center gap-2 text-center">
            <div>
              <p className="font-display text-xl font-bold">168/4</p>
              <p className="opacity-80">Lahore Lions</p>
            </div>
            <span className="opacity-70">vs</span>
            <div>
              <p className="font-display text-xl font-bold">172/8</p>
              <p className="opacity-80">Karachi Kings XI</p>
            </div>
          </div>
          <p className="mt-2 text-center opacity-90">Need 5 runs from 14 balls</p>
        </div>
        <div className="flex gap-1.5">
          {balls.map((b, i) => (
            <span
              key={i}
              className="grid size-7 place-items-center rounded-full border border-line font-bold"
              style={b === 'W' ? { background: accent, color: '#fff', borderColor: accent } : b === '6' || b === '4' ? { color: accent, borderColor: accent } : undefined}
            >
              {b}
            </span>
          ))}
        </div>
        <div className="rounded-lg border border-line p-3">
          <div className="mb-1.5 flex items-center gap-2">
            <span className="font-semibold">AI commentary</span>
            {['EN', 'UR', 'PA', 'PS', 'SD'].map((l, i) => (
              <span key={l} className="rounded px-1.5 py-0.5 text-[10px] font-semibold" style={i === 0 ? { background: `${accent}22`, color: accent } : { color: 'var(--fg-subtle)' }}>
                {l}
              </span>
            ))}
          </div>
          <p className="text-fg-muted">
            &ldquo;Short and wide outside off — and he&apos;s carved it over point for SIX! The Lions are within touching distance now.&rdquo;
          </p>
        </div>
      </div>
    </BrowserFrame>
  );
}

/** Stylised garment illustrations so the storefront preview shows real "products", not empty tiles. */
function DressArt({ kind, main, trim, bg }: { kind: 'lehenga' | 'suit' | 'lawn'; main: string; trim: string; bg: string }) {
  const id = `dress-${kind}`;
  return (
    <svg viewBox="0 0 100 125" className="h-full w-full" aria-hidden>
      <defs>
        <radialGradient id={`${id}-bg`} cx="50%" cy="35%" r="75%">
          <stop offset="0" stopColor="#fff7ed" />
          <stop offset="1" stopColor={bg} />
        </radialGradient>
        <linearGradient id={`${id}-fab`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor={main} />
          <stop offset="1" stopColor={main} stopOpacity="0.75" />
        </linearGradient>
        <pattern id={`${id}-emb`} width="6" height="6" patternUnits="userSpaceOnUse">
          <circle cx="3" cy="3" r="0.9" fill={trim} />
        </pattern>
      </defs>
      <rect width="100" height="125" fill={`url(#${id}-bg)`} />
      {/* hanger */}
      <path d="M50 8 q4 0 4 4 t-4 4 M50 16 L30 26 L70 26 Z" fill="none" stroke="#a8a29e" strokeWidth="1.2" strokeLinejoin="round" />
      {kind === 'lehenga' && (
        <>
          {/* dupatta drape */}
          <path d="M30 27 C18 50 20 80 26 104 L33 104 C30 80 32 52 40 30 Z" fill={trim} opacity="0.45" />
          {/* choli */}
          <path d="M36 26 L64 26 L66 44 L34 44 Z" fill={`url(#${id}-fab)`} />
          <path d="M34 44 L66 44" stroke={trim} strokeWidth="2" />
          {/* flared skirt */}
          <path d="M36 46 L64 46 L86 112 Q50 120 14 112 Z" fill={`url(#${id}-fab)`} />
          <path d="M36 46 L64 46 L86 112 Q50 120 14 112 Z" fill={`url(#${id}-emb)`} opacity="0.7" />
          <path d="M14 112 Q50 120 86 112" stroke={trim} strokeWidth="3.5" fill="none" />
          <path d="M22 92 Q50 99 78 92" stroke={trim} strokeWidth="1.2" fill="none" strokeDasharray="2 2" />
        </>
      )}
      {kind === 'suit' && (
        <>
          {/* long kameez with flare */}
          <path d="M38 26 L62 26 L70 34 L66 42 L64 40 L70 98 L30 98 L36 40 L34 42 L30 34 Z" fill={`url(#${id}-fab)`} />
          <path d="M44 26 L50 36 L56 26" fill="none" stroke={trim} strokeWidth="1.6" />
          <path d="M30 98 L70 98" stroke={trim} strokeWidth="3" />
          <path d="M40 50 L60 50 M38 62 L62 62" stroke={trim} strokeWidth="0.8" strokeDasharray="1.5 1.5" />
          {/* trousers */}
          <path d="M38 98 L46 98 L46 116 L39 116 Z M54 98 L62 98 L61 116 L54 116 Z" fill={main} opacity="0.55" />
          {/* sheer chiffon dupatta */}
          <path d="M62 27 C78 44 76 76 68 108 L62 106 C68 78 70 50 58 30 Z" fill="#ffffff" opacity="0.35" />
        </>
      )}
      {kind === 'lawn' && (
        <>
          {/* straight kurta with print */}
          <path d="M38 26 L62 26 L72 36 L66 46 L63 43 L64 104 L36 104 L37 43 L34 46 L28 36 Z" fill={`url(#${id}-fab)`} />
          <path d="M38 26 L62 26 L72 36 L66 46 L63 43 L64 104 L36 104 L37 43 L34 46 L28 36 Z" fill={`url(#${id}-emb)`} opacity="0.9" />
          <path d="M46 26 L50 40 L54 26" fill="none" stroke={trim} strokeWidth="1.6" />
          <path d="M42 58 q8 -8 16 0 q-8 8 -16 0 Z M42 78 q8 -8 16 0 q-8 8 -16 0 Z" fill={trim} opacity="0.85" />
          <path d="M36 104 L64 104" stroke={trim} strokeWidth="3" />
        </>
      )}
      {/* soft floor shadow */}
      <ellipse cx="50" cy="121" rx="30" ry="2.5" fill="#000" opacity="0.08" />
    </svg>
  );
}

function LaraibDemo({ accent }: { accent: string }) {
  const items = [
    { name: 'Bridal Lehenga', price: 'Rs 85,000', kind: 'lehenga' as const, main: '#9f1239', trim: '#f5c451', bg: '#fbcfe8', tag: 'Custom stitch' },
    { name: 'Chiffon Party Suit', price: 'Rs 18,500', kind: 'suit' as const, main: '#7e22ce', trim: '#fcd34d', bg: '#e9d5ff', tag: 'New' },
    { name: 'Embroidered Lawn', price: 'Rs 9,900', kind: 'lawn' as const, main: '#0f766e', trim: '#fde68a', bg: '#ccfbf1', tag: '−15%' },
  ];
  const stages = ['Order', 'Measure', 'Cutting', 'Stitching', 'QC', 'Shipped'];
  const current = 3;
  return (
    <BrowserFrame url="laraibcreative.studio/collections/bridal" accent={accent}>
      <div className="space-y-3 p-3">
        <div className="flex items-center gap-2">
          <div className="flex min-w-0 flex-1 items-center gap-2 rounded-lg border border-line px-3 py-2 text-fg-subtle">
            <Search className="size-3.5 shrink-0" /> <span className="truncate">Search bridal, party wear, fabrics…</span>
          </div>
          <span className="relative grid size-8 shrink-0 place-items-center rounded-lg border border-line">
            <ShoppingBag className="size-3.5" />
            <span className="absolute -right-1 -top-1 grid size-4 place-items-center rounded-full text-[9px] font-bold text-white" style={{ background: accent }}>
              2
            </span>
          </span>
        </div>

        <div className="flex items-center justify-between rounded-lg px-3 py-2 text-white" style={{ background: `linear-gradient(100deg, ${accent}, #7c2d12)` }}>
          <div>
            <p className="font-display text-xs font-bold">Bridal Collection 2026</p>
            <p className="text-[10px] opacity-85">Made to your measurements · free alterations</p>
          </div>
          <span className="rounded-full bg-white/20 px-2 py-0.5 text-[10px] font-semibold">Shop now →</span>
        </div>

        <div className="grid grid-cols-3 gap-2">
          {items.map((it) => (
            <div key={it.name} className="group overflow-hidden rounded-lg border border-line bg-elevated">
              <div className="relative aspect-[4/5] overflow-hidden">
                <div className="h-full transition-transform duration-500 group-hover:scale-105">
                  <DressArt kind={it.kind} main={it.main} trim={it.trim} bg={it.bg} />
                </div>
                <span className="absolute left-1.5 top-1.5 rounded-full px-1.5 py-0.5 text-[9px] font-bold text-white" style={{ background: it.tag.startsWith('−') ? '#dc2626' : accent }}>
                  {it.tag}
                </span>
                <span className="absolute right-1.5 top-1.5 grid size-5 place-items-center rounded-full bg-white/90 text-rose-500 shadow">
                  <Heart className="size-3" fill={it.kind === 'lehenga' ? 'currentColor' : 'none'} />
                </span>
              </div>
              <div className="p-2">
                <p className="truncate font-semibold">{it.name}</p>
                <div className="mt-0.5 flex items-center justify-between">
                  <span className="font-semibold" style={{ color: accent }}>
                    {it.price}
                  </span>
                  <span className="flex items-center gap-0.5 text-[10px] text-amber-500">
                    <Star className="size-2.5 fill-current" /> 4.9
                  </span>
                </div>
              </div>
            </div>
          ))}
        </div>

        <div className="rounded-lg border border-line p-3">
          <div className="mb-3 flex items-center justify-between">
            <p className="font-semibold">Order #LC-2048 · Custom stitching</p>
            <span className="rounded-full px-2 py-0.5 text-[10px] font-semibold" style={{ background: `${accent}1f`, color: accent }}>
              Est. delivery 6 days
            </span>
          </div>
          <div className="relative flex items-start">
            <div className="absolute left-[8%] right-[8%] top-[5px] h-0.5 rounded bg-line-strong" />
            <div className="absolute left-[8%] top-[5px] h-0.5 rounded" style={{ width: `${(current / (stages.length - 1)) * 84}%`, background: accent }} />
            {stages.map((s, i) => (
              <div key={s} className="relative flex flex-1 flex-col items-center gap-1">
                <span
                  className={`size-3 rounded-full border-2 ${i === current ? 'pulse-dot' : ''}`}
                  style={{
                    background: i <= current ? accent : 'var(--bg-elevated)',
                    borderColor: i <= current ? accent : 'var(--border-strong)',
                    color: accent,
                  }}
                />
                <span className={`text-[9px] ${i === current ? 'font-semibold text-fg' : 'text-fg-subtle'}`}>{s}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </BrowserFrame>
  );
}

function AlertProDemo({ accent }: { accent: string }) {
  return (
    <div className="mx-auto w-full max-w-[290px] rounded-[2.2rem] border border-line-strong bg-elevated p-2.5 shadow-float">
      <div className="overflow-hidden rounded-[1.7rem] bg-[#05080f] text-[11px] text-white">
        <div className="flex items-center justify-between px-4 pb-2 pt-3">
          <span className="font-semibold">AlertPro</span>
          <Bell className="size-3.5" />
        </div>
        <div className="relative mx-3 aspect-video overflow-hidden rounded-xl bg-[linear-gradient(160deg,#1e293b,#0f172a_60%,#111827)]">
          <div className="absolute inset-x-0 bottom-0 h-1/3 bg-[linear-gradient(transparent,#00000088)]" />
          <div className="absolute left-[18%] top-[22%] h-[62%] w-[20%] rounded border-2" style={{ borderColor: accent }}>
            <span className="absolute -top-4 left-0 whitespace-nowrap rounded px-1 text-[9px] font-bold text-black" style={{ background: accent }}>
              person 94%
            </span>
          </div>
          <div className="absolute right-[10%] top-[48%] h-[34%] w-[36%] rounded border-2 border-amber-400">
            <span className="absolute -top-4 left-0 whitespace-nowrap rounded bg-amber-400 px-1 text-[9px] font-bold text-black">car 88%</span>
          </div>
          <span className="absolute left-2 top-2 flex items-center gap-1 rounded bg-red-600 px-1.5 py-0.5 text-[9px] font-bold">
            <span className="pulse-dot size-1 rounded-full bg-white text-white" /> REC
          </span>
          <span className="absolute bottom-1.5 left-2 text-[9px] opacity-80">Front gate · CAM 01</span>
        </div>
        <div className="m-3 flex items-start gap-2 rounded-xl border border-red-500/40 bg-red-500/15 p-2.5">
          <ShieldAlert className="mt-0.5 size-4 shrink-0 text-red-400" />
          <div>
            <p className="font-semibold">Person detected</p>
            <p className="opacity-70">Front gate · just now · alarm on</p>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-2 px-3 pb-4">
          {['Garage', 'Backyard'].map((c) => (
            <div key={c} className="rounded-lg bg-white/5 p-2">
              <Camera className="size-3.5 opacity-70" />
              <p className="mt-1 font-medium">{c}</p>
              <p className="opacity-50">Clear</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function DownloaderDemo({ accent }: { accent: string }) {
  const items = [
    ['Product launch keynote.mp4', 72, '8.4 MB/s', '1m 12s'],
    ['Podcast EP 42.m4a', 100, 'Done', ''],
    ['Course lecture 07 (1080p)', 34, '5.1 MB/s', '3m 40s'],
    ['Conference playlist (12)', 0, 'Queued', ''],
  ] as const;
  return (
    <div className="overflow-hidden rounded-2xl border border-line bg-[#0b0f1c] text-[11px] text-white shadow-float">
      <div className="flex items-center justify-between border-b border-white/10 px-4 py-2.5">
        <span className="flex items-center gap-2 font-semibold">
          <Download className="size-3.5" style={{ color: accent }} /> MTK Download Manager
        </span>
        <div className="flex gap-1.5">
          <span className="size-2.5 rounded-full bg-white/20" />
          <span className="size-2.5 rounded-full bg-white/20" />
          <span className="size-2.5 rounded-full bg-red-500/80" />
        </div>
      </div>
      <div className="flex">
        <div className="hidden w-28 shrink-0 space-y-1 border-r border-white/10 p-3 sm:block">
          {['Queue', 'Completed', 'Scheduled', 'Settings'].map((s, i) => (
            <div key={s} className="rounded-md px-2 py-1.5" style={i === 0 ? { background: `${accent}33`, color: '#fff' } : { color: '#ffffff80' }}>
              {s}
            </div>
          ))}
        </div>
        <div className="min-w-0 flex-1 space-y-2 p-3">
          <div className="flex items-center gap-2 rounded-lg bg-white/5 px-3 py-2 text-white/50">
            Paste a link from 1000+ supported sites…
            <span className="ml-auto rounded-md px-2 py-1 font-semibold text-white" style={{ background: accent }}>
              Download
            </span>
          </div>
          {items.map(([name, pct, speed, eta]) => (
            <div key={name} className="rounded-lg bg-white/5 p-2.5">
              <div className="flex items-center gap-2">
                {pct === 100 ? <span className="text-emerald-400">✓</span> : pct > 0 ? <Pause className="size-3 opacity-70" /> : <Play className="size-3 opacity-70" />}
                <span className="truncate font-medium">{name}</span>
                <span className="ml-auto shrink-0 text-white/50">{speed}{eta && ` · ${eta}`}</span>
              </div>
              <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/10">
                <div
                  className="h-full rounded-full"
                  style={{
                    width: `${pct}%`,
                    background: pct === 100 ? '#34d399' : `repeating-linear-gradient(45deg, ${accent}, ${accent} 6px, ${accent}bb 6px, ${accent}bb 12px)`,
                    backgroundSize: '24px 100%',
                    animation: pct > 0 && pct < 100 ? 'progress-stripe 0.8s linear infinite' : undefined,
                  }}
                />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function RadarDemo({ accent }: { accent: string }) {
  const stages = ['Discover', 'Verify', 'Script', 'Capture', 'Render', 'Approve', 'Schedule', 'Publish'];
  const queue: [string, string, string][] = [
    ['YouTube', 'Tue 18:00', 'Scheduled'],
    ['TikTok', 'Tue 19:30', 'Awaiting approval'],
    ['Instagram', 'Wed 12:00', 'Rendering'],
  ];
  return (
    <BrowserFrame url="MTK Radar · Review" accent={accent}>
      <div className="flex">
        <Sidebar accent={accent} items={['Radar', 'Review', 'Studio', 'Queue', 'Calendar', 'Settings']} active={1} />
        <div className="min-w-0 flex-1 space-y-3 p-4">
          <div className="flex items-center justify-between gap-2">
            <p className="font-display text-sm font-bold">Offer pipeline</p>
            <span className="rounded-full px-2 py-0.5 font-semibold text-white" style={{ background: accent }}>
              Assisted
            </span>
          </div>
          <div className="flex items-center gap-1">
            {stages.map((s, i) => (
              <div key={s} className="flex min-w-0 flex-1 flex-col items-center gap-1">
                <span
                  className="grid size-5 place-items-center rounded-full text-[9px] font-bold text-white"
                  style={{ background: i < 5 ? accent : i === 5 ? '#f59e0b' : 'var(--border-strong)' }}
                >
                  {i < 5 ? '✓' : i + 1}
                </span>
                <span className="w-full truncate text-center text-[9px] text-fg-subtle">{s}</span>
              </div>
            ))}
          </div>
          <div className="rounded-lg border border-line p-2.5">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="truncate font-semibold">$300 cloud credits for students</p>
                <p className="text-fg-subtle">Official terms · snapshot 2h ago · hash 9f3a…c21</p>
              </div>
              <span className="shrink-0 rounded bg-emerald-500/15 px-1.5 py-0.5 font-semibold text-emerald-600">Verified</span>
            </div>
            <div className="mt-2 grid grid-cols-3 gap-1.5">
              <Kpi label="Confidence" value="0.94" accent={accent} />
              <Kpi label="Render QC" value="Passed" accent={accent} />
              <Kpi label="Expires" value="18 days" accent={accent} />
            </div>
          </div>
          <div className="space-y-1.5">
            {queue.map(([platform, when, state]) => (
              <div key={platform} className="flex items-center justify-between gap-2 rounded-md bg-muted px-2.5 py-1.5">
                <span className="font-semibold">{platform}</span>
                <span className="text-fg-subtle">{when}</span>
                <span className="font-semibold" style={{ color: state === 'Scheduled' ? accent : 'var(--fg-muted)' }}>
                  {state}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </BrowserFrame>
  );
}

export default function ProductDemo({ product }: { product: Product }) {
  const a = product.accent;
  switch (product.demo) {
    case 'instalease':
      return <InstalEaseDemo accent={a} />;
    case 'dairy':
      return <DairyDemo accent={a} />;
    case 'edu':
      return <EduDemo accent={a} />;
    case 'ssl':
      return <SslDemo accent={a} />;
    case 'laraib':
      return <LaraibDemo accent={a} />;
    case 'alertpro':
      return <AlertProDemo accent={a} />;
    case 'downloader':
      return <DownloaderDemo accent={a} />;
    case 'radar':
      return <RadarDemo accent={a} />;
  }
}

/* Small decorative widgets used in the hero */
export function HeroWidgets() {
  return (
    <>
      <div className="animate-float absolute -left-10 top-24 z-10 hidden w-48 rounded-2xl border border-line bg-elevated p-3 text-xs shadow-float md:block">
        <div className="flex items-center gap-2">
          <span className="grid size-8 place-items-center rounded-lg bg-accent-soft text-accent">
            <Users className="size-4" />
          </span>
          <div>
            <p className="text-fg-subtle">Active tenants</p>
            <p className="font-display text-base font-bold">500+</p>
          </div>
        </div>
      </div>
      <div className="animate-float absolute -bottom-6 -right-6 z-10 hidden w-52 rounded-2xl border border-line bg-elevated p-3 text-xs shadow-float md:block" style={{ animationDelay: '1.5s' }}>
        <div className="flex items-center gap-1 text-amber-500">
          {Array.from({ length: 5 }).map((_, i) => (
            <Star key={i} className="size-3.5 fill-current" />
          ))}
        </div>
        <p className="mt-1.5 font-medium">&ldquo;Production-grade from day one.&rdquo;</p>
        <p className="mt-0.5 text-fg-subtle">— InstalEase client</p>
      </div>
    </>
  );
}
