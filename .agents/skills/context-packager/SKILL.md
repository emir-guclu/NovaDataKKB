---
name: context-packager
description: 'Belirli bir özellik veya kapsam dilimi için, bir ajan oturumu veya spec yazma görevi başlamadan önce kapsamı sınırlandırılmış, minimal bir bağlam paketi (ilgili gereksinim ID''leri, sözlük terimleri, bağlayıcı ADR kuralları ve DECIDED kararları) hazırlar. Yeni bir özellik/kapsam üzerinde çalışmaya başlarken veya tüm repoyu yeniden okutmadan herhangi bir ajana görev devrederken kullanın. Tetikleme ifadeleri: "/context-packager", "bu görev için bağlam hazırla", "context package oluştur".'
argument-hint: 'Özellik/kapsam adı veya gereksinim ID''leri (örn. R-06, R-07 — iş ilanı girişi) kategori: [frontend|backend|testing|ai]'
user-invocable: true
---

# Yetenek (Skill): `context-packager`

## Amaç
`GLOSSARY.md` içinde tanımlanan "Taze Bağlam" (Fresh Context) ilkesine uygun olarak, herhangi bir ajanın (Analist, Mimar, Geliştirici vb.) veya insanın bir göreve yalnızca kendisini ilgilendiren bağlamla başlamasını sağlamak amacıyla kompakt ve kapsamı sınırlı bir bağlam paketi üretir. İki hatalı durumu önler: (a) bir ajanın tüm repoyu okuyup odağının dağılması ve (b) sunulmadığı için bağlayıcı bir kısıtlamayı gözden kaçırması.

## Ne Zaman Çağrılmalı
- Yeni bir özellik/kapsam dilimi üzerinde Analist Ajanı veya Mimar Ajanı çalışmaya başlamadan önce.
- Test Geliştirici Ajanı başarısız testler yazmadan veya Geliştirici Ajanı belirli bir özellik ID'si için uygulama kodu yazmadan önce. Her ikisinin de tüm repoya değil, dokunacakları alanla sınırlı bağlayıcı ADR kurallarına ve kapalı kararlara ihtiyacı vardır.
- Belirli bir kapsam için `spec-writer` tetiklenmeden önce.
- Bir insan, ilgili dosyaları manuel olarak okuyup kopyalamak zorunda kalmadan herhangi bir ajana görev devretmek istediğinde.
- Projenin tamamı için tek seferde çağırmayın. Bu yetenek tasarım gereği kapsam sınırlıdır; "tüm proje bağlamını" istemek yeteneğin amacına aykırıdır.

## Gerekli Girdiler
1. Kapsam: Bir özellik adı (örn. "iş ilanı girişi") veya gereksinim ID'leri listesi (örn. `R-06`, `R-07`).

## Süreç
1. **İlgili gereksinim ID'lerini belirle:** `docs/requirements/requirements_inventory.md` dosyasını okuyun ve yalnızca verilen kapsamla eşleşen satırları çıkarın. Doğrudan belirtilen gereksinimleri VE bunlardan türetilmiş gereksinimleri dahil edin.
2. **Sadece ilgili sözlük terimlerini çek:** `docs/GLOSSARY.md` dosyasını okuyun ve yalnızca 1. adımda belirlenen gereksinimler tarafından doğrudan referans verilen terimleri dahil edin. İlgisiz terimleri eklemeyin.
3. **Sadece ilgili bağlayıcı kuralları çek:** `docs/binding_rules/` altındaki ilgili alan kurallarını (örn. `backend.md`, `frontend.md`, `test.md` veya `system.md` dosyalarını) tarayın. `applyTo` kapsamı veya `<!-- source: ADR-NNNN -->` yorumu bu özelliğin kapsamıyla eşleşen kural satırlarını kaynak yorumuyla birlikte çıkarın.
4. **Sadece ilgili kapalı kararları çek:** Merkezdeki `docs/decisions/open_decisions.md` ve `docs/decisions/closed_decisions.md` dosyaları ile varsa özelliğe özel `docs/handoff/F-XXX/open_decisions.md` dosyasını tarayın. Bu kapsamla ilgili, durumu `DECIDED` veya `DECIDED_NO_ADR` olan satırların "Karar" sütunundaki metinleri dahil edin.
5. **Çözülmemiş maddeleri açıkça işaretle:** Bu dosyalarda bu kapsamla ilgili `OPEN`, `IN_DISCUSSION` veya `PROPOSED` durumunda satırlar varsa bunları sessizce atlamak yerine, hangi dosyadan geldiklerini belirterek "⚠️ Çözülmemiş - Varsayımda Bulunmayın" başlığı altında ayrı bir yerde listeleyin.
6. **Tek bir Markdown paketi üretin:** Tam olarak şu bölümleri ve şu sırayla içeren bir Markdown çıktısı oluşturun: `## Scope`, `## Relevant Requirements`, `## Relevant Glossary Terms`, `## Binding Constraints`, `## Closed Decisions`, `## ⚠️ Unresolved (do not assume)`.
7. **Sonucu doğrudan iletin:** Bu paketi doğrudan sohbet yanıtında döndürün. Çağıran kişi özellikle kaydetmek istemediği sürece dosyaya yazmayın. Eğer kaydedilmesi istenirse özelliğe özel klasörün altındaki `docs/handoff/F-XXX/context.md` yoluna kaydedin.


## Kurallar
- Kaynak dosyalarda kelimesi kelimesine mevcut olmayan hiçbir gereksinim, sözlük terimi, kural veya karar uydurmayın.
- Genel anlamda "ilişkili" görünse bile verilen kapsamın dışındaki hiçbir gereksinimi/terimi/kuralı dahil etmeyin. Sıkı bir kapsam filtrelemesi bu yeteneğin tek amacıdır.
- `OPEN`/`IN_DISCUSSION` durumundaki kararları kendiniz çözmeyin veya bunlarda taraf seçmeyin; sadece listeleyin.
- Kod, spec veya ADR yazmaz. Sadece okuma ve özetleme yapar.
- Verilen kapsam hiçbir gereksinimle eşleşmiyorsa, en yakın olanı tahmin etmeye çalışmak yerine bunu açıkça belirtin.