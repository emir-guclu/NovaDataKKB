# Open Decisions (Acik Kararlar)

> Projenin almak zorunda oldugu her **proje/sistem seviyesi** (cross-feature veya henuz hicbir feature'a bagli olmayan) kararin backlog listesi. Her satir bir karar. Bu dosyanin parcasi oldugu tum surecin detayi icin bkz. `docs/decisions/decision-pipeline.md`.

> **Feature-ozel kararlar burada degil.** Bir agent (Analyst, Architect, ...) belirli bir `F-nn` feature'i uzerinde calisirken karsilastigi ve sadece o feature'i ilgilendiren belirsizlikler, `docs/handoff/<feature-id>/open-decisions.md` dosyasina yazilir (paralel calisan birden fazla kisinin ayni ID'yi cakistirmasini onlemek icin - bkz. `docs/decisions/decision-pipeline.md`). Bir belirsizlik birden fazla feature'i veya tum sistemi etkiliyorsa (or. LLM saglayicisi, auth stratejisi), o zaman buraya, bu merkezi dosyaya yazilir. Feature dosyasindaki bir karar `DECIDED` olup ADR gerektirdiginde, satir feature dosyasinda kalir; ilgili ADR o dosyadaki satira referans verir, satir buraya kopyalanmaz.

## ID semasi

| Onek | Kategori | Ornek |
|---|---|---|
| `T-` | Teknik - stack, altyapi, kutuphaneler, tooling | `T-01` LLM saglayicisi |
| `P-` | Urun - kullaniciya gorunen davranis, kapsam, bonus ozellikler | `P-01` toplu mu yoksa tek tek mi soru uretimi |
| `S-` | Surec - ekip is akisi, agent kadrosu, konvansiyonlar | `S-01` branch stratejisi |

ID'ler onek basina sirali verilir, **asla tekrar kullanilmaz** ve **asla yeniden numaralandirilmaz**.

## Status degerleri

| Status | Anlami |
|---|---|
| `OPEN` | Henuz baslanmadi. |
| `IN_DISCUSSION` | Su an `decision-facilitator` tarafindan ele aliniyor. |
| `DECIDED` | Kapandi. Teknik kararlar **mutlaka** bir ADR'ye baglanmali. |
| `DECIDED_NO_ADR` | Karar zaten bir yerde (genelde constitution'da) uygulanmis ama henuz kayda gecmemis. Borc durumu - `DECIDED`'a donusmeli. |
| `DEFERRED` | Bilincli olarak ertelendi. Karari tekrar acacak tetikleyici belirtilmeli. |

## Kurallar

1. Satirlar asla silinmez. Alakasiz hale gelen bir karar, bir sebep belirtilerek `DEFERRED` olur.
2. `decision-facilitator`, konusma sirasinda bir karar ortaya cikarsa yeni satir ekleyebilir.
3. Bir satiri `DECIDED` yapmak sadece insana aittir. Bir agent onerebilir, asla sonuclandiramaz.
4. ADR baglantisi olmayan `DECIDED` durumundaki bir teknik satir bir hatadir.
5. Tersine cevrilen bir karar icin yeni bir satir/ADR acilir ve eskisinin yerini alir; eski satir sadece `ADR` baglantisi disinda duzenlenmez.
6. `Ilgili Feature` kolonu, bu merkezi dosyaya yazilan bir kararin hangi feature(lar)i etkiledigini iz birakmak icindir (cross-feature kararlar icin - bkz. dosya basindaki not). Birden fazla feature'i etkileyen kararlarda virgulle ayrilmis birden fazla ID yazilabilir; bos birakilmasi karar surecini etkilemez, sadece filtrelemeyi zorlastirir.
7. Bir feature'a ozel (yalnizca o feature'i ilgilendiren) bir belirsizlik bu dosyaya **yazilmaz** - `docs/handoff/<feature-id>/open-decisions.md` dosyasina yazilir (bkz. dosya basindaki not). Bu merkezi dosya yalnizca proje/sistem seviyesi ve cross-feature kararlar icindir.

## Karar Backlog'u

### Teknik Kararlar (`T-`)

| ID | Status | Karar | Neden onemli | Ilgili Feature | Tarih | ADR |
|---|---|---|---|---|---|---|
| T-01 | OPEN | Kloudeks model envanteri ve limitleri nedir? | Model adlari, context uzunlugu, tool-calling, JSON mode, embedding ve rate limit bilgileri model kademelendirmesini belirler. |  | 2026-09-07 |  |
| T-02 | OPEN | Kloudeks API'sine self-hosted sunucudan erisim mumkun mu? | IP/ag kisiti deployment mimarisini VPS, VPN veya laptop+tunnel seceneklerinden birine zorlar. |  | 2026-09-07 |  |
| T-03 | OPEN | Canli deploy hedefi ne olacak? | Diger altyapi kararlarina bagli olarak maliyet, kurulum hizi ve ekip deneyimi acisindan hedef ortam secilmeli. |  | 2026-09-07 |  |
| T-05 | OPEN | Ana veritabani teknolojisi ne olacak? | PostgreSQL, SQLite veya NoSQL secimi kalicilik, analitik sorgular, deployment karmasikligi ve demo guvenilirligini belirler. |  | 2026-09-07 |  |
| T-06 | OPEN | Veritabani tablo sinirlari ve semasi ne olacak? | Kaynak metaverisi, seriler, sorgular, cevaplar, geri bildirimler ve loglar icin tablo sinirlari netlesmeden backend sozlesmeleri sabitlenemez. |  | 2026-09-07 |  |
| T-07 | OPEN | Veri cekme ve guncelleme stratejisi nasil calisacak? | Ana verilerin tek seferlik yuklenmesi ile scheduler destekli surekli guncelleme arasindaki secim veri tazeligi, maliyet ve operasyonel riski etkiler. |  | 2026-09-07 |  |
| T-09 | OPEN | Veri toplamada kullanilacak kutuphaneler neler olacak? | HTTP client, PDF parsing, Excel okuma, HTML scraping, OCR ve API istemcisi secimleri kaynak kapsamini ve bakim riskini belirler. |  | 2026-09-07 |  |
| T-10 | OPEN | BDDK yil-ici kumulatif tablo metaverisi var mi? | Resmi liste varsa decumulate modulu otomatik tespit ve capraz dogrulama ile daha guvenilir hale gelir. |  | 2026-09-07 |  |
| T-11 | OPEN | Borsa Istanbul verileri nasil ele alinacak? | BIST 100, kiymetli madenler, PDF ve grafik kaynaklarinin cekilmesi, normalize edilmesi ve sunulmasi ek connector ve parsing stratejisi gerektirir. |  | 2026-09-07 |  |
| T-12 | OPEN | Web arama motoru altyapisi ne olacak? | Anahtarsiz ve acik kaynak olma beklentisi, kurulum kolayligi ve demo gunu stabilitesi mimariyi etkiliyor. |  | 2026-09-07 |  |
| T-13 | OPEN | Ticari arama API'leri kullanilabilir mi? | Ucuncu taraf servis kisitinin LLM API'leriyle mi sinirli oldugu netlesmeden arama mimarisi kesinlesemez. |  | 2026-09-07 |  |
| T-14 | OPEN | Prompt icindeki URL, PDF, gorsel ve Excel girdileri nasil islenecek? | Kullanici girdisi veya URL uzerinden gelen dosyalarin indirme, parse etme, OCR, tablo cikarma, guvenlik ve kaynaklama akisi netlesmeli. |  | 2026-09-07 |  |
| T-15 | OPEN | Kloudeks'te gorsel girdi alabilen VLM var mi? | VLM yoksa url_ingest kapsaminda OCR ve tablo yeniden yapilandirma yaklasimi gerekir. |  | 2026-09-07 |  |
| T-16 | OPEN | Agentic AI altyapisi nasil tasarlanacak? | Planner, tool router, executor, verifier ve answer composer gibi rollerin tek ajan mi cok adimli pipeline mi olacagi sistem davranisini belirler. |  | 2026-09-07 |  |
| T-17 | OPEN | Dogal dil sorulari generic olarak tool'lara nasil yonlendirilecek? | LLM tabanli router, veri kaynagi analizi, tool secimi ve tool-ozel sistem prompt'lari genel cozum beklentisinin merkezinde yer alir. |  | 2026-09-07 |  |
| T-18 | OPEN | AI'a hangi bilgiler hangi formatta verilecek? | Semalar, kaynak metaverisi, tool sozlesmeleri, kullanici baglami, veri ornekleri ve ara sonuclarin prompt'a nasil tasinacagi dogruluk ve token maliyetini etkiler. |  | 2026-09-07 |  |
| T-19 | OPEN | Bir kullanici sorusu icin kac LLM istegi atilacak? | Soru anlama, tool secimi, veri ihtiyaci belirleme, cevap uretme ve dogrulama adimlarinin ayri veya birlesik cagrilar olmasi maliyet, hiz ve kaliteyi belirler. |  | 2026-09-07 |  |
| T-20 | OPEN | Model kademelendirmesinde hangi gorev hangi modele atanacak? | Kloudeks envanterine bagli olarak hiz, maliyet ve dogruluk dengesi icin model routing stratejisi secilmeli. |  | 2026-09-07 |  |
| T-21 | OPEN | RAG sistemi hangi kapsamda kullanilacak? | Dokuman, metaveri, kaynak aciklamalari ve onceki analizlerin retrieval kapsami netlesmeden cevap kalitesi ve izlenebilirlik standardi belirlenemez. |  | 2026-09-07 |  |
| T-22 | OPEN | LLM ciktilari nasil dogrulanacak? | Schema validation, tool-result grounding, kaynak referansi, hesaplama yeniden kontrolu ve hallucination guardrail'leri olmadan analitik cevaplar guvenilir olmayabilir. |  | 2026-09-07 |  |
| T-23 | OPEN | LLM call log'lari tutulacak mi? | Prompt, model, latency, token, maliyet, tool trace ve cevap kalitesi kayitlari debug, audit ve optimizasyon icin gerekli olabilir; KVKK ve gizlilik sinirlariyla dengelenmeli. |  | 2026-09-07 |  |
| T-24 | OPEN | Veri analizi hangi teknoloji ve yontemlerle yapilacak? | Pandas, Polars, DuckDB, SQL, istatistik kutuphaneleri veya lakehouse motoru secimi analitik derinlik ve performansi etkiler. |  | 2026-09-07 |  |
| T-25 | OPEN | Neden-sonuc iliskisi ve korelasyon nasil hesaplanacak? | Korelasyon, gecikmeli iliski, anomali, change detection ve nedensellik iddialarinin istatistiksel sinirlari belirlenmezse cevaplar yaniltici olabilir. |  | 2026-09-07 |  |
| T-26 | OPEN | Grafik olusturma stratejisi ne olacak? | Grafiklerin backend chart spec, frontend rendering veya LLM destekli onerilerle uretilmesi dogruluk, tekrar uretilebilirlik ve UI kontrolunu etkiler. |  | 2026-09-07 |  |
| T-27 | OPEN | Frontend dosya yapisi ve coklu dil destegi nasil olacak? | Sayfa, component, state, API client ve i18n sinirlari bastan netlesmezse UI gelistirmesi daginik ve tekrarli hale gelebilir. |  | 2026-09-07 |  |
| T-28 | OPEN | Frontend teknolojisi ne olacak? | 13 gunluk sure icinde ekip deneyimi, gelistirme hizi ve demo kalitesi dengelenmeli; 2026-09-08'e kadar kilitlenmeli. |  | 2026-09-07 |  |
| T-29 | OPEN | Sayfalama ve sorgu limit stratejisi ne olacak? | `limit`, `offset`, `cursor`, `skip` ve maksimum sonuc sinirlari API performansi ile kullanici deneyimini dogrudan etkiler. |  | 2026-09-07 |  |
| T-30 | OPEN | Cache mekanizmasi nasil olacak ve hangi veriler saklanacak? | Kaynak metaverisi, sorgu sonuclari, RAG retrieval sonuclari, LLM yanitlari veya grafik spesifikasyonlarinin cache'lenmesi maliyet ve tutarlilik dengesini etkiler. |  | 2026-09-07 |  |
| T-31 | OPEN | Performans optimizasyonu icin hangi yaklasimlar uygulanacak? | Indeksleme, async isleme, batch sorgular, background jobs ve model cagri azaltma stratejileri gecikme ve maliyeti belirler. |  | 2026-09-07 |  |
| T-32 | OPEN | API sozlesmesi nasil tanimlanacak? | REST endpoint standardi, response envelope, error format ve OpenAPI uretimi netlesmeden frontend-backend entegrasyonu kirilgan hale gelir. |  | 2026-09-07 |  |
| T-33 | OPEN | Background job altyapisi ne olacak? | Scheduler disinda queue, worker, retry, dead-letter ve job status takibi karar verilmeden veri isleme surecleri guvenilir tasarlanamaz. |  | 2026-09-07 |  |
| T-34 | OPEN | Dosya saklama stratejisi ne olacak? | Yuklenen PDF, Excel ve gorsel dosyalarin local disk, object storage veya gecici storage olarak tutulmasi maliyet, guvenlik ve deployment davranisini etkiler. |  | 2026-09-07 |  |
| T-35 | OPEN | Migration ve seed stratejisi ne olacak? | DB semasinin versiyonlanmasi ve demo verilerinin tekrarlanabilir yuklenmesi gelistirme, test ve canli deploy guvenilirligi icin gerekli. |  | 2026-09-07 |  |
| T-36 | OPEN | Observability standardi ne olacak? | App log, error tracking, metrics, tracing ve healthcheck sinirlari belirlenmeden hata ayiklama ve demo gunu operasyonu zorlasir. |  | 2026-09-07 |  |
| T-37 | OPEN | Test stratejisi ne olacak? | Unit, integration, tool-level eval, golden question set ve smoke test ayrimi netlesmeden dogruluk ve regresyon takibi yapilamaz. |  | 2026-09-07 |  |
| T-38 | OPEN | Kaynak ve citation standardi ne olacak? | Cevaplarda hangi veri, tarih, kaynak ve hesaplama kullanildiginin gosterilmesi guvenilirlik ve denetlenebilirlik icin kritik olabilir. |  | 2026-09-07 |  |
| T-39 | OPEN | Veri dogrulama ve schema standardi ne olacak? | Pydantic modelleri, request/response validasyonu, tool input-output sozlesmeleri, LLM structured output dogrulama ve DB oncesi veri kalite kontrolleri icin ortak standart belirlenmeli. |  | 2026-09-07 |  |
| T-40 | OPEN | Semantik katalog ve hybrid search stratejisi nasil olacak? | BM25, embedding aramasi, RRF, `synonyms.yaml` kapsami ve reranking mantigi netlesmeden `search_series` tool sozlesmesi sabitlenemez. |  | 2026-09-07 |  |
| T-41 | OPEN | Artifact registry ve oturum durumu tasarimi nasil olacak? | Cok adimli senaryolarda "bu tabloyu" veya "bozmadan" gibi referanslarin cozumu, session tablolarinin tutulmasi ve schema koruyan transform operasyonlari netlesmeli. |  | 2026-09-07 |  |
| T-42 | OPEN | Veri revizyonu ve vintage modellemesi nasil olacak? | BDDK gibi sonradan revize edilebilen veriler icin vintage alanlari, gecmise donuk sorgu tutarliligi ve raporda revizyon gosterimi belirlenmeli. |  | 2026-09-07 |  |
| T-43 | OPEN | Secret ve credential yonetimi nasil olacak? | EVDS ve Kloudeks gibi API anahtarlarinin commit edilmemesi icin `.env` stratejisi, secret dagitimi ve pre-commit kontrolu netlesmeli. |  | 2026-09-07 |  |
| T-44 | OPEN | Prompt injection ve guvenilmeyen icerik izolasyonu nasil saglanacak? | `url_ingest` ve `web_search` kaynakli iceriklerin komut gibi yorumlanmasini onlemek icin sanitization, etiketleme ve validation kurallari belirlenmeli. |  | 2026-09-07 |  |
| T-45 | OPEN | Rapor disa aktarim implementasyonu nasil olacak? | `report_export` tool'unun PDF, XLSX ve Markdown ciktisini hangi kutuphanelerle ve hangi format standardiyla uretecegi netlesmeli. |  | 2026-09-07 |  |

### Urun Kararlari (`P-`)

| ID | Status | Karar | Neden onemli | Ilgili Feature | Tarih | ADR |
|---|---|---|---|---|---|---|
| P-01 | OPEN | Urun ismi ne olacak? | README, sunum ve demo boyunca tutarli kullanilacak; bir kez secilip degistirilmemeli. |  | 2026-09-07 |  |
| P-02 | OPEN | Mockup'lar ve genel frontend tarzi nasil belirlenecek? | Demo kalitesi ve tutarli kullanici deneyimi icin ekran akislari, dashboard tarzi, grafik sunumu ve gorsel dil erken netlesmeli. |  | 2026-09-07 |  |
| P-03 | OPEN | Zorunlu tool seti ve sonrasinda eklenecek ek tool'lar ne olacak? | Lakehouse, Web Search, Web URL Agent, Anomali, Causality ve Change Detection tool'lari disinda hangi tool'larin hangi sirayla eklenecegi kapsam disiplinini belirler. |  | 2026-09-07 |  |
| P-04 | OPEN | BDDK/EVDS disi kaynaklar kalici connector olarak eklenecek mi? | Ek kaynaklarin puan getirip getirmedigi ve kapsam disi sayilip sayilmayacagi urun kapsamini etkiler. |  | 2026-09-07 |  |
| P-05 | OPEN | Zorunlu kaynaklar disinda hangi ek veri kaynaklari cekilebilir? | BDDK/EVDS disinda eklenecek kaynaklar urun degerini artirabilir ama kapsam, guvenilirlik ve lisans riskini buyutur. |  | 2026-09-07 |  |
| P-06 | OPEN | Hesap acma ve kullanici bazli limit olacak mi? | Anonim kullanim, login, soru sorma limiti ve kullanici bazli kota karari urun kapsamini ve backend auth ihtiyacini belirler. |  | 2026-09-07 |  |
| P-07 | OPEN | Admin hesabi ve admin dashboard olacak mi? | Sorulari, feedback'leri, kullanim metriklerini ve hata loglarini izleme ihtiyaci varsa ek ekranlar ve yetki modeli gerekir. |  | 2026-09-07 |  |
| P-08 | OPEN | Cevap formati standardi ne olacak? | Kisa cevap, tablo, grafik, kaynaklar, metodoloji ve uyarilarin hangi sirayla sunulacagi kullanici deneyimi ve guvenilirlik algisini belirler. |  | 2026-09-07 |  |
| P-09 | OPEN | Demo icin ana kullanim senaryolari hangileri olacak? | Her karar demo akisina hizmet etmeli; ana senaryolar netlesmezse kapsam genisler ve uygulama odagini kaybeder. |  | 2026-09-07 |  |
| P-10 | OPEN | Kanit paneli ve ajan adimlari zaman cizelgesi ne kadar detayli olacak? | SQL syntax highlight, kullanilan yontem ve parametreler, dogrulama rozeti ve ajan izinin UI'da ne kadar gosterilecegi demo ayrisma gucunu etkiler. |  | 2026-09-07 |  |
| P-11 | OPEN | Cok adimli senaryolarda kullanici deneyimi nasil olacak? | Son artifact referansi, diff gosterimi, korunan satir/sutun bilgisi ve eklenen donusumlerin kullaniciya nasil sunulacagi netlesmeli. |  | 2026-09-07 |  |

### Surec Kararlari (`S-`)

| ID | Status | Karar | Neden onemli | Ilgili Feature | Tarih | ADR |
|---|---|---|---|---|---|---|
| S-01 | OPEN | Canlida deploy edilmis cozum tanimi nedir? | Kendi VPS'nin yeterli olup olmadigi teslimat kriterinin dogru karsilanmasini belirler. |  | 2026-09-07 |  |
| S-02 | OPEN | Degerlendirme rubrigi agirliklari ve kod review beklentileri nedir? | Zaman ve efor tahsisinin dogru onceliklendirilmesi icin puanlama beklentileri netlesmeli. |  | 2026-09-07 |  |
| S-03 | OPEN | 2026-09-20 sonrasi commit atmak serbest mi? | 2026-09-21 ile 2026-10-04 arasinin prova mi gelistirme mi olacagini belirleyen stratejik surec karari. |  | 2026-09-07 |  |
| S-04 | OPEN | Demo gunu sunum formati netlesene kadar prova senaryosu nasil kurgulanacak? | Sure siniri, slayt sayisi ve demo akisinin prova planiyla uyumlu olmasi gerekiyor. |  | 2026-09-07 |  |
| S-05 | OPEN | 2026-10-17 final sunum formati nedir? | Sure, konusmaci sayisi, ekran ve internet kosullari prova planini belirler. |  | 2026-09-07 |  |
| S-06 | OPEN | KVKK ve veri gizliligi mantigi nasil ele alinacak? | Kullanici girdileri, yuklenen dosyalar, loglar ve LLM'e giden icerikler icin saklama, maskeleme ve silme kurallari belirlenmeli. |  | 2026-09-07 |  |
| S-07 | OPEN | Definition of Done ne olacak? | Bir tool veya feature'in hangi kosullarda bitti sayilacagi netlesmeden kalite ve kapsam kontrolu tutarsiz kalir. |  | 2026-09-07 |  |
| S-08 | OPEN | Risk ve fallback plani nasil takip edilecek? | Kloudeks, veri kaynagi, deploy veya scraping bozulursa cache isitma, offline fallback ve video yedek dahil hangi alternatife donulecegi ve kimlerin ne zaman test edecegi belirlenmeli. |  | 2026-09-07 |  |
| S-09 | OPEN | Branch stratejisi ve PR review sureci nasil olacak? | Main branch korumasi, her degisikligin PR ile gitmesi, en az bir review alinmasi ve commit gecmisinin juri tarafindan incelenmesi nedeniyle ekip kural seti netlesmeli. |  | 2026-09-07 |  |
| S-10 | OPEN | Bagimlilik lisans denetimi sureci nasil olacak? | Yasakli arac ve lisans riski icin `pip-licenses` gibi kontrollerin ne siklikla calisacagi ve `docs/licenses.md` sorumlulugu belirlenmeli. |  | 2026-09-07 |  |
| S-11 | OPEN | Eval harness soru sorumlulugu nasil dagitilacak? | Golden question set icinde gelistirme yapilmamis konularin da yer almasi icin kimin hangi kategoriden kac soru ekleyecegi netlesmeli. |  | 2026-09-07 |  |

## Triage

### Katman 1 - Ekip ici, 2026-09-08'e kadar kilitlenmeli

Kod yazilmaya baslamadan once kapanmasi gereken, sonradan degistirilmesi pahali mimari iskelet kararlari.

- `P-01`: urun adi.
- `T-28`: frontend teknolojisi (`T-04` kapatildi).
- `T-05`, `T-24`: veritabani ve veri analizi teknolojisi; ayni oturumda birlikte ele alinmali.
- `T-16`, `T-19`: agent mimarisi ve bir soru icin LLM cagri sayisi; art arda konusulmali.
- `S-09`: branch stratejisi ve PR review sureci.

### Katman 2 - Ayni hafta icinde teknik guardrail

Ekip standardi olarak bastan ayni uygulanmasi gereken, kisa kararlarla kapatilabilecek guardrail'ler.

- `T-32`: API sozlesmesi.
- `T-39`: veri dogrulama ve schema standardi.
- `T-43`: secret ve credential yonetimi.
- `T-37`: test stratejisi.

### Katman 3 - Cekirdek ozellikler yazilmadan once, 2026-09-10/11'e kadar

Ilk uctan uca cevabi ve 2026-09-11 kilometre tasini dogrudan etkileyen kararlar.

- `T-06`, `T-40`, `T-41`: DB semasi, semantik katalog/hybrid search ve artifact registry.
- `T-17`, `T-18`, `T-20`: tool routing, AI'a verilecek bilgi formati ve model kademelendirme.
- `T-22`, `T-38`, `P-08`: LLM dogrulama, citation standardi ve cevap formati.
- `P-03`: zorunlu tool seti ve ek tool sirasi.
- `T-09`, `T-11`: connector kutuphaneleri ve Borsa Istanbul yaklasimi (`T-08` kapatildi).

### Katman 4 - Gelistirme ilerledikce organik netlesebilir

Ilgili modul yazilirken makul default ile kapatilabilecek veya daha dusuk degisiklik maliyetli kararlar.

- `T-07`, `T-12`, `T-14`, `T-21`, `T-23`, `T-25`, `T-26`, `T-27`, `T-29`, `T-30`, `T-31`.
- `T-33`, `T-34`, `T-35`, `T-36`, `T-42`, `T-44`, `T-45`.
- `P-02`, `P-04`, `P-05`, `P-06`, `P-07`, `P-09`, `P-10`, `P-11`.
- `S-04`, `S-05`, `S-06`, `S-07`, `S-08`, `S-10`, `S-11`.

## Notlar

- 2026-09-07 tarihinde kapatilmasi kritik gorunen kararlar: `P-01`, `T-02`, `T-28`; `T-01` ve `T-15` icin Mentor/Slack sorulari gonderilmis olmali.
- Mentor/Slack kaynakli satirlar dis onay bekler; ekip-ici satirlar ekip hizalanmasi ile kapatilabilir.
