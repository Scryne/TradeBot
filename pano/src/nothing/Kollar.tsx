import { gunTR, kolAdi, oran, yuzde } from '@/lib/bicim'
import type { Kol, Pano, Seri } from '@/lib/tip'

import { BolumBasi, DurumEtiketi, isaretRenk, MaruziyetCubugu } from './Ortak'

/** Kol (düz, ekran) ve kıyas (kesikli, ikincil: QQQ al-tut) getirisi; alan dolgusu yok, sıfır çizgisi kesikli. */
function Cizgi({ a, b, taban, gen = 160, yuk = 32, etiket }: { a: Seri; b?: Seri; taban: number; gen?: number; yuk?: number; etiket: string }) {
  const s1 = a.map(([t, v]) => [t, v / taban - 1] as const)
  const s2 = (b ?? []).map(([t, v]) => [t, v / taban - 1] as const)
  const tum = [...s1, ...s2]
  if (s1.length < 2) return <svg width={gen} height={yuk} role="img" aria-label={`${etiket}: yeterli veri yok`} />
  const t0 = Math.min(...tum.map((x) => x[0]))
  const t1 = Math.max(...tum.map((x) => x[0]))
  const lo = Math.min(0, ...tum.map((x) => x[1]))
  const hi = Math.max(0, ...tum.map((x) => x[1]))
  const pay = (hi - lo) * 0.12 || 0.002
  const X = (t: number) => ((t - t0) / (t1 - t0 || 1)) * (gen - 6) + 2
  const Y = (v: number) => yuk - 3 - ((v - lo + pay) / (hi - lo + 2 * pay)) * (yuk - 6)
  const yol = (s: readonly (readonly [number, number])[]) => s.map(([t, v], i) => `${i ? 'L' : 'M'}${X(t).toFixed(1)},${Y(v).toFixed(1)}`).join('')
  const son = s1[s1.length - 1]
  return (
    <svg width={gen} height={yuk} role="img" aria-label={etiket} className="block overflow-visible">
      <line x1={0} x2={gen} y1={Y(0)} y2={Y(0)} stroke="var(--color-cizgi-belirgin)" strokeDasharray="1 3" />
      {s2.length > 1 && <path d={yol(s2)} fill="none" stroke="var(--color-ikincil)" strokeWidth={1} strokeDasharray="2 2" />}
      <path d={yol(s1)} fill="none" stroke="var(--color-ekran)" strokeWidth={1.5} strokeLinejoin="round" />
      <rect x={X(son[0]) - 2} y={Y(son[1]) - 2} width={4} height={4} fill="var(--color-ekran)" />
    </svg>
  )
}

type Cift = { taban: Kol; jev?: Kol }

const fark = (c: Cift) => c.taban.kiyas?.fark ?? -Infinity

function ciftler(kollar: Kol[]): Cift[] {
  const ad = new Map(kollar.map((k) => [k.kol, k]))
  return kollar.filter((k) => k.tur === 'kol' && !k.jev).map((k) => ({ taban: k, jev: ad.get(k.kol + '+jev') }))
}

/** Emekli kollar (kripto/forex dönemi, gün içi gözlem kolu): son durumları, katlanmış. */
function Emekli({ kollar, onSec }: { kollar: Kol[]; onSec: (kol: string) => void }) {
  if (!kollar.length) return null
  return (
    <details className="group mt-10 border-t border-cizgi pt-4">
      <summary className="etiket flex cursor-pointer list-none flex-wrap items-center gap-x-3 gap-y-1 text-ikincil hover:text-birincil">
        <span aria-hidden className="inline-block transition-transform duration-200 group-open:rotate-90">
          ›
        </span>
        Emekli kollar · {kollar.length}
        <span className="text-ucuncul">durduruldu, son durumları</span>
      </summary>
      <ul className="mt-4 grid gap-x-10 sm:grid-cols-2 lg:grid-cols-3">
        {[...kollar]
          .sort((a, b) => a.kol.localeCompare(b.kol))
          .map((k) => (
            <li key={k.kol} className="border-t border-cizgi">
              <button
                type="button"
                onClick={() => onSec(k.kol)}
                className="flex w-full items-baseline justify-between gap-4 py-2.5 text-left transition-colors duration-200 hover:bg-yuzey"
              >
                <span className="min-w-0 truncate text-govde-sm text-ikincil">
                  {kolAdi(k)}
                  {k.jev && <span className="etiket text-ucuncul"> + Jev</span>}
                  <span className="etiket ml-2 text-ucuncul">{k.grup.replace(/_/g, ' ')}</span>
                </span>
                <span className={`veri whitespace-nowrap shrink-0 text-govde-sm ${isaretRenk(k.toplam)}`}>{yuzde(k.toplam)}</span>
              </button>
            </li>
          ))}
      </ul>
    </details>
  )
}

export function Kollar({ p, onSec }: { p: Pano; onSec: (kol: string) => void }) {
  // Kilit kolları kendi bölümünde (Kilit.tsx); çalışan kollar QQQ kıyasıyla, emekliler katlanmış listede
  const tum = p.kollar.filter((k) => k.strateji !== 'kilit_kisa')
  const calisan = tum.filter((k) => !k.durduruldu)
  const cs = ciftler(calisan).sort((a, b) => fark(b) - fark(a))
  return (
    <section aria-labelledby="kollar-baslik">
      <BolumBasi id="kollar-baslik" baslik="Kollar">
        <ul className="etiket flex items-center gap-5 text-ikincil" aria-label="Çizgi açıklaması">
          <li className="flex items-center gap-2">
            <svg width="20" height="4" aria-hidden>
              <line x1="0" x2="20" y1="2" y2="2" stroke="var(--color-ekran)" strokeWidth="1.5" />
            </svg>
            Kol
          </li>
          <li className="flex items-center gap-2">
            <svg width="20" height="4" aria-hidden>
              <line x1="0" x2="20" y1="2" y2="2" stroke="var(--color-ikincil)" strokeWidth="1" strokeDasharray="2 2" />
            </svg>
            QQQ al-tut
          </li>
        </ul>
      </BolumBasi>
      <p className="mt-3 max-w-[66ch] text-govde-sm text-pretty text-ikincil">
        Her kol, aynı gün QQQ alıp beklemekle kıyaslanıyor: QQQ, kolun ilk dolumunun yapıldığı açılışta alınmış sayılır ve iki
        taraf aynı kapanışa bakar. Backtest'te hiçbir kol QQQ'nun getirisini geçmedi; gerçek para kararı bu farka bakacak.
        Sıralama farka göre.
      </p>

      {cs.length === 0 ? (
        <p className="mt-8 border-l-2 border-cizgi-belirgin py-1 pl-4 text-govde-sm text-ikincil">Çalışan kol yok.</p>
      ) : (
        <table className="mt-8 w-full border-collapse text-left">
          <thead>
            <tr className="etiket border-b border-cizgi-belirgin text-ucuncul">
              <th scope="col" className="py-3 pr-4 font-normal">Strateji</th>
              <th scope="col" className="hidden px-4 py-3 font-normal lg:table-cell">Başlangıçtan</th>
              <th scope="col" className="px-4 py-3 text-right font-normal">Getiri</th>
              <th scope="col" className="hidden px-4 py-3 text-right font-normal sm:table-cell">QQQ</th>
              <th scope="col" className="py-3 pl-4 text-right font-normal md:pr-4">QQQ'ya göre</th>
              <th scope="col" className="hidden px-4 py-3 text-right font-normal md:table-cell">Jev'li ikiz</th>
              <th scope="col" className="hidden px-4 py-3 text-right font-normal xl:table-cell">En kötü düşüş</th>
              <th scope="col" className="hidden px-4 py-3 text-right font-normal xl:table-cell">Hisse</th>
              <th scope="col" className="hidden px-4 py-3 font-normal lg:table-cell">Maruziyet</th>
              <th scope="col" className="hidden py-3 pl-4 text-right font-normal md:table-cell">Durum</th>
            </tr>
          </thead>
          <tbody>
            {cs.map(({ taban: k, jev }) => {
              const q = k.kiyas
              const aralik = q ? `${gunTR(q.bas_ms)} açılış → ${gunTR(q.bit_ms)} kapanış` : 'henüz dolum ya da QQQ kapanışı yok'
              const kisa = q ? `${gunTR(q.bas_ms)} → ${gunTR(q.bit_ms)}` : 'bekliyor'
              return (
                <tr key={k.kol} className="group relative border-b border-cizgi transition-colors duration-200 hover:bg-yuzey">
                  <th scope="row" className="py-4 pr-4 align-middle font-normal">
                    <button
                      type="button"
                      onClick={() => onSec(k.kol)}
                      className="block w-full text-left after:absolute after:inset-0 after:content-['']"
                    >
                      <span className="block text-birincil">{kolAdi(k)}</span>
                      <span className="etiket mt-1 block text-ucuncul" title={aralik}>kıyas {kisa}</span>
                    </button>
                    <div className="mt-3 lg:hidden">
                      <Cizgi a={k.seri} b={q?.seri} taban={k.baslangic_ozkaynak} gen={150} yuk={28} etiket={`${kolAdi(k)} getiri çizgisi`} />
                    </div>
                  </th>
                  <td className="hidden px-4 py-4 lg:table-cell">
                    <Cizgi
                      a={k.seri}
                      b={q?.seri}
                      taban={k.baslangic_ozkaynak}
                      etiket={`${kolAdi(k)}: ${yuzde(k.toplam)}${q ? `, QQQ al-tut ${yuzde(q.kiyas)}` : ''}`}
                    />
                  </td>
                  <td className={`veri whitespace-nowrap px-4 py-4 text-right text-govde ${isaretRenk(k.toplam)}`}>{yuzde(k.toplam)}</td>
                  <td className={`veri whitespace-nowrap hidden px-4 py-4 text-right text-govde-sm sm:table-cell ${q ? isaretRenk(q.kiyas) : 'text-ucuncul'}`}>
                    {yuzde(q?.kiyas)}
                  </td>
                  <td className={`veri whitespace-nowrap py-4 pl-4 text-right text-govde md:pr-4 ${q ? isaretRenk(q.fark) : 'text-ucuncul'}`} title={aralik}>
                    {yuzde(q?.fark)}
                  </td>
                  <td className={`veri whitespace-nowrap hidden px-4 py-4 text-right text-govde-sm md:table-cell ${jev ? isaretRenk(jev.toplam) : 'text-ucuncul'}`}>
                    {jev ? yuzde(jev.toplam) : '—'}
                  </td>
                  <td className="veri whitespace-nowrap hidden px-4 py-4 text-right text-govde-sm text-ikincil xl:table-cell">{yuzde(k.en_kotu_dusus, 1)}</td>
                  <td className="veri whitespace-nowrap hidden px-4 py-4 text-right text-govde-sm text-ikincil xl:table-cell">{k.hisse}</td>
                  <td className="hidden px-4 py-4 lg:table-cell">
                    <span className="flex items-center gap-3">
                      <MaruziyetCubugu x={k.maruziyet} etiket={`Maruziyet ${oran(k.maruziyet)}`} />
                      <span className="veri whitespace-nowrap text-govde-sm text-birincil">{oran(k.maruziyet)}</span>
                    </span>
                  </td>
                  <td className="hidden py-4 pl-4 text-right md:table-cell">
                    <DurumEtiketi d={k.durum} durduruldu={k.durduruldu} />
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}

      <Emekli kollar={tum.filter((k) => k.durduruldu)} onSec={onSec} />
    </section>
  )
}
