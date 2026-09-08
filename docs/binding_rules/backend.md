# Backend Bağlayıcı Kuralları (Binding Rules)

<!-- source: ADR-0001 -->
* [T-0001-1] Backend iş mantığı ve çekirdek bileşenleri (modüller, modeller, LLM tool'ları) app/ dizini altında servis bazlı organize edilmelidir.
<!-- source: ADR-0001 -->
* [T-0001-2] LLM ajanları tarafından çağrılabilir tüm araç ve fonksiyon tanımları app/tools/ klasörü altında izole edilmelidir.
<!-- source: ADR-0001 -->
* [T-0001-3] Veritabanı migrasyonları (alembic) ve ortam yapılandırmaları doğrudan backend/ kök dizininde yer almalı, app/ içine karıştırılmamalıdır.
