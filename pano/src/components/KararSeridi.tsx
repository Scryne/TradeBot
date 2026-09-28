import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'

import { durumAdi, gunTR, kolAdi, kolKisa, oran, saatTR, saatUTC } from '@/lib/bicim'
import { satirSirasi } from '@/lib/kol'
import type { Kol, Pano } from '@/lib/tip'

const SATIR = 14 // hücre yüksekliği
const ARA = 4 // satır arası
const CIFT_ARA = 10 // Jev'siz/Jev'li çiftler arası
const UST = 22 // gün etiketleri
const ALT = 20 // saat etiketleri
const SAAT_MS = 3_600_000

type Satir = { kol: Kol; y: number; ciftBasi: boolean }

function trGun(ms: number) {
  // İstanbul UTC+3, yaz saati yok: gün sınırı 21:00 UTC
  return Math.floor((ms + 3 * SAAT_MS) / (24 * SAAT_MS))
}

export function KararSeridi({ p, onSec }: { p: Pano; onSec: (kol: string) => void }) {
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
      const ciftBasi = !kol.jev
      const y = once ? once.y + SATIR + (ciftBasi || sira[i - 1].tur !== 'kol' ? CIFT_ARA : ARA) : UST
      out.push({ kol, y, ciftBasi })
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

  const kolG = Math.max(10, Math.floor((gen - 8) / saatler.length))
  const svgGen = kolG * saatler.length + 8

  // Telefonda şerit kendi kutusunda kayar: en yeni saat görünür başlasın
  useEffect(() => {
    const el = kaydir.current
    if (el && el.scrollWidth > el.clientWidth) el.scrollLeft = el.scrollWidth
  }, [gen, svgGen])

  const gunSinirlari = saatler
    .map((h, c) => ({ h, c }))
    .filter(({ h, c }) => c > 0 && trGun(h) !== trGun(saatler[c - 1]))

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

  // Dokunmatikte ilk dokunuş hücreyi seçer (okuma satırı), aynı hücreye ikinci dokunuş kolu açar; farede tık açar
  const acilabilir = useRef(false)

  function isaretle(e: React.PointerEvent<SVGSVGElement>) {
    const r = e.currentTarget.getBoundingClientRect()
    const x = e.clientX - r.left
    const y = e.clientY - r.top
    const c = Math.floor(x / kolG)
    const ri = satirlar.findIndex((s) => y >= s.y - ARA / 2 && y < s.y + SATIR + ARA / 2)
    if (c >= 0 && c < saatler.length && ri >= 0) {
      if (e.type === 'pointerdown')
        acilabilir.current = e.pointerType === 'mouse' || (imlec?.r === ri && imlec?.c === c)
      setImlec({ r: ri, c })
    }
  }

  return (
    <section aria-labelledby="serit-baslik" className="border-y border-cizgi bg-gece/55">
      <div className="mx-auto max-w-[1320px] px-gutter py-6">
        <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-2">
          <h2 id="serit-baslik" className="font-display text-display-md font-bold tracking-display-md uppercase">
            Karar şeridi
          </h2>
          <Lejant />
        </div>
        <p id="serit-okuma" aria-live="polite" className="mt-3 min-h-[2.75rem] text-body-sm text-pretty text-kursun sm:min-h-6">
          {secili ? (
            <>
              <span className="text-sis">{kolAdi(secili.s.kol)}</span>
              {secili.s.kol.jev && <span className="text-soluk"> · Jev'li</span>}
              <span className="sayi"> · {gunTR(secili.h)} {saatTR(secili.h)} TR ({saatUTC(secili.h)} UTC)</span>
              {' · '}
              {secili.x?.m == null ? (
                'işaret yok'
              ) : (
                <>
                  maruziyet <span className="sayi text-sis">{oran(secili.x.m)}</span>
                </>
              )}
              {secili.x?.i ? <span className="sayi"> · {secili.x.i} dolum</span> : null}
              {secili.x?.v ? <span className="text-sodyum"> · Jev vetosu</span> : null}
              {secili.x?.f ? <span className="text-kayip"> · {durumAdi(secili.x.f)}</span> : null}
            </>
          ) : (
            <>Son 72 saat, her kol her saat. Bir hücrenin üzerine gel ya da dokun, ok tuşlarıyla gez. Tıklamak ya da Enter kolu açar.</>
          )}
        </p>

        <div className="mt-3 grid grid-cols-[112px_minmax(0,1fr)] gap-3 sm:grid-cols-[208px_minmax(0,1fr)]">
          <ul className="relative text-body-sm" style={{ height: yuk }} aria-hidden>
            {satirlar.map((s, i) => (
              <li
                key={s.kol.kol}
                className={`absolute inset-x-0 flex items-center truncate leading-none ${imlec?.r === i ? 'text-sis' : s.kol.jev ? 'text-soluk' : 'text-kursun'}`}
                style={{ top: s.y - 2, height: SATIR + 4 }}
              >
                {s.kol.jev ? (
                  <span className="pl-3">+ Jev</span>
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
              aria-label="Karar şeridi. Ok tuşlarıyla hücreler arasında gezin, Enter kolu açar."
              aria-describedby="serit-okuma"
              onKeyDown={tus}
              onBlur={() => setImlec(null)}
              className="overflow-x-auto overscroll-x-contain rounded-control [scrollbar-width:thin]"
            >
              {gen > 0 && (
                <svg
                  width={svgGen}
                  height={yuk}
                  aria-hidden
                  className="block touch-pan-x select-none"
                  onPointerMove={isaretle}
                  onPointerDown={isaretle}
                  onPointerLeave={(e) => e.pointerType === 'mouse' && setImlec(null)}
                  onClick={() => imlec && acilabilir.current && onSec(satirlar[imlec.r].kol.kol)}
                >
                  {gunSinirlari.map(({ h, c }) => (
                    <g key={h}>
                      <line x1={c * kolG - 1} x2={c * kolG - 1} y1={UST - 6} y2={yuk - ALT + 2} stroke="var(--color-cizgi)" />
                      <text x={c * kolG + 3} y={11} className="fill-kursun font-mono text-[10px] tracking-label-sm uppercase">
                        {gunTR(h)}
                      </text>
                    </g>
                  ))}
                  {saatler.map((h, c) =>
                    (h / SAAT_MS + 3) % 6 === 0 && (h / SAAT_MS + 3) % 24 !== 0 ? (
                      <text key={h} x={c * kolG + kolG / 2} y={yuk - 6} textAnchor="middle" className="fill-soluk font-mono text-[10px]">
                        {saatTR(h).slice(0, 2)}
                      </text>
                    ) : null,
                  )}
                  {saatler.map((h, c) => (
                    <g key={h} className="serit-kolon" style={{ animationDelay: `${c * 7}ms` }}>
                      {satirlar.map((s) => {
                        const x = hucreler.get(s.kol.kol)?.[c]
                        const cx = c * kolG + 1
                        const w = kolG - 2
                        return (
                          <g key={s.kol.kol}>
                            {x?.m == null ? (
                              <rect x={cx} y={s.y} width={w} height={SATIR} fill="var(--color-yuzey-ust)" opacity={0.35} />
                            ) : (
                              <rect
                                x={cx}
                                y={s.y}
                                width={w}
                                height={SATIR}
                                fill="var(--color-sis)"
                                opacity={0.07 + 0.83 * Math.min(1, x.m)}
                              />
                            )}
                            {x?.i ? (
                              <circle cx={cx + w / 2} cy={s.y + SATIR / 2} r={1.6} fill={x.m && x.m > 0.45 ? 'var(--color-gece)' : 'var(--color-sis)'} />
                            ) : null}
                            {x?.v ? <rect x={cx} y={s.y - 3} width={w} height={2} fill="var(--color-sodyum)" /> : null}
                            {x?.f ? <rect x={cx} y={s.y + SATIR + 1} width={w} height={2} fill="var(--color-kayip)" /> : null}
                          </g>
                        )
                      })}
                    </g>
                  ))}
                  <line
                    x1={saatler.length * kolG + 3}
                    x2={saatler.length * kolG + 3}
                    y1={UST - 6}
                    y2={yuk - ALT + 2}
                    stroke="var(--color-sodyum)"
                    strokeWidth={2}
                  />
                  {imlec && (
                    <rect
                      x={imlec.c * kolG - 0.5}
                      y={satirlar[imlec.r].y - 1.5}
                      width={kolG + 1}
                      height={SATIR + 3}
                      fill="none"
                      stroke="var(--color-sis)"
                      strokeWidth={1.5}
                      rx={2}
                    />
                  )}
                </svg>
              )}
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

function Lejant() {
  return (
    <ul className="flex flex-wrap items-center gap-x-4 gap-y-1 text-body-sm text-kursun">
      <li className="flex items-center gap-1.5">
        <span className="flex" aria-hidden>
          {[0.1, 0.35, 0.6, 0.9].map((o) => (
            <span key={o} className="size-2.5 bg-sis" style={{ opacity: o }} />
          ))}
        </span>
        maruziyet
      </li>
      <li className="flex items-center gap-1.5">
        <span className="relative size-2.5 bg-sis/20" aria-hidden>
          <span className="absolute inset-x-0 -top-1 h-0.5 bg-sodyum" />
        </span>
        Jev vetosu
      </li>
      <li className="flex items-center gap-1.5">
        <span className="relative size-2.5 bg-sis/20" aria-hidden>
          <span className="absolute inset-x-0 -bottom-1 h-0.5 bg-kayip" />
        </span>
        fren
      </li>
      <li className="flex items-center gap-1.5">
        <span className="flex size-2.5 items-center justify-center bg-sis/20" aria-hidden>
          <span className="size-1 rounded-full bg-sis" />
        </span>
        dolum
      </li>
      <li className="flex items-center gap-1.5">
        <span className="h-3 w-0.5 bg-sodyum" aria-hidden />
        şimdi
      </li>
    </ul>
  )
}
