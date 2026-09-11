# Gold Column Naming

Bu doküman, Gold katmanı Dalga 1 implementasyonunda çapraz kaynaklı (cross-source) tablolar için kullanılacak somut kolon isimlerini tanımlar. Ham kaynak referansları yerine iş birimlerine/agent'a anlamlı gelecek açıklamalı isimler tercih edilmiştir.

## 2. gold_housing_credit_market
- `date`: Tarih
- `konut_kredisi_hacmi_tp`: BDDK Tüketici Kredileri - Konut (TP) `[BDDK_MONTHLY:tuketici_kredileri:tuketici_kredileri_konut, variable=TP]`
- `konut_kredisi_faiz_orani`: Bankalarca Açılan Kredilere Uygulanan Ağırlıklı Ortalama Faiz Oranları - Konut Kredileri `[EVDS:TP.KTF12]`
- `konut_fiyat_endeksi`: Konut Fiyat Endeksi `[EVDS:TP.KFE.TR]`
- `toplam_konut_satisi`: Türkiye Geneli Konut Satış Sayısı Toplamı `[EVDS:TP.AKONUTSAT1.KTRTOPLAM]`

## 3. gold_credit_market
- `date`: Tarih
- `toplam_kredi_hacmi`: BDDK Toplam Krediler (Toplam) `[BDDK_MONTHLY:krediler:toplam_krediler, variable=Toplam]`
- `yurtici_toplam_kredi_hacmi_evds`: Yurtiçi Kredi Hacmi `[EVDS:TP.KREHACBS.A1]`
- `ticari_kredi_faiz_orani`: Ticari Krediler Faiz Oranı `[EVDS:TP.KTF17]`

## 4. gold_deposit_market
- `date`: Tarih
- `mevduat_katilim_fonu_tp`: BDDK Mevduat ve Katılım Fonu (TP) `[BDDK_MONTHLY:bilanco:mevduat_katilim_fonu, variable=TP]`
- `tl_mevduat_faiz_orani`: Bankalarca Açılan Mevduatlara Uygulanan Ağırlıklı Ortalama Faiz Oranları - Toplam (TL) `[EVDS:TP.TRY.MT06]`
