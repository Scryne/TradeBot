import { gorece, gunTR, ikiSaat, sayi } from '@/lib/bicim'
import type { Pano } from '@/lib/tip'

function durum(p: Pano): { cumle: string; ton: 'sakin' | 'dikkat' | 'alarm' } {
  const d = p.durum
  if (d.bayat) return { cumle: `Paper verisi gelmiyor. Son işaret ${d.son_isaret_ms ? gorece(d.son_isaret_ms, p.simdi_ms) : 'hiç'}.`, ton: 'alarm' }
  if (d.acil) return { cumle: `${d.acil} kol acil durdurmada.`, ton: 'alarm' }
  if (d.fren) return { cumle: `${d.fren} kol frende, diğerleri normal.`, ton: 'dikkat' }
  return { cumle: 'Hepsi normal.', ton: 'sakin' }
}

/** Faz 14 paper süresi (4 hafta × 7 gün) nokta matrisi: geçen günler dolu, bugün çerçeveli, kalanlar sönük. */
function Cetvel({ p }: { p: Pano }) {
  const t = p.turnuva
  if (!t.bas_ms || !t.bit_ms)
    return <p className="text-govde-sm text-ikincil">Çalışan kol yok. Paper düğümü bir kol açınca cetvel burada görünür.</p>
  const hafta = Math.ceil(t.toplam_gun / 7)
  const buHafta = Math.min(hafta, Math.floor((t.gun - 1) / 7) + 1)
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="etiket text-ikincil">Nasdaq paper</h2>
        <p className="etiket text-ucuncul">
          hafta {buHafta}/{hafta}
        </p>
      </div>
      <p className="veri mt-4 text-veri-lg leading-none">
        <span className="text-birincil">{t.gun}</span>
        <span className="text-ucuncul"> / {t.toplam_gun} gün</span>
      </p>
      <div
        role="img"
        aria-label={`Paper süresinin ${t.toplam_gun} gününden ${t.gun}. gün`}
        className="mt-6 grid grid-flow-col gap-[7px]"
        style={{ gridTemplateRows: 'repeat(7, minmax(0, 1fr))', gridTemplateColumns: `repeat(${hafta}, minmax(0, 1fr))`, maxWidth: hafta * 25 }}
      >
        {Array.from({ length: hafta * 7 }, (_, i) => {
          const g = i + 1
          const gecti = g < t.gun
          const bugun = g === t.gun
          return (
            <span
              key={i}
              className="aspect-square rounded-full"
              style={
                bugun
                  ? { background: 'var(--color-ekran)', outline: '1px solid var(--color-ekran)', outlineOffset: 2 }
                  : { background: gecti ? 'rgb(255 255 255 / 0.6)' : 'var(--color-cizgi-belirgin)' }
              }
            />
          )
        })}
      </div>
      <div className="etiket mt-4 flex justify-between gap-4 text-ucuncul" style={{ maxWidth: Math.max(140, hafta * 25) }}>
        <span>{gunTR(t.bas_ms)}</span>
        <span>{gunTR(t.bit_ms)}</span>
      </div>
    </div>
  )
}

export function Kahraman({ p }: { p: Pano }) {
  const d = p.durum
  const { cumle, ton } = durum(p)
  const heroRenk = ton === 'alarm' ? 'text-kirmizi' : 'text-ekran'
  const cumleRenk = ton === 'alarm' ? 'text-kirmizi-metin' : ton === 'dikkat' ? 'text-amber' : 'text-birincil'
  const sayaclar: [string, number, string][] = [
    ['Karar', d.karar_24s, 'text-birincil'],
    ['Dolum', d.islem_24s, 'text-birincil'],
    ['Jev vetosu', d.veto_24s, d.veto_24s ? 'text-amber' : 'text-birincil'],
    ['Risk reddi', d.ret_24s, d.ret_24s ? 'text-kirmizi-metin' : 'text-birincil'],
  ]
  return (
    <section aria-labelledby="durum-baslik" className="grid gap-12 md:grid-cols-12 md:gap-8">
      <div className="md:col-span-7 lg:col-span-8">
        <p className="etiket text-ikincil">{d.son_karar_ms ? <>Son karar · {ikiSaat(d.son_karar_ms)}</> : 'Henüz karar yok'}</p>
        <div className="mt-6 flex flex-wrap items-end gap-x-6 gap-y-4">
          <p
            aria-hidden
            className={`font-dot text-[104px] leading-[0.8] font-bold tracking-[-0.02em] [font-variation-settings:'ROND'_100] sm:text-[148px] lg:text-[184px] ${heroRenk}`}
          >
            {d.bayat ? '--' : String(d.kol).padStart(2, '0')}
          </p>
          <div className="pb-2">
            <p className="etiket text-ikincil">
              kol çalışıyor
              {d.durdurulan > 0 && <span className="text-ucuncul"> · {d.durdurulan} durduruldu</span>}
            </p>
            <h1 id="durum-baslik" aria-live="polite" className={`mt-2 text-baslik leading-tight text-balance ${cumleRenk}`}>
              <span className="sr-only">{d.kol} kol çalışıyor. </span>
              {cumle}
            </h1>
          </div>
        </div>
        <dl className="mt-12 grid max-w-[560px] grid-cols-2 gap-x-8 gap-y-6 sm:grid-cols-4">
          {sayaclar.map(([ad, n, renk]) => (
            <div key={ad}>
              <dt className="etiket text-ikincil">{ad}</dt>
              <dd className={`veri mt-2 text-veri-lg leading-none ${renk}`}>{sayi(n)}</dd>
            </div>
          ))}
        </dl>
        <p className="etiket mt-3 text-ucuncul">son 24 saat · her emir risk motorundan geçti</p>
      </div>
      <div className="md:col-span-5 md:border-l md:border-cizgi md:pl-8 lg:col-span-4">
        <Cetvel p={p} />
      </div>
    </section>
  )
}
