import { useState } from 'react'

import { TooltipProvider } from '@/components/ui/tooltip'
import { ikiSaat } from '@/lib/bicim'
import { usePano, useSaglik } from '@/lib/veri'

import { Defter, SaglikBolumu, UstCubuk } from './Alt'
import { KolCekmece } from './Cekmece'
import { Jev } from './Jev'
import { Kahraman } from './Kahraman'
import { Kilit } from './Kilit'
import { Kollar } from './Kollar'
import { Risk } from './Risk'
import { Serit } from './Serit'

const KAP = 'mx-auto w-full max-w-[1320px] px-gutter'

export default function App() {
  const pano = usePano()
  const saglik = useSaglik()
  const [secili, setSecili] = useState<string | null>(null)
  const p = pano.veri

  return (
    <TooltipProvider>
      <UstCubuk pano={p} saglik={saglik.veri} />
      {pano.hata && (
        <div role="alert" className={`${KAP} mt-6`}>
          <p className="border-l-2 border-kirmizi py-1 pl-4 text-govde-sm text-birincil">
            <span className="etiket text-kirmizi-metin">[hata]</span> Pano güncellenemedi: {pano.hata}.{' '}
            {p ? <>Ekrandaki veri {ikiSaat(p.simdi_ms)} anına ait.</> : null} Dakikada bir yeniden deneniyor; sürerse host'ta{' '}
            <span className="veri">pano</span> servisinin loguna bak.
          </p>
        </div>
      )}
      <main className="flex flex-col gap-bolum pt-12 md:pt-16" style={{ paddingBottom: 'max(6rem, env(safe-area-inset-bottom))' }}>
        {!p ? (
          <p className={`${KAP} etiket text-ikincil`} aria-busy>
            [yükleniyor]
          </p>
        ) : (
          <>
            <div className={`${KAP} belir`}>
              <Kahraman p={p} />
            </div>
            {p.kilit.kollar.length > 0 && (
              <div className={KAP}>
                <Kilit p={p} />
              </div>
            )}
            <div className={KAP}>
              <Serit p={p} onSec={setSecili} />
            </div>
            <div className={KAP}>
              <Kollar p={p} onSec={setSecili} />
            </div>
            <section aria-label="Risk ve Jev" className={`${KAP} grid gap-16 lg:grid-cols-12 lg:gap-12`}>
              <div className="lg:col-span-7">
                <h2 className="text-baslik leading-tight text-ekran">Risk</h2>
                <div className="mt-6">
                  <Risk p={p} />
                </div>
              </div>
              <div className="lg:col-span-5">
                <h2 className="text-baslik leading-tight text-ekran">Jev</h2>
                <div className="mt-6">
                  <Jev p={p} />
                </div>
              </div>
            </section>
            <div className={KAP}>
              <Defter p={p} />
            </div>
            <div className={KAP}>
              <SaglikBolumu s={saglik.veri} simdi={p.simdi_ms} kod={p.kod_surumu} />
            </div>
          </>
        )}
      </main>
      <KolCekmece kol={secili} ozet={p?.kollar.find((k) => k.kol === secili)} onKapat={() => setSecili(null)} />
    </TooltipProvider>
  )
}
