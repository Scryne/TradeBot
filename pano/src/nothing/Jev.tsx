import { enstrumanAdi, gorece, oran, sayi, tarihSaatTR } from '@/lib/bicim'
import type { Pano } from '@/lib/tip'

const ROL: Record<string, string> = { A1_binance: 'Binance duyuruları', A2_kap: 'KAP bildirimleri', manuel: 'Elle' }
const TUR: Record<string, string> = { veto: 'veto', uyari: 'uyarı', kurumsal: 'kurumsal işlem', kaldir: 'kaldırma' }

export function Jev({ p }: { p: Pano }) {
  const o = p.olaylar
  const y = o.yargi_24s
  const roller = [...new Set(o.sayim_7g.map((s) => s.rol))].sort()
  const veto = o.aktif_veto.length > 0
  return (
    <div>
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h3 className="etiket text-ikincil">Jev ve vetolar</h3>
        <p className="etiket text-ucuncul">yalnız riski azaltabilir</p>
      </div>

      <div className={`mt-5 border-l-2 py-1 pl-4 ${veto ? 'border-amber' : 'border-cizgi-belirgin'}`}>
        {veto ? (
          <>
            <p className="etiket text-amber">[etkin veto: {o.aktif_veto.map((v) => enstrumanAdi(v.enstruman)).join(', ')}]</p>
            <p className="mt-2 text-govde-sm text-pretty text-ikincil">{o.aktif_veto[0].neden}</p>
          </>
        ) : (
          <p className="etiket text-ikincil">[etkin veto yok] <span className="text-ucuncul">· BTC, ETH</span></p>
        )}
      </div>

      <dl className="mt-8 grid grid-cols-3 gap-4">
        {[
          ['Yargı · 24 sa', sayi(y.adet)],
          ['Medyan gecikme', y.gecikme_medyan_ms == null ? '—' : `${sayi(y.gecikme_medyan_ms / 1000, 1)} sn`],
          ["NVIDIA'ya çıkan", y.adet ? oran(y.nvidia / y.adet, 1) : '—'],
        ].map(([a, v]) => (
          <div key={a}>
            <dt className="etiket text-ikincil">{a}</dt>
            <dd className="veri mt-2 text-veri-lg leading-none text-birincil">{v}</dd>
          </div>
        ))}
      </dl>
      {y.hata > 0 && <p className="etiket mt-3 text-kirmizi-metin">[hata] {y.hata} yargı hatayla döndü</p>}

      <table className="mt-8 w-full text-govde-sm">
        <caption className="etiket pb-2 text-left text-ucuncul">Son 7 gün</caption>
        <tbody>
          {roller.map((r) => (
            <tr key={r} className="border-t border-cizgi">
              <th scope="row" className="py-2.5 text-left font-normal text-ikincil">{ROL[r] ?? r}</th>
              <td className="py-2.5 text-right text-ikincil">
                {o.sayim_7g
                  .filter((s) => s.rol === r)
                  .map((s) => (
                    <span key={s.tur} className="ml-4 inline-block">
                      <span className={`veri ${s.tur === 'veto' ? 'text-amber' : 'text-birincil'}`}>{sayi(s.adet)}</span> {TUR[s.tur] ?? s.tur}
                    </span>
                  ))}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <h4 className="etiket mt-8 text-ucuncul">Son vetolar ve uyarılar</h4>
      <ol className="mt-2">
        {o.son.slice(0, 5).map((v) => (
          <li key={v.id} className="border-t border-cizgi py-3">
            <div className="flex items-baseline justify-between gap-3">
              <span className="flex items-baseline gap-3">
                <span className={`etiket ${v.tur === 'veto' ? 'text-amber' : 'text-ikincil'}`}>[{TUR[v.tur] ?? v.tur}]</span>
                <span className="veri text-govde-sm text-birincil">{enstrumanAdi(v.enstruman)}</span>
              </span>
              <time className="veri shrink-0 text-govde-sm text-ucuncul" dateTime={new Date(v.zaman_ms).toISOString()} title={tarihSaatTR(v.zaman_ms)}>
                {gorece(v.zaman_ms, p.simdi_ms)}
              </time>
            </div>
            <p className="mt-1 line-clamp-2 text-govde-sm text-pretty text-ikincil">{v.neden}</p>
          </li>
        ))}
        {!o.son.length && <li className="border-t border-cizgi py-3 text-govde-sm text-ikincil">Henüz veto ya da uyarı yok.</li>}
      </ol>
    </div>
  )
}
