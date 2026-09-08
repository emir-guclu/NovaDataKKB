# Closed Decisions (Kapanan Kararlar)

> Bu dosya, projede karara bağlanan (`DECIDED`) ve açık kararlar listesinden çıkarılan teknik (`T-`), ürün (`P-`) ve süreç (`S-`) kararlarının tarihsel kaydını tutar.
> Teknik kararlar kural gereği bir ADR ile belgelenmelidir.

## Kapanan Karar Listesi

| ID | Kategori | Orijinal Karar Sorusu | Alınan Karar ve Gerekçe | İlgili Feature | Karar Tarihi | ADR |
|---|---|---|---|---|---|---|
| **T-08** | Teknik (`T-`) | EVDS veri erisimi icin pip paketi mi, ozel httpx istemcisi mi kullanilacak? | **`evds` pip paketi kullanılacak.**<br>- Geliştirme hızını artırması,<br>- Projede `.venv` ortamında halihazırda kurulu ve test edilmiş olması,<br>- `evdspy` gibi CLI/dosya karmaşıklığı yaratmadan doğrudan `pandas.DataFrame` dönmesi,<br>- Çoklu API anahtarı havuzunun dinamik olarak beslenebilmesi nedeniyle tercih edildi. |  | 2026-09-08 | [ADR bekleniyor] |
| **T-04** | Teknik (`T-`) | Backend kod organizasyonu nasil olacak? | **Servis-bazlı klasör yapısı kullanılacak.**<br>- Çekirdek backend yapıtaşları `app/` altında toplanacak (`models/`, `modules/`, `tools/` vb.).<br>- LLM'lerin kullanabileceği tool'lar ayrılmış bir klasörde (`app/tools/`) tutulacak.<br>- Altyapı ve araçlar (`alembic/` vb.) `backend/` ana dizini altında yer alacak.<br>- Modüler servis izolasyonu ve LLM tool yönetimi netleştirildi. |  | 2026-09-08 | [ADR-0001](adr/0001-service-based-backend-structure.md) |

