import { CircleAlert, CircleCheck, CircleX } from 'lucide-react'

import { ikiSaat } from '@/lib/bicim'
import type { Pano, Saglik } from '@/lib/tip'

function saglikOzeti(s: Saglik | null) {
  if (!s?.hazir) return { durum: 'bekliyor' as const, metin: 'Sağlık ölçülüyor' }
  const hata = s.kontroller.filter((k) => k.durum === 'HATA').length
  const uyari = s.kontroller.filter((k) => k.durum === 'UYARI').length
  const tamam = s.kontroller.length - hata - uyari
  if (hata) return { durum: 'hata' as const, metin: `${hata} kontrol hatalı` }
  if (uyari) return { durum: 'uyari' as const, metin: `${uyari} uyarı · ${tamam}/${s.kontroller.length} sağlam` }
  return { durum: 'tamam' as const, metin: `${tamam}/${s.kontroller.length} sağlam` }
}

export function UstCubuk({ pano, saglik }: { pano: Pano | null; saglik: Saglik | null }) {
  const s = saglikOzeti(saglik)
  const Ikon = s.durum === 'hata' ? CircleX : s.durum === 'uyari' ? CircleAlert : CircleCheck
  const renk = s.durum === 'hata' ? 'text-kayip' : s.durum === 'uyari' ? 'text-sodyum' : 'text-kursun'
  return (
    <header
      className="cam sticky top-0 border-x-0 border-t-0"
      style={{ zIndex: 'var(--z-bar)', paddingTop: 'env(safe-area-inset-top)' }}
    >
      <div className="mx-auto flex h-14 max-w-[1320px] items-center gap-4 px-gutter">
        <a href="#" className="flex items-baseline gap-2 rounded-control">
          <span className="font-display text-[26px] leading-none font-extrabold tracking-display-md uppercase">TradeBot</span>
          <span className="etiket-ust hidden text-soluk sm:inline">paper</span>
        </a>
        <div className="ml-auto flex items-center gap-4 text-body-sm">
          <a href="#saglik" className={`flex items-center gap-1.5 rounded-control ${renk}`}>
            <Ikon className="size-4" aria-hidden />
            <span>{s.metin}</span>
          </a>
          {pano && (
            <span className="sayi hidden text-kursun md:inline" title="Verinin alındığı an">
              {ikiSaat(pano.simdi_ms)}
            </span>
          )}
        </div>
      </div>
    </header>
  )
}
