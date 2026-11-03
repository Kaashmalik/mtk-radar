import "server-only";
import { createHash } from "node:crypto";

const cloud = process.env.NEXT_PUBLIC_CLOUDINARY_CLOUD_NAME;
const apiKey = process.env.CLOUDINARY_API_KEY;
const apiSecret = process.env.CLOUDINARY_API_SECRET;

export const isCloudinaryConfigured = Boolean(cloud && apiKey && apiSecret);

/**
 * Signed server-side upload. Payment slips and receipts use `authenticated`
 * delivery so they are not publicly reachable by URL guessing.
 */
export async function uploadFile(file: File, folder: string, privateAsset = true): Promise<string | null> {
  if (!isCloudinaryConfigured || file.size === 0) return null;

  const timestamp = Math.floor(Date.now() / 1000).toString();
  const params: Record<string, string> = { folder, timestamp };
  if (privateAsset) params.type = "authenticated";

  const toSign = Object.keys(params)
    .sort()
    .map((k) => `${k}=${params[k]}`)
    .join("&");
  const signature = createHash("sha1").update(toSign + apiSecret).digest("hex");

  const body = new FormData();
  body.append("file", file);
  body.append("api_key", apiKey!);
  body.append("signature", signature);
  Object.entries(params).forEach(([k, v]) => body.append(k, v));

  const res = await fetch(`https://api.cloudinary.com/v1_1/${cloud}/auto/upload`, { method: "POST", body });
  if (!res.ok) throw new Error(`Cloudinary upload failed: ${res.status}`);
  const json = (await res.json()) as { secure_url: string };
  return json.secure_url;
}
