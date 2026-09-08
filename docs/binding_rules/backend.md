# Backend Bağlayıcı Kuralları (Binding Rules)

<!-- source: ADR-0001 -->
* [T-0001-1] Backend iş mantığı ve çekirdek bileşenleri (modüller, modeller, LLM tool'ları) app/ dizini altında servis bazlı organize edilmelidir.
<!-- source: ADR-0001 -->
* [T-0001-2] LLM ajanları tarafından çağrılabilir tüm araç ve fonksiyon tanımları app/tools/ klasörü altında izole edilmelidir.
<!-- source: ADR-0001 -->
* [T-0001-3] Veritabanı migrasyonları (alembic) ve ortam yapılandırmaları doğrudan backend/ kök dizininde yer almalı, app/ içine karıştırılmamalıdır.

<!-- source: ADR-0002 -->
* [T-0002-1] EVDS veri erişimi için evds pip paketi kullanılmalıdır.
<!-- source: ADR-0002 -->
* [T-0002-2] Bronze katmanı arşivlemesinde evds kütüphanesi veri çekim çağrıları raw=True parametresiyle ham JSON döndürecek şekilde yapılmalıdır.
<!-- source: ADR-0002 -->
* [T-0002-3] EVDS API isteklerinde .env üzerinden sağlanan çoklu anahtar havuzu (EVDS_API_KEY_1..4) kullanılarak rotasyon ve hata yönetimi sağlanmalıdır.
