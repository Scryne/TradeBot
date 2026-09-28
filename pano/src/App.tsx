import { useState } from 'react'

import { TooltipProvider } from '@/components/ui/tooltip'
import { ikiSaat } from '@/lib/bicim'
import { usePano, useSaglik } from '@/lib/veri'

import { Defter } from './components/Defter'
import { Jev } from './components/Jev'
import { Kahraman } from './components/Kahraman'
import { KararSeridi } from './components/KararSeridi'
import { KolCekmece } from './components/KolCekmece'
import { Kollar } from './components/Kollar'
import { Risk } from './components/Risk'
import { SaglikBolumu } from './components/SaglikBolumu'
import { UstCubuk } from './components/UstCubuk'

function Iskelet() {
  return (
    <div className="mx-auto flex max-w-[1320px] flex-col gap-6 px-gutter pt-8" aria-busy aria-label="Pano yükleniyor">
      <div className="h-[280px] rounded-panel bg-yuzey/70" />
      <div className="h-[260px] rounded-panel bg-yuzey/50" />
    </div>
  )
}

export default function App() {
  const pano = usePano()
  const saglik = useSaglik()
  const [secili, setSecili] = useState<string | null>(null)
  const p = pano.veri

  return (
    <TooltipProvider>
      <UstCubuk pano={p} saglik={saglik.veri} />
      {pano.hata && (
        <div role="alert" className="mx-auto mt-4 max-w-[1320px] px-gutter">
          <p className="rounded-control border border-kayip/50 bg-kayip/10 px-4 py-3 text-body-sm text-sis">
            Pano güncellenemedi: {pano.hata}.{' '}
            {p ? <>Ekrandaki veri {ikiSaat(p.simdi_ms)} anına ait.</> : null} Dakikada bir yeniden deneniyor; sürerse
            host'ta <span className="sayi">pano</span> servisinin loguna bak.
          </p>
        </div>
      )}
      <main className="flex flex-col gap-section pb-24" style={{ paddingBottom: 'max(6rem, env(safe-area-inset-bottom))' }}>
        {!p ? (
          <Iskelet />
        ) : (
          <>
            <div className="flex flex-col">
              <div className="mx-auto w-full max-w-[1320px] px-gutter pt-6 pb-8 md:pt-10">
                <Kahraman p={p} />
              </div>
              <KararSeridi p={p} onSec={setSecili} />
            </div>
            <Kollar p={p} onSec={setSecili} />
            <section aria-label="Risk ve Jev" className="mx-auto grid w-full max-w-[1320px] gap-4 px-gutter lg:grid-cols-12">
              <div className="lg:col-span-7">
                <h2 className="mb-5 font-display text-display-md font-bold tracking-display-md uppercase">Risk</h2>
                <Risk p={p} />
              </div>
              <div className="lg:col-span-5">
                <h2 className="mb-5 font-display text-display-md font-bold tracking-display-md uppercase">Jev</h2>
                <Jev p={p} />
              </div>
            </section>
            <Defter p={p} />
            <SaglikBolumu s={saglik.veri} simdi={p.simdi_ms} kod={p.kod_surumu} />
          </>
        )}
      </main>
      <KolCekmece kol={secili} ozet={p?.kollar.find((k) => k.kol === secili)} onKapat={() => setSecili(null)} />
    </TooltipProvider>
  )
}
