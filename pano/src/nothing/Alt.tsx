import { gorece, ikiSaat, sayi, tarihTR } from '@/lib/bicim'
import type { Pano, Plan, Saglik } from '@/lib/tip'

import { BolumBasi } from './Ortak'

// ── Araştırma defteri ──────────────────────────────────────────────────────────

function KararEtiketi({ p }: { p: Plan }) {
  if (p.karar === 'A' || p.karar === 'B') return <span className="etiket text-ekran">[{p.karar} · paper'a]</span>
  if (p.karar === 'KALDI') return <span className="etiket text-ikincil">[kaldı]</span>
  if (p.durum === 'kapandi') return <span className="etiket text-ikincil">[kapandı]</span>
  return <span className="etiket text-ucuncul">[sonuç yok]</span>
}

const PARCA: Record<string, string> = {
  viop1: 'VİOP 1', viop2: 'VİOP 2', tasima: 'taşıma', altin: 'Altın', m15: 'M15', donus: 'dönüş',
  gosterim: 'gösterim', oynaklik: 'oynaklık', fomc: 'FOMC', btc: 'BTC',
}

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
    <section aria-labelledby="defter-baslik" className="grid gap-10 md:grid-cols-12">
      <div className="md:col-span-4">
        <BolumBasi id="defter-baslik" baslik="Araştırma defteri" />
        <p className="mt-3 max-w-[40ch] text-govde-sm text-pretty text-ikincil">
          Her fikir önce ön kayıtla yazılır, sonra koşulur. Sonuca bakıp kural değiştirmek yeni bir deneme sayılır.
        </p>
        <dl className="mt-8 flex gap-10">
          {[
            ['Deneme', sayi(d.deneme_toplam)],
            ['Plan', sayi(d.planlar.length)],
            ["Paper'a geçen", sayi(gecen)],
          ].map(([a, v]) => (
            <div key={a}>
              <dt className="etiket text-ikincil">{a}</dt>
              <dd className="veri mt-2 text-veri-lg leading-none text-birincil">{v}</dd>
            </div>
          ))}
        </dl>
      </div>
      <ol className="md:col-span-8">
        {d.planlar.map((x) => (
          <li key={x.kimlik} className="grid grid-cols-[1fr_auto] gap-x-6 border-t border-cizgi py-4 last:border-b">
            <div className="min-w-0">
              <p className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
                <span className="text-birincil first-letter:uppercase">{planAdi(x.kimlik)}</span>
                <span className="etiket text-ucuncul">
                  {tarihTR(x.zaman_ms)} · {sayi(x.deneme)} deneme
                </span>
              </p>
              {(x.sonuc || x.kollar.length > 0) && (
                <p className="mt-1 line-clamp-2 text-govde-sm text-pretty text-ikincil">
                  {x.sonuc ??
                    x.kollar
                      .slice(0, 3)
                      .map((k) => `${k.kol.split('@')[0]} ${k.karar}${k.sharpe != null ? ` (Sharpe ${sayi(k.sharpe, 2)})` : ''}`)
                      .join(' · ')}
                </p>
              )}
            </div>
            <div className="self-start pt-0.5">
              <KararEtiketi p={x} />
            </div>
          </li>
        ))}
      </ol>
    </section>
  )
}

// ── Sağlık ─────────────────────────────────────────────────────────────────────

const AD: Record<string, string> = {
  dns: 'DNS', saat: 'Saat', veritabani: 'Veritabanı', disk: 'Disk', sirlar: 'Sırlar', paper: 'Paper kalp atışı',
  gece_isi: 'Gece işi', yedek: 'Yedek', mt5: 'MT5 köprüleri', saglik: 'Sağlık bekçisi',
}

const DURUM = {
  OK: { metin: 'sağlam', renk: 'text-ikincil', nokta: 'var(--color-ekran)' },
  UYARI: { metin: 'uyarı', renk: 'text-amber', nokta: 'var(--color-amber)' },
  HATA: { metin: 'hata', renk: 'text-kirmizi-metin', nokta: 'var(--color-kirmizi)' },
} as const

export function SaglikBolumu({ s, simdi, kod }: { s: Saglik | null; simdi: number; kod?: string }) {
  return (
    <section id="saglik" aria-labelledby="saglik-baslik" className="scroll-mt-20">
      <BolumBasi id="saglik-baslik" baslik="Sağlık">
        <p className="etiket text-ucuncul">
          {s?.zaman_ms ? <>ölçüm {gorece(s.zaman_ms, simdi)} · {ikiSaat(s.zaman_ms)}</> : 'ölçülüyor'}
          {kod ? <> · kod {kod}</> : null}
        </p>
      </BolumBasi>
      {!s?.hazir ? (
        <p className="etiket mt-6 text-ikincil" aria-busy>
          [ölçülüyor]
        </p>
      ) : (
        <ul className="mt-6 grid gap-px overflow-hidden rounded-kart bg-cizgi sm:grid-cols-2 lg:grid-cols-3">
          {s.kontroller.map((k) => {
            const d = DURUM[k.durum]
            return (
              <li key={k.ad} className="bg-siyah p-5">
                <p className="flex items-center justify-between gap-3">
                  <span className="flex items-center gap-3">
                    <span className="size-1.5 rounded-full" style={{ background: d.nokta }} aria-hidden />
                    <span className="text-birincil">{AD[k.ad] ?? k.ad}</span>
                  </span>
                  <span className={`etiket ${d.renk}`}>[{d.metin}]</span>
                </p>
                <p className="mt-2 pl-[18px] text-govde-sm break-words text-pretty text-ikincil">{k.ayrinti}</p>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}

// ── Üst çubuk ──────────────────────────────────────────────────────────────────

function saglikOzeti(s: Saglik | null) {
  if (!s?.hazir) return { renk: 'text-ikincil', nokta: 'var(--color-pasif)', metin: 'ölçülüyor' }
  const hata = s.kontroller.filter((k) => k.durum === 'HATA').length
  const uyari = s.kontroller.filter((k) => k.durum === 'UYARI').length
  const tamam = s.kontroller.length - hata - uyari
  if (hata) return { renk: 'text-kirmizi-metin', nokta: 'var(--color-kirmizi)', metin: `${hata} hata` }
  if (uyari) return { renk: 'text-amber', nokta: 'var(--color-amber)', metin: `${uyari} uyarı · ${tamam}/${s.kontroller.length} sağlam` }
  return { renk: 'text-ikincil', nokta: 'var(--color-ekran)', metin: `${tamam}/${s.kontroller.length} sağlam` }
}

export function UstCubuk({ pano, saglik }: { pano: Pano | null; saglik: Saglik | null }) {
  const s = saglikOzeti(saglik)
  return (
    <header className="sticky top-0 border-b border-cizgi bg-siyah" style={{ zIndex: 'var(--z-bar)', paddingTop: 'env(safe-area-inset-top)' }}>
      <div className="mx-auto flex h-14 max-w-[1320px] items-center gap-4 px-gutter">
        <a href="#" className="etiket flex items-baseline gap-3 text-ekran">
          TradeBot
          <span className="hidden text-ucuncul sm:inline">[paper]</span>
        </a>
        <div className="etiket ml-auto flex items-center gap-6">
          <a href="#saglik" className={`flex items-center gap-2 ${s.renk}`}>
            <span className="size-1.5 rounded-full" style={{ background: s.nokta }} aria-hidden />
            {s.metin}
          </a>
          {pano && (
            <span className="hidden text-ucuncul md:inline" title="Verinin alındığı an">
              {ikiSaat(pano.simdi_ms)}
            </span>
          )}
        </div>
      </div>
    </header>
  )
}
