/**
 * Offer record schema — master plan §3 ("Offer record schema" table).
 * Used by the dashboard, extension submit path, and workers for validation.
 */
import { z } from "zod";
import { OFFER_STATES } from "./offer-state";

export const offerRecordSchema = z.object({
  title: z.string().min(3),
  provider: z.string().min(1),
  category: z.enum([
    "model_hubs",
    "dev_platforms",
    "coding_tools",
    "student_programs",
    "cloud_startup",
    "domains_software",
  ]),
  offerType: z.enum([
    "free_trial",
    "credits",
    "student_perk",
    "model_access",
    "giveaway",
    "discount",
    "swag_prize",
  ]),
  eligibility: z.object({
    countries: z.array(z.string()).default([]),
    studentStatus: z.boolean().default(false),
    startupStatus: z.boolean().default(false),
    newCustomerOnly: z.boolean().default(false),
    verificationRequired: z.boolean().default(false),
  }),
  value: z.object({
    currency: z.string().optional(),
    amount: z.number().nonnegative().optional(),
    usageCap: z.string().optional(),
    duration: z.string().optional(),
    exclusions: z.array(z.string()).default([]),
  }),
  claimSteps: z
    .array(
      z.object({
        order: z.number().int().positive(),
        kind: z.enum(["account_action", "command", "manual_check"]),
        text: z.string().min(1),
        expectedOutput: z.string().optional(),
      })
    )
    .default([]),
  promo: z
    .object({
      code: z.string().optional(),
      redemptionUrl: z.string().url().optional(),
      startsAt: z.coerce.date().optional(),
      expiresAt: z.coerce.date().optional(),
      timezone: z.string().default("Asia/Karachi"),
    })
    .default({}),
  renewal: z.object({
    autoRenew: z.boolean().default(false),
    regularPrice: z.string().optional(),
    paymentMethodRequired: z.boolean().default(false),
  }),
  state: z.enum(OFFER_STATES).default("candidate"),
  evidence: z
    .array(
      z.object({
        url: z.string().url(),
        capturedAt: z.coerce.date(),
        contentHash: z.string(),
        excerpt: z.string().optional(),
        supportedFields: z.array(z.string()).default([]),
      })
    )
    .min(1), // at least one official source required for "verified"
  recheckAt: z.coerce.date(),
});

export type OfferRecord = z.infer<typeof offerRecordSchema>;
