# Mimari

NovaData KKB, Türkiye finans/kredi verilerini (BDDK, TCMB EVDS, FinTürk) tek bir
Lakehouse'ta toplar ve bu veri üzerinde **araç çağıran (tool-calling) bir LLM ajanı**
çalıştırır. Her cevap, ajanın çalıştırdığı araçların çıktısına dayanır ve izlenebilir.

- Veritabanı tanımları: [database_schema.md](database_schema.md) (koddan otomatik üretilir)
- Veri pipeline'ı adım adım: [../SETUP.md](../SETUP.md)
- Mimari kararlar: [decisions/adr/](decisions/adr/)

> **Sayılar hakkında not.** Aşağıdaki gözlem/seri sayıları repodaki `data/` klasöründen
> ölçülmüştür. SETUP.md'nin ilk doğrulama bölümü daha eski bir veri sürümünü
> (canonical 433.801 gözlem / 863 seri, aligned 305.283 gözlem / 817 seri) anar.

---

## 1. Veri Akışı

```
  BDDK CSV (haftalık/aylık/FinTürk)          TCMB EVDS JSON
              │                                    │
              ▼                                    ▼
      ┌───────────────────────────────────────────────────┐
      │ BRONZE   ham veri, değiştirilmeden arşivlenir     │  data/bronze/
      └─────────────────────────┬─────────────────────────┘
                                ▼
      ┌───────────────────────────────────────────────────┐
      │ SOURCE-SPECIFIC SILVER   kaynak başına normalize  │  data/silver/{bddk,evds}/
      │   BDDK 426.367 gözlem / 845 seri                  │
      │   EVDS  25.333 gözlem / 118 seri                  │
      └─────────────────────────┬─────────────────────────┘
                                ▼
      ┌───────────────────────────────────────────────────┐
      │ CANONICAL SILVER   ortak şema, kaynaklar arası    │  data/silver/silver.duckdb
      │   451.700 gözlem / 963 seri                       │
      │   anahtar: (series_id, date, dims)                │
      └─────────────────────────┬─────────────────────────┘
                                ▼
      ┌───────────────────────────────────────────────────┐
      │ MONTHLY ALIGNED   ortak aylık zaman ekseni        │  data/aligned/monthly/
      │   311.678 gözlem / 917 seri                       │
      │   seriye özel hizalama politikası (nature)        │
      └─────────────────────────┬─────────────────────────┘
                                ▼
      ┌───────────────────────────────────────────────────┐
      │ GOLD   analitik tablolar + lineage                │  data/gold/*.parquet
      │   gold_periodic_change (omurga)  311.704 / 917    │
      │   geniş görünümler + gold_series_evidence         │
      └─────────────────────────┬─────────────────────────┘
                                ▼
      ┌───────────────────────────────────────────────────┐
      │ lakehouse.duckdb   birleşik (unified) router      │  data/lakehouse.duckdb
      │   Gold view'leri + Silver/Aligned ATTACH          │
      │   LLM araçlarının tek giriş noktası (read-only)   │
      └───────────────────────────────────────────────────┘
```

| Katman | Ne yapar | Üreten script | Çıktı |
|---|---|---|---|
| Bronze | Kaynaktan ham veriyi indirir/doğrular; değiştirmez | `backend/scripts/bddk/build_bronze_bddk.py`, `backend/scripts/evds/build_bronze_evds.py` | `data/bronze/bddk/*/*.csv`, `data/bronze/evds/*.json` |
| Source-specific Silver | Kaynağın kendi frekansını (W/M/Q) koruyarak normalize eder; kümülatif (YTD) seriler ham korunur | `backend/scripts/bddk/build_silver_bddk.py`, `backend/scripts/evds/build_silver_evds.py` | `data/silver/{bddk,evds}/observations.parquet`, `series_metadata.parquet` |
| Canonical Silver | Tüm kaynakları tek şemaya (`CanonicalObservation` / `CanonicalSeriesMetadata`) getirir; `nature` ve `accumulation` semantiğini işler | `backend/scripts/build_silver_canonical.py` | `data/silver/silver.duckdb` |
| Monthly Aligned | Günlük/haftalık/aylık serileri ortak aya indirger. Politika seri doğasına bağlıdır (stock→last, flow→sum, rate/price→mean); ham kümülatif seriler dışlanır, çeyreklik seriler uydurma aylar üretmez | `backend/scripts/build_aligned_monthly.py` | `data/aligned/monthly/{aligned.duckdb, observations.parquet, series_metadata.parquet}` |
| Gold | Aylık/yıllık değişimleri hesaplar, çapraz kaynak görünümleri ve lineage tablosunu üretir | `backend/app/modules/gold/build_all_gold.py` (alt builder'ları sırayla çağırır) | `data/gold/*.parquet` |
| lakehouse.duckdb | Gold view'lerini ve Silver/Aligned veritabanlarını tek DuckDB'de birleştirir; araçlar buraya salt-okunur bağlanır | `backend/app/modules/gold/build_duckdb_views.py` | `data/lakehouse.duckdb` |

Semantik embedding kataloğu (`data/gold/series_embeddings.parquet`, 963 seri) ayrıca
`backend/scripts/generate_catalog_embeddings.py` ile üretilir ve `series_catalog_search`
aracı tarafından kullanılır.

Katmanların ilkeleri: ham veri asla üzerine yazılmaz; her katman bir öncekinden
script ile yeniden üretilebilir; alignment istek anında değil batch olarak çalışır.

---

## 2. Ajan Döngüsü

Ajan döngüsü **elle yazılmıştır** — LangGraph, LangChain gibi bir orkestrasyon
framework'ü kullanılmaz. Bu bilinçli bir karardır: döngü tek bir okunabilir fonksiyondur
(`run_agent`, [loop.py:97](../backend/app/agent/loop.py#L97)), her güvenlik ve sınır kontrolü
kodda görünür, test edilebilir ve harici bir bağımlılığın davranış değişikliğine açık değildir.
Sağlayıcı soyutlaması `LLMProvider` ABC ile korunur (`backend/app/core/llm_provider.py`).

```
 ┌────────────────────────────────────────────────────────────────────────────┐
 │ GİRİŞ                                                                      │
 │ (1) Kullanıcı sorusu şüpheli kalıp taraması + güvenli mesaj sarmalama      │
 │       flag_suspicious_content / format_safe_user_message   loop.py:110-111 │
 │       (varsa ek dosya: format_attached_document)           loop.py:112-118 │
 └───────────────────────────────────┬────────────────────────────────────────┘
                                     ▼
 ┌────────────────────────────────────────────────────────────────────────────┐
 │ (2) Mesaj listesi kurulur                                                  │
 │       [sistem promptu] + [sanitize edilmiş geçmiş] + [kullanıcı mesajı]    │
 │       get_system_prompt()  _sanitize_history()          loop.py:120-122    │
 │       geçmiş: son 6 tur, tur başına 4000 karakter, yalnız user/assistant   │
 │                                              _sanitize_history loop.py:23  │
 │       tool şeması: registry.to_openai_tools_format()        loop.py:123    │
 └───────────────────────────────────┬────────────────────────────────────────┘
                                     ▼
        ┌──────────────────────►  for iteration in 1..max_iterations  loop.py:128
        │                                    │
        │                                    ▼
        │            ┌───────────────────────────────────────────────┐
        │            │ (3) LLM çağrısı: provider.chat(messages,tools)│  loop.py:148
        │            │     on_event("llm_input")                     │  loop.py:137
        │            └──────────────────────┬────────────────────────┘
        │                                   ▼
        │                        tool_call var mı?  loop.py:151
        │                        │                    │
        │                     HAYIR                 EVET
        │                        │                    │
        │                        ▼                    ▼
        │   ┌──────────────────────────┐   ┌────────────────────────────────────┐
        │   │ (11) NİHAİ CEVAP         │   │ (4) assistant tool_calls mesaja    │
        │   │  kaynak ekleme:          │   │     eklenir            loop.py:168 │
        │   │  _ensure_citations_in_   │   ├────────────────────────────────────┤
        │   │  response      loop.py:77│   │ (5) PARALEL ÇAĞRI LİMİTİ           │
        │   │  on_event("llm_final")   │   │     max_parallel_calls = 2         │
        │   │  return       loop.py:164│   │     ilk 2 çalışır      loop.py:188 │
        │   └──────────────────────────┘   │     fazlası "limit aşıldı"         │
        │                                  │     mesajı alır        loop.py:408 │
        │                                  ├────────────────────────────────────┤
        │                                  │ Her çağrı için:                    │
        │                                  │ (6) tool kayıtlı mı?  loop.py:212  │
        │                                  │     hayır → hata mesajı → devam    │
        │                                  │ (7) ANTI-THRASHING KONTROLÜ        │
        │                                  │     _canonical_tool_signature      │
        │                                  │     (ad + sıralı JSON argüman)     │
        │                                  │     aynı çağrı daha önce           │
        │                                  │     BAŞARILI olduysa çalıştırma,   │
        │                                  │     "sonuç yukarıda" de            │
        │                                  │                loop.py:45,248-249  │
        │                                  │ (8) TOOL ÇALIŞTIRMA                │
        │                                  │     model_validate_json → run      │
        │                                  │                loop.py:285-290     │
        │                                  │     başarılıysa imza kaydedilir    │
        │                                  │     ve web kaynakları toplanır     │
        │                                  │                loop.py:296-297     │
        │                                  │ (9) HATA GERİ BESLEMESİ            │
        │                                  │     ValidationError  loop.py:336   │
        │                                  │     diğer Exception  loop.py:375   │
        │                                  │     → hata metni tool mesajı olur, │
        │                                  │       model kendini düzeltebilir   │
        │                                  │ (10) sonuç "tool" mesajı olarak    │
        │                                  │      eklenir; on_event("tool_output")
        │                                  └─────────────────┬──────────────────┘
        │                                                    │
        └────────────────────────────────────────────────────┘
                              (döngü başına dön)

   adım bütçesi (max_iterations) dolarsa:
                                     ▼
 ┌────────────────────────────────────────────────────────────────────────────┐
 │ (12) GRACEFUL FORCE-SYNTHESIS                                    loop.py:422│
 │      "yeni araç çağırma, elindekilerle en dürüst sentezi üret" mesajı eklenir│
 │      provider.chat(messages, tools=None)  → araçsız tek son çağrı  loop.py:444│
 │      cevap yine kaynak eklemeden geçer             loop.py:448  return :462 │
 └────────────────────────────────────────────────────────────────────────────┘
```

| # | Düğüm | Amaç | Kod |
|---|---|---|---|
| 1 | Giriş temizliği | Prompt-injection kalıplarını loglar, kullanıcı metnini güvenli etiketle sarar | `run_agent`, loop.py:110-118 |
| 2 | Mesaj kurulumu | Sistem promptu + sınırlı geçmiş + soru | loop.py:120-123, `_sanitize_history` :23 |
| 3 | LLM tool seçimi | Model hangi aracı hangi parametreyle çağıracağına karar verir | loop.py:148 |
| 5 | Paralel limit | Tek turda en fazla 2 araç; gecikme patlamasını önler | loop.py:126, 188-190, 408 |
| 7 | Anti-thrashing | Aynı başarılı çağrının tekrarını engeller | `_canonical_tool_signature` :45, loop.py:248 |
| 8 | Çalıştırma | Pydantic ile parametre doğrulama, sonra araç | loop.py:285-290 |
| 9 | Hata geri beslemesi | Hata istisna olarak yükselmez, modele mesaj olarak döner | loop.py:336, 375 |
| 11 | Kaynak ekleme | `web_search` / `web_url_reader` URL'lerini `### 🔗 Kaynaklar` altında ekler | `_collect_sources_from_tool_result` :54, `_ensure_citations_in_response` :77 |
| 12 | Force-synthesis | Bütçe bitince araçsız, dürüst bir sentez ister | loop.py:422-462 |

Sistem promptu: `backend/app/prompts/system_prompt.md` (kapsam politikası dahil).
Prompt/sanitizer katmanı: `backend/app/prompts/sanitizer.py`.

---

## 3. Araç Katmanı

12 araç, `create_default_tool_registry()` ile kaydedilir
([tool_registry.py](../backend/app/agent/tool_registry.py)). Her araç bir Pydantic `Input`
şemasına sahiptir; şema hem LLM'e tool tanımı olarak verilir hem de çağrıda doğrulama için kullanılır.

| Kategori | Araç | Ne yapar |
|---|---|---|
| **Keşif** | `series_catalog_search` | Doğal dille seri arar (embedding kataloğu, kosinüs benzerliği); doğru `series_id`'yi bulur |
| **Sorgulama** | `lakehouse_query` | Silver/Aligned/Gold tablolarından yapılandırılmış, salt-okunur, sınırlı veri getirir (ham SQL almaz) |
| | `evds_data_service` | Lakehouse'ta olmayan TCMB serilerini resmi EVDS'te arar / canlı yükler |
| **Dış dünya** | `web_search` | Sistem verisiyle cevaplanamayan güncel/harici bilgi için web araması |
| | `web_url_reader` | Verilen URL'deki HTML/CSV/Excel/PDF/görsel içeriği metne çevirir (içerik "güvenilmez" etiketiyle sarılır) |
| **Zorunlu analitik** | `change_detection` | Serinin aylık (MoM) / yıllık (YoY) değişimi |
| | `anomaly_detection` | Tek seride z-score tabanlı olağan dışı yükseliş/düşüş |
| | `causality_check` | İki seri arası korelasyon / ilişki analizi (nedensellik kanıtı değildir) |
| **İleri analitik** | `real_value_deflator` | Nominal serileri TÜFE'den arındırır, reel büyüme ve grafik üretir |
| | `elasticity_and_sensitivity_analyzer` | İki değişken arası esneklik / duyarlılık (log-log OLS), grafikli |
| | `risk_concentration_analyzer` | CR3/CR5 ve HHI ile bölgesel/kurumsal yoğunlaşma, Pareto grafiği |
| | `turning_point_and_cycle_detector` | Dönüm noktaları, genişleme/daralma fazları, döngü görselleştirmesi |

`change_detection`, `anomaly_detection` ve `causality_check` aynı omurga tablo
(`gold_periodic_change`) üzerinde çalışır; hiçbiri belirli bir veri kaynağına özel değildir.

---

## 4. Güven Katmanı

Cevapların kaynağı ve nasıl üretildiği iki yerden izlenebilir:

**a) Trace akışı — hangi araç, hangi parametre, ne kadar sürdü**

```
  run_agent ──on_event(kind, payload)──►  API katmanı (backend/app/api/routes.py)
                                              │
              ┌───────────────────────────────┴──────────────────────────┐
              ▼                                                          ▼
   POST /api/v1/ask/stream                                  POST /api/v1/ask
   on_event → SSE olayları                                  _collect → trace listesi
   (tool_name, iteration, success,                          {type: tool_call | tool_result,
    duration_s, llm_decision'da                              tool_name, arguments,
    arguments; llm_input ham                                 success, duration_s}
    yayınlanmaz: mesaj geçmişi                                       │
    ve sistem promptu sızmaz)                                        ▼
              │                                          yanıt: data.trace
              └──────────────────┬───────────────────────────────────┘
                                 ▼
                    Frontend: kanıt / izlenebilirlik paneli
                    (frontend/app/[locale]/page.tsx, MessageReasoningAccordion)
```

`llm_input` olayı tüm mesaj geçmişini ve sistem promptunu taşıdığı için istemciye
**asla ham yayınlanmaz**; yalnızca seçilmiş alanlar gönderilir. `arguments` ise
modelin ürettiği tool çağrısı JSON'udur, prompt değildir.

**b) Veri lineage'ı — `gold_series_evidence`**

Geniş Gold tablolarındaki her üretilmiş kolon için bu tabloda kayıt vardır: hangi
Gold tablosu ve kolonu, hangi kaynak seriden (`series_id`), hangi filtre ve hangi
hizalama yöntemiyle türetildi. Tablo `backend/app/modules/gold/build_evidence.py` ile
üretilir; şeması [database_schema.md](database_schema.md) içindedir.
Bir sayının "nereden geldiği" bu tablodan koda bakmadan okunabilir.
