import { ShieldAlert } from 'lucide-react'

import { enstrumanAdi, gorece, oran, sayi, tarihSaatTR } from '@/lib/bicim'
import type { Pano } from '@/lib/tip'

const ROL: Record<string, string> = {
  A1_binance: 'Binance duyuruları',
  A2_kap: 'KAP bildirimleri',
  manuel: 'Elle',
}
const TUR: Record<string, string> = { veto: 'veto', uyari: 'uyarı', kurumsal: 'kurumsal işlem', kaldir: 'kaldırma' }

export function Jev({ p }: { p: Pano }) {
  const o = p.olaylar
  const y = o.yargi_24s
  const roller = [...new Set(o.sayim_7g.map((s) => s.rol))].sort()
  return (
    <div className="panel flex flex-col p-panel md:p-6">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h3 className="etiket-ust text-kursun">Jev ve vetolar</h3>
        <p className="text-body-sm text-kursun">yalnız riski azaltabilir</p>
      </div>

      <div
        className={`mt-4 flex items-start gap-3 rounded-control border p-4 ${o.aktif_veto.length ? 'border-sodyum/50 bg-sodyum-koyu/60' : 'border-cizgi bg-yuzey-ust/40'}`}
      >
        <ShieldAlert className={`mt-0.5 size-4 shrink-0 ${o.aktif_veto.length ? 'text-sodyum' : 'text-kursun'}`} aria-hidden />
        {o.aktif_veto.length ? (
          <div>
            <p className="text-sodyum">
              {o.aktif_veto.map((v) => enstrumanAdi(v.enstruman)).join(', ')} üzerinde etkin veto var.
            </p>
            <p className="mt-1 text-body-sm text-pretty text-kursun">{o.aktif_veto[0].neden}</p>
          </div>
        ) : (
          <p className="text-kursun">Paper enstrümanlarında (BTC, ETH) etkin veto yok.</p>
        )}
      </div>

      <dl className="mt-5 grid grid-cols-3 gap-4 text-body-sm">
        <div>
          <dt className="text-kursun">Yargı · 24 sa</dt>
          <dd className="sayi mt-0.5 text-data-lg leading-none text-sis">{sayi(y.adet)}</dd>
        </div>
        <div>
          <dt className="text-kursun">Medyan gecikme</dt>
          <dd className="sayi mt-0.5 text-data-lg leading-none text-sis">
            {y.gecikme_medyan_ms == null ? '—' : `${sayi(y.gecikme_medyan_ms / 1000, 1)} sn`}
          </dd>
        </div>
        <div>
          <dt className="text-kursun">NVIDIA'ya çıkan</dt>
          <dd className="sayi mt-0.5 text-data-lg leading-none text-sis">{y.adet ? oran(y.nvidia / y.adet, 1) : '—'}</dd>
        </div>
      </dl>
      {y.hata > 0 && <p className="mt-2 text-body-sm text-kayip">{y.hata} yargı hatayla döndü.</p>}

      <table className="mt-5 w-full text-body-sm">
        <caption className="etiket-ust pb-2 text-left text-soluk">Son 7 gün</caption>
        <tbody>
          {roller.map((r) => (
            <tr key={r} className="border-t border-cizgi/60">
              <th scope="row" className="py-2 text-left font-normal text-kursun">{ROL[r] ?? r}</th>
              <td className="py-2 text-right text-kursun">
                {o.sayim_7g
                  .filter((s) => s.rol === r)
                  .map((s) => (
                    <span key={s.tur} className="ml-3 inline-block">
                      <span className={`sayi ${s.tur === 'veto' ? 'text-sodyum' : 'text-sis'}`}>{sayi(s.adet)}</span> {TUR[s.tur] ?? s.tur}
                    </span>
                  ))}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <h4 className="etiket-ust mt-6 text-soluk">Son vetolar ve uyarılar</h4>
      <ol className="mt-2 divide-y divide-cizgi/60">
        {o.son.slice(0, 6).map((v) => (
          <li key={v.id} className="py-3">
            <div className="flex items-baseline justify-between gap-3">
              <span className="flex items-baseline gap-2">
                <span className={`etiket-ust ${v.tur === 'veto' ? 'text-sodyum' : 'text-kursun'}`}>{TUR[v.tur] ?? v.tur}</span>
                <span className="sayi text-sis">{enstrumanAdi(v.enstruman)}</span>
              </span>
              <time className="sayi shrink-0 text-body-sm text-soluk" dateTime={new Date(v.zaman_ms).toISOString()} title={tarihSaatTR(v.zaman_ms)}>
                {gorece(v.zaman_ms, p.simdi_ms)}
              </time>
            </div>
            <p className="mt-1 line-clamp-2 text-body-sm text-pretty text-kursun">{v.neden}</p>
          </li>
        ))}
        {!o.son.length && <li className="py-3 text-kursun">Henüz veto ya da uyarı yok.</li>}
      </ol>
    </div>
  )
}
