import { ChevronRight } from 'lucide-react'

import { bps, durumAdi, kolAdi, oran, yuzde } from '@/lib/bicim'
import type { Kol, Pano } from '@/lib/tip'

import { IkizCizgi } from './IkizCizgi'

const isaretRenk = (x: number) => (x > 0.00005 ? 'text-kazanc' : x < -0.00005 ? 'text-kayip' : 'text-kursun')

export function DurumEtiketi({ d }: { d: string | null }) {
  if (!d || d === 'normal') return <span className="etiket-ust rounded-full bg-yuzey-ust px-2 py-1 text-kursun">normal</span>
  return <span className="etiket-ust rounded-full bg-kayip/15 px-2 py-1 text-kayip">{durumAdi(d)}</span>
}

type Cift = { taban: Kol; jev?: Kol }

function ciftler(kollar: Kol[]): { ciftler: Cift[]; tekler: Kol[] } {
  const ad = new Map(kollar.map((k) => [k.kol, k]))
  const c = kollar
    .filter((k) => k.tur === 'kol' && !k.jev)
    .sort((a, b) => (ad.get(b.kol + '+jev')?.toplam ?? b.toplam) - (ad.get(a.kol + '+jev')?.toplam ?? a.toplam))
    .map((k) => ({ taban: k, jev: ad.get(k.kol + '+jev') }))
  return { ciftler: c, tekler: kollar.filter((k) => k.tur !== 'kol') }
}

export function Kollar({ p, onSec }: { p: Pano; onSec: (kol: string) => void }) {
  const { ciftler: cs, tekler } = ciftler(p.kollar)
  return (
    <section aria-labelledby="kollar-baslik" className="mx-auto w-full max-w-[1320px] px-gutter">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 id="kollar-baslik" className="font-display text-display-md font-bold tracking-display-md uppercase">
            Kollar
          </h2>
          <p className="mt-2 max-w-[62ch] text-pretty text-kursun">
            Her strateji iki kopya koşuyor: biri Jev vetosuyla, biri vetosuz. İkisinin farkı Jev'in değeridir. Sıralama Jev'li
            kopyanın başlangıçtan getirisine göre.
          </p>
        </div>
        <ul className="flex items-center gap-4 text-body-sm text-kursun" aria-label="Çizgi açıklaması">
          <li className="flex items-center gap-2">
            <svg width="22" height="6" aria-hidden>
              <line x1="1" x2="21" y1="3" y2="3" stroke="var(--color-sis)" strokeWidth="2" strokeLinecap="round" />
            </svg>
            Jev'li
          </li>
          <li className="flex items-center gap-2">
            <svg width="22" height="6" aria-hidden>
              <line x1="1" x2="21" y1="3" y2="3" stroke="var(--color-kursun)" strokeWidth="1.5" strokeDasharray="3 3" />
            </svg>
            Jev'siz
          </li>
        </ul>
      </div>

      <div className="panel mt-6 overflow-hidden">
        <table className="w-full border-collapse text-left">
          <thead>
            <tr className="etiket-ust border-b border-cizgi text-soluk">
              <th scope="col" className="px-4 py-3 font-medium">Strateji</th>
              <th scope="col" className="hidden px-4 py-3 font-medium lg:table-cell">Başlangıçtan</th>
              <th scope="col" className="px-4 py-3 text-right font-medium">Jev'li</th>
              <th scope="col" className="hidden px-4 py-3 text-right font-medium sm:table-cell">Jev'siz</th>
              <th scope="col" className="hidden px-4 py-3 text-right font-medium md:table-cell">En kötü düşüş</th>
              <th scope="col" className="hidden px-4 py-3 text-right font-medium xl:table-cell">Dolum</th>
              <th scope="col" className="hidden px-4 py-3 text-right font-medium xl:table-cell">Yürütme</th>
              <th scope="col" className="hidden px-4 py-3 text-right font-medium md:table-cell">Maruziyet</th>
              <th scope="col" className="hidden px-4 py-3 font-medium md:table-cell">Durum</th>
            </tr>
          </thead>
          <tbody>
            {cs.map(({ taban, jev }) => {
              const k = jev ?? taban
              return (
                <tr key={taban.kol} className="group relative border-b border-cizgi/70 transition-colors last:border-0 hover:bg-yuzey-ust/60">
                  <th scope="row" className="px-4 py-3 align-middle font-normal">
                    <button
                      type="button"
                      onClick={() => onSec(k.kol)}
                      className="flex w-full items-center gap-2 rounded-control text-left after:absolute after:inset-0 after:content-['']"
                    >
                      <span className="min-w-0">
                        <span className="block truncate text-sis">{kolAdi(taban)}</span>
                        <span className="sayi mt-0.5 block text-body-sm text-soluk">{taban.grup.replace(/_/g, ' ')}</span>
                      </span>
                      <ChevronRight className="ml-auto size-4 shrink-0 text-soluk transition-transform group-hover:translate-x-0.5 lg:hidden" aria-hidden />
                    </button>
                    <div className="mt-2 lg:hidden">
                      <IkizCizgi jevli={k.seri} jevsiz={jev ? taban.seri : undefined} taban={k.baslangic_ozkaynak} gen={200} yuk={32} etiket={`${kolAdi(taban)} getiri çizgisi`} />
                    </div>
                  </th>
                  <td className="hidden px-4 py-3 lg:table-cell">
                    <IkizCizgi jevli={k.seri} jevsiz={jev ? taban.seri : undefined} taban={k.baslangic_ozkaynak} etiket={`${kolAdi(taban)}: Jev'li ${yuzde(k.toplam)}, Jev'siz ${yuzde(taban.toplam)}`} />
                  </td>
                  <td className={`sayi px-4 py-3 text-right text-[15px] ${isaretRenk(k.toplam)}`}>{yuzde(k.toplam)}</td>
                  <td className={`sayi hidden px-4 py-3 text-right sm:table-cell ${isaretRenk(taban.toplam)}`}>{yuzde(taban.toplam)}</td>
                  <td className="sayi hidden px-4 py-3 text-right text-kursun md:table-cell">{yuzde(k.en_kotu_dusus, 1)}</td>
                  <td className="sayi hidden px-4 py-3 text-right text-kursun xl:table-cell">{k.islem}</td>
                  <td className="sayi hidden px-4 py-3 text-right text-kursun xl:table-cell">{bps(k.yurutme_bps)}</td>
                  <td className="sayi hidden px-4 py-3 text-right text-sis md:table-cell">{oran(k.maruziyet)}</td>
                  <td className="hidden px-4 py-3 md:table-cell">
                    <DurumEtiketi d={k.durum} />
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {tekler.length > 0 && (
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          {tekler.map((k) => (
            <button
              key={k.kol}
              type="button"
              onClick={() => onSec(k.kol)}
              className="panel flex items-center gap-5 p-panel text-left transition-colors hover:bg-yuzey-ust/60"
            >
              <span className="min-w-0 flex-1">
                <span className="flex items-baseline gap-2">
                  <span className="text-sis">{kolAdi(k)}</span>
                  <span className="etiket-ust text-soluk">{k.tur === 'agresif' ? 'tam Kelly gözlem' : 'sermaye dağıtıcı'}</span>
                </span>
                <span className="mt-1 block text-body-sm text-pretty text-kursun">
                  {k.tur === 'agresif'
                    ? 'Kolların ortalaması uzunsa o enstrümanda yarım özkaynak. Dağıtıma girmez.'
                    : 'Haftalık ERC × yarım Kelly. Sermaye yalnız A kollarına gider; şu an hepsi B.'}
                </span>
              </span>
              <span className="hidden sm:block">
                <IkizCizgi jevli={k.seri} taban={k.baslangic_ozkaynak} gen={120} yuk={36} etiket={`${kolAdi(k)} getiri çizgisi`} />
              </span>
              <span className="text-right">
                <span className={`sayi block text-[15px] ${isaretRenk(k.toplam)}`}>{yuzde(k.toplam)}</span>
                <span className="sayi block text-body-sm text-kursun">maruziyet {oran(k.maruziyet)}</span>
              </span>
            </button>
          ))}
        </div>
      )}
    </section>
  )
}
