---
version: alpha
name: TradeBot
description: <BIR_CUMLE_URUN_TANIMI>
---

# TradeBot

> Bu dosya Google DESIGN.md spec'ini (alpha) izler. **Kesin degerler frontmatter'da,
> gerekce ve uygulama rehberligi Markdown'da.** Ayni token iki yerde yasamaz.
> Doldurulduktan sonra dogrula:
>
> ```bash
> npx @google/design.md lint DESIGN.md
> npx @google/design.md export --format css-tailwind DESIGN.md
> ```
>
> Frontmatter'a `colors`, `typography`, `rounded`, `spacing`, `components` bloklarini
> ancak projede o sistemi tanimlayan gercek bir kaynak (token dosyasi, tema, Tailwind
> config) varken ekle. Uydurma token adi acma. Detayli kurallar: `create-design-md` skill'i.
>
> Bu blogu doldurduktan sonra sil.

## Overview

Taban disiplin (sabit, tum projelerde ayni): `~/.claude/CLAUDE.md` icindeki Dark
Glassmorphism kurallari — blur/border/kontrast/performans degerleri oradan gelir, burada
tekrar edilmez. Bu dosya sadece **bu projeyi digerlerinden ayiran** katmani kaydeder.

- **Mood:**
- **Farklilastirici detay:**

## Colors

(Accent paletin gerekcesi. Kesin degerler frontmatter'daki `colors` altinda.)

## Typography

(Tipografi eslesmesinin gerekcesi. Kesin degerler frontmatter'daki `typography` altinda.)

## Components

(Component bazli ozel kararlar — bu projede nav nasil duruyor, kart stili vb.
Her cumle bir implementasyon karari degistirmeli; YAML'i tekrar eden prose yazma.)

## Do's and Don'ts

(Sadece acikca kararlastirilmis yasaklar. "Iyi olsun" tipi tavsiye yazma.)
