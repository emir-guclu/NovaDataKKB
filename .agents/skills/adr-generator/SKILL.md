---
name: adr-generator
description: '2-3 gerçekçi teknik seçeneği 5 eksenli bir matris üzerinde puanlayarak mimari karar vermeyi kolaylaştırır, docs/decisions/adr/ altında yapılandırılmış bir ADR dosyası oluşturur ve bağlayıcı proje kurallarını günceller. Kullanıcı "/create-adr", "/adr-generator", "ADR yaz" veya "teknik seçenekleri kıyasla" dediğinde tetiklenir.'
argument-hint: 'Karar konusu, aday seçenekler ve kategori (backend|frontend|system|testing)'
user-invocable: true
---

# Yetenek (Skill): `adr-generator`

## Amaç
Teknik bir karar noktasını (mimari, framework, veritabanı, kütüphane, protokol vb.) yapılandırılmış, karşılaştırılabilir ve izlenebilir bir Mimari Karar Kaydına (Architecture Decision Record - ADR) dönüştürür. Kararların, değerlendirmeler sırasında ekibin savunabileceği kayıtlı bir gerekçe olmadan alınmasını veya sessizce geri alınmasını engeller.

## Ne Zaman Tetiklenmeli?
- Birden fazla **geçerli teknik seçeneğe** sahip ve **önemsiz olmayan sonuçları olan** (geri alınması zor, birden fazla modülü etkileyen veya güvenlik/maliyet/performans etkileri olan) bir kararla karşı karşıya kalan herhangi bir Ajan veya insan geliştirici tarafından.
- Genellikle `architect` (Mimar) ajanı tarafından çağrılır, ancak herhangi bir ajan veya ekip üyesi de çağırabilir; bu ajana özel değil, genel bir yetenektir.
- Tetikleme ifadeleri: `/adr-generator`, "bunun için bir ADR yaz", "teknik seçenekleri kıyasla".
- Geri döndürülebilir, düşük riskli seçimler (örn. tek bir değişkenin adlandırılması, bir linter kuralı seçimi) için **TETİKLEMEYİN**; bu durum yeteneğin kapsam dışına çıkması anlamına gelir.

## Gerekli Girdiler
1. Problem Tanımı — Hangi kararın neden şimdi verilmesi gerekiyor?
2. En az 2, ideal olarak 3 gerçekçi seçenek (hayali seçenekler değil; her biri ekibin gerçekten değerlendireceği şeyler olmalıdır).
3. Kararı sınırlandıran mevcut proje kısıtları (teknoloji yığını, sözlük terimleri, ekip yetkinlik seviyeleri, proje takvimi).

## Süreç
1. **Problemi tanımlayın:** Karar ihtiyacını neyin tetiklediğini ve bu karar verilmezse ne olacağını 1-3 cümleyle açıklayın.
2. **Değerlendirilen seçenekleri listeleyin:** Kararlar için sıfırdan analiz üretmek yerine, varsa ekibin mevcut araştırmalarını ve belgelerini yeniden kullanın.
3. **Her seçeneği 5 eksenli matriste puanlayın:** Performans, Karmaşıklık, Ölçeklenebilirlik, Sürdürülebilirlik, Maliyet. Her hücre için kısa ve somut ifadeler kullanın (basitçe "iyi/kötü" yazmayın); gözden geçiren kişi metni okumadan *nedenini* görebilmelidir.
4. **Tek bir belirleyici faktör seçin:** Eşit ağırlıklı beş ekseni olan ve karar vermeyi kolaylaştıran bir belirleyici faktörü bulunmayan bir analiz karar değildir. Teraziyi hangi faktörün (örn. ekip uzmanlığı, güvenlik gereksinimi, zaman kısıtı) gerçekten eğdiğini açıkça belirtin.
5. **Sonuçları dürüstçe yazın:** Her seçeneğin dezavantajları vardır; elenen seçeneklerin yanı sıra *seçilen* seçeneğin de olumsuz sonuçlarını dürüstçe listeleyin ve her anlamlı risk için bir azaltma (mitigation) yöntemi önerin.
6. **Varsa `Supersedes` / `Superseded by` (Geçersiz Kılma) alanlarını doldurun:** Bu ADR daha önceki bir kararı revize ediyorsa veya onun yerine geçiyorsa belirtin.
7. **Bağlayıcı Kuralları (Binding Rules) Tanımlayın:** Zorunlu bölüm. Bu karardan türetilen 1-3 kısa, net ve tartışmaya kapalı kural yazın.
   - Her kural mutlaka izlenebilir bir ID formatına sahip olmalıdır: Teknik kararlar için `[T-NNNN-X]` veya Süreç/Ürün kararları için `[P-NNNN-X]` (örn. `* [T-0001-1] Backend FastAPI kullanılarak Python 3.11+ ile yazılmalıdır.`).
   - **T- ve P- Ayrımı:** `T-` = kodlama veya mimari kısıtı (hangi dil, framework veya kütüphanenin kullanılacağını belirtir - kodun *nasıl* yazılacağını belirler). `P-` = süreç veya iş kuralı (sistemin *ne* yapması gerektiğini belirtir - kodun mimarisinden bağımsız iş mantığıdır). Kuralın hangisine ait olduğundan emin değilseniz ve belirli bir teknoloji/kütüphane adı geçiyorsa `T-`yi tercih edin, aksi takdirde `P-`yi seçin.
   - Bu kuralların ilgili talimat/kural dosyalarına yönlendirilmesi ayrı bir adımdır.
8. Kuralları ilgili dosyalara eklemeden önce ADR'nin Durum (Status) alanını kontrol edin. Durum `PROPOSED` (Önerilen) ise, kuralı hemen talimat dosyasına ekleyin ancak kuralın başına `[ONAY BEKLENİYOR — kaynak ADR ÖNERİLDİ durumundadır]` ön ekini ekleyin. ADR durumu daha sonra `ACCEPTED` (Kabul Edildi) yapıldığında bu ön eki kaldırın. Kuralları doğru dosyalara yönlendirin:
   - ADR kategorisi **`backend`**, **`frontend`** veya **`testing`** ise: Kuralı `docs/binding_rules/{kategori}.md` dosyasına ekleyin.
   - ADR kategorisi **`system`** ise (yani genel sistem düzeyindeyse - hem backend hem frontend'i etkileyen auth yapısı vb.): Kuralı doğrudan `AGENTS.md` dosyasına veya `docs/binding_rules/system.md` dosyasına ekleyin.
   - Eklenen her kuralın hemen üzerinde kaynak yorumu yer almalıdır: `<!-- source: ADR-NNNN -->`. Bu sayede bir ADR geçersiz kaldığında ilgili kural kolayca bulunup silinebilir veya güncellenebilir.
9. **ADR dosyasını kaydedin:** `docs/decisions/adr_template.md` şablonunu kullanarak dosyayı şu konuma kaydedin:
   `docs/decisions/adr/NNNN-kebab-case-baslik.md`
   — Burada `NNNN`, tüm kategoriler (backend/frontend/system/testing) arasında paylaşılan, proje genelinde tek bir sıralı sayaçtır (örn. 0001, 0002).
10. **Karar Listelerini Güncelleyin:** Karar `PROPOSED` durumundaysa `docs/decisions/open_decisions.md` dosyasına yeni bir satır ekleyin; onaylanıp `ACCEPTED` olduğunda ise `docs/decisions/closed_decisions.md` dosyasına taşıyın.

## Çıktı Konumu ve İsimlendirme
- ADR Dosyaları: `docs/decisions/adr/NNNN-kebab-case-baslik.md`
- Karar Dosyaları (Açık/Kapalı): `docs/decisions/open_decisions.md` ve `docs/decisions/closed_decisions.md`
- Kapsamlı Kurallar: `docs/binding_rules/{backend|frontend|system|testing}.md`
- Genel Kurallar: `AGENTS.md`

## Kısıtlar
- Uygulama kodunu yazmaz veya değiştirmez.
- Gerçekten değerlendirilmemiş seçenekleri varmış gibi göstermez; yalnızca tek bir seçenek makul ise bunu "1. Bağlam ve Problem Tanımı" kısmında dürüstçe belirtir.
- Ekibin veya Mimar Ajanının verdiği *gerçek* kararı yansıtır, kendi tercih ettiği kararı tek taraflı olarak dayatmaz.
- **Durum Alanı Kuralı:** Yeni oluşturulan tüm ADR'ler mutlaka `PROPOSED` durumunda oluşturulmalıdır. İlk oluşturulduğunda asla doğrudan `ACCEPTED` yapılamaz; kabul edilmesi için ekip veya gözden geçirici onayı gerekir.
- Sistem düzeyinde (`system`) olmayan kategoriye özel kuralları asla root veya genel dosyalara kestirmeden eklemeyin.
- `PROPOSED` durumundaki bir ADR'den kural/talimat dosyalarına yönlendirilen kurallar, kaynak ADR `ACCEPTED` yapılana kadar mutlaka `[ONAY BEKLENİYOR — kaynak ADR ÖNERİLDİ durumundadır]` ön ekini taşımalıdır. Bu sayede talimat dosyalarındaki kuralların doğruluk durumu sürekli güncel tutulur.