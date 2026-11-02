export const dynamic = 'force-static';

// Windows Start-menu tiles.
export function GET() {
  const xml = `<?xml version="1.0" encoding="utf-8"?>
<browserconfig>
  <msapplication>
    <tile>
      <square150x150logo src="/icons/mstile-150.png"/>
      <square310x310logo src="/icons/mstile-310.png"/>
      <TileColor>#031f2b</TileColor>
    </tile>
  </msapplication>
</browserconfig>
`;
  return new Response(xml, { headers: { 'Content-Type': 'application/xml; charset=utf-8' } });
}
