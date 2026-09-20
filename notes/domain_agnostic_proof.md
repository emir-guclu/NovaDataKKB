# T18 — Domain-Agnostic Proof

## Amaç

NOVA'nın yalnızca finans verisine özel olmadığını canlı ve tekrar üretilebilir
şekilde kanıtlamak.

Sağlık alanı bu iddianın örnek kanıt domain'idir. Sağlık için ayrı bir analiz
motoru veya sağlık-özel bir agent yazılmamıştır.

## Kaynak Veri

Kaynak:
T.C. Sağlık Bakanlığı, Sağlık İstatistikleri Yıllığı 2024,
Şekil 7.2 — Yıllara ve Sektörlere Göre Hastane Yatağı Sayısı.

Asıl kaynak kurum:
Sağlık Hizmetleri Genel Müdürlüğü.

Kullanılan seri:

- Series ID: `HEALTH_MOH:hospital_beds_total`
- Ad: Türkiye Toplam Hastane Yatağı Sayısı
- Frekans: Yıllık (`Y`)
- Birim: adet
- Nature: stock
- Nature reviewed: true

Gözlemler:

| Yıl | Toplam Hastane Yatağı |
|---|---:|
| 2002 | 164471 |
| 2020 | 251182 |
| 2021 | 254497 |
| 2022 | 262190 |
| 2023 | 266594 |
| 2024 | 268359 |

## Mimari Kanıt

Sağlık verisi mevcut canonical sözleşmeye dönüştürülmüştür.

Canonical builder, EVDS ve BDDK dışındaki canonical-compatible Silver
kaynaklarını otomatik keşfedecek şekilde genelleştirilmiştir.

Bu nedenle yeni bir domain eklemek için analiz tool'larının değiştirilmesi
gerekmez.

## Aynı Tool'larla Çalışma

Sağlık serisi mevcut analitik araçlarla başarıyla çalıştırılmıştır:

- `series_catalog_search`
- `change_detection`
- `anomaly_detection`

Sağlık için ayrı bir tool yazılmamıştır.

`Türkiye toplam hastane yatağı sayısı` doğal dil sorgusunda
`HEALTH_MOH:hospital_beds_total` birinci katalog sonucu olarak bulunmuştur.

## Frekans Farkındalığı

Silver periodic resolver domain yerine frekans üzerinden çalışacak şekilde
genelleştirilmiştir.

Yıllık serilerde:

- aylık değişim üretilmez (`mom_* = null`)
- yıllık değişim önceki yıllık gözlemden hesaplanır

2024:

- değer: 268359 adet
- yıllık mutlak değişim: +1765 adet
- yıllık değişim: yaklaşık +%0,66

## Anomali Analizi

Aynı robust anomaly tool'u sağlık serisinde çalışmıştır.

Altı gözlem içinde 2002 seviyesi istatistiksel uç olarak işaretlenmiştir.

Serinin yalnızca 6 gözlem içermesi ve 2002–2020 arasında büyük zaman boşluğu
bulunması nedeniyle bu sonuç yapısal veya nedensel bir sağlık anomalisi olarak
yorumlanmamalıdır.

## Finans Regression

Sağlık/domain-agnostic değişikliklerinden sonra mevcut BDDK aylık konut kredisi
serisi tekrar test edilmiştir.

2024 Kasım ve Aralık için:

- MoM hesapları çalışmaktadır
- YoY hesapları çalışmaktadır
- birim `milyon TL`
- nature `stock`
- dimension `Toplam`

Mevcut finans davranışı korunmuştur.

## Otomatik Testler

`backend/tests/domain_agnostic/test_health_domain_proof.py`

Sonuç:

`5 passed`

Test kapsamı:

1. Sağlık serisinin canonical Silver'da bulunması
2. Doğal dil katalog aramasında bulunması
3. Yıllık frequency-aware değişim hesabı
4. Mevcut anomaly tool ile analiz
5. BDDK aylık finans regression kontrolü

## Sonuç

NOVA'nın analitik motoru sağlık domain'ine özel kod yazılmadan aynı canonical
contract ve aynı tool registry üzerinden çalışmıştır.

Sağlık yalnızca proof datasetidir. Aynı canonical sözleşmeye uyarlanan enerji,
trafik, eğitim, nüfus, iklim veya başka bir zaman-serisi domain'i de aynı analiz
altyapısından geçirilebilir.

Sistemde bulunmayan veri için ise sistem veri uydurmamalı; kapsamını açıkça
belirtmelidir.
