<div align="center">

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:7c3aed,50:06b6d4,100:22d3ee&height=220&section=header&text=MTK%20CODEX&fontSize=68&fontColor=ffffff&fontAlignY=38&desc=Code%20That%20Scales%20Your%20Business&descAlignY=58&descSize=22&descColor=22d3ee&animation=fadeIn" alt="MTK Codex Banner" width="100%" />

[![Next.js 16](https://img.shields.io/badge/Next.js_16-000000?style=for-the-badge&logo=nextdotjs&logoColor=white)](#-tech-stack)
[![React 19](https://img.shields.io/badge/React_19-23272F?style=for-the-badge&logo=react&logoColor=61DAFB)](#-tech-stack)
[![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?style=for-the-badge&logo=typescript&logoColor=white)](#-tech-stack)
[![Tailwind CSS v4](https://img.shields.io/badge/Tailwind_CSS_v4-06B6D4?style=for-the-badge&logo=tailwindcss&logoColor=white)](#-tech-stack)
&nbsp;
[![License: MIT](https://img.shields.io/badge/License-MIT-22c55e?style=for-the-badge&logo=opensourceinitiative&logoColor=white)](./LICENSE)
[![Stars](https://img.shields.io/github/stars/Kaashmalik/mtkcodex?style=for-the-badge&logo=github&color=yellow)](https://github.com/Kaashmalik/mtkcodex/stargazers)
[![Deploy to Netlify](https://img.shields.io/badge/Deploy-Netlify-00C7B7?style=for-the-badge&logo=netlify&logoColor=white)](https://app.netlify.com/start/deploy?repository=https://github.com/Kaashmalik/mtkcodex)

<img src="https://readme-typing-svg.demolab.com?font=Fira+Code&weight=600&size=22&pause=1200&color=22D3EE&center=true&vCenter=true&multiline=true&repeat=true&width=650&height=75&lines=SaaS+platforms+shipped+%E2%80%94+7+industries%2C+one+team.;Web+%2B+Mobile+%2B+Desktop+from+a+single+codebase.;Automation+that+works+while+your+business+sleeps." alt="Animated tagline" />

**[mtkcodex.tech](https://mtkcodex.tech)** — the company website of MTK Codex: SaaS products, software development, maintenance, audits and automation.

Visit the site · [Products](https://mtkcodex.tech/products) · [Services](https://mtkcodex.tech/services) · [Pricing](https://mtkcodex.tech/pricing) · [Contact](https://mtkcodex.tech/contact)

</div>

---

## ✨ Highlights

| | |
| --- | --- |
| 🏗️ **7 production platforms** | FinTech · AgriTech · EdTech · SportsTech · e-commerce · AI security · desktop software |
| ⚡ **95+ Lighthouse score** | Static-ready App Router pages with streaming demos and OG image generation |
| 🤖 **Automation-first** | Contact routing by `?intent=` / `?service=` / `?product=`, WhatsApp deep links, Resend email |
| 🔍 **SEO-complete** | Structured data, `sitemap.ts`, `robots.ts`, `llms.txt`, `ads.txt`, per-page OG images |
| 🎨 **Motion-rich UI** | Count-up stats, reveal-on-scroll, interactive product demos, dark/light theme |
| 🌍 **Global reach** | Lahore HQ with coverage across PK · AE · SA · UK · EU · US/CA |

## 🧰 Tech Stack

<div align="center">

[![Next.js](https://img.shields.io/badge/Next.js-000000?style=flat-square&logo=nextdotjs)](https://nextjs.org)
[![React](https://img.shields.io/badge/React-61DAFB?style=flat-square&logo=react&logoColor=black)](https://react.dev)
[![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?style=flat-square&logo=typescript&logoColor=white)](https://www.typescriptlang.org)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-06B6D4?style=flat-square&logo=tailwindcss&logoColor=white)](https://tailwindcss.com)
[![lucide-react](https://img.shields.io/badge/lucide--react-F56565?style=flat-square)](https://lucide.dev)
[![marked](https://img.shields.io/badge/marked-000000?style=flat-square&logo=markdown&logoColor=white)](https://marked.js.org)
[![Resend](https://img.shields.io/badge/Resend-black?style=flat-square&logo=resend&logoColor=white)](https://resend.com)
[![Netlify](https://img.shields.io/badge/Netlify-00C7B7?style=flat-square&logo=netlify&logoColor=white)](https://www.netlify.com)

</div>

## 🚀 Getting Started

```bash
git clone https://github.com/Kaashmalik/mtkcodex.git
cd mtkcodex
npm install
cp .env.example .env.local   # optional: enables direct email delivery
npm run dev                  # → http://localhost:3000
```

### Scripts

| Command | Description |
| --- | --- |
| `npm run dev` | Start the dev server on <http://localhost:3000> |
| `npm run build` | Production build |
| `npm start` | Serve the production build |
| `npm run lint` | Lint with ESLint |
| `npm test` | Unit tests (Vitest) |
| `npm run typecheck` | TypeScript check |
| `npm run outreach:doc` | Render `src/data/leads.seed.json` into a dated batch record under `docs/outreach/` |

### Environment Variables

Copy [`.env.example`](./.env.example) to `.env.local`. The essentials:

```bash
ADMIN_EMAIL= / ADMIN_PASSWORD= / ADMIN_SESSION_SECRET=   # admin login (required)
SUPABASE_URL= / SUPABASE_SERVICE_ROLE_KEY=               # database (required in production)
RESEND_API_KEY= / EMAIL_FROM=                            # email from the inbox (optional)
VAPID_PUBLIC_KEY= / VAPID_PRIVATE_KEY=                   # phone alerts (optional)
```

Every channel (live chat, email in/out, WhatsApp Cloud API, push and Telegram alerts, booking link)
switches on by itself once its variables are set. The step-by-step go-live checklist, including the
DNS records for `mtkcodex.tech`, is in [`docs/CRM.md`](./docs/CRM.md).

### Admin CRM

`/admin` is an owner-only CRM: leads with import/export (CSV or Google Sheets), a deals board, an
activity timeline, and **one inbox for website live chat, WhatsApp and email** with visitor
locations, local times and phone alerts. It installs on a phone as an app.

## 🗺️ Pages

| Route | Content |
| --- | --- |
| `/` | Hero, product strip, stats, suite, interactive demos, services, automation, industries, process, reviews, founder, pricing, FAQ |
| `/products`, `/products/[slug]` | All 7 platforms with coded UI demos, metrics, features, stack |
| `/services` | 8 service lines with deliverables |
| `/industries` | Industry coverage with per-industry pages |
| `/customers` | Client reviews |
| `/pricing` | Engagement models + FAQ |
| `/about` | Values, founder, timeline |
| `/contact` | Lead form (pre-filled from `?intent=`, `?service=`, `?product=`), WhatsApp, email |
| `/blog/[slug]` | Markdown blog rendered with `marked` from `content/blog/` |
| `/locations` | Location pages incl. Lahore, with keyless maps embeds |
| `/admin` | Lead CRM: pipeline, filters, notes, follow-ups, CSV export (owner-only) |
| `/admin/outreach` | WhatsApp send queue with pre-written, personalised openers |
| `/admin/docs` | In-app playbook; full version in [`docs/CRM.md`](./docs/CRM.md) |

## 📁 Project Structure

```
mtkcodex/
├── content/blog/           # Markdown blog posts
├── docs/                   # CRM runbook + outreach batch records
├── public/                 # Static assets (icons, favicon)
├── supabase/migrations/    # Lead CRM table + RLS migration
├── scripts/                # Batch doc generator
├── src/
│   ├── app/                # App Router pages, API routes, SEO files
│   │   ├── (site)/         # Public marketing pages (navbar/footer chrome)
│   │   ├── admin/          # Owner-only CRM dashboard + outreach desk
│   │   ├── api/contact/    # Resend-powered contact endpoint
│   │   ├── api/admin/      # Session-guarded CRM API
│   │   ├── blog/[slug]/    # Blog + dynamic OG images
│   │   └── products/[slug]/
│   ├── components/         # layout · sections · motion · ui · demo · admin
│   ├── data/               # 👈 All site copy lives here
│   │   ├── site.ts         # Brand, contact, founder, stats
│   │   ├── products.ts     # The 7 products (add here → appears everywhere)
│   │   ├── services.ts     # Services + delivery process
│   │   ├── leads.seed.json # Current outreach batch (imported by the CRM)
│   │   └── content.ts      # Testimonials, industries, pricing, FAQ
│   └── lib/                # blog, seo, auth, lead storage, consent, OG helpers
├── .env.example
├── LICENSE                 # MIT
└── package.json
```

> **Adding content:** drop a new product into `src/data/products.ts` or a new `.md` file into `content/blog/` — routing, sitemap and OG images pick it up automatically.

## 🎯 Lead CRM & Outreach

The site includes a private CRM for the Lahore outreach pipeline — no third-party CRM needed.

1. Set `ADMIN_EMAIL`, `ADMIN_PASSWORD` and `ADMIN_SESSION_SECRET`.
2. (Production) run [`supabase/migrations/0001_leads.sql`](./supabase/migrations/0001_leads.sql) and add `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY`.
3. Sign in at `/admin`, import the bundled batch once, then work the queue at `/admin/outreach`.

Each lead stores its score, source area, pre-written opener, status, notes, last contact and next follow-up. The outreach desk opens `wa.me` with the message pre-filled — sending stays manual, one at a time, which keeps the business number safe.

Full runbook: [`docs/CRM.md`](./docs/CRM.md). Lead batches and outreach logs are private and stay in the gitignored `.data/` folder.

## ☁️ Deploy

<a href="https://app.netlify.com/start/deploy?repository=https://github.com/Kaashmalik/mtkcodex">
  <img src="https://www.netlify.com/img/deploy/button.svg" alt="Deploy to Netlify" />
</a>

1. Click the button above (or import the repo in Netlify → *Add new project*)
2. Run the Supabase migrations and add the environment variables (see `docs/CRM.md` → Go-live checklist)
3. Point `mtkcodex.tech` at the project

Hosting runs on **Netlify's free plan** (commercial use allowed; Vercel Hobby is non-commercial
only). `netlify.toml` holds the build settings, and `docs/CRM.md` → *Step 0* walks through the site,
environment variables and domain/DNS switch.

## 📄 License

Released under the [MIT License](./LICENSE) — free to use, copy, modify and distribute with attribution.

## 🤝 Connect

<div align="center">

**Muhammad Kashif** — CEO & Founder · Full-Stack SaaS Architect

[![GitHub](https://img.shields.io/badge/GitHub-181717?style=for-the-badge&logo=github&logoColor=white)](https://github.com/Kaashmalik)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-0A66C2?style=for-the-badge&logo=linkedin&logoColor=white)](https://www.linkedin.com/in/muhammadkashif-mtkcodex)
[![Portfolio](https://img.shields.io/badge/Portfolio-7c3aed?style=for-the-badge&logo=aboutdotme&logoColor=white)](https://pf.mtkcodex.site)
[![Email](https://img.shields.io/badge/Email-EA4335?style=for-the-badge&logo=gmail&logoColor=white)](mailto:kaash0542@gmail.com)
[![WhatsApp](https://img.shields.io/badge/WhatsApp-25D366?style=for-the-badge&logo=whatsapp&logoColor=white)](https://wa.me/923020718182)

📍 Lahore, Pakistan · Serving clients worldwide · Mon–Sat · Response within 12 hours

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:22d3ee,50:06b6d4,100:7c3aed&height=140&section=footer" alt="Footer" width="100%" />

</div>
