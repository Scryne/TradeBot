import { gorece, gunTR, ikiSaat } from '@/lib/bicim'
import type { Pano } from '@/lib/tip'

function cumle(p: Pano): { ana: string; ton: 'sakin' | 'dikkat' | 'alarm' } {
  const d = p.durum
  if (d.bayat) {
    const ne = d.son_isaret_ms ? gorece(d.son_isaret_ms, p.simdi_ms) : 'hiç'
    return { ana: `Paper verisi gelmiyor. Son işaret ${ne}.`, ton: 'alarm' }
  }
  if (d.acil) return { ana: `${d.acil} kol acil durdurmada.`, ton: 'alarm' }
  if (d.fren) return { ana: `${d.kol} kol çalışıyor, ${d.fren} kol frende.`, ton: 'dikkat' }
  return { ana: `${d.kol} kol çalışıyor, hepsi normal.`, ton: 'sakin' }
}

/** 12 haftalık turnuva cetveli: haftalar gerçek bir sıra olduğu için numaralı (DESIGN.md › Layout). */
function Cetvel({ p }: { p: Pano }) {
  const t = p.turnuva
  if (!t.bas_ms || !t.bit_ms) return <p className="text-kursun">Turnuva başlamadı. Paper düğümü ilk kolu açınca cetvel burada görünür.</p>
  const hafta = Math.ceil(t.toplam_gun / 7)
  const oran = Math.min(1, t.gun / t.toplam_gun)
  return (
    <div className="flex h-full flex-col justify-between gap-4">
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="etiket-ust text-kursun">Paper turnuvası</h2>
        <p className="sayi text-body-sm text-kursun">
          hafta {Math.min(hafta, Math.floor((t.gun - 1) / 7) + 1)}/{hafta}
        </p>
      </div>
      <p className="sayi text-data-lg leading-none">
        <span className="text-sis">gün {t.gun}</span>
        <span className="text-soluk"> / {t.toplam_gun}</span>
      </p>
      <div
        role="img"
        aria-label={`Turnuvanın ${t.toplam_gun} gününden ${t.gun}. gün`}
        className="grid gap-[3px]"
        style={{ gridTemplateColumns: `repeat(${hafta}, minmax(0, 1fr))` }}
      >
        {Array.from({ length: hafta }, (_, i) => {
          const dolu = Math.max(0, Math.min(1, oran * hafta - i))
          return (
            <div key={i} className="relative h-7 overflow-hidden rounded-[3px] bg-yuzey-ust">
              <div className="absolute inset-y-0 left-0 bg-sis/70" style={{ width: `${dolu * 100}%` }} />
              {dolu > 0 && dolu < 1 && (
                <div className="absolute inset-y-0 w-0.5 bg-sodyum" style={{ left: `calc(${dolu * 100}% - 1px)` }} />
              )}
            </div>
          )
        })}
      </div>
      <div className="flex justify-between text-body-sm text-kursun">
        <span>{gunTR(t.bas_ms)}</span>
        <span>{gunTR(t.bit_ms)}</span>
      </div>
    </div>
  )
}

export function Kahraman({ p }: { p: Pano }) {
  const c = cumle(p)
  const d = p.durum
  const renk = c.ton === 'alarm' ? 'text-kayip' : c.ton === 'dikkat' ? 'text-sodyum' : 'text-sis'
  return (
    <section aria-labelledby="durum-baslik" className="cam grid gap-8 rounded-panel p-panel md:grid-cols-12 md:gap-0 md:p-8">
      <div className="md:col-span-8 md:pr-8">
        <p className="etiket-ust text-kursun">
          {d.son_karar_ms ? <>Son karar {ikiSaat(d.son_karar_ms)}</> : 'Henüz karar yok'}
        </p>
        <h1
          id="durum-baslik"
          aria-live="polite"
          className={`mt-4 max-w-[18ch] font-display text-[44px] leading-[0.95] font-extrabold tracking-display-xl text-balance sm:text-display-xl lg:text-[88px] ${renk}`}
        >
          {c.ana}
        </h1>
        <p className="mt-6 max-w-[60ch] text-pretty text-kursun">
          Son 24 saatte <span className="sayi text-sis">{d.karar_24s}</span> karar,{' '}
          <span className="sayi text-sis">{d.islem_24s}</span> dolum,{' '}
          <span className={`sayi ${d.veto_24s ? 'text-sodyum' : 'text-sis'}`}>{d.veto_24s}</span> Jev vetosu
          {d.ret_24s > 0 && (
            <>
              , <span className="sayi text-kayip">{d.ret_24s}</span> risk reddi
            </>
          )}
          . Her emir risk motorundan geçti.
        </p>
      </div>
      <div className="border-cizgi md:col-span-4 md:border-l md:pl-8">
        <Cetvel p={p} />
      </div>
    </section>
  )
}
