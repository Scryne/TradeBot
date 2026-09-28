// Türkçe sayı ve saat biçimi (DESIGN.md › Typography): binlik nokta, ondalık virgül, eksi U+2212, yüzde işareti önde.

const EKSI = '−'
const sayiBicim = (basamak: number) =>
  new Intl.NumberFormat('tr-TR', { minimumFractionDigits: basamak, maximumFractionDigits: basamak })

export function sayi(x: number, basamak = 0): string {
  const s = sayiBicim(basamak).format(Math.abs(x))
  return x < 0 && s !== sayiBicim(basamak).format(0) ? EKSI + s : s
}

/** Oran → işaretli yüzde: 0.0123 → "+%1,23", −0.004 → "−%0,40". Sıfır işaretsiz. */
export function yuzde(x: number | null | undefined, basamak = 2): string {
  if (x == null || !Number.isFinite(x)) return '—'
  const v = x * 100
  const yuvarli = Number(v.toFixed(basamak))
  const isaret = yuvarli > 0 ? '+' : yuvarli < 0 ? EKSI : ''
  return `${isaret}%${sayiBicim(basamak).format(Math.abs(yuvarli))}`
}

/** İşaretsiz yüzde (maruziyet, oran): 0.37 → "%37". */
export function oran(x: number | null | undefined, basamak = 0): string {
  if (x == null || !Number.isFinite(x)) return '—'
  return `%${sayiBicim(basamak).format(x * 100)}`
}

export function bps(x: number | null | undefined): string {
  if (x == null || !Number.isFinite(x)) return '—'
  return `${x < 0 ? EKSI : ''}${sayiBicim(1).format(Math.abs(x))} bps`
}

export function para(x: number): string {
  return `${x < 0 ? EKSI : ''}${sayiBicim(0).format(Math.abs(x))} $`
}

const tr = (o: Intl.DateTimeFormatOptions) => new Intl.DateTimeFormat('tr-TR', { timeZone: 'Europe/Istanbul', ...o })
const utc = (o: Intl.DateTimeFormatOptions) => new Intl.DateTimeFormat('tr-TR', { timeZone: 'UTC', ...o })

export const saatTR = (ms: number) => tr({ hour: '2-digit', minute: '2-digit' }).format(ms)
export const saatUTC = (ms: number) => utc({ hour: '2-digit', minute: '2-digit' }).format(ms)
export const gunTR = (ms: number) => tr({ day: 'numeric', month: 'short' }).format(ms)
export const tarihSaatTR = (ms: number) => tr({ day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }).format(ms)
export const tarihTR = (ms: number) => tr({ day: 'numeric', month: 'long' }).format(ms)

/** "14:00 TR · 11:00 UTC" (DESIGN.md › Do's: her zaman damgası UTC ve İstanbul saatiyle). */
export const ikiSaat = (ms: number) => `${saatTR(ms)} TR · ${saatUTC(ms)} UTC`

export function gorece(ms: number, simdi: number): string {
  const dk = Math.round((simdi - ms) / 60_000)
  if (dk < 1) return 'az önce'
  if (dk < 60) return `${dk} dk önce`
  const sa = Math.floor(dk / 60)
  if (sa < 48) return `${sa} saat önce`
  return `${Math.floor(sa / 24)} gün önce`
}

const STRATEJI: Record<string, string> = {
  ma_yon: 'MA yön',
  tsmom: 'TS momentum',
  donchian_ls: 'Donchian L/S',
  agresif: 'Agresif',
  portfoy: 'Portföy',
}

export const stratejiAdi = (s: string) => STRATEJI[s] ?? s

/** Kol kısa adı: "Donchian L/S · 4h · D2" */
export function kolAdi(k: { strateji: string; zd: string | null; dalga: string; tur: string }): string {
  if (k.tur !== 'kol') return stratejiAdi(k.strateji)
  return [stratejiAdi(k.strateji), k.zd, k.dalga.toUpperCase()].filter(Boolean).join(' · ')
}

const KISA: Record<string, string> = { ma_yon: 'MA', tsmom: 'TSM', donchian_ls: 'DON', agresif: 'Agresif', portfoy: 'Portföy' }

/** Dar ekran için: "DON 4h D2" */
export function kolKisa(k: { strateji: string; zd: string | null; dalga: string; tur: string }): string {
  if (k.tur !== 'kol') return KISA[k.strateji] ?? k.strateji
  return [KISA[k.strateji] ?? k.strateji, k.zd, k.dalga.toUpperCase()].filter(Boolean).join(' ')
}

export const ENSTRUMAN: Record<string, string> = { 'BINANCE:BTCUSDT': 'BTC', 'BINANCE:ETHUSDT': 'ETH' }
export const enstrumanAdi = (k: string) => ENSTRUMAN[k] ?? k.split(':').pop() ?? k

const DURUM: Record<string, string> = {
  normal: 'normal',
  fren_gunluk: 'günlük fren',
  fren_haftalik: 'haftalık fren',
  acil_durdurma: 'acil durdurma',
}
export const durumAdi = (d: string | null) => (d ? (DURUM[d] ?? d) : '—')
