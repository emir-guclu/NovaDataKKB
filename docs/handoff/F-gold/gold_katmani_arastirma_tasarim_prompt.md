# GÖREV: Gold Katmanı Tasarımı — Repo Analizi + Araştırma + Uygulama

## Rol ve Genel Hedef

Sen bir veri mimarisi danışmanı ve mühendisisin. KKB Hackathon projesinde Bronze ve Silver
katmanları tamamlandı — **BDDK (Haftalık + Aylık), FinTürk ve EVDS** verileri; align_service ile
bu dört kaynağın frekans hizalaması da bitti. Şimdi görevin, **Gold katmanını** tasarlamak ve
uygulamak.

**Not:** EVDS tarafı bir takım arkadaşı tarafından ayrı geliştirildi (bu prompt'un ilk taslağında
kapsam dışıydı, artık dahil). Faz 1'de EVDS'in Silver şemasının, BDDK/FinTürk ile birebir aynı
kanonik şemaya (`series_id, source, date, period_start, period_end, value, freq, unit, dims,
source_file`) gerçekten uyup uymadığını mutlaka doğrula — iki farklı kişi/ekip tarafından ayrı
geliştirildiği için küçük tutarsızlıklar (örn. `dims` anahtar isimlendirmesi, `unit` formatı,
`source` değeri büyük/küçük harf farkı) olabilir. Gold tasarımına geçmeden önce bu tutarsızlıkları
tespit edip bir listede topla.

Bu görev iki fazdan oluşuyor: **önce derinlemesine inceleme/araştırma, sonra tasarım/uygulama.**
Araştırma adımını atlayıp doğrudan tablo tasarımına geçme — bu görevin en kritik kısmı, mevcut
sistemin gerçek durumunu ve iyi pratikleri anlamadan tasarım yapmamak.

**Nihai amaç:** Gold katmanını, hackathon jürisini etkileyecek, projeyi rakiplerinden ayıracak,
ve en önemlisi **Agent/LLM'in veriye baktığında neden-sonuç ilişkisini kolayca kavrayabileceği**
bir yapıda kurmak. "Rastgele bir sürü agregasyon tablosu" değil, düşünülmüş, gerekçeli bir mimari.

---

## FAZ 0 — Ön Koşul: `nature` (Finansal Doğa) Alanının Tamamlanması

Bu adımı Gold tasarımından ÖNCE bitir çünkü Gold'un doğruluğu, align_service'in doğru
çalışmasına dayanıyor. Takım içinde şu tespit yapıldı: hizalama (weekly→monthly gibi) şu an
`source` string'ine (`if source == "BDDK_WEEKLY": method = "last"`) veya seri kodundaki anahtar
kelimelere bakılarak (`"FAIZ" geçiyorsa mean`) kararlaştırılıyor. Bu kırılgan — yeni bir seri
türü (örn. haftalık bir "akım" verisi) eklendiğinde sessizce yanlış hizalanabilir.

**Çözüm:** Her seriye, kaynağından bağımsız, verinin finansal karakterini tanımlayan bir
`nature` alanı ekle:
- `stock` (bakiye/seviye, örn. kredi stoku, mevduat, TCMB rezervi) → hizalama: `last`
- `flow` (dönem içi akım/hacim, örn. faiz geliri, altın basım adedi) → hizalama: `sum`
- `rate` (oran, örn. faiz oranı) → hizalama: `mean`
- `price` (fiyat/kur, örn. USD/TRY) → hizalama: `mean` (not: gelecekte endeks/kapanış değeri
  gibi `last` gerektiren bir alt-tür çıkabilir, kategori setini kapalı/sabit tasarlama)

**Uygularken şu 5 noktaya MUTLAKA dikkat et — bunlar gözden kaçırılmış, kritik riskler:**

1. **`accumulation` (YTD) ile `nature` etkileşimi:** Kümülatif (`accumulation != "none"`) bir
   serinin HAM hali ile decumulate edilmiş `_periodic` hali, **farklı `nature` almalı.** Ham YTD
   seri aslında bir "stock" gibi davranır (yıl başından bugüne birikmiş seviye) → `last`.
   `_periodic` (decumulate edilmiş) versiyonu gerçek bir "flow"dur → `sum`. Bunu ayırt etmezsen,
   `_periodic` serileri üst frekansa hizalarken (örn. aylık→çeyreklik) sessizce yanlış toplanır.

2. **Varsayılan değeri `"stock"` yapma — silent risk yaratır, bunun yerine PIPELINE'I DURDUR.**
   `CanonicalSeriesMetadata`'da `nature` alanı boşsa/sınıflandırılmamışsa, sessizce bir
   varsayılana düşme ve sadece "uyarı loglama" ile de yetinme (uyarılar loglarda kaybolur,
   kimse fark etmeyebilir). Bunun yerine **`align_service` / Silver build script'i, sınıflandırılmamış
   bir `nature` ile karşılaştığında açıkça `raise ValueError(...)` fırlatıp build'i durdursun.**
   Hata mesajı hangi `series_id`'nin sınıflandırılmadığını net söylesin, örn:
   ```python
   if nature not in {"stock", "flow", "rate", "price"}:
       raise ValueError(
           f"Seri '{series_id}' için nature tanımlanmamış. "
           f"Align edilmeden önce series_catalog'a nature eklenmeli."
       )
   ```
   Amaç: sınıflandırılmamış bir seri, build zamanında **hemen ve gürültülü şekilde** yakalansın;
   kimse "aa meğer bu seri yanlış hizalanmış" diye demo günü veya haftalar sonra fark etmesin.
   EVDS'te 53.000 seri olduğu için, dinamik çekilen sınıflandırılmamış bir serinin sessizce
   (ya da fark edilmeyen bir logla) yanlış hizalanması gerçek bir risk — bunu mimari seviyede,
   build'i kırarak engelle. Bu, sizin decumulate() için zaten uyguladığınız "otomatik tahmin
   etme, emin olmadığın şeyi işleme" prensibiyle tam tutarlı; sadece burada "işleme" yerine
   "işlemeye çalışma, patla" diyoruz çünkü align_service bir batch/build adımı, kullanıcı
   karşısında çalışan canlı bir servis değil — build zamanında patlaması demo'yu bozmaz,
   tam tersine demo'dan ÖNCE hatayı yakalamanızı sağlar.

3. **Dinamik yeni seri sınıflandırması (`evds_loader.py`) anahtar kelime tahminine dayanmasın.**
   Bu, "kaynak ismine göre kör atama" sorununu bir seviye aşağı taşımaktan ibaret olur. Mümkünse
   EVDS'in kendi resmi seri metadata'sındaki (varsa) kategori/birim bilgisini kullan; emin
   olamıyorsan seriyi `unclassified` bırak — yukarıdaki (madde 2) kural gereği bu, align_service
   çalıştığında build'i durduracaktır. **Bu istenen davranıştır:** yeni bir seri sisteme girdiğinde
   sınıflandırılana kadar pipeline kasıtlı olarak durur, böylece kimse fark etmeden yanlış
   hizalanmış veri Gold'a sızmaz.

4. **Seri bazlı override imkanı ekle.** `series_catalog`'a opsiyonel bir `alignment_override`
   alanı koy — genel `nature` kuralına uymayan istisnai seriler için (53.000 seri arasında
   mutlaka çıkacaktır) kod içine özel if-else eklemeye gerek kalmasın.

5. **Time-weighting yaklaşımını dokümante et.** `mean` hesaplarken, ay sınırına denk gelen
   kısmi haftalar basit aritmetik ortalamaya mı dahil ediliyor yoksa gün sayısına göre mi
   ağırlıklandırılıyor — hangisi yapılıyorsa `notes/` altında bilinen bir yaklaşım/sınırlama
   olarak not düş, sessiz bir varsayım bırakma.

**Dokunulacak dosyalar (mevcut planınızdan):** `silver_canonical.py` (Pydantic model),
`transformer.py` (EVDS metadata üretici), `build_silver_bddk.py`, `evds_loader.py`,
`build_silver_canonical.py` (DuckDB şema), `alignment_policies.py`, `align_service.py`,
ilgili test dosyaları (`test_silver_canonical.py`, `test_alignment_policies.py` vb.).

**Bu faz bitmeden Faz 1'e (repo audit) geçme** — çünkü Faz 1'in çıktısı (hangi seriler hangi
nature'da, hangi align yöntemini kullanıyor) Gold tasarımının girdisi olacak.

---

## FAZ 1 — Mevcut Durumu İncele (Atlanmayacak)

### 1.1 Repoyu Çek ve Genel Yapıyı Çıkar

- GitHub reposunun en güncel halini çek (`git pull` / `git clone`) — bu noktada hem senin
  (BDDK/FinTürk) hem takım arkadaşının (EVDS) commit'lerinin merge edilmiş/güncel halini
  görmelisin
- Klasör yapısını, özellikle şu alanları incele:
  - `data/bronze/`, `data/silver/` — gerçekte hangi dosyalar, hangi boyutlarda var; **BDDK/
    FinTürk ile EVDS'in klasör/isimlendirme konvansiyonu tutarlı mı** (örn. ikisi de
    `data/silver/<source>/*.parquet` mı, yoksa EVDS farklı bir yerde mi duruyor)
  - `backend/app/modules/bddk/parsers/` ve EVDS için eşdeğer parser klasörü — Silver
    parser'larının son hali
  - `series_catalog` tablosu/dosyası — kaç seri var, hangi `source`, `freq`, `unit`,
    `accumulation`, `description` değerleri dolu; **BDDK/FinTürk/EVDS serileri aynı catalog'da
    mı birleşiyor, yoksa ayrı mı tutuluyor** (birleşik olmalı, ayrıysa bunu düzeltilecekler
    listesine ekle)
  - `align_service` (veya benzer isimli modül) — nasıl çalışıyor, hangi frekansları hangi
    ortak zemine indirgiyor, çıktısı nasıl bir şema; **EVDS'in (muhtemelen günlük, `D`)
    frekansını da bu servisin doğru şekilde hizalayıp hizalamadığını** kontrol et
  - Varsa mevcut test dosyaları, `notes/cumulative_inspection.md` gibi daha önce üretilmiş
    dokümantasyon (hem senin hem arkadaşının notları)

### 1.2 Gerçek Veriyi Örnekle

- `series_catalog`'dan gerçek seri isimlerinin, kategori dağılımının (Krediler, Mevduat,
  Bireysel Bankacılık, Oranlar, Şubeler, Altın Kredileri/Mevduatı, Seçilmiş Sektörel Krediler,
  FinTürk il bazlı seriler, **EVDS'in kapsadığı seriler** — döviz kurları, faiz oranları,
  enflasyon vb. muhtemelen) bir dökümünü çıkar
- Hangi seriler `accumulation != "none"` (yani `_periodic` kardeşi olan YTD seriler) — bunları
  ayrıca listele, Gold tasarımında öncelik bunlarda olmalı çünkü zaten "değişim" hesaplamaya hazırlar
- Silver'daki gerçek tarih aralığını, frekans dağılımını (kaç seri W, kaç seri M, FinTürk'ün
  gerçek `freq` değeri neyse onu) doğrula

### 1.3 Kısa Bir Durum Özeti Yaz

Bu incelemenin sonunda, `notes/gold_pre_design_audit.md` adıyla kısa (1 sayfa civarı) bir özet
yaz: kaç seri, hangi kategoriler, hangi frekanslar, hangi seriler kümülatiften dönüştürülmüş,
align_service'in tam olarak ne ürettiği. Bu özet, Faz 2'deki tasarım kararlarının gerekçesi
olacak — "şu tabloyu şunun için seçtim çünkü catalog'da X kadar seri bu kategoride" diyebilmen
lazım, tahminle değil veriye bakarak.

---

## FAZ 2 — Araştırma: "LLM İçin İyi Bir Gold/Semantic Katmanı" Ne Demek

Doğrudan tablo tasarımına geçme. Önce şu soruyu araştır ve kısaca (`notes/gold_design_principles.md`
içine) yaz: **Bir veri katmanı, bir LLM'in doğru ve güvenilir SQL/sorgu üretmesini nasıl kolaylaştırır?**

Araştırırken şu kavramlara bak (bunlar bilinen, yerleşik pratikler — kendi bildiğin yerlerden ya
da web'den araştırarak doğrula, uydurma):

- **Semantic layer / metrics layer** yaklaşımı (dbt Semantic Layer, Cube.dev gibi araçların
  çözdüğü problem) — metriklerin (büyüme oranı, ortalama, sapma gibi) merkezi, tek yerde
  tanımlanıp her sorguda tutarlı hesaplanması
- **Self-describing schema** prensibi — sütun isimlerinin, tablo isimlerinin insan/LLM için
  anlamlı olması (`gold.monthly_change` gibi, `t7_agg` gibi değil), ve her tabloya eşlik eden
  açık bir açıklama (catalog'a Gold tabloları için de description eklenmesi)
- **Text-to-SQL / NL-to-SQL için şema tasarımı** üzerine bilinen zorluklar — çok fazla JOIN
  gerektiren normalize şemaların LLM'in doğru sorgu üretmesini zorlaştırdığı, "pre-joined"
  geniş (wide) tabloların hata oranını düşürdüğü
- **Nedensellik/açıklanabilirlik (explainability) için tasarım** — bir Gold satırının, hangi
  Silver satırlarından/hangi Bronze dosyasından türediğinin izlenebilir olması (provenance
  chain). Bu, projenizin daha önce planladığı "Kaynak Zinciri Tool" fikriyle doğrudan bağlantılı.

Bu araştırmanın çıktısı, Faz 3'teki tasarım kararlarının **her birinin bir cümlelik gerekçesi**
olmalı — "bunu böyle yaptık çünkü [prensip]" diyebilmelisin.

---

## FAZ 3 — TAMAMLANDI: Onaylanmış Gold Tasarımı

Bu faz bitti ve tasarım onaylandı. Aşağıdaki 7 tablo + 1 destek view, gerçek Faz 1/2/2.5
çıktılarına dayanılarak kararlaştırıldı. Faz 4'e başlarken bu listeyi ilk elden kaynak olarak
kullan, yeniden tasarlamaya çalışma:

1. **`gold_periodic_change`** — series_id/dimension slice/date bazında MoM ve YoY değişim
   (hem mutlak hem yüzde). Alanlar: `date, series_id, value, mom_abs_change, mom_pct_change,
   yoy_abs_change, yoy_pct_change, source, nature, unit`
2. **`gold_housing_credit_market`** — BDDK konut kredisi (`variable=TP`) + EVDS konut faizi/
   fiyat endeksi/satış adedi. Aylık grain.
3. **`gold_credit_market`** — BDDK toplam kredi (`variable=Toplam`) + EVDS toplam kredi hacmi/
   ticari kredi faizi. Aylık grain.
4. **`gold_deposit_market`** — BDDK mevduat-katılım fonu (`variable=TP`) + EVDS TL mevduat
   faiz oranı. Aylık grain. (Kaynak seçimi Faz 1→2.5 arasında `toplam_mevduat`'tan
   `mevduat_katilim_fonu`'na kasıtlı olarak değişti — sebep: currency-scope uyumu.)
5. **`gold_precious_metal_ratios`** — EVDS altın/gümüş BIST kapanış fiyatları, GÜNLÜK grain
   (istisnai olarak canonical Silver'dan doğrudan besleniyor, Aligned katmandan değil).
   **Kritik kural:** oran, günlük gerçek kapanışlardan hesaplanır
   (`gold_close / silver_close`), aylık ortalamaların oranı ALINMAZ
   (`avg(gold)/avg(silver)` YANLIŞ, `avg(gold/silver_günlük)` doğru yaklaşım).
6. **`gold_finturk_province_credit_quality`** — il bazlı kredi/takipteki alacak/NPL oranı,
   çeyreklik grain. `geo_level=province` olanlar sıralamaya girer, `Yurt Dışı` ayrı tutulur.
   **Per-capita göstergeler v1 kapsamı DIŞINDA** — nüfus verisi mevcut kaynaklarda yok,
   bu alanı ekleme, boş bırakma, sadece kapsam dışı olduğunu dokümante et.
7. **`gold_series_evidence`** — her Gold sütununun hangi kaynak seriden, hangi alignment
   yönteminden, hangi dimension filtresinden türediğini tutan provenance tablosu.
   **Kapsamı 7 tablonun TAMAMI olmalı**, sadece cross-source olanlarla sınırlı tutma —
   tek kaynaklı tablolar (precious metals, FinTürk) için de evidence satırı üret.

**Destek view — `gold_evds_catalog`:** Materialize edilmiş bir Gold tablosu değil, DuckDB view.
`data/bronze/evds/evds_catalog.parquet`'ten beslenir, Agent'ın henüz çekilmemiş EVDS serilerini
keşfedip on-demand ingestion tool'unu tetikleyebilmesi için. **Bu view'ı, `evds_loader_duzeltme
_prompt.md` görevindeki Konu 3/4 (batch/live ayrımı, nature_reviewed) tamamlanmadan bağlama —
sırasıyla ilerle (bkz. Faz 4 sıralaması aşağıda).**

**Somut kolon isimlendirmesi eksikti, şimdi tamamla:** 2-4 numaralı tablolar için Faz 3
dokümanında sadece kaynak seri referansları vardı, gerçek kolon adları yoktu. Implementasyona
başlamadan önce her tablo için nihai, açıklayıcı kolon adlarını (örn. `konut_kredisi_hacmi`,
ham `EVDS:TP.KTF12` kodu değil) bir defada belirle ve `notes/gold_column_naming.md`'ye yaz.

**Join Safety Rule (zorunlu, her cross-source builder'da uygulanacak):** BDDK Monthly
gözlemleri, EVDS skaler verisiyle asla sadece `date` üzerinden JOIN edilmeyecek. JOIN'den önce
her BDDK girdisi, Faz 2.5'te onaylanmış dimension slice'a (`variable=Toplam`, `variable=TP`,
`variable=Rasyo` vb.) indirgenecek. Her final aylık cross-source tablo, tarih başına tek satır
ürettiğini doğrulayan bir assert/test içerecek.

---

## FAZ 4 — Uygulama (Dalga Dalga, Sırayla — Atlama Yapma)

Faz 4'e başlamadan önce **`evds_loader_duzeltme_prompt.md`** görevinin tamamlanmış olması
gerekiyor (Parquet sorumluluğu, isim-bazlı nature katmanının kaldırılması, batch/live ayrımı,
`nature_reviewed` alanı). O görev bitmeden Dalga 2'deki `gold_evds_catalog` entegrasyonuna
geçme — Gold'a `nature_reviewed=False` seri sızma riski olur.

### Dalga 0 — Ön Koşullar (Kod Yazmadan Önce Kararlaştırılacak, Zaten Yukarıda Netleşti)
- [x] 7 tablo + evidence + catalog view kapsamı onaylandı (yukarıdaki liste)
- [ ] Her tablo için somut kolon adları `notes/gold_column_naming.md`'de netleşti
- [ ] `gold_series_evidence` kapsamının 7 tablonun tamamını kapsayacağı teyit edildi
- [ ] Precious metals tablosunun doğrudan Silver'dan (Aligned değil) besleneceği kuralı
      `notes/gold_design_principles.md`'ye tek cümle olarak eklendi
- [ ] Per-capita göstergelerin v1 kapsamı dışında olduğu dokümante edildi
- [ ] `tests/test_gold_join_uniqueness.py` YAZILDI (implementasyondan ÖNCE — her cross-source
      Gold tablosunun tarih başına tek satır ürettiğini doğrulayan test, TDD mantığıyla önce
      test sonra kod)

### Dalga 1 — Çekirdek Gold Tabloları
Sırayla, bağımlılık ve risk azaltma önceliğine göre:
1. `gold_periodic_change` — en basit, MoM/YoY hesaplama mantığını burada merkezi olarak kur,
   diğer tablolar bu mantığı tekrar üretmesin, buradan import etsin
2. `gold_series_evidence` — diğer tablolarla PARALEL doldur, sonradan eklemeye çalışma
   (hangi hesaplamanın nereden geldiğini o an unutursun)
3. `gold_credit_market`, `gold_housing_credit_market`, `gold_deposit_market` — üçü aynı
   desende (BDDK slice + EVDS JOIN), art arda yaz; kod tekrarını fark edip ortak bir
   `build_cross_source_gold_table()` yardımcı fonksiyonuna çıkar
4. `gold_precious_metal_ratios` — günlük-oran-önce kuralını özellikle test et
   (`test_gold_precious_metal_ratio_calculation.py`: `avg(a)/avg(b) != avg(a/b)` farkını
   somut sayılarla doğrulayan bir regresyon testi ekle)

### Dalga 2 — Coğrafi + Keşif Katmanı
5. `gold_finturk_province_credit_quality` — per-capita hariç, geri kalan kapsamla
6. `gold_evds_catalog` view'ı — SADECE `evds_loader_duzeltme_prompt.md` görevi bittikten sonra

### Genel Uygulama Kuralları
- Her Gold tablosunu Parquet olarak `data/gold/` altına yaz
- `lakehouse.duckdb` içinde bu Parquet'lere bakan view'ları tanımla (Silver'daki hibrit
  mimariyle aynı desen — gerçek veri Parquet'te, DuckDB sadece kapı)
- Gold tabloları için Catalog'a (ya da ayrı bir `gold_catalog`'a) her tablonun ne işe
  yaradığını, hangi kolonların ne anlama geldiğini açıklayan `description` alanları ekle
- Her tabloyu kendi testi + evidence kaydıyla birlikte AYRI bir PR/commit olarak teslim et,
  tek dev bir commit'te hepsini birden yapma — review'ı ve demo öncesi doğrulamayı kolaylaştırır
- En az 2-3 örnek soru (Faz 3 dokümanındaki "Örnek Soru Aileleri" listesinden) için, bu Gold
  tablolarını kullanan çalışan SQL sorgusu yaz ve gerçek sonuç döndüğünü doğrula

---

## Teslim Edilecekler

- [x] `nature` alanı: `silver_canonical.py`, `transformer.py`, `build_silver_bddk.py`,
      `evds_loader.py`, `build_silver_canonical.py`, `alignment_policies.py`, `align_service.py`
      güncellemeleri + ilgili testler (Faz 0 — TAMAMLANDI)
- [x] `notes/gold_pre_design_audit.md` — Faz 1 çıktısı (TAMAMLANDI)
- [x] `notes/gold_design_principles.md` — Faz 2 çıktısı (TAMAMLANDI)
- [x] Dimension slice kararları — Faz 2.5 çıktısı (TAMAMLANDI)
- [x] 7 tablo + evidence + catalog view tasarımı — Faz 3 çıktısı (TAMAMLANDI, onaylandı)
- [x] `evds_loader_duzeltme_prompt.md` görevi (ayrı prompt, Dalga 2'den önce bitmeli)
- [ ] `notes/gold_column_naming.md` — nihai kolon adları (Dalga 0)
- [ ] `tests/test_gold_join_uniqueness.py` — implementasyondan ÖNCE yazılacak (Dalga 0)
- [ ] `data/gold/*.parquet` — 7 tablo (Dalga 1-2, sırayla)
- [ ] DuckDB view tanımları (Gold için)
- [ ] Gold tabloları için catalog/description girişleri
- [ ] `tests/test_gold_tables.py` — her tablonun satır sayısı, kolon tipi, bilinen bir değerin
      doğru hesaplandığı (örn. mom_change_pct elle hesaplanıp karşılaştırılarak) doğrulanır
- [ ] `tests/test_gold_precious_metal_ratio_calculation.py` — günlük-oran-önce kuralının testi
- [ ] 2-3 örnek soru + bu Gold tablolarını kullanan çalışan SQL sorgusu

## Kritik Uyarılar

- Araştırma fazını (Faz 2) atlayıp direkt tablo tasarımına geçme — gerekçesiz tasarım, jüriye
  "rastgele agregasyon" izlenimi verir, "neden bu tabloyu seçtik" sorusuna cevap veremezsiniz.
- Gerçek veri dağılımına (Faz 1) bakmadan, önceki hackathon'lardan hatırladığın genel şablonları
  kopyalama — bu proje BDDK/FinTürk'e özel, generic bir "sales analytics gold layer" şablonu
  uydurmayın.
- Her tablo için "bu, Agent'ın hangi soru tipini daha kolay/doğru cevaplamasını sağlıyor"
  sorusuna tek cümlelik bir cevabın olmalı. Cevap veremiyorsan, o tablo muhtemelen gereksiz.
