import type { Kol } from './tip'

/** Kollar çift çift: Jev'siz kopya, altında Jev'li ikizi; en sonda agresif ve portföy. */
export function satirSirasi(kollar: Kol[]): Kol[] {
  const ad = new Map(kollar.map((k) => [k.kol, k]))
  const out: Kol[] = []
  for (const k of [...kollar].filter((k) => k.tur === 'kol' && !k.jev).sort((a, b) => a.kol.localeCompare(b.kol))) {
    out.push(k)
    const j = ad.get(k.kol + '+jev')
    if (j) out.push(j)
  }
  for (const k of kollar) if (!out.includes(k)) out.push(k)
  return out
}
