import { CircleAlert, CircleCheck, CircleX } from 'lucide-react'

import { gorece, ikiSaat } from '@/lib/bicim'
import type { Saglik } from '@/lib/tip'

const AD: Record<string, string> = {
  dns: 'DNS',
  saat: 'Saat',
  veritabani: 'Veritabanı',
  disk: 'Disk',
  sirlar: 'Sırlar',
  paper: 'Paper kalp atışı',
  gece_isi: 'Gece işi',
  yedek: 'Yedek',
  mt5: 'MT5 köprüleri',
  saglik: 'Sağlık bekçisi',
}

export function SaglikBolumu({ s, simdi, kod }: { s: Saglik | null; simdi: number; kod?: string }) {
  return (
    <section id="saglik" aria-labelledby="saglik-baslik" className="mx-auto w-full max-w-[1320px] scroll-mt-20 px-gutter">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 id="saglik-baslik" className="font-display text-display-md font-bold tracking-display-md uppercase">
          Sağlık
        </h2>
        <p className="sayi text-body-sm text-kursun">
          {s?.zaman_ms ? <>ölçüm {gorece(s.zaman_ms, simdi)} · {ikiSaat(s.zaman_ms)}</> : 'ölçülüyor'}
          {kod ? <> · kod {kod}</> : null}
        </p>
      </div>
      {!s?.hazir ? (
        <ul className="mt-5 grid gap-px overflow-hidden rounded-panel border border-cizgi bg-cizgi sm:grid-cols-2 lg:grid-cols-3" aria-busy>
          {Array.from({ length: 9 }, (_, i) => (
            <li key={i} className="h-[76px] bg-yuzey" />
          ))}
        </ul>
      ) : (
        <ul className="mt-5 grid gap-px overflow-hidden rounded-panel border border-cizgi bg-cizgi sm:grid-cols-2 lg:grid-cols-3">
          {s.kontroller.map((k) => {
            const Ikon = k.durum === 'HATA' ? CircleX : k.durum === 'UYARI' ? CircleAlert : CircleCheck
            const renk = k.durum === 'HATA' ? 'text-kayip' : k.durum === 'UYARI' ? 'text-sodyum' : 'text-kursun'
            return (
              <li key={k.ad} className="flex gap-3 bg-yuzey p-4">
                <Ikon className={`mt-0.5 size-4 shrink-0 ${renk}`} aria-hidden />
                <div className="min-w-0">
                  <p className="flex items-baseline gap-2">
                    <span className="text-sis">{AD[k.ad] ?? k.ad}</span>
                    <span className={`etiket-ust ${renk}`}>
                      {k.durum === 'OK' ? 'sağlam' : k.durum === 'UYARI' ? 'uyarı' : 'hata'}
                    </span>
                  </p>
                  <p className="mt-1 text-body-sm break-words text-pretty text-kursun">{k.ayrinti}</p>
                </div>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}
