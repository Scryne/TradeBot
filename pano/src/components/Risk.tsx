import { enstrumanAdi, kolAdi, oran, sayi, yuzde } from '@/lib/bicim'
import { satirSirasi } from '@/lib/kol'
import type { Pano } from '@/lib/tip'


/** Enstrüman başına pozisyon oranı, tavan çentiğiyle. Uzun sağa, kısa sola; ölçek ±tavan × 1,2. */
function Cubuk({ deger, tavan, etiket }: { deger: number; tavan: number; etiket: string }) {
  const olcek = tavan * 1.2
  const w = Math.min(1, Math.abs(deger) / olcek) * 50
  return (
    <div className="relative h-3 w-full" role="img" aria-label={`${etiket}: ${oran(deger)}, tavan ${oran(tavan)}`}>
      <div className="absolute inset-y-[5px] inset-x-0 bg-yuzey-ust" />
      <div
        className="absolute inset-y-0.5 bg-sis/80"
        style={deger >= 0 ? { left: '50%', width: `${w}%` } : { right: '50%', width: `${w}%` }}
      />
      <div className="absolute inset-y-0 left-1/2 w-px bg-soluk" />
      {[-1, 1].map((s) => (
        <div key={s} className="absolute -inset-y-0.5 w-0.5 bg-kursun" style={{ left: `calc(${50 + (s * 50) / 1.2}% - 1px)` }} />
      ))}
    </div>
  )
}

export function Risk({ p }: { p: Pano }) {
  const t = p.tavan
  const kollar = satirSirasi(p.kollar)
  const ens = [...new Set(p.kollar.flatMap((k) => Object.keys(k.pozisyon)))].sort()
  const gosterilen = ens.length ? ens : ['BINANCE:BTCUSDT', 'BINANCE:ETHUSDT']
  return (
    <div className="panel p-panel md:p-6">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h3 className="etiket-ust text-kursun">Pozisyonlar ve tavanlar</h3>
        <p className="text-body-sm text-kursun">özkaynağa oran · dikey çentik = enstrüman tavanı</p>
      </div>
      <table className="mt-4 w-full text-body-sm">
        <thead>
          <tr className="etiket-ust text-soluk">
            <th scope="col" className="pb-2 text-left font-medium">Kol</th>
            {gosterilen.map((e) => (
              <th key={e} scope="col" className="pb-2 pl-3 text-left font-medium">
                {enstrumanAdi(e)}
              </th>
            ))}
            <th scope="col" className="pb-2 pl-3 text-right font-medium">Brüt</th>
          </tr>
        </thead>
        <tbody>
          {kollar.map((k) => (
            <tr key={k.kol} className="border-t border-cizgi/60">
              <th scope="row" className="max-w-[10rem] truncate py-2 pr-2 text-left font-normal text-kursun">
                {k.jev ? <span className="text-soluk">+ Jev</span> : kolAdi(k)}
              </th>
              {gosterilen.map((e) => (
                <td key={e} className="w-[30%] py-2 pl-3">
                  <Cubuk deger={k.pozisyon[e] ?? 0} tavan={t.enstruman} etiket={`${kolAdi(k)} ${enstrumanAdi(e)}`} />
                </td>
              ))}
              <td className="sayi py-2 pl-3 text-right text-sis">{oran(k.maruziyet)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <dl className="mt-6 grid grid-cols-2 gap-x-6 gap-y-3 border-t border-cizgi pt-5 text-body-sm sm:grid-cols-3">
        {[
          ['Enstrüman tavanı', oran(t.enstruman)],
          ['Sınıf tavanı', oran(t.sinif)],
          ['Kaldıraç tavanı', `${sayi(t.kaldirac)}x`],
          ['Günlük fren', yuzde(t.gunluk_fren, 0)],
          ['Haftalık fren', yuzde(t.haftalik_fren, 0)],
          ['Acil durdurma', yuzde(t.acil_durdurma, 0)],
        ].map(([a, v]) => (
          <div key={a}>
            <dt className="text-kursun">{a}</dt>
            <dd className="sayi mt-0.5 text-sis">{v}</dd>
          </div>
        ))}
      </dl>
      {p.dagitim && (
        <p className="mt-5 text-body-sm text-pretty text-kursun">
          Bu haftaki dağıtım: portföy kaldıracı <span className="sayi text-sis">{sayi(p.dagitim.kaldirac, 2)}x</span>.{' '}
          {p.dagitim.kaldirac === 0 ? 'Kollar henüz B sınıfında; sermaye ancak paper kanıtıyla A olunca dağıtılır.' : null}
        </p>
      )}
    </div>
  )
}
