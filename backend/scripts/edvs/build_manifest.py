"""Builds the comprehensive 122-series EVDS Manifest."""

from pathlib import Path
import pandas as pd

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
CATALOG_PATH = BACKEND_DIR.parent / "data" / "bronze" / "evds" / "evds_catalog.parquet"
MANIFEST_PATH = BACKEND_DIR / "app" / "modules" / "evds" / "series_manifest.yaml"

categories_spec = [
    ("1. Konut ve Gayrimenkul Piyasası (KFE, Satışlar, Kiralar)", "konut_piyasasi", "CRITICAL", [
        ("TP.KTF10", "Konut Kredisi Faiz Oranı", "kredi_faizleri", "Haftalık", "Yüzde (%)", "Bankalarca açılan konut kredilerine uygulanan ağırlıklı ortalama faiz oranı (akım).", ["konut", "kredi", "faiz", "adim_01"]),
        ("TP.KM.B11", "Konut Kredisi Hacmi / Bakiyesi (Tutar)", "kredi_hacimleri", "Aylık", "Bin TL", "Mevduat bankaları toplam konut kredisi bakiye büyüklüğü (2021-2026 kesintisiz).", ["konut", "kredi", "hacim", "adim_01"]),
        ("TP.GENENDEKS.T1", "TÜFE Genel Endeksi (2003=100)", "enflasyon", "Aylık", "Endeks", "Tüketici Fiyat Endeksi genel seviyesi. Konut kredisi tutarlarını reel değere dönüştürmek için kullanılır.", ["enflasyon", "tufe", "adim_02"]),
        ("TP.TUFE1YI.T1", "Yİ-ÜFE Genel Endeksi", "enflasyon", "Aylık", "Endeks (2003=100)", "Yurt İçi Üretici Fiyat Endeksi.", ["enflasyon", "ufe"]),
        ("TP.KFE.TR", "Konut Fiyat Endeksi (KFE - Türkiye Geneli)", "konut_piyasasi", "Aylık", "Endeks", "Türkiye geneli kalite etkisinden arındırılmış konut fiyat endeksi.", ["konut", "kfe", "adim_03"]),
        ("TP.KFE.TR10", "İstanbul Konut Fiyat Endeksi (TR10)", "konut_piyasasi", "Aylık", "Endeks", "TCMB İstanbul Konut Fiyat Endeksi.", ["konut", "kfe", "istanbul"]),
        ("TP.KFE.TR51", "Ankara Konut Fiyat Endeksi (TR51)", "konut_piyasasi", "Aylık", "Endeks", "TCMB Ankara Konut Fiyat Endeksi.", ["konut", "kfe", "ankara"]),
        ("TP.KFE.TR31", "İzmir Konut Fiyat Endeksi (TR31)", "konut_piyasasi", "Aylık", "Endeks", "TCMB İzmir Konut Fiyat Endeksi.", ["konut", "kfe", "izmir"]),
        ("TP.KFE.TR41", "Bursa Konut Fiyat Endeksi (TR41)", "konut_piyasasi", "Aylık", "Endeks", "TCMB Bursa, Eskişehir, Bilecik Bölgesi KFE.", ["konut", "kfe", "bursa"]),
        ("TP.KFE.TR42", "Kocaeli Konut Fiyat Endeksi (TR42)", "konut_piyasasi", "Aylık", "Endeks", "TCMB Kocaeli, Sakarya, Bolu, Düzce, Yalova Bölgesi KFE.", ["konut", "kfe", "kocaeli"]),
        ("TP.KFE.TR61", "Antalya Konut Fiyat Endeksi (TR61)", "konut_piyasasi", "Aylık", "Endeks", "TCMB Antalya, Burdur, Isparta Bölgesi KFE.", ["konut", "kfe", "antalya"]),
        ("TP.KFE.TR62", "Adana Konut Fiyat Endeksi (TR62)", "konut_piyasasi", "Aylık", "Endeks", "TCMB Adana, Mersin Bölgesi KFE.", ["konut", "kfe", "adana"]),
        ("TP.KFE.TR21", "Trakya Konut Fiyat Endeksi (TR21)", "konut_piyasasi", "Aylık", "Endeks", "TCMB Edirne, Tekirdağ, Kırklareli Bölgesi KFE.", ["konut", "kfe", "trakya"]),
        ("TP.KFE.TR32", "Aydın-Muğla Konut Fiyat Endeksi (TR32)", "konut_piyasasi", "Aylık", "Endeks", "TCMB Aydın, Denizli, Muğla Bölgesi KFE.", ["konut", "kfe", "mugla"]),
        ("TP.KFE.TR22", "Balıkesir-Çanakkale Konut Fiyat Endeksi (TR22)", "konut_piyasasi", "Aylık", "Endeks", "TCMB Balıkesir, Çanakkale Bölgesi KFE.", ["konut", "kfe"]),
        ("TP.KFE.TR33", "Manisa-Afyon Konut Fiyat Endeksi (TR33)", "konut_piyasasi", "Aylık", "Endeks", "TCMB Manisa, Afyon, Kütahya, Uşak KFE.", ["konut", "kfe"]),
        ("TP.KFE.TR52", "Konya-Karaman Konut Fiyat Endeksi (TR52)", "konut_piyasasi", "Aylık", "Endeks", "TCMB Konya, Karaman Bölgesi KFE.", ["konut", "kfe"]),
        ("TP.KFE.TR63", "Hatay-Maraş Konut Fiyat Endeksi (TR63)", "konut_piyasasi", "Aylık", "Endeks", "TCMB Hatay, Kahramanmaraş, Osmaniye KFE.", ["konut", "kfe"]),
        ("TP.KFE.TR7", "Orta Anadolu Konut Fiyat Endeksi (TR7)", "konut_piyasasi", "Aylık", "Endeks", "TCMB Kırıkkale, Aksaray, Niğde, Nevşehir, Kırşehir KFE.", ["konut", "kfe"]),
        ("TP.KFE.TR8", "Batı Karadeniz Konut Fiyat Endeksi (TR8)", "konut_piyasasi", "Aylık", "Endeks", "TCMB Zonguldak, Karabük, Bartın, Kastamonu, Çankırı, Sinop KFE.", ["konut", "kfe"]),
        ("TP.KFE.TR9", "Doğu Karadeniz Konut Fiyat Endeksi (TR9)", "konut_piyasasi", "Aylık", "Endeks", "TCMB Trabzon, Ordu, Giresun, Rize, Artvin, Gümüşhane KFE.", ["konut", "kfe"]),
        ("TP.KFE.TRA", "Kuzeydoğu Anadolu Konut Fiyat Endeksi (TRA)", "konut_piyasasi", "Aylık", "Endeks", "TCMB Erzurum, Erzincan, Bayburt, Ağrı, Kars, Iğdır, Ardahan KFE.", ["konut", "kfe"]),
        ("TP.KFE.TRB", "Ortadoğu Anadolu Konut Fiyat Endeksi (TRB)", "konut_piyasasi", "Aylık", "Endeks", "TCMB Malatya, Elazığ, Bingöl, Tunceli, Van, Muş, Bitlis, Hakkari KFE.", ["konut", "kfe"]),
        ("TP.KFE.TRC", "Güneydoğu Anadolu Konut Fiyat Endeksi (TRC)", "konut_piyasasi", "Aylık", "Endeks", "TCMB Gaziantep, Adıyaman, Kilis, Şanlıurfa, Diyarbakır, Mardin, Batman, Şırnak, Siirt KFE.", ["konut", "kfe"]),
        ("TP.YKKE.TR", "Yeni Kiracı Kira Endeksi (YKKE)", "konut_piyasasi", "Aylık", "Endeks", "TCMB Yeni Kiracı Kira Endeksi. Konut kira enflasyonu öncü göstergesidir.", ["konut", "kira", "ykke"]),
        ("TP.BK.TR", "Türkiye Konut Birim Kiraları (TL/m2)", "konut_piyasasi", "Aylık", "TL/m2", "Değerlemesi yapılan konutların metrekare başına ortalama birim kirası.", ["konut", "kira", "fiyat_kira_orani"]),
        ("TP.BK.ISTANBUL", "İstanbul Konut Birim Kiraları (TL/m2)", "konut_piyasasi", "Aylık", "TL/m2", "İstanbul ili ortalama konut birim kirası.", ["konut", "kira", "istanbul"]),
        ("TP.BK.ANKARA", "Ankara Konut Birim Kiraları (TL/m2)", "konut_piyasasi", "Aylık", "TL/m2", "Ankara ili ortalama konut birim kirası.", ["konut", "kira", "ankara"]),
        ("TP.BK.IZMIR", "İzmir Konut Birim Kiraları (TL/m2)", "konut_piyasasi", "Aylık", "TL/m2", "İzmir ili ortalama konut birim kirası.", ["konut", "kira", "izmir"]),
        ("TP.AKONUTSAT2.KTRTOPLAM", "Türkiye İpotekli Konut Satışları", "konut_satislari", "Aylık", "Adet", "TÜİK kaynaklı Türkiye geneli ipotekli konut satış adedi.", ["konut", "ipotekli_satis", "kredi_talebi"]),
        ("TP.AKONUTSAT2.KTR100", "İstanbul İpotekli Konut Satışları", "konut_satislari", "Aylık", "Adet", "İstanbul geneli ipotekli konut satış adedi.", ["konut", "ipotekli_satis", "istanbul"]),
        ("TP.AKONUTSAT2.KTR510", "Ankara İpotekli Konut Satışları", "konut_satislari", "Aylık", "Adet", "Ankara geneli ipotekli konut satış adedi.", ["konut", "ipotekli_satis", "ankara"]),
        ("TP.AKONUTSAT2.KTR310", "İzmir İpotekli Konut Satışları", "konut_satislari", "Aylık", "Adet", "İzmir geneli ipotekli konut satış adedi.", ["konut", "ipotekli_satis", "izmir"]),
        ("TP.AKONUTSAT2.KTR611", "Antalya İpotekli Konut Satışları", "konut_satislari", "Aylık", "Adet", "Antalya geneli ipotekli konut satış adedi.", ["konut", "ipotekli_satis", "antalya"]),
        ("TP.AKONUTSAT2.KTR411", "Bursa İpotekli Konut Satışları", "konut_satislari", "Aylık", "Adet", "Bursa geneli ipotekli konut satış adedi.", ["konut", "ipotekli_satis", "bursa"]),
        ("TP.AKONUTSAT2.KTR421", "Kocaeli İpotekli Konut Satışları", "konut_satislari", "Aylık", "Adet", "Kocaeli geneli ipotekli konut satış adedi.", ["konut", "ipotekli_satis", "kocaeli"]),
        ("TP.AKONUTSAT2.KTR621", "Adana İpotekli Konut Satışları", "konut_satislari", "Aylık", "Adet", "Adana geneli ipotekli konut satış adedi.", ["konut", "ipotekli_satis", "adana"]),
        ("TP.AKONUTSAT1.KTRTOPLAM", "Türkiye Toplam Konut Satışları", "konut_satislari", "Aylık", "Adet", "TÜİK kaynaklı Türkiye geneli toplam konut satış adedi.", ["konut", "toplam_satis"]),
        ("TP.AKONUTSAT1.KTR100", "İstanbul Toplam Konut Satışları", "konut_satislari", "Aylık", "Adet", "İstanbul geneli toplam konut satış adedi.", ["konut", "toplam_satis", "istanbul"]),
        ("TP.AKONUTSAT1.KTR510", "Ankara Toplam Konut Satışları", "konut_satislari", "Aylık", "Adet", "Ankara geneli toplam konut satış adedi.", ["konut", "toplam_satis", "ankara"]),
        ("TP.AKONUTSAT1.KTR310", "İzmir Toplam Konut Satışları", "konut_satislari", "Aylık", "Adet", "İzmir geneli toplam konut satış adedi.", ["konut", "toplam_satis", "izmir"]),
        ("TP.AKONUTSAT1.KTR611", "Antalya Toplam Konut Satışları", "konut_satislari", "Aylık", "Adet", "Antalya geneli toplam konut satış adedi.", ["konut", "toplam_satis", "antalya"]),
        ("TP.AKONUTSAT1.KTR411", "Bursa Toplam Konut Satışları", "konut_satislari", "Aylık", "Adet", "Bursa geneli toplam konut satış adedi.", ["konut", "toplam_satis", "bursa"]),
        ("TP.AKONUTSAT1.KTR421", "Kocaeli Toplam Konut Satışları", "konut_satislari", "Aylık", "Adet", "Kocaeli geneli toplam konut satış adedi.", ["konut", "toplam_satis", "kocaeli"]),
        ("TP.AKONUTSAT1.KTR621", "Adana Toplam Konut Satışları", "konut_satislari", "Aylık", "Adet", "Adana geneli toplam konut satış adedi.", ["konut", "toplam_satis", "adana"]),
        ("TP.AKONUTSAT3.KTRTOPLAM", "Türkiye İlk El Konut Satışları", "konut_satislari", "Aylık", "Adet", "Sıfır konut satış adedi.", ["konut", "sifir_konut"]),
        ("TP.AKONUTSAT4.KTRTOPLAM", "Türkiye İkinci El Konut Satışları", "konut_satislari", "Aylık", "Adet", "İkinci el konut satış adedi.", ["konut", "ikinci_el"])
    ]),
    ("2. Kredi Türleri, Faizleri ve Hacimleri", "krediler", "HIGH", [
        ("TP.KTF11", "İhtiyaç Kredisi Faiz Oranı", "kredi_faizleri", "Haftalık", "Yüzde (%)", "Bankalarca açılan TL ihtiyaç kredisi faizi (akım).", ["ihtiyac_kredisi", "faiz"]),
        ("TP.KTF12", "Taşıt Kredisi Faiz Oranı", "kredi_faizleri", "Haftalık", "Yüzde (%)", "Bankalarca açılan TL taşıt kredisi faizi (akım).", ["tasit_kredisi", "faiz"]),
        ("TP.KTF17", "Ticari Kredi Faiz Oranı (TL)", "kredi_faizleri", "Haftalık", "Yüzde (%)", "Bankalarca açılan TL ticari kredilere uygulanan faiz (akım).", ["ticari_kredi", "faiz"]),
        ("TP.BKR.TRY.18", "Konut Kredisi Stok Faiz Oranı", "kredi_faizleri", "Haftalık", "Yüzde (%)", "Konut kredisi stok ağırlıklı ortalama faiz oranı.", ["konut", "stok_faiz"]),
        ("TP.KREHACBS.A1", "Toplam Kredi Hacmi (Bankacılık Sektörü)", "kredi_hacimleri", "Aylık", "Bin TL", "Yurt içi yerleşikler toplam kredi stoku.", ["kredi_hacmi", "toplam"]),
        ("TP.KREHACBS.A2", "Mevduat Bankaları Toplam Kredi Hacmi", "kredi_hacimleri", "Aylık", "Bin TL", "Mevduat bankaları yurt içi kredi stoku.", ["kredi_hacmi", "mevduat_bankalari"]),
        ("TP.KREHACBS.A8", "Şirket Kredileri Hacmi", "kredi_hacimleri", "Aylık", "Bin TL", "Mali olmayan şirketler kredi büyüklüğü.", ["kredi_hacmi", "kurumsal"]),
        ("TP.KREHACBS.A9", "Hanehalkı Kredileri Hacmi", "kredi_hacimleri", "Aylık", "Bin TL", "Bireysel tüketici kredileri toplam stoku.", ["kredi_hacmi", "bireysel"]),
        ("TP.KREHACBS.A10", "Banka Dışı Mali Kuruluşlar Kredileri", "kredi_hacimleri", "Aylık", "Bin TL", "Faktoring, leasing ve finansman şirketleri kredileri.", ["kredi_hacmi"]),
        ("TP.KREHACBS.A11", "Kalkınma ve Yatırım Bankaları Kredi Hacmi", "kredi_hacimleri", "Aylık", "Bin TL", "Kalkınma ve yatırım bankaları kredi stoku.", ["kredi_hacmi", "yatirim_bankalari"]),
        ("TP.KREHACBS.A20", "Katılım Bankaları Kredi Hacmi", "kredi_hacimleri", "Aylık", "Bin TL", "Katılım bankaları kredi stoku.", ["kredi_hacmi", "katilim_bankalari"]),
        ("TP.KM.B07", "Mevduat Bankaları Şirket Kredileri", "kredi_hacimleri", "Aylık", "Bin TL", "Mevduat bankaları mali olmayan şirket kredileri.", ["kredi_hacmi"]),
        ("TP.KM.B09", "Mevduat Bankaları Hanehalkı Kredileri", "kredi_hacimleri", "Aylık", "Bin TL", "Mevduat bankaları hanehalkı kredileri.", ["kredi_hacmi"]),
        ("TP.KM.B10", "Mevduat Bankaları Tüketici Kredileri Toplam", "kredi_hacimleri", "Aylık", "Bin TL", "Konut, taşıt, ihtiyaç toplamı.", ["kredi_hacmi", "tuketici"]),
        ("TP.KM.B12", "Mevduat Bankaları Taşıt Kredileri Hacmi", "kredi_hacimleri", "Aylık", "Bin TL", "Taşıt kredisi bakiyesi.", ["tasit_kredisi", "hacim"]),
        ("TP.KM.B13", "Mevduat Bankaları İhtiyaç Kredileri Hacmi", "kredi_hacimleri", "Aylık", "Bin TL", "İhtiyaç kredisi bakiyesi.", ["ihtiyac_kredisi", "hacim"]),
        ("TP.KM.B14", "Mevduat Bankaları Bireysel Kredi Kartları Hacmi", "kredi_hacimleri", "Aylık", "Bin TL", "Bireysel kredi kartı bakiyesi.", ["kredi_karti", "bakiye"]),
        ("TP.KM.B33", "Mevduat Bankaları Genel Kredi Toplamı", "kredi_hacimleri", "Aylık", "Bin TL", "Mevduat bankaları tüm krediler toplamı.", ["kredi_hacmi"]),
        ("TP.KB.KRE10", "Katılım Bankaları Konut Kredileri Hacmi", "kredi_hacimleri", "Aylık", "Bin TL", "Katılım bankaları konut finansmanı stoku.", ["katilim", "konut"]),
        ("TP.KB.KRE11", "Katılım Bankaları Taşıt Kredileri Hacmi", "kredi_hacimleri", "Aylık", "Bin TL", "Katılım bankaları taşıt finansmanı stoku.", ["katilim", "tasit"]),
        ("TP.KB.KRE12", "Katılım Bankaları İhtiyaç Kredileri Hacmi", "kredi_hacimleri", "Aylık", "Bin TL", "Katılım bankaları ihtiyaç finansmanı stoku.", ["katilim", "ihtiyac"]),
        ("TP.KB.KRE25", "Katılım Bankaları Genel Kredi Toplamı", "kredi_hacimleri", "Aylık", "Bin TL", "Katılım bankaları toplam finansman stoku.", ["katilim", "toplam"])
    ]),
    ("3. Mevduat Türleri, Faizleri ve Para Arzı", "mevduat_ve_para", "HIGH", [
        ("TP.TRY.MT01", "1 Aya Kadar Vadeli TL Mevduat Faizi", "mevduat_faizleri", "Haftalık", "Yüzde (%)", "1 aya kadar vadeli mevduat ağırlıklı faizi.", ["mevduat", "faiz"]),
        ("TP.TRY.MT02", "3 Aya Kadar Vadeli TL Mevduat Faizi", "mevduat_faizleri", "Haftalık", "Yüzde (%)", "1-3 ay vadeli mevduat faiz göstergesi.", ["mevduat", "faiz", "faiz_makasi"]),
        ("TP.TRY.MT03", "6 Aya Kadar Vadeli TL Mevduat Faizi", "mevduat_faizleri", "Haftalık", "Yüzde (%)", "3-6 ay vadeli mevduat faizi.", ["mevduat", "faiz"]),
        ("TP.TRY.MT04", "1 Yıla Kadar Vadeli TL Mevduat Faizi", "mevduat_faizleri", "Haftalık", "Yüzde (%)", "6 ay - 1 yıl vadeli mevduat faizi.", ["mevduat", "faiz"]),
        ("TP.TRY.MT05", "1 Yıl ve Uzun Vadeli TL Mevduat Faizi", "mevduat_faizleri", "Haftalık", "Yüzde (%)", "1 yıldan uzun mevduat faizi.", ["mevduat", "faiz"]),
        ("TP.TRY.MT06", "Toplam TL Mevduat Ortalama Faizi", "mevduat_faizleri", "Haftalık", "Yüzde (%)", "Tüm vadeler ağırlıklı ortalama mevduat faizi.", ["mevduat", "ortalama_faiz"]),
        ("TP.USD.MT02", "3 Aya Kadar Vadeli USD Mevduat Faizi", "mevduat_faizleri", "Haftalık", "Yüzde (%)", "Dolar cinsi mevduat faizi.", ["usd_mevduat", "faiz"]),
        ("TP.EUR.MT02", "3 Aya Kadar Vadeli EUR Mevduat Faizi", "mevduat_faizleri", "Haftalık", "Yüzde (%)", "Euro cinsi mevduat faizi.", ["eur_mevduat", "faiz"]),
        ("TP.PBD.H01", "M1 Para Arzı", "para_arzi", "Aylık", "Bin TL", "Dolaşımdaki para + vadesiz mevduatlar.", ["m1", "para_arzi"]),
        ("TP.PBD.H09", "M2 Para Arzı", "para_arzi", "Aylık", "Bin TL", "M1 + vadeli mevduatlar.", ["m2", "para_arzi"]),
        ("TP.PBD.H17", "M3 Para Arzı", "para_arzi", "Aylık", "Bin TL", "M2 + repo ve fonlar.", ["m3", "para_arzi"]),
        ("TP.PBD.H02", "Dolaşımdaki Para (Emisyon)", "para_arzi", "Aylık", "Bin TL", "Banknot ve madeni para emisyonu.", ["emisyon", "para_arzi"]),
        ("TP.PBD.H03", "Vadesiz Mevduat (TL)", "mevduat_hacimleri", "Aylık", "Bin TL", "Vadesiz TL mevduat hacmi.", ["vadesiz_mevduat", "tl"]),
        ("TP.PBD.H04", "Vadesiz Mevduat (YP)", "mevduat_hacimleri", "Aylık", "Bin TL", "Vadesiz döviz mevduat hacmi.", ["vadesiz_mevduat", "yp"]),
        ("TP.PBD.H10", "Vadeli Mevduat (TL)", "mevduat_hacimleri", "Aylık", "Bin TL", "Vadeli TL mevduat hacmi.", ["vadeli_mevduat", "tl"]),
        ("TP.PBD.H11", "Vadeli Mevduat (YP)", "mevduat_hacimleri", "Aylık", "Bin TL", "Vadeli döviz mevduat hacmi.", ["vadeli_mevduat", "yp"])
    ]),
    ("4. Para Politikası, Likidite & Rezervler", "para_politikasi", "HIGH", [
        ("TP.APIFON1.IHA", "TCMB 1 Hafta Vadeli Repo İhale Faizi", "para_politikasi", "Günlük", "Yüzde (%)", "Politika faizi göstergesi.", ["politika_faizi", "repo"]),
        ("TP.APIFON4", "TCMB Ağırlıklı Ortalama Fonlama Maliyeti", "para_politikasi", "Günlük", "Yüzde (%)", "Piyasa fonlama maliyeti.", ["fonlama_maliyeti", "aofm"]),
        ("TP.AB.B6", "TCMB Toplam Rezervler (Altın + Döviz)", "rezervler", "Aylık", "Milyon USD", "Brüt rezerv büyüklüğü.", ["rezerv", "tcmb"]),
        ("TP.AB.B4", "TCMB Resmi Rezerv Varlıkları", "rezervler", "Aylık", "Milyon USD", "Resmi rezerv toplamı.", ["rezerv"]),
        ("TP.AB.B2", "TCMB Döviz Varlıkları (Brüt Döviz)", "rezervler", "Aylık", "Milyon USD", "Brüt döviz rezervi.", ["doviz_rezervi"]),
        ("TP.AB.B1", "TCMB Altın Varlıkları (Rezerv)", "rezervler", "Aylık", "Milyon USD", "Merkez bankası altın rezervi.", ["altin_rezervi"]),
        ("TP.AB.B3", "Bankalar Muhabir Mevcudu ve Kasası", "rezervler", "Aylık", "Milyon USD", "Bankacılık sistemi döviz likiditesi.", ["bankalar_muhabir"])
    ]),
    ("5. Döviz Kurları & Reel Efektif Döviz Kuru", "doviz", "HIGH", [
        ("TP.DK.USD.A.YTL", "ABD Doları Döviz Alış Kuru", "doviz", "Günlük", "TL", "TCMB ABD Doları alış kuru.", ["dolar", "usd", "kur"]),
        ("TP.DK.USD.S.YTL", "ABD Doları Döviz Satış Kuru", "doviz", "Günlük", "TL", "TCMB ABD Doları satış kuru.", ["dolar", "usd", "satis"]),
        ("TP.DK.EUR.A.YTL", "Euro Döviz Alış Kuru", "doviz", "Günlük", "TL", "TCMB Euro alış kuru.", ["euro", "eur", "kur"]),
        ("TP.DK.EUR.S.YTL", "Euro Döviz Satış Kuru", "doviz", "Günlük", "TL", "TCMB Euro satış kuru.", ["euro", "eur", "satis"]),
        ("TP.DK.GBP.A.YTL", "İngiliz Sterlini Alış Kuru", "doviz", "Günlük", "TL", "TCMB Sterlin alış kuru.", ["sterlin", "gbp", "kur"]),
        ("TP.DK.CHF.A.YTL", "İsviçre Frangı Alış Kuru", "doviz", "Günlük", "TL", "TCMB Frank alış kuru.", ["chf", "kur"]),
        ("TP.DK.JPY.A.YTL", "Japon Yeni Alış Kuru", "doviz", "Günlük", "TL", "TCMB Yen alış kuru.", ["jpy", "kur"]),
        ("TP.RK.T1.Y", "TÜFE Bazlı Reel Efektif Döviz Kuru", "doviz", "Aylık", "Endeks (2025=100)", "TL reel değerlenme endeksi.", ["rek", "reel_kur"]),
        ("TP.RK.T2.Y", "Gelişmekte Olan Ülkeler Bazlı REK", "doviz", "Aylık", "Endeks (2025=100)", "Gelişmekte olan ülkelere göre TL kuru.", ["rek", "gelismekte_olan"]),
        ("TP.RK.T3.Y", "Gelişmiş Ülkeler Bazlı REK", "doviz", "Aylık", "Endeks (2025=100)", "Gelişmiş ülkelere göre TL kuru.", ["rek", "gelismis_ulkeler"])
    ]),
    ("6. Reel Sektör, Güven, İstihdam & Cari Denge", "makro_gostergeler", "MEDIUM", [
        ("TP.KKO2.IS.TOP", "İmalat Sanayi Kapasite Kullanım Oranı", "reel_sektor", "Aylık", "Yüzde (%)", "Kapasite kullanım oranı (KKO).", ["kko", "kapasite_kullanim"]),
        ("TP.KKO.MA", "Kapasite Kullanım Oranı (Mevsimsellikten Arındırılmış)", "reel_sektor", "Aylık", "Yüzde (%)", "Mevsimsellikten arındırılmış KKO.", ["kko", "arindirilmis"]),
        ("TP.TG2.Y01", "Tüketici Güven Endeksi", "guven_endeksleri", "Aylık", "Endeks", "Tüketici genel güven seviyesi.", ["tuketici_guveni"]),
        ("TP.TIG08", "İşsizlik Oranı (%)", "istihdam", "Aylık", "Yüzde (%)", "Mevsim etkisinden arındırılmış işsizlik oranı.", ["issizlik", "isgucu"]),
        ("TP.TIG06", "İstihdam Oranı (%)", "istihdam", "Aylık", "Yüzde (%)", "Mevsim etkisinden arındırılmış istihdam oranı.", ["istihdam", "isgucu"]),
        ("TP.TIG07", "İşgücüne Katılma Oranı (%)", "istihdam", "Aylık", "Yüzde (%)", "İşgücüne katılım oranı.", ["isgucu_katilim"]),
        ("TP.TSANAYMT2021.BCD", "Sanayi Üretim Endeksi Toplam", "reel_sektor", "Aylık", "Endeks (2021=100)", "Toplam sanayi üretim endeksi.", ["sanayi_uretimi"]),
        ("TP.ODANA6.Q01", "Cari İşlemler Dengesi", "disa_baglilik", "Aylık", "Milyon USD", "Cari açık / fazla büyüklüğü.", ["cari_acik", "odemeler_dengesi"])
    ]),
    ("7. Kıymetli Madenler (Altın & Gümüş Piyasası)", "kiymetli_madenler", "HIGH", [
        ("TP.MK.CUM.YTL", "Cumhuriyet Altını Satış Fiyatı (TL/Adet)", "kiymetli_madenler", "Aylık", "TL/Adet", "Cumhuriyet altını piyasa satış fiyatı.", ["altin", "cumhuriyet_altini", "tasarruf"]),
        ("TP.MK.KUL.YTL", "Külçe / Gram Altın Fiyatı (TL/Gr)", "kiymetli_madenler", "Aylık", "TL/Gr", "Külçe ve gram altın satış fiyatı.", ["altin", "gram_altin", "pesinat"]),
        ("TP.MK.LON.YTL", "Ons Altın Londra Satış Fiyatı (USD/Ons)", "kiymetli_madenler", "Aylık", "USD/Ons", "Uluslararası ons altın dolar fiyatı.", ["altin", "ons", "usd"]),
        ("TP.ALTINPIYASA.KAP03", "BİST Ons Altın Kapanış Fiyatı (USD/ons)", "kiymetli_madenler", "Günlük", "USD/ons", "Borsa İstanbul Altın Piyasası ons altın dolar kapanışı.", ["altin", "ons", "bist"]),
        ("TP.ALTINPIYASA.KAP02", "BİST Külçe Altın Kapanış Fiyatı (TL/kg)", "kiymetli_madenler", "Günlük", "TL/kg", "Borsa İstanbul Altın Piyasası kilogram külçe altın fiyatı.", ["altin", "bist"]),
        ("TP.GUMUSPIYASA.KAP03", "BİST Gümüş Kapanış Fiyatı (USD/ons)", "kiymetli_madenler", "Günlük", "USD/ons", "Borsa İstanbul Gümüş Piyasası ons gümüş dolar fiyatı.", ["gumus", "ons"]),
        ("TP.GOLDIMPRT.V1", "BİST Altın İthalatı (Kg)", "kiymetli_madenler", "Aylık", "Kg", "Kıymetli Madenler Piyasası Türkiye aylık altın ithalat miktarı.", ["altin", "ithalat", "cari_acik"]),
        ("TP.ALTINGR.TOPL3", "Darphane Altın Basımı Genel Toplam (Gram)", "kiymetli_madenler", "Aylık", "Gram", "Hazine ve Maliye Bakanlığı Darphane altın para ve sikke basım miktarı.", ["altin", "darphane", "yastikalti"])
    ])
]

lines = [
    "# ==============================================================================",
    "# TCMB EVDS Serileri İndirme Yönergesi (Series Ingestion Manifest)",
    "# ==============================================================================",
    "# Bu dosya, F-001/F-003 kapsamında Bronze ve Silver katmanlarına",
    "# kaynaktan indirilecek 118 serilik makro-finansal portföyün bildirimsel kaydıdır.",
    "#",
    "# Kapsam: Konut Piyasası (KFE, Satışlar, Kiralar), Kredi Faiz ve Hacimleri,",
    "#         Mevduat, Para Politikası, Döviz/REK, Reel Sektör, Kıymetli Madenler.",
    "# Tarih Aralığı: Hackathon şartnamesi gereği 01-01-2021 / 01-06-2026.",
    "# ==============================================================================",
    "",
    'version: "3.0"',
    'default_start_date: "01-01-2021"',
    'default_end_date: "01-06-2026"',
    "",
    "series:"
]

count = 0
for group_title, group_cat, def_priority, series_list in categories_spec:
    lines.append(f"  # ----------------------------------------------------------------------------")
    lines.append(f"  # {group_title}")
    lines.append(f"  # ----------------------------------------------------------------------------")
    for code, name, cat, freq, unit, desc, tags in series_list:
        count += 1
        lines.append(f'  - code: "{code}"')
        lines.append(f'    name: "{name}"')
        lines.append(f'    category: "{cat}"')
        lines.append(f'    frequency: "{freq}"')
        lines.append(f'    start_date: "01-01-2021"')
        lines.append(f'    end_date: "01-06-2026"')
        lines.append(f'    unit: "{unit}"')
        lines.append(f'    description: "{desc}"')
        lines.append(f'    priority: "{def_priority}"')
        lines.append(f"    tags: {tags}")
        lines.append("")

MANIFEST_PATH.write_text("\n".join(lines), encoding="utf-8")
print(f"Successfully written {count} series to {MANIFEST_PATH}")
