import { bps, kolAdi, oran, yuzde } from '@/lib/bicim'
import type { Kol, Pano, Seri } from '@/lib/tip'

import { BolumBasi, DurumEtiketi, isaretRenk, MaruziyetCubugu } from './Ortak'

/** Jev'li (düz, ekran) ve Jev'siz (kesikli, ikincil) getiri; alan dolgusu yok, sıfır çizgisi kesikli. */
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

function ciftler(kollar: Kol[]): { ciftler: Cift[]; tekler: Kol[] } {
  const ad = new Map(kollar.map((k) => [k.kol, k]))
  const c = kollar
    .filter((k) => k.tur === 'kol' && !k.jev)
    .sort((a, b) => (ad.get(b.kol + '+jev')?.toplam ?? b.toplam) - (ad.get(a.kol + '+jev')?.toplam ?? a.toplam))
    .map((k) => ({ taban: k, jev: ad.get(k.kol + '+jev') }))
  return { ciftler: c, tekler: kollar.filter((k) => k.tur !== 'kol') }
}

export function Kollar({ p, onSec }: { p: Pano; onSec: (kol: string) => void }) {
  // Kilit kolları kendi bölümünde (Kilit.tsx); burada yalnız trend turnuvası
  const trend = p.kollar.filter((k) => k.strateji !== 'kilit_kisa')
  const { ciftler: cs, tekler } = ciftler(trend)
  const durdu = trend.filter((k) => k.durduruldu).length
  return (
    <section aria-labelledby="kollar-baslik">
      <BolumBasi id="kollar-baslik" baslik="Kollar">
        <ul className="etiket flex items-center gap-5 text-ikincil" aria-label="Çizgi açıklaması">
          <li className="flex items-center gap-2">
            <svg width="20" height="4" aria-hidden>
              <line x1="0" x2="20" y1="2" y2="2" stroke="var(--color-ekran)" strokeWidth="1.5" />
            </svg>
            Jev'li
          </li>
          <li className="flex items-center gap-2">
            <svg width="20" height="4" aria-hidden>
              <line x1="0" x2="20" y1="2" y2="2" stroke="var(--color-ikincil)" strokeWidth="1" strokeDasharray="2 2" />
            </svg>
            Jev'siz
          </li>
        </ul>
      </BolumBasi>
      <p className="mt-3 max-w-[62ch] text-govde-sm text-pretty text-ikincil">
        Her strateji iki kopya koşuyor: biri Jev vetosuyla, biri vetosuz. Aradaki fark Jev'in değeri. Sıralama Jev'li kopyanın
        başlangıçtan getirisine göre.
        {durdu > 0 && (
          <span className="text-birincil">
            {' '}
            {durdu === trend.length ? 'Bu kolların hepsi durduruldu;' : `${durdu} kol durduruldu;`} tablo son durumlarını gösteriyor.
          </span>
        )}
      </p>

      <table className="mt-8 w-full border-collapse text-left">
        <thead>
          <tr className="etiket border-b border-cizgi-belirgin text-ucuncul">
            <th scope="col" className="py-3 pr-4 font-normal">Strateji</th>
            <th scope="col" className="hidden px-4 py-3 font-normal lg:table-cell">Başlangıçtan</th>
            <th scope="col" className="px-4 py-3 text-right font-normal">Jev'li</th>
            <th scope="col" className="hidden px-4 py-3 text-right font-normal sm:table-cell">Jev'siz</th>
            <th scope="col" className="hidden px-4 py-3 text-right font-normal md:table-cell">En kötü düşüş</th>
            <th scope="col" className="hidden px-4 py-3 text-right font-normal xl:table-cell">Dolum</th>
            <th scope="col" className="hidden px-4 py-3 text-right font-normal xl:table-cell">Yürütme</th>
            <th scope="col" className="hidden px-4 py-3 font-normal md:table-cell">Maruziyet</th>
            <th scope="col" className="hidden py-3 pl-4 text-right font-normal md:table-cell">Durum</th>
          </tr>
        </thead>
        <tbody>
          {cs.map(({ taban, jev }) => {
            const k = jev ?? taban
            return (
              <tr key={taban.kol} className="group relative border-b border-cizgi transition-colors duration-200 hover:bg-yuzey">
                <th scope="row" className="py-4 pr-4 align-middle font-normal">
                  <button
                    type="button"
                    onClick={() => onSec(k.kol)}
                    className="block w-full text-left after:absolute after:inset-0 after:content-['']"
                  >
                    <span className="block truncate text-birincil">{kolAdi(taban)}</span>
                    <span className="etiket mt-1 block text-ucuncul">{taban.grup.replace(/_/g, ' ')}</span>
                  </button>
                  <div className="mt-3 lg:hidden">
                    <Cizgi a={k.seri} b={jev ? taban.seri : undefined} taban={k.baslangic_ozkaynak} gen={200} yuk={28} etiket={`${kolAdi(taban)} getiri çizgisi`} />
                  </div>
                </th>
                <td className="hidden px-4 py-4 lg:table-cell">
                  <Cizgi a={k.seri} b={jev ? taban.seri : undefined} taban={k.baslangic_ozkaynak} etiket={`${kolAdi(taban)}: Jev'li ${yuzde(k.toplam)}, Jev'siz ${yuzde(taban.toplam)}`} />
                </td>
                <td className={`veri px-4 py-4 text-right text-govde ${isaretRenk(k.toplam)}`}>{yuzde(k.toplam)}</td>
                <td className={`veri hidden px-4 py-4 text-right text-govde-sm sm:table-cell ${isaretRenk(taban.toplam)}`}>{yuzde(taban.toplam)}</td>
                <td className="veri hidden px-4 py-4 text-right text-govde-sm text-ikincil md:table-cell">{yuzde(k.en_kotu_dusus, 1)}</td>
                <td className="veri hidden px-4 py-4 text-right text-govde-sm text-ikincil xl:table-cell">{k.islem}</td>
                <td className="veri hidden px-4 py-4 text-right text-govde-sm text-ikincil xl:table-cell">{bps(k.yurutme_bps)}</td>
                <td className="hidden px-4 py-4 md:table-cell">
                  <span className="flex items-center gap-3">
                    <MaruziyetCubugu x={k.maruziyet} etiket={`Maruziyet ${oran(k.maruziyet)}`} />
                    <span className="veri text-govde-sm text-birincil">{oran(k.maruziyet)}</span>
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

      {tekler.length > 0 && (
        <div className="mt-10 grid gap-4 md:grid-cols-2">
          {tekler.map((k) => (
            <button
              key={k.kol}
              type="button"
              onClick={() => onSec(k.kol)}
              className="kart flex items-center gap-6 p-panel text-left transition-colors duration-200 hover:bg-yuzey-ust"
            >
              <span className="min-w-0 flex-1">
                <span className="etiket block text-ikincil">{k.tur === 'agresif' ? 'tam Kelly gözlem' : 'sermaye dağıtıcı'}</span>
                <span className="mt-2 block text-birincil">{kolAdi(k)}</span>
                <span className="mt-1 block text-govde-sm text-pretty text-ikincil">
                  {k.tur === 'agresif'
                    ? 'Kolların ortalaması uzunsa o enstrümanda yarım özkaynak. Dağıtıma girmez.'
                    : 'Haftalık ERC × yarım Kelly. Sermaye yalnız A kollarına gider; şu an hepsi B.'}
                </span>
              </span>
              <span className="text-right">
                <span className={`veri block text-veri-lg leading-none ${isaretRenk(k.toplam)}`}>{yuzde(k.toplam)}</span>
                <span className="etiket mt-2 block text-ucuncul">maruziyet {oran(k.maruziyet)}</span>
              </span>
            </button>
          ))}
        </div>
      )}
    </section>
  )
}
