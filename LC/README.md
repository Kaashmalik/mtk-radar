# Laraib Creative — laraibcreative.com

Premium online ladies tailoring for Lahore: the website and order flow (manual payment slips), customer accounts, the rider app, and the admin dashboard (orders, slip verification, dispatch, reviews & gallery, inquiries, expenses and the 50/50 partnership settlement).

## Stack

| Layer | Choice |
|---|---|
| Framework | Next.js 16 (App Router, Cache Components, Turbopack) + React 19 + TypeScript |
| Styling | Tailwind CSS 4 with a custom design system (`src/app/globals.css`) |
| Motion | Motion (`motion/react`), GSAP + ScrollTrigger, Lenis smooth scroll |
| Database & auth | Supabase (Postgres + RLS; staff password login, customer email-code login) |
| Media | Cloudinary (signed server uploads; slips, receipts and handover photos are `authenticated` assets) |
| Messaging | WhatsApp Business Cloud API (optional) + click-to-chat links |
| Hosting | Vercel |

## Apps in this project

| URL | Who | What |
|---|---|---|
| `/` … | Customers | Website, 4-step order flow, track order, review links |
| `/account` | Customers | Sign in with an emailed code, orders + handover codes, family measurement profiles, reviews, re-order |
| `/rider` | Riders (phone) | Today's jobs, call / WhatsApp / map, start → arrived → handover code + photo + cash, failed visits, end-of-shift cash |
| `/admin` | Staff | Overview, orders board + order detail, payment slips, dispatch & riders, inquiries, reviews & gallery, expenses, partnership 50/50 |

## Project structure

```
supabase/migrations/
  0001_init.sql                     Core schema, RLS, seed data (zones, sizes, expense categories, partners)
  0002_accounts_riders_reviews.sql  Customer accounts, custody chain, cash closings, notifications log
src/
  proxy.ts                          Session refresh + login redirects for /admin, /rider, /account
  app/(site)/                       Public website, /order, /track, /account, /review/[orderNo]
  app/rider/                        Rider app
  app/admin/                        Staff login + dashboard
  components/                       brand/, motion/, site/, order/, account/, rider/, admin/
  lib/
    config.ts                       Business config — garments, options, zones, payment accounts
    pricing.ts                      Price calculation (shared by client and server)
    actions/                        Server actions: public, account, rider, admin
    data/                           Supabase queries (+ demo data for preview mode)
    auth.ts                         Staff / rider / customer sessions and role checks
    dispatch.ts                     Rider job creation, zone service days
    handover.ts                     HMAC handover codes + review-link tokens (nothing secret stored)
    notify.ts, whatsapp.ts          WhatsApp notifications (logged to `notifications`)
    cloudinary.ts, finance.ts
```

## How the order lifecycle works

1. Customer orders → status **Pending payment** or **Verifying payment** (if a slip was uploaded). A rider **pickup job** (or **measurement visit** for home measurement) is created automatically with a 4-digit handover code shown to the customer.
2. Staff approve the slip on **Payment slips** → order **Confirmed**, customer gets WhatsApp.
3. Rider starts the job → customer gets "rider on the way" + code. At the door: code + photo → order **Awaiting fabric**, custody logged.
4. Warehouse logs intake with a photo on the order page → **Fabric received** → cutting / stitching / finishing / QC (status board).
5. Marking **Ready** auto-creates a **delivery job** with the balance as cash to collect.
6. Delivery handover (code + photo + cash) → **Delivered**, cash recorded as a verified payment, WhatsApp with a review link.
7. Review arrives in **Reviews & gallery** for moderation; QC photos can be published to the gallery if the customer consented.

## Run locally

```bash
pnpm install
cp .env.example .env.local   # fill in values
pnpm dev
```

Without Supabase keys the app runs in **preview mode**: the site works, orders return `LC-PREVIEW`, and the admin and rider app show sample data.

## Go live

1. **Supabase** — create a project (Singapore or Mumbai region), then run both migration files in order in the SQL editor.
2. **Customer sign-in email** — Authentication → Email Templates → *Magic Link*: include `{{ .Token }}` so customers receive a code (e.g. "Your Laraib sign-in code is {{ .Token }}").
3. **Partners & staff** — create users in Authentication → Users, then:
   ```sql
   insert into profiles (id, full_name, role) values ('<auth user id>', 'Your Name', 'partner');
   update partners set profile_id = '<auth user id>', name = 'Your Name' where role = 'tech_online';
   -- repeat for the tailor partner with role = 'stitching'
   ```
   Riders can be added (with their app login) from **Admin → Dispatch & riders**.
4. **Cloudinary** — copy cloud name, API key and secret.
5. **Secrets** — set `HANDOVER_SECRET` (random 32+ bytes). Changing it later invalidates open handover codes and review links.
6. **WhatsApp (optional)** — create the templates listed in `src/lib/whatsapp.ts` in WhatsApp Manager, then set `WHATSAPP_TOKEN` and `WHATSAPP_PHONE_NUMBER_ID`. Without them, messages are logged as "skipped" and staff use the WhatsApp buttons.
7. Fill `.env.local` and the same variables in Vercel, deploy, and point `laraibcreative.com` to it.

## Photos, SEO & AdSense

- **Photos** — upload real photos in **Admin → Site media** (hero, services, workshop, rider, studio) and **Admin → Lookbook designs**. Until a slot has a photo, a neutral placeholder shows. Uploads are compressed in the browser and served through Cloudinary (`f_auto,q_auto`).
- **Icons** — `src/app/icon.svg`, `apple-icon.tsx` and `/brand-icon/{48,96,192,512,maskable-512}.png` are generated from the brand mark in `src/lib/brand-art.tsx`.
- **SEO** — `sitemap.xml`, `robots.txt`, web manifest, per-page canonical URLs, Open Graph share images, and JSON-LD (Organization, WebSite, ClothingStore/LocalBusiness with geo + hours + price list, BreadcrumbList, FAQPage, Article). Local pages live at `/tailor/<area>` (`src/lib/content/areas.ts`) and articles at `/journal` (`src/lib/content/journal.ts`).
- **After deploying**: verify the domain in Google Search Console and submit `https://laraibcreative.com/sitemap.xml`; create a Google Business Profile for the Garhi Shahu studio with the same name, address and phone as the site; confirm the map pin in `src/lib/seo.tsx`.
- **AdSense** — set `NEXT_PUBLIC_ADSENSE_CLIENT`; the `google-adsense-account` meta tag and `/ads.txt` are added automatically. Ads appear only inside Style Journal articles and only after the visitor accepts cookies. For visitors from the EU/UK, Google requires a certified consent tool — enable Google's own *Privacy & messaging* consent message in AdSense.

## Before launch, replace placeholders

- Prices in `src/lib/config.ts` (and the `garment_types` seed) and the standard size chart (`size-guide/page.tsx` + `standard_sizes` seed): finalise with the master tailor.
- Payment account details and WhatsApp number (env vars).
- Illustrated garments: real "Stitched by Laraib" photos are published from each order's page (consent required).
