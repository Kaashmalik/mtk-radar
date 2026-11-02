import { ImageResponse } from 'next/og';
import { site } from '@/data/site';

export const ogSize = { width: 1200, height: 630 };

/** Branded 1200×630 social card, rendered at build time. */
export function renderOg({ eyebrow, title, subtitle, accent = '#62d84e' }: { eyebrow: string; title: string; subtitle?: string; accent?: string }) {
  return new ImageResponse(
    (
      <div
        style={{
          width: '100%',
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
          padding: '64px 72px',
          background: 'radial-gradient(circle at 85% 0%, #0b5a5f 0%, #032d42 45%, #021a26 100%)',
          color: '#f1f7f5',
          fontFamily: 'sans-serif',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 18 }}>
          <div
            style={{
              width: 64,
              height: 64,
              borderRadius: 18,
              background: 'linear-gradient(135deg, #62d84e, #14a89a 55%, #0b4f6c)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: 30,
              fontWeight: 800,
              color: '#fff',
            }}
          >
            {'</>'}
          </div>
          <div style={{ display: 'flex', fontSize: 34, fontWeight: 800 }}>
            MTK&nbsp;<span style={{ color: '#62d84e' }}>Codex</span>
          </div>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          <div style={{ display: 'flex', fontSize: 24, fontWeight: 700, letterSpacing: 4, textTransform: 'uppercase', color: accent }}>{eyebrow}</div>
          <div style={{ display: 'flex', marginTop: 18, fontSize: title.length > 48 ? 58 : 70, fontWeight: 800, lineHeight: 1.05, maxWidth: 1000 }}>{title}</div>
          {subtitle && <div style={{ display: 'flex', marginTop: 22, fontSize: 28, color: '#a6bfc6', maxWidth: 980, lineHeight: 1.35 }}>{subtitle}</div>}
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 24, color: '#a6bfc6' }}>
          <div style={{ display: 'flex' }}>{site.slogan}</div>
          <div style={{ display: 'flex', padding: '10px 22px', borderRadius: 999, background: '#62d84e', color: '#032d1a', fontWeight: 700 }}>mtkcodex.tech</div>
        </div>
      </div>
    ),
    ogSize,
  );
}
