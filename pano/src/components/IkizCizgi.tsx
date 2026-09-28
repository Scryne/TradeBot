import { useId } from 'react'

import type { Seri } from '@/lib/tip'

/**
 * Jev'li (düz, sis) ve Jev'siz (kesikli, kurşun) kopyanın başlangıçtan getirisi. Aradaki alan öndeki kopyanın
 * rengiyle, düşük opaklıkta: Jev'li öndeyse kazanç, gerideyse kayıp (DESIGN.md › Components › Kol satırı).
 * Kimlik renge değil çizgi stiline dayanır; renk yalnız farkın yönünü söyler.
 */
export function IkizCizgi({
  jevli,
  jevsiz,
  taban,
  gen = 168,
  yuk = 40,
  etiket,
}: {
  jevli: Seri
  jevsiz?: Seri
  taban: number
  gen?: number
  yuk?: number
  etiket: string
}) {
  const id = useId()
  const a = jevli.map(([t, v]) => [t, v / taban - 1] as const)
  const b = (jevsiz ?? []).map(([t, v]) => [t, v / taban - 1] as const)
  const tum = [...a, ...b]
  if (a.length < 2) return <svg width={gen} height={yuk} role="img" aria-label={`${etiket}: yeterli veri yok`} />
  const t0 = Math.min(...tum.map((x) => x[0]))
  const t1 = Math.max(...tum.map((x) => x[0]))
  const lo = Math.min(0, ...tum.map((x) => x[1]))
  const hi = Math.max(0, ...tum.map((x) => x[1]))
  const pay = (hi - lo) * 0.12 || 0.002
  const X = (t: number) => ((t - t0) / (t1 - t0 || 1)) * (gen - 4) + 2
  const Y = (v: number) => yuk - 3 - ((v - lo + pay) / (hi - lo + 2 * pay)) * (yuk - 6)
  const yol = (s: readonly (readonly [number, number])[]) => s.map(([t, v], i) => `${i ? 'L' : 'M'}${X(t).toFixed(1)},${Y(v).toFixed(1)}`).join('')

  // İki seri aynı zamanlarda işaretlenir; eşleşen noktalarla fark alanı
  const bHarita = new Map(b.map(([t, v]) => [t, v]))
  const ortak = a.filter(([t]) => bHarita.has(t))
  const alan =
    ortak.length > 1
      ? `${yol(ortak)}L${[...ortak].reverse().map(([t]) => `${X(t).toFixed(1)},${Y(bHarita.get(t)!).toFixed(1)}`).join('L')}Z`
      : null
  // Jev'siz çizginin üstü (ekranda) = Jev'li önde → kazanç; altı → kayıp
  const bOrtak = ortak.map(([t]) => [t, bHarita.get(t)!] as const)
  const bYol = bOrtak.length > 1 ? yol(bOrtak) : ''
  const x0 = bOrtak.length ? X(bOrtak[0][0]).toFixed(1) : '0'
  const x1 = bOrtak.length ? X(bOrtak[bOrtak.length - 1][0]).toFixed(1) : '0'

  return (
    <svg width={gen} height={yuk} role="img" aria-label={etiket} className="block overflow-visible">
      <line x1={0} x2={gen} y1={Y(0)} y2={Y(0)} stroke="var(--color-cizgi)" strokeWidth={1} />
      {alan && (
        <>
          <clipPath id={`${id}-k`}>
            <path d={alan} />
          </clipPath>
          <g clipPath={`url(#${id}-k)`} opacity={0.2}>
            <path d={`${bYol}L${x1},-10L${x0},-10Z`} fill="var(--color-kazanc)" />
            <path d={`${bYol}L${x1},${yuk + 10}L${x0},${yuk + 10}Z`} fill="var(--color-kayip)" />
          </g>
        </>
      )}
      {b.length > 1 && (
        <path d={yol(b)} fill="none" stroke="var(--color-kursun)" strokeWidth={1.5} strokeDasharray="3 3" strokeLinejoin="round" />
      )}
      <path d={yol(a)} fill="none" stroke="var(--color-sis)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={X(a[a.length - 1][0])} cy={Y(a[a.length - 1][1])} r={3} fill="var(--color-sis)" stroke="var(--color-yuzey)" strokeWidth={2} />
    </svg>
  )
}
