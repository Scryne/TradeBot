// /api/pano ve /api/kol yanıtları (src/tradebot/pano/veri.py ile birebir)

export type Seri = [number, number][]

export interface Kol {
  kol: string
  taban: string
  jev: boolean
  strateji: string
  dalga: string
  zd: string | null
  grup: string
  tur: 'kol' | 'agresif' | 'portfoy'
  hesap: string | null
  durduruldu: boolean
  sinif: string
  baslangic_ozkaynak: number
  baslangic_ms: number
  ozkaynak: number
  toplam: number
  gun: number
  en_kotu_dusus: number
  islem: number
  karar: number
  yurutme_bps: number | null
  gecikme_bps: number | null
  fren: number
  veto: number
  durum: string | null
  son_karar_ms: number | null
  maruziyet: number
  pozisyon: Record<string, number>
  seri: Seri
}

export interface Hucre {
  m: number | null
  v: number
  f: string | null
  i: number
}

export interface OlaySatir {
  id: number
  zaman_ms: number
  tur: string
  rol: string
  enstruman: string
  neden: string
  guven: number | null
  baslik: string | null
  canli: boolean | null
  gecerli_ms: number
  bitis_ms: number | null
}

export interface Plan {
  kimlik: string
  zaman_ms: number
  aile: string
  hipotez: string
  durum: string
  sonuc: string | null
  deneme: number
  karar: 'A' | 'B' | 'KALDI' | null
  kollar: { kol: string; karar: string; sharpe: number | null; yillik: number | null; dsr: number | null; dalga: string }[]
}

export interface KilitOlay {
  sembol: string
  olay_ms: number
  giris_ms: number | null
  cikis_ms: number
  notional: number
  btc_dahil: boolean
  acik: boolean
  kapanis_ms: number | null
  neden: string | null
  nominal: number
  sonuc: number | null
  sonuc_oran: number | null
}

export interface KilitKol {
  kol: string
  gercek: boolean
  ortam: string | null
  baslangic_ozkaynak: number
  baslangic_ms: number
  ozkaynak: number
  toplam: number
  en_kotu_dusus: number
  fonlama: number
  son_isaret_ms: number | null
  durum: string | null
  seri: Seri
  kapi: { hafta: number; sr: number | null; psr: number | null; gerekli_hafta: number | null; gecti: boolean }
  acik: KilitOlay[]
  kapanan: KilitOlay[]
  kapanan_ozet: { adet: number; kazanan: number; toplam: number }
  kararlar: {
    gun_ms: number
    karar_ms: number
    durum: string
    olay_sayisi: number | null
    ac: { sembol: string; dolum: boolean }[]
    kapat: string[]
    red: { sembol: string; neden: string | null }[]
    takvim_hatasi: string | null
    gecikmeli: boolean
  }[]
  retler: { zaman_ms: number; enstruman: string; gerekce: string }[]
}

export interface Kilit {
  kollar: KilitKol[]
  kural: {
    giris: number | null
    cikis: number | null
    notional: number | null
    azami_brut: number | null
    azami_btc: number | null
    asgari_oran: number | null
    kategoriler: string[]
  }
  kapi: { asgari_hafta: number; psr: number }
  sonraki_karar_ms: number
  yaklasan: {
    takvim_gun_ms: number
    hata: string | null
    olaylar: {
      sembol: string
      olay_ms: number
      oran: number
      kategori: string
      perp: boolean
      giris_ms: number
      durum: 'acik' | 'kapandi' | 'perp_yok' | 'kacti' | 'bekliyor'
      neden: string | null
    }[]
  } | null
}

export interface Pano {
  simdi_ms: number
  kod_surumu: string
  turnuva: { bas_ms: number | null; bit_ms: number | null; gun: number; toplam_gun: number; hafta?: number }
  durum: {
    son_isaret_ms: number | null
    son_karar_ms: number | null
    bayat: boolean
    kol: number
    durdurulan: number
    normal: number
    fren: number
    acil: number
    karar_24s: number
    ret_24s: number
    islem_24s: number
    veto_24s: number
  }
  kollar: Kol[]
  serit: { saatler: number[]; satirlar: { kol: string; hucreler: Hucre[] }[] }
  tavan: { enstruman: number; sinif: number; kaldirac: number; gunluk_fren: number; haftalik_fren: number; acil_durdurma: number }
  kol_olaylari: { kol: string; zaman_ms: number; tur: string }[]
  dagitim: { portfoy: string; hafta_ms: number; kaldirac: number; kollar: Record<string, { agirlik?: number; katsayi?: number; sinif?: string }> } | null
  kilit: Kilit
  olaylar: {
    sayim_7g: { rol: string; tur: string; adet: number }[]
    son: OlaySatir[]
    aktif_veto: OlaySatir[]
    yargi_24s: { adet: number; hata: number; nvidia: number; gecikme_medyan_ms: number | null }
  }
  defter: { planlar: Plan[]; deneme_toplam: number }
}

export interface SaglikKontrol {
  ad: string
  durum: 'OK' | 'UYARI' | 'HATA'
  ayrinti: string
}

export interface Saglik {
  hazir: boolean
  zaman_ms?: number
  kontroller: SaglikKontrol[]
}

export interface KolAyrinti {
  kol: string
  taban: string
  jev: boolean
  strateji: string
  dalga: string
  zd: string | null
  ikiz: string | null
  sinif: string
  tanim: Record<string, unknown>
  baslangic_ozkaynak: number
  kod_surumu: string
  seri: Seri
  ikiz_seri: Seri
  kararlar: {
    bar_ms: number
    karar_ms: number
    durum: string
    veto: string[]
    hedef: number[] | null
    yeni: number[] | null
    kimlikler: string[] | null
    gecikmeli: boolean
    kod_surumu: string
    veri_hash: string
  }[]
  dolumlar: {
    zaman_ms: number
    tur: string
    enstruman: string
    miktar: number
    fiyat: number | null
    ucret: number
    karar_fiyati: number
    gonderim_fiyati: number | null
    risk_gerekce: string[]
  }[]
}
