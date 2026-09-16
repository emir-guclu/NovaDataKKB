# NovaData KKB — NOVA Analytics Agent

Türkiye finans/kredi verilerini (EVDS, BDDK) tek bir Lakehouse'ta toplayıp, kaynağı izlenebilir ve araç-çıktılarına dayalı cevaplar üreten bir LLM ajanı ve API/arayüzü.

---

## 1. Mimari

```
┌──────────────┐   ┌──────────────┐
│  EVDS API    │   │  BDDK CSV    │        Connector'lar
│  Connector   │   │  Connector   │        (Bronze üretimi)
└──────┬───────┘   └──────┬───────┘
       │                  │
       ▼                  ▼
┌─────────────────────────────────────────────────────────┐
│                     LAKEHOUSE (DuckDB)                   │
│  ┌─────────┐   ┌─────────┐   ┌──────────┐   ┌─────────┐  │
│  │ Bronze  │→ │ Silver  │→ │ Aligned  │→ │  Gold   │  │
│  │ ham veri│  │ normalize│  │ ortak zaman│  │ analitik│  │
│  └─────────┘   └─────────┘   └──────────┘   └─────────┘  │
└───────────────────────────┬───────────────────────────────┘
                             ▼
                    ┌─────────────────┐
                    │   Tool Katmanı   │  lakehouse_query, evds_data_service,
                    │                  │  series_catalog_search, web_search,
                    │                  │  change_detection, anomaly_detection...
                    └────────┬─────────┘
                             ▼
                    ┌─────────────────┐
                    │  Agent Döngüsü   │  backend/app/agent/loop.py
                    │  (tool-calling)  │  run_agent(): LLM ↔ tool iterasyonu
                    └────────┬─────────┘
                             ▼
                    ┌─────────────────┐
                    │   FastAPI API    │  POST /api/v1/ask
                    │                  │  GET  /health
                    └────────┬─────────┘
                             ▼
                    ┌─────────────────┐
                    │  Next.js Arayüz  │  Sohbet + İzlenebilirlik paneli
                    └─────────────────┘

  ── Güven Katmanı: Kaynak Gösterimi · İzlenebilirlik · Doğruluk Kontrolü ──
     (yukarıdaki tüm aşamaların altından geçer: her tool çağrısı ve süresi
      API yanıtındaki `data.trace` alanında, kaynaklar `### Kaynaklar`
      bölümünde raporlanır)
```

## 2. Hızlı Başlangıç (Docker)

```bash
cp .env.example .env
# .env içine en az EVDS_API_KEY ve MIA_API_KEY değerlerini doldurun.

docker compose up -d --build
curl -f http://localhost:8000/health
```

Arayüz: http://localhost:3000 — API: http://localhost:8000

`data/` klasörü backend konteynerine `./data:/app/data` olarak bağlanır; Lakehouse'u
sıfırdan üretmek için bkz. [SETUP.md](SETUP.md).

## 3. Geliştirme Kurulumu (Docker'sız)

Backend ve frontend'i ayrı ayrı, hot-reload ile çalıştırmak için:

```bash
# Backend
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=backend uvicorn backend.app.main:app --reload --port 8000

# Frontend
cd frontend && npm install && npm run dev
```

Veri pipeline'ının (Bronze → Silver → Aligned → Gold) sıfırdan nasıl üretileceği,
katman katman [SETUP.md](SETUP.md) içinde anlatılmıştır.

## 4. Veri Katmanları

| Katman  | İçerik                                           | Üretim scripti (özet)                          |
|---------|---------------------------------------------------|-------------------------------------------------|
| Bronze  | EVDS/BDDK'dan indirilen ham veri                  | `backend/scripts/{evds,bddk}/build_bronze_*.py` |
| Silver  | Kaynak bazlı normalize edilmiş seri + metadata    | `backend/scripts/{evds,bddk}/build_silver_*.py` |
| Canonical Silver | Ortak şemaya getirilmiş, çapraz kaynak veri | `backend/scripts/build_silver_canonical.py`     |
| Aligned | Ortak (aylık) zaman eksenine hizalanmış veri      | `backend/scripts/build_aligned_monthly.py`      |
| Gold    | Analitik, LLM'in doğrudan sorguladığı tablolar    | `backend/app/modules/gold/build_all_gold.py`    |

Gold katmanındaki tablolar (bkz. [backend/app/models/lakehouse_models.py](backend/app/models/lakehouse_models.py)):

| Tablo                                     | İçerik                                                        |
|--------------------------------------------|----------------------------------------------------------------|
| `gold_periodic_change`                     | Her serinin aylık/yıllık mutlak ve yüzdesel değişimi           |
| `gold_housing_credit_market`                | Konut kredisi hacmi, faizi, fiyat endeksi, satış adedi          |
| `gold_credit_market`                        | Genel kredi hacmi ve ticari kredi faiz oranı                    |
| `gold_deposit_market`                       | Mevduat/katılım fonu hacmi ve TL mevduat faiz oranı              |
| `gold_precious_metal_ratios_daily`          | Günlük Altın/Gümüş (USD/Ons) fiyat ve rasyosu                   |
| `gold_precious_metal_ratios_monthly`        | Aylık Altın/Gümüş rasyosu ve momentum (MoM değişim)              |
| `gold_finturk_province_credit_quality`      | İl bazlı kredi hacmi ve NPL (takibe dönüşüm) oranı               |
| `gold_series_evidence`                      | Her gold kolonunun hangi ham seriden, hangi yöntemle türediğini gösteren lineage/kanıt tablosu |

Ayrıca `lakehouse_data_catalog` (tüm tabloların haritası) ve `data/gold/series_embeddings.parquet`
(doğal dil ile seri arama için embedding kataloğu, `series_catalog_search` tool'u tarafından kullanılır).

## 5. Neden Bu Teknolojiler

- **DuckDB** — Gömülü (embedded) bir OLAP motoru: ayrı bir veritabanı sunucusu/process
  kurmayı gerektirmez, MIT lisanslıdır ve Parquet dosyalarını doğrudan sorgulayabilir.
  Bu proje için "hazır bir bulut veri platformu" yerine, repo içinde taşınabilir tek
  dosyalık (`lakehouse.duckdb`) bir çözüm tercih edilmiştir.
- **Parquet** — Kolon bazlı, sıkıştırılmış, self-describing (şemasını içinde taşıyan)
  bir format. Gold katmanı ve embedding kataloğu Parquet olarak tutulur; hem DuckDB hem
  pandas/pyarrow ile ek bir dönüştürme yapmadan okunabilir.
- **LanceDB** — Değerlendirildi ancak kullanılmadı: `series_catalog_search` tool'u,
  963 serilik embedding kataloğunu ayrı bir vektör veritabanı servisi/sürecine ihtiyaç
  duymadan doğrudan `data/gold/series_embeddings.parquet` içinden okuyup NumPy ile
  kosinüs benzerliği hesaplayarak arıyor (bkz.
  [backend/app/tools/series_catalog_search.py](backend/app/tools/series_catalog_search.py)).
  Veri seti boyutunda (binlerce satır) ek bir vektör-DB'nin getirisi, getirdiği
  operasyonel karmaşıklığı karşılamadığı için bu yalın yaklaşım tercih edilmiştir.

## 6. ÖNEMLİ NOT

requirements.txt içindeki `openai` paketi yalnızca OpenAI-uyumlu bir HTTP
istemcisi olarak, Kloudeks endpoint'ine (https://mia.csp.kloudeks.com/v1) karşı
kullanılmaktadır. Projede api.openai.com'a veya herhangi bir üçüncü taraf LLM
servisine yapılan hiçbir çağrı yoktur.

## 7. Testler

```bash
PYTHONPATH=backend python -m pytest --import-mode=importlib
```

Bu repoda toplam **277 test** bulunur. Bronze/Silver/Aligned/Gold veri katmanları
yerelde üretilmeden (bkz. [SETUP.md](SETUP.md)) çalıştırıldığında **227'si geçer**,
gerçek Gold/Aligned/Silver parquet çıktılarına ihtiyaç duyan **38'i veri eksikliğinden
başarısız olur** ve **12'si atlanır (skip)**. Tam pipeline üretildikten sonra tüm
testlerin geçmesi beklenir.

## 8. Daha Fazla Doküman

- [SETUP.md](SETUP.md) — veri pipeline'ının sıfırdan kurulumu ve doğrulanmış sonuçları
- [docs/api_contract.md](docs/api_contract.md) — API sözleşmesi
- [docs/decisions/](docs/decisions/) — mimari kararlar (ADR'ler) ve açık/kapalı kararlar
- [docs/features/features_inventory.md](docs/features/features_inventory.md) — özellik envanteri
- [docs/binding_rules/](docs/binding_rules/) — backend/frontend/sistem/test kuralları
- [notes/](notes/) — geliştirme sürecindeki teknik notlar (alignment semantiği, gold
  kolon isimlendirme, deploy timeout kararları, e2e test sonuçları vb.)
