---
name: spec-writer
description: 'Belirli bir özellik ID''si için docs/handoff/<feature-id>/spec.md dosyasını (kullanıcı hikayesi + numaralandırılmış İş Kuralları + Açık Sorular) yazar veya günceller. Bu doküman, Analist Ajanının acceptance-criteria.feature dosyasını yazarken kullanacağı temel iş kurallarını tanımlar. Tetikleme ifadeleri: "/spec-writer", "bu feature için spec yaz", "business rule dokümanı oluştur".'
argument-hint: 'Özellik ID''si (örn. F-07) ve varsa context-packager çıktısı'
user-invocable: true
---

# Yetenek (Skill): `spec-writer`

## Amaç
Belirli bir özellik ID'si için `docs/handoff/<feature-id>/spec.md` dosyasını üretir: Düz yazı ve madde işaretleriyle yapılandırılmış bir iş kuralları dokümanı (kullanıcı hikayesi + numaralandırılmış `BR-nn` iş kuralları) ve açık sorular listesi oluşturur. 

Bu doküman, Analist Ajanının `docs/handoff/<feature-id>/acceptance-criteria.feature` dosyasına girdi sağlar. Analist Ajanı bu dosyadaki `BR-nn` listesini okuyarak her bir kuralı Gherkin `Scenario:`'larına dönüştürür. `spec-writer` doğrudan Gherkin senaryoları üretmez.

## Ne Zaman Çağrılmalı
- Özellik ID'si için bir `context-packager` paketi oluşturulduktan sonra (tercih edilen girdi) veya özelliğe ait gereksinim ID'leri doğrudan sağlandığında.
- Analist Ajanı ilgili özellik için `docs/handoff/<feature-id>/acceptance-criteria.feature` dosyasını yazmadan önce.
- Tek seferde sadece tek bir özellik ID'si işlenmelidir. Tüm proje veya birden fazla özellik için tek seferde spec yazmaya çalışmayın.

## Gerekli Girdiler
1. **Özellik ID'si** (örn. `F-07`): Çıktı klasör yolunu belirlemek için zorunludur. Eğer verilmediyse `docs/features/feature-inventory.md` dosyasından bulmaya çalışın veya kullanıcıya sorun.
2. Bu özellik için hazırlanmış `docs/handoff/<feature-id>/context.md` bağlam paketi dosyası (tercih edilen) VEYA özelliğin ilişkili olduğu gereksinimlerin (`R-nn`) listesi.

## Okunacak Dosyalar
1. `docs/features/feature-inventory.md` — İlgili özellik ID'sinin satırını bul (başlık, kapsam, ilişkili `R-nn` gereksinimleri, bağımlılıklar). Dosya yoksa veya ID bulunamazsa durun ve eksikliği sohbette bildirin.
2. Gereksinim belgeleri (örn. `docs/requirements/requirements_inventory.md`) Özelliğin bağlı olduğu gereksinimlerin detayları.
3. `GLOSSARY.md` — Terimleri sözlük tanımlarına sadık kalarak harfiyen kullanın; yeni terimler uydurmayın.
4. `docs/decisions/open_decisions.md` (merkezi) ve `docs/handoff/<feature-id>/open_decisions.md` (varsa, özelliğe özel) — Durumu `DECIDED` veya `DECIDED_NO_ADR` olan kararları bağlayıcı kabul edin. `OPEN`, `PROPOSED` durumundakileri nihai karar saymayın.
5. `docs/handoff/<feature-id>/spec.md` — Dosya zaten varsa önce okuyun. Elle eklenmiş notları/açıklamaları koruyarak yalnızca gerekli güncellemeleri yapın.
6. `docs/handoff/<feature-id>/context.md` — `context-packager` tarafından üretilmiş bağlam paketi dosyası (varsa, birincil girdi kaynağı olarak okunmalıdır).


## Çıktı
`docs/handoff/<feature-id>/spec.md` — Bu yeteneğin tek çıktısıdır. Gherkin (ATDD) yazmayın ve `acceptance-criteria.feature` dosyasına asla dokunmayın.

## Süreç
1. **Kapsamı Tanımla:** Özelliğin neyi kapsadığını ve hangi gereksinimlerle (`R-nn`) eşleştiğini 1-2 cümleyle yazın.
2. **Kapsam Dışı Notunu Kopyala:** `feature-inventory.md` içindeki `**Out of scope:**` ifadesini aynen taşıyın.
3. **Kullanıcı Hikayesini Yaz:** (Kim olarak / Ne istiyorum / Böylelikle) formatında yazın.
4. **İş Kurallarını Numaralandırılmış Listele (`BR-nn`):** Gereksinimler ve kapalı kararlardan kuralları türetin. Her kuralın sonuna referans gereksinimini yazın, örn. `- BR-01: Sorular tek tek gösterilmelidir. (R-08)`. Mevcut `BR-nn` ID'lerini asla değiştirmeyin veya yeniden numaralandırmayın; yenileri sona ekleyin.
5. **Türetilmiş Kuralları İşaretle:** Doğrudan belirtilmeyen ancak mantıksal olarak çıkarılan kuralların başına `[DERIVED]` ekleyin.
6. **Açık Soruları Listele:** Eğer soru zaten kararlar dosyasında varsa referans verin, yoksa `[NEW — not yet in open-decisions.md]` olarak işaretleyin.
7. **Çıktıyı Kaydet:** `docs/handoff/<feature-id>/spec.md` dosyasına yazın.

## Dosya Yapısı
```markdown
# Spec: <feature-id> — <Kısa Başlık>

## 1. Spec Durumu
<Draft | Decisions Pending | Implementation Ready | Completed>

## 2. Amaç ve Başarı Sinyali
<Bu özelliği neden yapıyoruz? Başarıyı tanımlayan gözlemlenebilir sonuç nedir?
 Şablon: "<Paydaş> <hedefe> ulaşabilsin diye, <sistem> <gözlemlenebilir davranış> gerçekleştirmelidir.">

## 3. Kapsam / Kapsam Dışı
**Kapsam İçi:**
- <Açıkça dahil edilen davranış veya yetenek>
**Kapsam Dışı:**
- <Açıkça hariç tutulan davranış — bu yinelemede geliştirilmeyecek>

## 4. Girdi, Çıktı ve Hata Kontratı
**Girdiler:**
- <CLI bayrakları, env değişkenleri, konfigürasyon anahtarları, stdin verisi veya TUI tuş basımı>
**Çıktılar (Başarı):**
- <Stdout mesajı, diskteki dosya, git commiti, TUI görsel değişimi, exit code 0>
**Çıktılar (Hata):**
- <Stderr mesajı, sıfır olmayan exit code, yazılmayan dosya, commit yok>
**Yan Etkiler:**
- <Geçmiş günlük kaydı, kilit edinimi, git commiti, konfigürasyon değişikliği>

## 5. Karar Günlüğü
| # | Soru | Karar | Karar Veren | Tarih |
|---|------|-------|-------------|-------|
| 1 | <Çözülen tasarım sorusu> | <Seçilen yanıt/çözüm> | <spec-writer veya kullanıcı> | <tarih> |

## 6. İş Kuralları
- BR-01: <Kural 1: koşul → davranış> (R-nn)
- BR-02: <Kural 2: koşul → davranış> (R-nn) [DERIVED from R-nn — <kısa gerekçe>]
<Her kural somut ve doğruluğu sınanabilir bir ifade olmalıdır.>

## 7. Teknik Kısıtlar
<AGENTS.md dosyasından kopyalanan veya türetilen kısıtlar. Yalnızca BU özelliği bağlayan kısıtları dahil edin:>
- <Örn: Yalnızca ESM, class kullanılmayacak, yazmadan önce advisory lock, git otomatik commit motoru, Vitest testleri vb.>

## 8. Varsayımlar / Açık Sorular
**Varsayımlar (Geçici, doğrulanması gerekebilir):**
- <Varsayım — gözden geçirenlerin sorgulayabilmesi için açıkça belirtin>
**Açık Sorular (ENGELLEYİCİ — Geliştirmeye Hazır olmadan önce çözülmelidir):**
- <soru> — bkz. T-05, özelliğin open_decisions.md dosyası
- <soru> [NEW — not yet in open-decisions.md]
```

## Kurallar
- Gereksinimlere veya kapalı kararlara dayanmayan hiçbir iş kuralı uydurmayın.
- Açık soruları kendiniz çözmeye çalışmayın; sadece listeleyin.
- `docs/handoff/<feature-id>/acceptance-criteria.feature` dosyasına asla dokunmayın.
- Re-run durumlarında eski `BR-nn` numaralarını değiştirmeyin.
