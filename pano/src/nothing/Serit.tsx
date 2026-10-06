import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'

import { durumAdi, gunTR, kolAdi, kolKisa, oran, saatTR, saatUTC } from '@/lib/bicim'
import { satirSirasi } from '@/lib/kol'
import type { Kol, Pano } from '@/lib/tip'

import { BolumBasi } from './Ortak'

const SATIR = 12
const ARA = 5
const CIFT_ARA = 12
const UST = 22
const ALT = 20
const SAAT_MS = 3_600_000

type Satir = { kol: Kol; y: number }

const trGun = (ms: number) => Math.floor((ms + 3 * SAAT_MS) / (24 * SAAT_MS))

/** Karar şeridi, nokta matris: her kol her saat bir nokta; saydamlık = brüt maruziyet (DESIGN.md › Components). */
export function Serit({ p, onSec }: { p: Pano; onSec: (kol: string) => void }) {
  const kutu = useRef<HTMLDivElement>(null)
  const kaydir = useRef<HTMLDivElement>(null)
  const [gen, setGen] = useState(0)
  const [imlec, setImlec] = useState<{ r: number; c: number } | null>(null)

  const saatler = p.serit.saatler
  const hucreler = useMemo(() => new Map(p.serit.satirlar.map((s) => [s.kol, s.hucreler])), [p.serit])
  const satirlar: Satir[] = useMemo(() => {
    const sira = satirSirasi(p.kollar)
    const out: Satir[] = []
    for (const [i, kol] of sira.entries()) {
      const once = out.at(-1)
      const y = once ? once.y + SATIR + (!kol.jev || sira[i - 1].tur !== 'kol' ? CIFT_ARA : ARA) : UST
      out.push({ kol, y })
    }
    return out
  }, [p.kollar])
  const yuk = (satirlar.at(-1)?.y ?? UST) + SATIR + ALT

  useLayoutEffect(() => {
    const el = kutu.current
    if (!el) return
    const ro = new ResizeObserver(([e]) => setGen(e.contentRect.width))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const kolG = Math.max(11, Math.floor((gen - 10) / saatler.length))
  const svgGen = kolG * saatler.length + 10

  useEffect(() => {
    const el = kaydir.current
    if (el && el.scrollWidth > el.clientWidth) el.scrollLeft = el.scrollWidth
  }, [gen, svgGen])

  const gunSinirlari = saatler.map((h, c) => ({ h, c })).filter(({ h, c }) => c > 0 && trGun(h) !== trGun(saatler[c - 1]))
  const secili = imlec ? { s: satirlar[imlec.r], h: saatler[imlec.c], x: hucreler.get(satirlar[imlec.r].kol.kol)?.[imlec.c] } : null

  function tus(e: React.KeyboardEvent) {
    const r = imlec?.r ?? 0
    const c = imlec?.c ?? saatler.length - 1
    const yeni = { ArrowLeft: { r, c: c - 1 }, ArrowRight: { r, c: c + 1 }, ArrowUp: { r: r - 1, c }, ArrowDown: { r: r + 1, c } }[
      e.key as 'ArrowLeft'
    ]
    if (yeni) {
      e.preventDefault()
      setImlec({ r: Math.max(0, Math.min(satirlar.length - 1, yeni.r)), c: Math.max(0, Math.min(saatler.length - 1, yeni.c)) })
    } else if (e.key === 'Enter' && imlec) onSec(satirlar[imlec.r].kol.kol)
    else if (e.key === 'Escape') setImlec(null)
  }

  const acilabilir = useRef(false)
  function isaretle(e: React.PointerEvent<SVGSVGElement>) {
    const r = e.currentTarget.getBoundingClientRect()
    const c = Math.floor((e.clientX - r.left) / kolG)
    const y = e.clientY - r.top
    const ri = satirlar.findIndex((s) => y >= s.y - ARA / 2 && y < s.y + SATIR + ARA / 2)
    if (c >= 0 && c < saatler.length && ri >= 0) {
      if (e.type === 'pointerdown') acilabilir.current = e.pointerType === 'mouse' || (imlec?.r === ri && imlec?.c === c)
      setImlec({ r: ri, c })
    }
  }

  const yaricap = Math.min(kolG, SATIR) / 2 - 1

  return (
    <section aria-labelledby="serit-baslik">
      <BolumBasi id="serit-baslik" baslik="Karar şeridi">
        <Lejant />
      </BolumBasi>
      <p id="serit-okuma" aria-live="polite" className="veri mt-4 min-h-[2.75rem] text-govde-sm text-ikincil sm:min-h-6">
        {secili ? (
          <>
            <span className="text-birincil">{kolAdi(secili.s.kol)}</span>
            {secili.s.kol.jev && <span className="text-ucuncul"> · Jev'li</span>}
            <span> · {gunTR(secili.h)} {saatTR(secili.h)} TR ({saatUTC(secili.h)} UTC)</span>
            {' · '}
            {secili.x?.m == null ? 'işaret yok' : <>maruziyet <span className="text-birincil">{oran(secili.x.m)}</span></>}
            {secili.x?.i ? <span> · {secili.x.i} dolum</span> : null}
            {secili.x?.v ? <span className="text-amber"> · Jev vetosu</span> : null}
            {secili.x?.f ? <span className="text-kirmizi-metin"> · {durumAdi(secili.x.f)}</span> : null}
          </>
        ) : (
          <span className="font-sans">Son 72 saat, her kol her saat. Bir noktanın üzerine gel ya da dokun, ok tuşlarıyla gez; tıklamak ya da Enter kolu açar.</span>
        )}
      </p>

      <div className="mt-4 grid grid-cols-[96px_minmax(0,1fr)] gap-4 sm:grid-cols-[200px_minmax(0,1fr)]">
        <ul className="relative" style={{ height: yuk }} aria-hidden>
          {satirlar.map((s, i) => (
            <li
              key={s.kol.kol}
              className={`absolute inset-x-0 flex items-center truncate text-govde-sm leading-none ${imlec?.r === i ? 'text-ekran' : s.kol.jev ? 'text-ucuncul' : 'text-ikincil'}`}
              style={{ top: s.y - 2, height: SATIR + 4 }}
            >
              {s.kol.jev ? (
                <span className="etiket pl-3">+ jev</span>
              ) : (
                <>
                  <span className="truncate sm:hidden">{kolKisa(s.kol)}</span>
                  <span className="hidden truncate sm:inline">{kolAdi(s.kol)}</span>
                </>
              )}
            </li>
          ))}
        </ul>

        <div ref={kutu} className="min-w-0">
          <div
            ref={kaydir}
            tabIndex={0}
            role="group"
            aria-label="Karar şeridi. Ok tuşlarıyla noktalar arasında gezin, Enter kolu açar."
            aria-describedby="serit-okuma"
            onKeyDown={tus}
            onBlur={() => setImlec(null)}
            className="overflow-x-auto overscroll-x-contain [scrollbar-width:thin]"
          >
            {gen > 0 && (
              <svg
                width={svgGen}
                height={yuk}
                aria-hidden
                className="belir block touch-pan-x select-none"
                onPointerMove={isaretle}
                onPointerDown={isaretle}
                onPointerLeave={(e) => e.pointerType === 'mouse' && setImlec(null)}
                onClick={() => imlec && acilabilir.current && onSec(satirlar[imlec.r].kol.kol)}
              >
                {gunSinirlari.map(({ h, c }) => (
                  <g key={h}>
                    <line x1={c * kolG} x2={c * kolG} y1={UST - 6} y2={yuk - ALT + 2} stroke="var(--color-cizgi-belirgin)" strokeDasharray="1 3" />
                    <text x={c * kolG + 4} y={11} className="fill-ikincil font-mono text-[10px] tracking-[0.08em] uppercase">
                      {gunTR(h)}
                    </text>
                  </g>
                ))}
                {saatler.map((h, c) =>
                  (h / SAAT_MS + 3) % 6 === 0 && (h / SAAT_MS + 3) % 24 !== 0 ? (
                    <text key={h} x={c * kolG + kolG / 2} y={yuk - 6} textAnchor="middle" className="fill-ucuncul font-mono text-[10px]">
                      {saatTR(h).slice(0, 2)}
                    </text>
                  ) : null,
                )}
                {saatler.map((h, c) => (
                  <g key={h}>
                    {satirlar.map((s) => {
                      const x = hucreler.get(s.kol.kol)?.[c]
                      const cx = c * kolG + kolG / 2
                      const cy = s.y + SATIR / 2
                      return (
                        <g key={s.kol.kol}>
                          {x?.m == null ? (
                            <circle cx={cx} cy={cy} r={1} fill="var(--color-pasif)" />
                          ) : (
                            <circle cx={cx} cy={cy} r={yaricap} fill="var(--color-ekran)" opacity={0.1 + 0.9 * Math.min(1, x.m)} />
                          )}
                          {x?.i ? <circle cx={cx} cy={cy} r={yaricap + 1.5} fill="none" stroke="var(--color-ekran)" strokeWidth={1} /> : null}
                          {x?.v ? <rect x={cx - yaricap} y={s.y - 3.5} width={yaricap * 2} height={2} fill="var(--color-amber)" /> : null}
                          {x?.f ? <rect x={cx - yaricap} y={s.y + SATIR + 1.5} width={yaricap * 2} height={2} fill="var(--color-kirmizi)" /> : null}
                        </g>
                      )
                    })}
                  </g>
                ))}
                <line
                  x1={saatler.length * kolG + 4}
                  x2={saatler.length * kolG + 4}
                  y1={UST - 6}
                  y2={yuk - ALT + 2}
                  stroke="var(--color-ekran)"
                  strokeWidth={2}
                />
                {imlec && (
                  <rect
                    x={imlec.c * kolG}
                    y={satirlar[imlec.r].y - 2}
                    width={kolG}
                    height={SATIR + 4}
                    fill="none"
                    stroke="var(--color-ekran)"
                    strokeWidth={1}
                  />
                )}
              </svg>
            )}
          </div>
        </div>
      </div>
    </section>
  )
}

function Lejant() {
  return (
    <ul className="etiket flex flex-wrap items-center gap-x-5 gap-y-2 text-ikincil">
      <li className="flex items-center gap-2">
        <span className="flex gap-[3px]" aria-hidden>
          {[0.15, 0.45, 0.75, 1].map((o) => (
            <span key={o} className="size-2 rounded-full bg-ekran" style={{ opacity: o }} />
          ))}
        </span>
        maruziyet
      </li>
      <li className="flex items-center gap-2">
        <span className="size-2.5 rounded-full border border-ekran" aria-hidden />
        dolum
      </li>
      <li className="flex items-center gap-2">
        <span className="h-0.5 w-2.5 bg-amber" aria-hidden />
        jev vetosu
      </li>
      <li className="flex items-center gap-2">
        <span className="h-0.5 w-2.5 bg-kirmizi" aria-hidden />
        fren
      </li>
      <li className="flex items-center gap-2">
        <span className="h-3 w-0.5 bg-ekran" aria-hidden />
        şimdi
      </li>
    </ul>
  )
}
