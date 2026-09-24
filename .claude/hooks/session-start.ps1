#requires -Version 7.0
<#
    Proje durumu bağlam enjektörü. proje-baslat skill'i ile kurulan her proje
    klasöründe çalışır. .claude/state.json'u ve roadmap'i okuyup "şu an
    neredeyiz" bağlamını Claude'a enjekte eder. Kendi başına çalışır, ScryneOS
    vault'undaki lib.ps1'e bağımlı değildir.

    KANONİK KOPYA: ~/.claude/skills/proje-baslat/templates/.claude/hooks/
    Projedeki dosya bu şablonun birebir kopyası olmalı; projeye özgü her şey
    state.json'dan okunur (proje_adi, isteğe bağlı `roadmap` yolu). Hook'u
    projede elle değiştirme, şablonu değiştir ve kopyala. `durum` sapmayı
    DIKKAT bölümünde gösterir.

    2026-09-22: dört projedeki dört farklı sürüm tek dosyada birleşti.
    Parser ScryneQuant sürümünden (durum yalnız 3. sütundan, tetiklemeli ve
    koşullu fazlar sıradaki iş sayılmaz, 'R3' gibi harf önekli ve '17.5' gibi
    alt fazlı kimlikler tanınır).
#>

Set-StrictMode -Version Latest
try { [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false) } catch { }

$projectDir = if (-not [string]::IsNullOrWhiteSpace($env:CLAUDE_PROJECT_DIR)) {
    $env:CLAUDE_PROJECT_DIR
}
else {
    (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
}

$statePath = Join-Path $projectDir '.claude\state.json'
$docsDir = Join-Path $projectDir 'docs'

function Write-HookContext {
    param([Parameter(Mandatory)][string]$Text)
    if ([string]::IsNullOrEmpty($Text)) { return }
    @{
        hookSpecificOutput = @{
            hookEventName     = 'SessionStart'
            additionalContext = $Text
        }
    } | ConvertTo-Json -Compress -Depth 5
}

if (-not (Test-Path -LiteralPath $statePath -PathType Leaf)) {
    Write-HookContext -Text "[Proje Sistemi] Bu klasörde .claude/state.json yok. Proje henüz proje-baslat skill'i ile başlatılmamış olabilir, ya da state dosyası silinmiş. Devam etmeden önce durumu kullanıcıya sor, gerekiyorsa proje-baslat skill'ini çalıştır."
    exit 0
}

try {
    $state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
}
catch {
    Write-HookContext -Text "[Proje Sistemi] .claude/state.json okunamadı (bozuk JSON). Elle kontrol et."
    exit 0
}

$asama = "$($state.asama)"
$projeAdi = "$($state.proje_adi)"
# Kanonik roadmap yolu state.json'da değiştirilebilir (ScryneQuant: docs/ROADMAP-RESET.md).
$roadmapRel = if ($state.PSObject.Properties['roadmap'] -and "$($state.roadmap)") { "$($state.roadmap)" } else { 'docs/Roadmap.md' }

$asamaAciklamalari = @{
    'fikir'        = 'Fikir dokümanı geliştiriliyor (docs/Proje-Fikri.md). Sıradaki adım: dokümanı netleştir, sonra denetime geç.'
    'denetim'      = 'Fikir dokümanı denetleniyor. Sıradaki adım: riskli/bilinmeyen teknoloji kararları varsa küçük bir spike ile doğrula, sonra finalizasyona geç.'
    'finalizasyon' = 'Final doküman hazırlanıyor (docs/Final-Dokuman.md) -- teknoloji stack ve mimari kararları netleşiyor. Sıradaki adım: roadmap.'
    'roadmap'      = 'Roadmap hazırlanıyor -- faz faz, her faz için bitti kriteri tanımlanıyor. Sıradaki adım: uygulamaya başla.'
    'uygulama'     = 'Roadmap takip edilerek uygulanıyor.'
    'tamamlandi'   = 'Proje tamamlandı.'
}

$aciklama = if ($asamaAciklamalari.ContainsKey($asama)) { $asamaAciklamalari[$asama] } else { "Bilinmeyen aşama: $asama" }

$lines = [System.Collections.Generic.List[string]]::new()
$lines.Add("[Proje Sistemi] Proje: $projeAdi")
$lines.Add("Aşama: $asama -- $aciklama")

if ($asama -eq 'uygulama') {
    $roadmapPath = Join-Path $projectDir $roadmapRel
    if (Test-Path -LiteralPath $roadmapPath -PathType Leaf) {
        # Yalnız FAZ tablosunun satırları: ilk sütun faz kimliği (7, R3, 17.5),
        # üçüncü sütun bir durum işaretiyle başlıyor. Spike tablosu gibi başka
        # numaralı tablolar bu yüzden sayılmaz (eski desen 9 fazı 13 sayıyordu).
        $rows = @(
            Get-Content -LiteralPath $roadmapPath |
                Where-Object { $_ -match '^\|\s*[A-Za-z]?\d+(\.\d+)?\s*\|[^|]*\|\s*(✅|🔄|⏳|⛔)' }
        )
        $total = $rows.Count
        $done = @($rows | Where-Object { ($_ -split '\|')[3] -match '✅' }).Count
        # Durum yalnız ÜÇÜNCÜ sütundan okunur: bitti-kriteri metnindeki "(a) ✅" gibi
        # işaretler satırı tamamlanmış göstermemeli. Tetiklemeli/koşullu fazlar bir
        # olaya bağlı, sıradaki iş olamaz.
        $current = $rows |
            Where-Object {
                $durum = ($_ -split '\|')[3]
                $durum -notmatch '✅' -and $durum -notmatch '⛔' -and $_ -notmatch '\((tetiklemeli|koşullu)\)'
            } |
            Select-Object -First 1
        if ($current) {
            if ($current.Length -gt 400) { $current = $current.Substring(0, 397) + '...' }
            $lines.Add("Roadmap ($roadmapRel): $done/$total faz bitti, sıradaki satır -> $current")
        }
        elseif ($total -gt 0) {
            $lines.Add("Roadmap ($roadmapRel): $total fazın hepsi tamamlandı ya da tetiklemeli görünüyor -- bitti ise state.json'da asama'yı 'tamamlandi' yapmayı düşün.")
        }
    }
    else {
        $lines.Add("Not: roadmap dosyası bulunamadı ($roadmapRel). state.json'daki 'roadmap' alanını kontrol et.")
    }
}

$designPath = Join-Path $projectDir 'DESIGN.md'
$legacyDesignPath = Join-Path $docsDir 'Design.md'
$hasDesign = Test-Path -LiteralPath $designPath -PathType Leaf
$hasLegacy = Test-Path -LiteralPath $legacyDesignPath -PathType Leaf
if ($hasLegacy -and -not $hasDesign) {
    # İkisi birden varsa eski dosya bilinçli bırakılmış bir işaretçidir (OsintLab: Kontrast Sözleşmesi).
    $lines.Add("Not: eski docs/Design.md duruyor. Frontend işine dönüldüğünde create-design-md ile köke DESIGN.md olarak taşı, ikisini birden canlı tutma.")
}
if (-not $hasDesign -and -not $hasLegacy -and $asama -in @('finalizasyon', 'roadmap', 'uygulama')) {
    $lines.Add("Not: DESIGN.md henüz yok. Frontend işine başlamadan önce create-design-md + ui-ux-pro-max ile oluştur (bkz. global CLAUDE.md).")
}
elseif ($hasDesign) {
    $designContent = ''
    try { $designContent = Get-Content -LiteralPath $designPath -Raw -ErrorAction Stop } catch { }
    if ($designContent -cmatch '<[A-ZÇĞİÖŞÜ_]{3,}>') {
        $lines.Add("Not: DESIGN.md var ama hâlâ yer tutucu içeriyor gibi görünüyor, doldurulmamış olabilir.")
    }
}

# Son senkron hatası: session-end sessizce başarısız olursa burada görünür.
$healthPath = Join-Path $projectDir '.claude\sync-health.json'
if (Test-Path -LiteralPath $healthPath -PathType Leaf) {
    try {
        $h = Get-Content -LiteralPath $healthPath -Raw | ConvertFrom-Json
        $age = ([System.DateTimeOffset]::UtcNow.ToUnixTimeSeconds() - [int64]$h.ts) / 86400
        if ($age -lt 3) { $lines.Add("Uyarı: son oturum kapanış senkronu başarısız oldu ($($h.error)). Aşama/roadmap elle kontrol edilmeli.") }
    }
    catch { }
}

Write-HookContext -Text ($lines -join "`n")
exit 0
