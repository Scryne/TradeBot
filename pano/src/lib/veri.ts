import { useCallback, useEffect, useRef, useState } from 'react'

import type { KolAyrinti, Pano, Saglik } from './tip'

const YENILEME_MS = 60_000

async function al<T>(yol: string, sinyal?: AbortSignal): Promise<T> {
  let r: Response
  try {
    r = await fetch(yol, { signal: sinyal, headers: { Accept: 'application/json' } })
  } catch (e) {
    if (sinyal?.aborted) throw e
    throw new Error('pano sunucusuna ulaşılamıyor (host kapalı ya da Tailscale bağlı değil)')
  }
  if (r.status === 404) throw new Error('istenen kayıt bulunamadı')
  if (!r.ok) throw new Error(`pano sunucusu hata verdi (${r.status})`)
  return r.json() as Promise<T>
}

interface Durum<T> {
  veri: T | null
  hata: string | null
  zaman: number | null
}

/** Dakikada bir yeniler; sekme gizliyken beklemez, görünür olunca hemen yeniler. Hata eski veriyi silmez. */
export function useYoklama<T>(yol: string | null, aralik = YENILEME_MS): Durum<T> & { yenile: () => void } {
  const [d, setD] = useState<Durum<T>>({ veri: null, hata: null, zaman: null })
  const sayac = useRef(0)

  const yenile = useCallback(() => {
    if (!yol) return
    const no = ++sayac.current
    const iptal = new AbortController()
    al<T>(yol, iptal.signal)
      .then((veri) => no === sayac.current && setD({ veri, hata: null, zaman: Date.now() }))
      .catch((e: unknown) => {
        if (no !== sayac.current || iptal.signal.aborted) return
        setD((o) => ({ ...o, hata: e instanceof Error ? e.message : String(e) }))
      })
  }, [yol])

  useEffect(() => {
    if (!yol) return
    yenile()
    const t = window.setInterval(() => document.visibilityState === 'visible' && yenile(), aralik)
    const gorunur = () => document.visibilityState === 'visible' && yenile()
    document.addEventListener('visibilitychange', gorunur)
    return () => {
      window.clearInterval(t)
      document.removeEventListener('visibilitychange', gorunur)
    }
  }, [yol, aralik, yenile])

  return { ...d, yenile }
}

export const usePano = () => useYoklama<Pano>('/api/pano')
export const useSaglik = () => useYoklama<Saglik>('/api/saglik', 30_000)
export const useKol = (kol: string | null) =>
  useYoklama<KolAyrinti>(kol ? `/api/kol/${encodeURIComponent(kol)}` : null)
