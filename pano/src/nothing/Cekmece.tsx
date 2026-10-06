import { useState } from 'react'

import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { durumAdi, enstrumanAdi, gunTR, kolAdi, oran, para, sayi, tarihSaatTR, yuzde } from '@/lib/bicim'
import type { Kol, KolAyrinti, Seri } from '@/lib/tip'
import { useKol } from '@/lib/veri'

import { DurumEtiketi } from './Ortak'

const G = 560
const Y_ = 200
const SOL = 48
const ALT = 22

/** Başlangıçtan getiri, Jev'li (düz) ve Jev'siz (kesikli); üzerine gelince dikey imleç ve okuma satırı (tek eksen). */
function BuyukCizgi({ seri, ikiz, taban, jev }: { seri: Seri; ikiz: Seri; taban: number; jev: boolean }) {
  const [i, setI] = useState<number | null>(null)
  const a = seri.map(([t, v]) => [t, v / taban - 1] as const)
  const b = ikiz.map(([t, v]) => [t, v / taban - 1] as const)
  const tum = [...a, ...b]
  const olcek = (() => {
    if (tum.length < 2) return null
    const t0 = Math.min(...tum.map((x) => x[0]))
    const t1 = Math.max(...tum.map((x) => x[0]))
    const lo = Math.min(0, ...tum.map((x) => x[1]))
    const hi = Math.max(0, ...tum.map((x) => x[1]))
    const pay = (hi - lo) * 0.1 || 0.002
    return { t0, t1, lo: lo - pay, hi: hi + pay }
  })()
  if (!olcek || a.length < 2)
    return <p className="text-govde-sm text-ikincil">Çizgi için en az iki işaret gerekiyor. Paper düğümü her saat başında bir işaret yazar.</p>
  const X = (t: number) => SOL + ((t - olcek.t0) / (olcek.t1 - olcek.t0 || 1)) * (G - SOL - 8)
  const Y = (v: number) => 8 + (1 - (v - olcek.lo) / (olcek.hi - olcek.lo)) * (Y_ - ALT - 8)
  const yol = (s: readonly (readonly [number, number])[]) => s.map(([t, v], k) => `${k ? 'L' : 'M'}${X(t).toFixed(1)},${Y(v).toFixed(1)}`).join('')
  const adim = (olcek.hi - olcek.lo) / 3
  const tikler = [0, 1, 2, 3].map((k) => olcek.lo + adim * k)
  const gunler = [...new Set(a.map(([t]) => Math.floor((t + 3 * 3.6e6) / 864e5)))]
  const gunAdim = Math.max(1, Math.ceil(gunler.length / 5))
  const secili = i == null ? a[a.length - 1] : a[i]
  const ikizEs = b.find(([t]) => t === secili[0])

  function isaretle(e: React.PointerEvent<SVGSVGElement>) {
    const r = e.currentTarget.getBoundingClientRect()
    const x = ((e.clientX - r.left) / r.width) * G
    let en = 0
    for (let k = 1; k < a.length; k++) if (Math.abs(X(a[k][0]) - x) < Math.abs(X(a[en][0]) - x)) en = k
    setI(en)
  }

  return (
    <figure>
      <figcaption aria-live="polite" className="etiket flex flex-wrap items-baseline gap-x-5 gap-y-1 text-ikincil">
        <span>{tarihSaatTR(secili[0])}</span>
        <span>
          {jev ? "Jev'li" : "Jev'siz"} <span className="veri text-birincil">{yuzde(secili[1])}</span>
        </span>
        {ikizEs && (
          <span>
            {jev ? "Jev'siz" : "Jev'li"} <span className="veri text-birincil">{yuzde(ikizEs[1])}</span>
          </span>
        )}
      </figcaption>
      <svg
        viewBox={`0 0 ${G} ${Y_}`}
        className="mt-4 block h-auto w-full touch-pan-y"
        role="img"
        aria-label="Başlangıçtan getiri çizgisi"
        onPointerMove={isaretle}
        onPointerDown={isaretle}
        onPointerLeave={() => setI(null)}
      >
        {tikler.map((v) => (
          <g key={v}>
            <line x1={SOL} x2={G - 8} y1={Y(v)} y2={Y(v)} stroke="var(--color-cizgi)" />
            <text x={SOL - 8} y={Y(v) + 3.5} textAnchor="end" className="fill-ucuncul font-mono text-[10px]">
              {yuzde(v, 1)}
            </text>
          </g>
        ))}
        <line x1={SOL} x2={G - 8} y1={Y(0)} y2={Y(0)} stroke="var(--color-cizgi-belirgin)" strokeDasharray="1 3" />
        {gunler
          .filter((_, k) => k % gunAdim === 0)
          .map((g) => (
            <text key={g} x={X(g * 864e5 - 3 * 3.6e6)} y={Y_ - 6} className="fill-ucuncul font-mono text-[10px]">
              {gunTR(g * 864e5)}
            </text>
          ))}
        {b.length > 1 && <path d={yol(b)} fill="none" stroke="var(--color-ikincil)" strokeWidth={1} strokeDasharray="2 2" />}
        <path d={yol(a)} fill="none" stroke="var(--color-ekran)" strokeWidth={1.5} strokeLinejoin="round" />
        <line x1={X(secili[0])} x2={X(secili[0])} y1={8} y2={Y_ - ALT} stroke="var(--color-ekran)" strokeWidth={1} opacity={i == null ? 0 : 0.6} />
        <rect x={X(secili[0]) - 3} y={Y(secili[1]) - 3} width={6} height={6} fill="var(--color-ekran)" />
      </svg>
    </figure>
  )
}

function Icerik({ d, ozet }: { d: KolAyrinti; ozet?: Kol }) {
  return (
    <div className="flex flex-col gap-10 px-5 pb-10 sm:px-6">
      <BuyukCizgi seri={d.seri} ikiz={d.ikiz_seri} taban={d.baslangic_ozkaynak} jev={d.jev} />

      {ozet && (
        <dl className="grid grid-cols-2 gap-x-6 gap-y-5 sm:grid-cols-4">
          {[
            ['Özkaynak', para(ozet.ozkaynak)],
            ['Son 24 saat', yuzde(ozet.gun)],
            ['En kötü düşüş', yuzde(ozet.en_kotu_dusus, 1)],
            ['Maruziyet', oran(ozet.maruziyet)],
            ['Karar', sayi(ozet.karar)],
            ['Dolum', sayi(ozet.islem)],
            ['Frenli karar', sayi(ozet.fren)],
            ['Vetolu karar', sayi(ozet.veto)],
          ].map(([a, v]) => (
            <div key={a}>
              <dt className="etiket text-ikincil">{a}</dt>
              <dd className="veri mt-1.5 text-govde-sm text-birincil">{v}</dd>
            </div>
          ))}
        </dl>
      )}

      <section aria-labelledby="k-kararlar">
        <h3 id="k-kararlar" className="etiket text-ikincil">
          Son kararlar
        </h3>
        <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[440px] text-govde-sm">
            <thead>
              <tr className="etiket border-b border-cizgi-belirgin text-ucuncul">
                <th scope="col" className="py-2 text-left font-normal">Bar</th>
                <th scope="col" className="py-2 text-left font-normal">Durum</th>
                <th scope="col" className="py-2 text-right font-normal">Hedef</th>
                <th scope="col" className="py-2 pl-3 text-left font-normal">Veto</th>
              </tr>
            </thead>
            <tbody>
              {d.kararlar.slice(0, 24).map((k) => (
                <tr key={k.bar_ms} className="border-b border-cizgi">
                  <td className="veri py-2 text-ikincil">{tarihSaatTR(k.bar_ms)}</td>
                  <td className={`py-2 ${k.durum === 'normal' ? 'text-ikincil' : 'text-kirmizi-metin'}`}>{durumAdi(k.durum)}</td>
                  <td className="veri py-2 text-right text-birincil">
                    {(k.kimlikler ?? []).map((e, j) => `${enstrumanAdi(e)} ${oran(k.hedef?.[j] ?? 0)}`).join(' · ')}
                  </td>
                  <td className="py-2 pl-3 text-amber">{k.veto.map(enstrumanAdi).join(', ')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section aria-labelledby="k-dolumlar">
        <h3 id="k-dolumlar" className="etiket text-ikincil">
          Son dolumlar
        </h3>
        {d.dolumlar.length ? (
          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[440px] text-govde-sm">
              <thead>
                <tr className="etiket border-b border-cizgi-belirgin text-ucuncul">
                  <th scope="col" className="py-2 text-left font-normal">Zaman</th>
                  <th scope="col" className="py-2 text-left font-normal">Enstrüman</th>
                  <th scope="col" className="py-2 text-right font-normal">Adet</th>
                  <th scope="col" className="py-2 text-right font-normal">Fiyat</th>
                  <th scope="col" className="py-2 text-right font-normal">Ücret</th>
                </tr>
              </thead>
              <tbody>
                {d.dolumlar.slice(0, 20).map((x, j) => (
                  <tr key={`${x.zaman_ms}-${j}`} className="border-b border-cizgi">
                    <td className="veri py-2 text-ikincil">{tarihSaatTR(x.zaman_ms)}</td>
                    <td className="py-2 text-birincil">{enstrumanAdi(x.enstruman)}</td>
                    <td className={`veri py-2 text-right ${x.miktar > 0 ? 'text-yesil' : 'text-kirmizi-metin'}`}>
                      {x.miktar > 0 ? '+' : ''}
                      {sayi(x.miktar, 4)}
                    </td>
                    <td className="veri py-2 text-right text-birincil">{x.fiyat == null ? '—' : sayi(x.fiyat, 2)}</td>
                    <td className="veri py-2 text-right text-ikincil">{sayi(x.ucret, 2)} $</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="mt-3 text-govde-sm text-ikincil">Bu kol henüz dolum almadı: sinyali şu ana kadar pozisyon açtırmadı.</p>
        )}
      </section>

      <p className="etiket text-ucuncul">
        kod {d.kod_surumu} · son karar verisi {d.kararlar[0]?.veri_hash ?? '—'}
      </p>
    </div>
  )
}

export function KolCekmece({ kol, ozet, onKapat }: { kol: string | null; ozet?: Kol; onKapat: () => void }) {
  const { veri, hata } = useKol(kol)
  const d = veri && veri.kol === kol ? veri : null
  return (
    <Sheet open={kol != null} onOpenChange={(a) => !a && onKapat()}>
      <SheetContent
        side="right"
        className="w-full gap-0 overflow-y-auto border-l border-cizgi-belirgin bg-yuzey p-0 data-[side=right]:w-full data-[side=right]:sm:max-w-[640px]"
      >
        <SheetHeader className="gap-2 px-5 pt-6 pb-6 sm:px-6">
          <div className="flex items-center gap-3 pr-10">
            <SheetTitle className="text-baslik leading-none font-normal tracking-[-0.01em] text-ekran">{ozet ? kolAdi(ozet) : '…'}</SheetTitle>
            {ozet && <DurumEtiketi d={ozet.durum} />}
          </div>
          <SheetDescription className="text-govde-sm text-ikincil">
            {ozet?.jev ? 'Jev vetolu kopya. Kesikli çizgi aynı stratejinin vetosuz ikizi.' : ozet?.tur === 'kol' ? 'Jev vetosuz kopya.' : 'Tek kopya.'}{' '}
            <span className="veri">{kol}</span>
          </SheetDescription>
        </SheetHeader>
        {hata && !d ? (
          <p role="alert" className="px-6 text-govde-sm text-birincil">
            <span className="etiket text-kirmizi-metin">[hata]</span> Kol yüklenemedi: {hata}. Dakikada bir yeniden deneniyor.
          </p>
        ) : d ? (
          <Icerik d={d} ozet={ozet} />
        ) : (
          <p className="etiket px-6 text-ikincil" aria-busy>
            [yükleniyor]
          </p>
        )}
      </SheetContent>
    </Sheet>
  )
}
