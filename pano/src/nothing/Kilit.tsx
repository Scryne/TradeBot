import { gunTR, ikiSaat, kalan, oran, para, paraIsaretli, sayi, yuzde } from '@/lib/bicim'
import type { Kilit as KilitVeri, KilitKol, KilitOlay, Pano } from '@/lib/tip'

import { BolumBasi, DurumEtiketi, isaretRenk, Segmentler, StatSatiri } from './Ortak'

const GUN = 86_400_000

const NEDEN: Record<string, string> = {
  cikis: 'açılım günü',
  durdur: 'elle durduruldu',
  islem_gormuyor: 'perp kalktı',
  teslim_planli: 'delist planı',
  acil_durdurma: 'acil durdurma',
  zarar_kes: 'zarar kes',
}
const RED: Record<string, string> = { islem_gormuyor: 'perp yok', tavan: 'tavan dolu', yeni_risk_yok: 'yeni risk kapalı' }
const KATEGORI: Record<string, string> = { insiders: 'içeriden', privateSale: 'özel satış' }

const nedenAdi = (n: string | null) => (n ? (NEDEN[n] ?? n) : '—')
const kategoriAdi = (k: string) => k.split('+').map((x) => KATEGORI[x] ?? x).join(' + ')
const kolEtiketi = (k: KilitKol) => (k.gercek ? `Binance ${k.ortam === 'ana' ? 'gerçek' : 'Demo'}` : 'Paper')
const tutar = (k: KilitKol, x: number) => para(x, k.baslangic_ozkaynak < 10_000 ? 2 : 0)
const isaretliTutar = (k: KilitKol, x: number | null) => paraIsaretli(x, k.baslangic_ozkaynak < 10_000 ? 2 : 0)

/** İki kol, her biri kendi başlangıcına göre getiri: paper düz (ekran), Demo kesikli (ikincil). */
function IkiCizgi({ kollar }: { kollar: KilitKol[] }) {
  const G = 600
  const Y_ = 96
  const seriler = kollar.map((k) => k.seri.map(([t, v]) => [t, v / k.baslangic_ozkaynak - 1] as const))
  const tum = seriler.flat()
  if (!seriler[0] || seriler[0].length < 2)
    return <p className="text-govde-sm text-ikincil">Çizgi için en az iki saatlik işaret gerekiyor.</p>
  const t0 = Math.min(...tum.map((x) => x[0]))
  const t1 = Math.max(...tum.map((x) => x[0]))
  const lo = Math.min(0, ...tum.map((x) => x[1]))
  const hi = Math.max(0, ...tum.map((x) => x[1]))
  const pay = (hi - lo) * 0.12 || 0.002
  const X = (t: number) => ((t - t0) / (t1 - t0 || 1)) * (G - 8) + 2
  const Y = (v: number) => Y_ - 4 - ((v - lo + pay) / (hi - lo + 2 * pay)) * (Y_ - 8)
  const yol = (s: readonly (readonly [number, number])[]) => s.map(([t, v], i) => `${i ? 'L' : 'M'}${X(t).toFixed(1)},${Y(v).toFixed(1)}`).join('')
  const son = seriler[0][seriler[0].length - 1]
  return (
    <figure>
      <svg
        viewBox={`0 0 ${G} ${Y_}`}
        preserveAspectRatio="none"
        className="block h-24 w-full overflow-visible"
        role="img"
        aria-label={kollar.map((k) => `${kolEtiketi(k)} ${yuzde(k.toplam)}`).join(', ')}
      >
        <line x1={0} x2={G} y1={Y(0)} y2={Y(0)} stroke="var(--color-cizgi-belirgin)" strokeDasharray="1 3" vectorEffect="non-scaling-stroke" />
        {seriler.slice(1).map((s, i) =>
          s.length > 1 ? (
            <path key={i} d={yol(s)} fill="none" stroke="var(--color-ikincil)" strokeWidth={1} strokeDasharray="2 2" vectorEffect="non-scaling-stroke" />
          ) : null,
        )}
        <path d={yol(seriler[0])} fill="none" stroke="var(--color-ekran)" strokeWidth={1.5} strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
        <rect x={X(son[0]) - 2} y={Y(son[1]) - 2} width={4} height={4} fill="var(--color-ekran)" />
      </svg>
      <figcaption className="etiket mt-3 flex flex-wrap justify-between gap-x-6 gap-y-2 text-ucuncul">
        <span>{gunTR(t0)}</span>
        <span className="flex gap-5">
          {kollar.map((k, i) => (
            <span key={k.kol} className="flex items-center gap-2 text-ikincil">
              <svg width="18" height="4" aria-hidden>
                <line
                  x1="0"
                  x2="18"
                  y1="2"
                  y2="2"
                  stroke={i === 0 ? 'var(--color-ekran)' : 'var(--color-ikincil)'}
                  strokeWidth={i === 0 ? 1.5 : 1}
                  strokeDasharray={i === 0 ? undefined : '2 2'}
                />
              </svg>
              {kolEtiketi(k)}
            </span>
          ))}
        </span>
        <span>{gunTR(t1)}</span>
      </figcaption>
    </figure>
  )
}

function KolOzeti({ k }: { k: KilitKol }) {
  return (
    <div>
      <p className="etiket flex items-baseline justify-between gap-3 text-ikincil">
        <span>
          {kolEtiketi(k)} · {tutar(k, k.baslangic_ozkaynak)}
        </span>
        <DurumEtiketi d={k.durum} />
      </p>
      <p className={`veri mt-4 text-veri-lg leading-none ${isaretRenk(k.toplam)}`}>{yuzde(k.toplam)}</p>
      <dl className="mt-5">
        <StatSatiri ad="Özkaynak" deger={tutar(k, k.ozkaynak)} />
        <StatSatiri ad="Funding" deger={isaretliTutar(k, k.fonlama)} renk={isaretRenk(k.fonlama)} />
        <StatSatiri ad="En kötü düşüş" deger={yuzde(k.en_kotu_dusus, 1)} renk="text-ikincil" />
        <StatSatiri ad="Açık olay" deger={sayi(k.acik.length)} />
      </dl>
    </div>
  )
}

/** Gerçek para kapısı: 26 hafta = 26 segment; PSR ve bugünkü hızla gereken hafta. */
function Kapi({ k, v }: { k: KilitKol; v: KilitVeri }) {
  const n = v.kapi.asgari_hafta
  const h = Math.min(n, k.kapi.hafta)
  return (
    <div>
      <h3 className="etiket text-ikincil">Gerçek para kapısı</h3>
      <p className="veri mt-4 text-veri-lg leading-none">
        <span className="text-birincil">{h}</span>
        <span className="text-ucuncul"> / {n} hafta</span>
      </p>
      <Segmentler
        hucreler={Array.from({ length: n }, (_, i) => (i < h ? 'var(--color-ekran)' : null))}
        yuk={10}
        etiket={`Paper kaydı ${n} haftanın ${h}. haftasında`}
        className="mt-6"
      />
      <dl className="mt-6">
        <StatSatiri ad={`PSR (eşik ${sayi(v.kapi.psr, 2)})`} deger={k.kapi.psr == null ? 'henüz yok' : sayi(k.kapi.psr, 2)} />
        <StatSatiri
          ad="Bu hızla gereken"
          deger={k.kapi.gerekli_hafta ? `${k.kapi.gerekli_hafta} hafta` : 'getiri artıya dönmeli'}
          renk={k.kapi.gerekli_hafta ? 'text-birincil' : 'text-ikincil'}
        />
      </dl>
      <p className="mt-4 max-w-[44ch] text-govde-sm text-pretty text-ikincil">
        Gerçek paraya geçiş üç şarta bağlı: {n} haftalık paper kaydı, PSR'ın {sayi(v.kapi.psr, 2)}'i geçmesi ve senin açık onayın.
        PSR, ilk tam haftadan sonra hesaplanır.
      </p>
    </div>
  )
}

/** Girişten açılıma kadar geçen günler: her gün bir segment. */
function Zaman({ e, simdi, gunSayisi }: { e: KilitOlay; simdi: number; gunSayisi: number }) {
  const gecen = e.giris_ms == null ? 0 : Math.min(gunSayisi, Math.max(0, Math.floor((simdi - e.giris_ms) / GUN) + 1))
  return (
    <Segmentler
      hucreler={Array.from({ length: gunSayisi }, (_, i) => (i < gecen ? 'var(--color-ekran)' : null))}
      yuk={6}
      etiket={`Girişten açılıma ${gunSayisi} günün ${gecen}. günü`}
      className="w-[84px]"
    />
  )
}

function AcikOlaylar({ k, demo, v, simdi }: { k: KilitKol; demo?: KilitKol; v: KilitVeri; simdi: number }) {
  const gunSayisi = Math.max(1, -(v.kural.giris ?? -7))
  const demoAcik = new Set(demo?.acik.map((e) => `${e.sembol}:${e.olay_ms}`))
  const siradaki = v.yaklasan?.olaylar.find((e) => e.durum === 'bekliyor')
  return (
    <div>
      <h3 className="etiket text-ikincil">Açık olaylar · paper</h3>
      {k.acik.length === 0 ? (
        <p className="mt-4 text-govde-sm text-ikincil">
          Açık olay yok.{siradaki ? ` Sıradaki giriş ${siradaki.sembol}, ${gunTR(siradaki.giris_ms)}.` : ''}
        </p>
      ) : (
        <ul className="mt-4">
          {k.acik.map((e) => {
            const gun = Math.ceil((e.olay_ms - simdi) / GUN)
            return (
              <li
                key={`${e.sembol}:${e.olay_ms}`}
                className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-6 gap-y-2 border-t border-cizgi py-4 last:border-b sm:grid-cols-[96px_96px_minmax(0,1fr)_auto]"
              >
                <p className="text-birincil">{e.sembol}</p>
                <p className={`veri text-right text-govde sm:order-last ${isaretRenk(e.sonuc ?? 0)}`}>
                  {isaretliTutar(k, e.sonuc)}
                  <span className="etiket ml-2 text-ucuncul">{yuzde(e.sonuc_oran, 1)}</span>
                </p>
                <div className="col-span-2 flex flex-wrap items-center gap-x-4 gap-y-2 sm:contents">
                  <Zaman e={e} simdi={simdi} gunSayisi={gunSayisi} />
                  <p className="etiket text-ikincil">
                    açılım {gunTR(e.olay_ms)} · {gun <= 0 ? 'bugün' : `${gun} gün`} · {tutar(k, e.nominal)} kısa
                    {demo && !demoAcik.has(`${e.sembol}:${e.olay_ms}`) && <span className="text-birincil"> · Demo'da yok</span>}
                  </p>
                </div>
              </li>
            )
          })}
        </ul>
      )}
      <p className="etiket mt-3 text-ucuncul">sonuç funding hariç, BTC koruması dahil, son saatlik işaretle</p>
    </div>
  )
}

function DurumYaklasan({ e }: { e: NonNullable<KilitVeri['yaklasan']>['olaylar'][number] }) {
  switch (e.durum) {
    case 'acik':
      return <span className="etiket text-ekran">[açık]</span>
    case 'bekliyor':
      return <span className="etiket text-birincil">[giriş {gunTR(e.giris_ms)}]</span>
    case 'kapandi':
      return <span className="etiket text-ikincil">[kapandı · {nedenAdi(e.neden)}]</span>
    case 'kacti':
      return <span className="etiket text-ucuncul">[girilmedi]</span>
    default:
      return <span className="etiket text-ucuncul">[perp yok]</span>
  }
}

/** 31 gün = 31 nokta (bugün çerçeveli). Dolu: girilebilir açılım; sönük: yalnız perp'siz açılım. */
function GunSeridi({ y, simdi }: { y: NonNullable<KilitVeri['yaklasan']>; simdi: number }) {
  const bugun = Math.floor(simdi / GUN) * GUN
  const gunler = Array.from({ length: 31 }, (_, i) => bugun + i * GUN)
  const gun = new Map<number, { girilir: number; diger: number }>()
  for (const e of y.olaylar) {
    const g = gun.get(e.olay_ms) ?? { girilir: 0, diger: 0 }
    if (e.perp) g.girilir++
    else g.diger++
    gun.set(e.olay_ms, g)
  }
  return (
    <div>
      <div role="img" aria-label={`Önümüzdeki 30 günde ${y.olaylar.filter((e) => e.perp).length} girilebilir açılım`} className="grid grid-cols-[repeat(31,minmax(0,1fr))] gap-[4px]">
        {gunler.map((g, i) => {
          const d = gun.get(g)
          return (
            <span
              key={g}
              className="aspect-square rounded-full"
              title={d ? `${gunTR(g)}: ${d.girilir} girilebilir, ${d.diger} perp'siz` : gunTR(g)}
              style={{
                background: d?.girilir ? 'var(--color-ekran)' : d?.diger ? 'var(--color-pasif)' : 'var(--color-cizgi-belirgin)',
                ...(i === 0 ? { outline: '1px solid var(--color-ekran)', outlineOffset: 2 } : {}),
              }}
            />
          )
        })}
      </div>
      <div className="etiket mt-3 flex justify-between text-ucuncul">
        <span>bugün</span>
        <span>{gunTR(gunler[30])}</span>
      </div>
    </div>
  )
}

function Yaklasan({ v, simdi }: { v: KilitVeri; simdi: number }) {
  const y = v.yaklasan
  if (!y)
    return (
      <div>
        <h3 className="etiket text-ikincil">Yaklaşan açılımlar</h3>
        <p className="mt-4 text-govde-sm text-ikincil">Takvim henüz yok. Düğüm her gün 00:05 UTC'de DefiLlama takvimini ham depoya yazar.</p>
      </div>
    )
  const girilir = y.olaylar.filter((e) => e.perp || e.durum === 'acik' || e.durum === 'kapandi')
  const perpsiz = y.olaylar.length - girilir.length
  return (
    <div>
      <h3 className="etiket flex flex-wrap justify-between gap-x-4 gap-y-1 text-ikincil">
        <span>Yaklaşan açılımlar · 30 gün</span>
        <span className="text-ucuncul">takvim {gunTR(y.takvim_gun_ms)} · DefiLlama</span>
      </h3>
      {y.hata ? (
        <p className="mt-4 text-govde-sm text-birincil">
          <span className="etiket text-kirmizi-metin">[hata]</span> {y.hata}. Düğüm yarın yeni takvimi indirince düzelir; sürerse
          kilit servisinin loguna bak.
        </p>
      ) : (
        <>
          <div className="mt-5">
            <GunSeridi y={y} simdi={simdi} />
          </div>
          <ol className="mt-6">
            {girilir.map((e) => (
              <li
                key={`${e.sembol}:${e.olay_ms}`}
                className="grid grid-cols-[64px_minmax(0,1fr)_auto] items-baseline gap-x-4 border-t border-cizgi py-3 last:border-b"
              >
                <span className="veri text-govde-sm text-ikincil">{gunTR(e.olay_ms)}</span>
                <span className="min-w-0">
                  <span className="text-birincil">{e.sembol}</span>
                  <span className="etiket mt-1 block text-ucuncul sm:mt-0 sm:ml-3 sm:inline">
                    arzın {oran(e.oran, 1)} · {kategoriAdi(e.kategori)}
                  </span>
                </span>
                <DurumYaklasan e={e} />
              </li>
            ))}
          </ol>
          <p className="mt-3 text-govde-sm text-pretty text-ikincil">
            Eşik: azami arzın {oran(v.kural.asgari_oran, 1)}'i, yalnız içeriden ve özel satış kilitleri.
            {perpsiz > 0 ? ` Eşiği geçen ${perpsiz} açılımın Binance perp'i yok, bunlara girilmez.` : ''}
          </p>
        </>
      )}
    </div>
  )
}

function Kapanan({ k }: { k: KilitKol }) {
  const o = k.kapanan_ozet
  return (
    <div>
      <h3 className="etiket flex flex-wrap justify-between gap-x-4 gap-y-1 text-ikincil">
        <span>Sonuçlanan olaylar · paper</span>
        {o.adet > 0 && (
          <span className="whitespace-nowrap">
            {o.kazanan}/{o.adet} kazandı · <span className={`veri ${isaretRenk(o.toplam)}`}>{isaretliTutar(k, o.toplam)}</span>
          </span>
        )}
      </h3>
      {k.kapanan.length === 0 ? (
        <p className="mt-4 text-govde-sm text-ikincil">Henüz sonuçlanan olay yok. İlk sonuç ilk açılım gününde gelir.</p>
      ) : (
        <ol className="mt-4">
          {k.kapanan.map((e) => (
            <li
              key={`${e.sembol}:${e.olay_ms}`}
              className="grid grid-cols-[minmax(0,1fr)_auto] items-baseline gap-x-4 border-t border-cizgi py-3 last:border-b"
            >
              <span className="min-w-0">
                <span className="text-birincil">{e.sembol}</span>
                <span className="etiket mt-1 block text-ucuncul sm:mt-0 sm:ml-3 sm:inline">
                  açılım {gunTR(e.olay_ms)} · {nedenAdi(e.neden)}
                </span>
              </span>
              <span className={`veri text-right text-govde-sm ${isaretRenk(e.sonuc ?? 0)}`}>
                {isaretliTutar(k, e.sonuc)}
                <span className="etiket ml-2 text-ucuncul">{yuzde(e.sonuc_oran, 1)}</span>
              </span>
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}

/** Günlük kararlar; Demo'da dolmayan açılışlar paper satırının altına yazılır. */
function KararGunlugu({ k, demo }: { k: KilitKol; demo?: KilitKol }) {
  const demoGun = new Map(demo?.kararlar.map((x) => [x.gun_ms, x]))
  return (
    <div>
      <h3 className="etiket text-ikincil">Karar günlüğü</h3>
      <ol className="mt-4">
        {k.kararlar.slice(0, 7).map((x) => {
          const d = demoGun.get(x.gun_ms)
          const dolmayan = (d?.ac ?? []).filter((a) => !a.dolum).map((a) => a.sembol)
          const ret = dolmayan.length ? demo?.retler.find((r) => dolmayan.some((s) => r.enstruman.startsWith(s))) : undefined
          return (
            <li key={x.gun_ms} className="border-t border-cizgi py-3 last:border-b">
              <p className="grid grid-cols-[64px_minmax(0,1fr)] gap-x-4 text-govde-sm">
                <span className="veri text-ikincil">{gunTR(x.gun_ms)}</span>
                <span className="text-pretty text-birincil">
                  {x.takvim_hatasi ? (
                    <>
                      <span className="etiket text-kirmizi-metin">[takvim yok]</span> yalnız kapanış
                    </>
                  ) : (
                    <>
                      {[x.ac.length ? `aç ${x.ac.map((a) => a.sembol).join(', ')}` : null, x.kapat.length ? `kapat ${x.kapat.join(', ')}` : null]
                        .filter(Boolean)
                        .join(' · ') || 'işlem yok'}
                      {x.red.length > 0 && (
                        <span className="text-ikincil"> · {x.red.map((r) => `${r.sembol} ${r.neden ? (RED[r.neden] ?? r.neden) : ''}`).join(', ')}</span>
                      )}
                    </>
                  )}
                  <span className="etiket ml-2 text-ucuncul">
                    {x.olay_sayisi != null ? `${x.olay_sayisi} olay` : ''}
                    {x.gecikmeli ? ' · gecikmeli' : ''}
                  </span>
                </span>
              </p>
              {dolmayan.length > 0 && (
                <p className="mt-1.5 pl-[80px] text-govde-sm text-pretty text-ikincil">
                  <span className="etiket text-birincil">[Demo]</span> {dolmayan.join(', ')} açılamadı
                  {ret ? <>: {ret.gerekce.replace(/^hata: BorsaHatasi: /, 'borsa hatası ')}</> : null}
                </p>
              )}
            </li>
          )
        })}
      </ol>
    </div>
  )
}

export function Kilit({ p }: { p: Pano }) {
  const v = p.kilit
  const paper = v.kollar.find((k) => !k.gercek)
  const demo = v.kollar.find((k) => k.gercek)
  const giris = -(v.kural.giris ?? -7)
  return (
    <section aria-labelledby="kilit-baslik">
      <BolumBasi id="kilit-baslik" baslik="Kilit açılımı">
        <p className="etiket text-ucuncul">
          <span className="text-ekran">[ana bot]</span> · sonraki karar {ikiSaat(v.sonraki_karar_ms)} · {kalan(v.sonraki_karar_ms, p.simdi_ms)} sonra
        </p>
      </BolumBasi>
      <p className="mt-3 max-w-[66ch] text-govde-sm text-pretty text-ikincil">
        Kilidi açılacak tokenı açılımdan {giris} gün önce açığa satar, aynı tutarda BTC alır, açılım günü ikisini kapatır. Olay başına
        özkaynağın {oran(v.kural.notional)}'i; piyasa yönüne değil, açılımda satılacak arza oynar.
      </p>

      {!paper ? (
        <p className="mt-8 text-govde-sm text-ikincil">
          Kilit kolu çalışmıyor: paper defterinde açık kilit kolu yok. Kol durdurulduysa yeniden başlatmak senin onayını ister.
        </p>
      ) : (
        <>
          <div className="mt-10 grid gap-12 md:grid-cols-12 md:gap-8">
            <div className="md:col-span-7">
              <div className="grid gap-10 sm:grid-cols-2 sm:gap-8">
                {[paper, demo].filter((k): k is KilitKol => !!k).map((k) => (
                  <KolOzeti key={k.kol} k={k} />
                ))}
              </div>
              <div className="mt-8">
                <IkiCizgi kollar={[paper, demo].filter((k): k is KilitKol => !!k)} />
              </div>
            </div>
            <div className="md:col-span-5 md:border-l md:border-cizgi md:pl-8">
              <Kapi k={paper} v={v} />
            </div>
          </div>

          <div className="mt-16">
            <AcikOlaylar k={paper} demo={demo} v={v} simdi={p.simdi_ms} />
          </div>

          <div className="mt-16 grid gap-16 lg:grid-cols-12 lg:gap-12">
            <div className="lg:col-span-7">
              <Yaklasan v={v} simdi={p.simdi_ms} />
            </div>
            <div className="flex flex-col gap-12 lg:col-span-5">
              <Kapanan k={paper} />
              <KararGunlugu k={paper} demo={demo} />
            </div>
          </div>
        </>
      )}
    </section>
  )
}
