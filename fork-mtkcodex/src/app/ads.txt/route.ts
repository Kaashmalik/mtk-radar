export const dynamic = 'force-static';

// Authorised Digital Sellers file required by AdSense. Derived from NEXT_PUBLIC_ADSENSE_CLIENT.
export function GET() {
  const client = process.env.NEXT_PUBLIC_ADSENSE_CLIENT;
  const body = client
    ? `google.com, ${client.replace(/^ca-/, '')}, DIRECT, f08c47fec0942fa0\n`
    : '# Set NEXT_PUBLIC_ADSENSE_CLIENT (ca-pub-…) to publish the AdSense seller line.\n';
  return new Response(body, { headers: { 'Content-Type': 'text/plain; charset=utf-8' } });
}
