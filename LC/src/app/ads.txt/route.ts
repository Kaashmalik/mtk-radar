// Authorised Digital Sellers file required by AdSense. Publisher id comes from NEXT_PUBLIC_ADSENSE_CLIENT (ca-pub-…).
export function GET() {
  const client = process.env.NEXT_PUBLIC_ADSENSE_CLIENT;
  const body = client ? `google.com, ${client.replace(/^ca-/, "")}, DIRECT, f08c47fec0942fa0\n` : "# AdSense not configured\n";
  return new Response(body, { headers: { "Content-Type": "text/plain; charset=utf-8", "Cache-Control": "public, max-age=86400" } });
}
