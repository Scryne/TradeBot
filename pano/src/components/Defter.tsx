import { sayi, tarihTR } from '@/lib/bicim'
import type { Pano, Plan } from '@/lib/tip'

function KararEtiketi({ p }: { p: Plan }) {
  if (p.karar === 'A' || p.karar === 'B')
    return <span className="etiket-ust rounded-full bg-sis px-2 py-1 text-gece">{p.karar} · paper'a</span>
  if (p.karar === 'KALDI') return <span className="etiket-ust rounded-full bg-yuzey-ust px-2 py-1 text-kursun">kaldı</span>
  if (p.durum === 'kapandi') return <span className="etiket-ust rounded-full bg-yuzey-ust px-2 py-1 text-kursun">kapandı</span>
  return <span className="etiket-ust rounded-full border border-cizgi px-2 py-1 text-soluk">sonuç yok</span>
}

const PARCA: Record<string, string> = {
  viop1: 'VİOP 1',
  viop2: 'VİOP 2',
  tasima: 'taşıma',
  altin: 'Altın',
  m15: 'M15',
  donus: 'dönüş',
  gosterim: 'gösterim',
  oynaklik: 'oynaklık',
  fomc: 'FOMC',
  btc: 'BTC',
}

/** Plan kimliği "2026-09-28-viop2-tasima" → "VİOP 2 taşıma" (tarih ayrıca gösterilir). */
function planAdi(k: string) {
  const m = k.match(/^\d{4}-\d{2}-\d{2}-(.+)$/)
  return (m ? m[1] : k)
    .split('-')
    .map((x) => PARCA[x] ?? (/^[a-z]\d[a-z]?$/.test(x) ? x.toUpperCase() : x))
    .join(' ')
}

export function Defter({ p }: { p: Pano }) {
  const d = p.defter
  const gecen = d.planlar.filter((x) => x.karar === 'A' || x.karar === 'B').length
  return (
    <section aria-labelledby="defter-baslik" className="mx-auto w-full max-w-[1320px] px-gutter">
      <div className="grid gap-6 md:grid-cols-12">
        <div className="md:col-span-4">
          <h2 id="defter-baslik" className="font-display text-display-md font-bold tracking-display-md uppercase">
            Araştırma defteri
          </h2>
          <p className="mt-3 max-w-[40ch] text-pretty text-kursun">
            Her fikir önce ön kayıtla yazılır, sonra koşulur. Sonuca bakıp kural değiştirmek yeni bir deneme sayılır.
          </p>
          <dl className="mt-6 flex gap-8">
            <div>
              <dt className="text-body-sm text-kursun">Deneme</dt>
              <dd className="sayi mt-1 text-data-lg leading-none text-sis">{sayi(d.deneme_toplam)}</dd>
            </div>
            <div>
              <dt className="text-body-sm text-kursun">Plan</dt>
              <dd className="sayi mt-1 text-data-lg leading-none text-sis">{d.planlar.length}</dd>
            </div>
            <div>
              <dt className="text-body-sm text-kursun">Paper'a geçen</dt>
              <dd className="sayi mt-1 text-data-lg leading-none text-sis">{gecen}</dd>
            </div>
          </dl>
        </div>
        <ol className="md:col-span-8">
          {d.planlar.map((x) => (
            <li key={x.kimlik} className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 border-t border-cizgi py-4 last:border-b">
              <div className="min-w-0">
                <p className="flex flex-wrap items-baseline gap-x-3">
                  <span className="text-sis first-letter:uppercase">{planAdi(x.kimlik)}</span>
                  <span className="sayi text-body-sm text-soluk">
                    {tarihTR(x.zaman_ms)} · {sayi(x.deneme)} deneme
                  </span>
                </p>
                {(x.sonuc || x.kollar.length > 0) && (
                  <p className="mt-1 line-clamp-2 text-body-sm text-pretty text-kursun">
                    {x.sonuc ??
                      x.kollar
                        .slice(0, 3)
                        .map((k) => `${k.kol.split('@')[0]} ${k.karar}${k.sharpe != null ? ` (Sharpe ${sayi(k.sharpe, 2)})` : ''}`)
                        .join(' · ')}
                  </p>
                )}
              </div>
              <div className="self-start">
                <KararEtiketi p={x} />
              </div>
            </li>
          ))}
        </ol>
      </div>
    </section>
  )
}
