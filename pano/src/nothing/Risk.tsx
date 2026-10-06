import { enstrumanAdi, kolAdi, oran, sayi, yuzde } from '@/lib/bicim'
import { satirSirasi } from '@/lib/kol'
import type { Pano } from '@/lib/tip'

import { StatSatiri } from './Ortak'

const YAN = 12 // merkezden her yana segment; 10. segment tavan

/** Pozisyon: merkezden uzun sağa, kısa sola; segment = tavanın %10'u, tavanı aşan segmentler kırmızı. */
function PozisyonCubugu({ deger, tavan, etiket }: { deger: number; tavan: number; etiket: string }) {
  const n = Math.min(YAN, Math.round((Math.abs(deger) / tavan) * 10))
  const yan = (taraf: 1 | -1) =>
    Array.from({ length: YAN }, (_, i) => {
      const dolu = (deger >= 0 ? taraf === 1 : taraf === -1) && i < n
      const asim = i >= 10
      return (
        <span
          key={i}
          className="min-w-0 flex-1"
          style={{
            background: dolu ? (asim ? 'var(--color-kirmizi)' : 'var(--color-ekran)') : asim ? 'transparent' : 'var(--color-cizgi-belirgin)',
            boxShadow: asim && !dolu ? 'inset 0 0 0 1px var(--color-cizgi-belirgin)' : undefined,
          }}
        />
      )
    })
  return (
    <div className="flex h-2 items-stretch gap-[2px]" role="img" aria-label={`${etiket}: ${oran(deger)}, tavan ${oran(tavan)}`}>
      <div className="flex flex-1 flex-row-reverse gap-[2px]">{yan(-1)}</div>
      <span className="w-px bg-ikincil" />
      <div className="flex flex-1 gap-[2px]">{yan(1)}</div>
    </div>
  )
}

export function Risk({ p }: { p: Pano }) {
  const t = p.tavan
  const kollar = satirSirasi(p.kollar)
  const ens = [...new Set(p.kollar.flatMap((k) => Object.keys(k.pozisyon)))].sort()
  const gosterilen = ens.length ? ens : ['BINANCE:BTCUSDT', 'BINANCE:ETHUSDT']
  return (
    <div>
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h3 className="etiket text-ikincil">Pozisyonlar ve tavanlar</h3>
        <p className="etiket text-ucuncul">10 segment = tavan</p>
      </div>
      <table className="mt-5 w-full">
        <thead>
          <tr className="etiket text-ucuncul">
            <th scope="col" className="pb-3 text-left font-normal">Kol</th>
            {gosterilen.map((e) => (
              <th key={e} scope="col" className="pb-3 pl-4 text-left font-normal">
                {enstrumanAdi(e)}
              </th>
            ))}
            <th scope="col" className="pb-3 pl-4 text-right font-normal">Brüt</th>
          </tr>
        </thead>
        <tbody>
          {kollar.map((k) => (
            <tr key={k.kol} className="border-t border-cizgi">
              <th scope="row" className="max-w-[10rem] truncate py-2.5 pr-2 text-left text-govde-sm font-normal text-ikincil">
                {k.jev ? <span className="etiket pl-3 text-ucuncul">+ Jev</span> : kolAdi(k)}
              </th>
              {gosterilen.map((e) => (
                <td key={e} className="w-[30%] py-2.5 pl-4">
                  <PozisyonCubugu deger={k.pozisyon[e] ?? 0} tavan={t.enstruman} etiket={`${kolAdi(k)} ${enstrumanAdi(e)}`} />
                </td>
              ))}
              <td className="veri py-2.5 pl-4 text-right text-govde-sm text-birincil">{oran(k.maruziyet)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <dl className="mt-10 grid gap-x-10 sm:grid-cols-2">
        <StatSatiri ad="Enstrüman tavanı" deger={oran(t.enstruman)} />
        <StatSatiri ad="Günlük fren" deger={yuzde(t.gunluk_fren, 0)} />
        <StatSatiri ad="Sınıf tavanı" deger={oran(t.sinif)} />
        <StatSatiri ad="Haftalık fren" deger={yuzde(t.haftalik_fren, 0)} />
        <StatSatiri ad="Kaldıraç tavanı" deger={`${sayi(t.kaldirac)}x`} />
        <StatSatiri ad="Acil durdurma" deger={yuzde(t.acil_durdurma, 0)} />
      </dl>
      {p.dagitim && (
        <p className="mt-6 text-govde-sm text-pretty text-ikincil">
          Bu haftaki dağıtım: portföy kaldıracı <span className="veri text-birincil">{sayi(p.dagitim.kaldirac, 2)}x</span>.{' '}
          {p.dagitim.kaldirac === 0 ? 'Kollar henüz B sınıfında; sermaye ancak paper kanıtıyla A olunca dağıtılır.' : null}
        </p>
      )}
    </div>
  )
}
