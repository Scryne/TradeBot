import type { ReactNode } from 'react'

import { durumAdi } from '@/lib/bicim'

/** İşaretli değerin rengi: yalnız değere uygulanır (DESIGN.md › Colors). */
export const isaretRenk = (x: number) => (x > 0.00005 ? 'text-yesil' : x < -0.00005 ? 'text-kirmizi-metin' : 'text-ikincil')

/** Ayrık bloklar, 2 px aralık. Her hücre bir renk ya da boş (null). */
export function Segmentler({
  hucreler,
  yuk = 8,
  etiket,
  className = '',
}: {
  hucreler: (string | null)[]
  yuk?: number
  etiket: string
  className?: string
}) {
  return (
    <div role="img" aria-label={etiket} className={`flex gap-[2px] ${className}`} style={{ height: yuk }}>
      {hucreler.map((r, i) => (
        <span key={i} className="min-w-0 flex-1" style={{ background: r ?? 'var(--color-cizgi-belirgin)' }} />
      ))}
    </div>
  )
}

/** Maruziyet: 10 segment, her biri özkaynağın %10'u; 1'i aşan kısım kırmızı devam eder. */
export function MaruziyetCubugu({ x, etiket }: { x: number; etiket: string }) {
  const dolu = Math.round(Math.min(1.2, Math.max(0, x)) * 10)
  const hucreler = Array.from({ length: 12 }, (_, i) =>
    i < dolu ? (i >= 10 ? 'var(--color-kirmizi)' : 'var(--color-ekran)') : i >= 10 ? 'transparent' : null,
  )
  return <Segmentler hucreler={hucreler} yuk={6} etiket={etiket} className="w-[84px]" />
}

export function DurumEtiketi({ d }: { d: string | null }) {
  if (!d || d === 'normal') return <span className="etiket text-ucuncul">[normal]</span>
  return <span className="etiket text-kirmizi-metin">[{durumAdi(d)}]</span>
}

export function BolumBasi({ id, baslik, children }: { id: string; baslik: string; children?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-x-8 gap-y-3">
      <h2 id={id} className="text-baslik leading-tight tracking-[-0.01em] text-ekran">
        {baslik}
      </h2>
      {children}
    </div>
  )
}

/** Etiket solda, değer sağda (enstrüman paneli satırı). */
export function StatSatiri({ ad, deger, renk = 'text-birincil' }: { ad: string; deger: ReactNode; renk?: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-t border-cizgi py-2.5">
      <dt className="etiket text-ikincil">{ad}</dt>
      <dd className={`veri text-govde-sm ${renk}`}>{deger}</dd>
    </div>
  )
}
