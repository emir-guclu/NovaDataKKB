# Feature Inventory (Özellik Envanteri)

> Projede geliştirilecek özelliklerin (`F-nnn`) merkezi kayıt ve takip listesi.

| ID | Başlık | Durum | Kapsam Özeti | İlgili Kararlar | Hedef Tarih |
|---|---|---|---|---|---|
| **F-001** | EVDS Veri Temini (Bronze Katmanı) | `COMPLETED` | TCMB EVDS API üzerinden makroekonomik serilerin ve metaverilerin ham JSON formatında çekilip `data/bronze/evds/` altına kaydedilmesi. (Silver ve Gold aşamaları kapsam dışıdır). | `T-08`, `T-43`, `ADR-0001` | 2026-09-09 |

| **F-002** | BDDK Veri Temini (Bronze Katmanı) | `COMPLETED` | BDDK Haftalık Bülten, Aylık Bülten ve FinTürk - İllere Göre kaynaklarından 2021-01 ile 2026-06 dönemine ait verilerin otomatik olarak toplanması, normalize edilmesi, doğrulanması ve `data/bronze/bddk/` altında saklanması. Haftalık dönem audit kontrolü ve pytest tabanlı parser/normalizasyon testleri dahildir. | `TBD` | 2026-09-09 |
| **F-003** | EVDS Veri Standardizasyonu ve Normalizasyonu (Silver Katmanı) | `COMPLETED` | EVDS Bronze JSON verilerinin ve zengin TCMB metadatalarının iki aşamalı boru hattı (`metadata.py` -> `transformer.py`) ile temizlenip, kanonik şemaya uygun `observations.parquet` ve `series_metadata.parquet` dosyalarına dönüştürülmesi. | `ADR-0001`, `§5.4` | 2026-09-09 |
