---
name: debugging
description: 'Beklenmeyen davranışları veya test hatalarını teşhis etmek için sistematik prosedür: Tahmin yürütmek veya semptomları yamamak yerine hatayı yeniden üretin, izole edin, hipotez kurun, kanıtlarla doğrulayın ve kök nedeni çözün. Bir test beklenmedik bir şekilde başarısız olduğunda, bir değişiklik kabul kriterleriyle çeliştiğinde veya bir ajanın beyan ettiği çıktı gerçek davranışla eşleşmediğinde kullanın. Tetikleme ifadeleri: "/debugging", "bu hatayı çöz", "neden böyle davranıyor".'
argument-hint: 'Teşhis edilecek beklenmeyen davranış, hata mesajı veya başarısız olan test'
user-invocable: true
---

# Yetenek (Skill): `debugging`

## Amaç
Geliştirme veya test aşamasında karşılaşılan, işin içinden çıkılamayan, karmaşık ve sebebi kolayca bulunamayan hataların teşhis edilmesi ve çözülmesi için sistematik bir kılavuz tanımlar. 

Bu yetenek, sıradan hata ayıklama yöntemlerinin yetersiz kaldığı durumlarda, tahmine dayalı yama yapmak yerine hatayı adım adım izole edip gerçek kök nedeni bulmayı hedefler. "Ajan bir şeylerin çalıştığını iddia ediyor ama fiilen çalışmıyor" gibi karmaşık kilitlenme durumlarında devreye girer.

## Ne Zaman Çağrılmalı
- Bir test beklenmedik bir şekilde başarısız olduğunda (ATDD'nin beklenen kırmızı aşaması dışında, açıklanamayan gerçek bir başarısızlık durumunda).
- Bir kod değişikliğinin (diff) gerçek davranışı, kabul kriterleri veya Gherkin senaryolarıyla eşleşmediğinde.
- Bir ajan (veya genel olarak yapay zeka) bir görevin tamamlandığını iddia ettiği halde manuel doğrulama (diff incelemesi, kodu çalıştırma, çıktı dosyasını okuma) durumun öyle olmadığını veya yanlış yapıldığını gösterdiğinde.
- ATDD'nin beklenen kırmızı aşamasında (henüz implementasyon yazılmadan önce) başarısız olan testler için **çağırmayın**; bu bir hata değil, sürecin doğru çalıştığının göstergesidir.

## Gerekli Girdiler
1. Teşhis edilecek beklenmeyen davranış, hata mesajı veya başarısız olan test/çıktı.
2. Bunun yerine ne beklendiği ve neden beklendiği (hangi gereksinim, kabul kriteri veya bağlayıcı kuralın bu beklentiyi oluşturduğu).

## Süreç
1. **Önce yeniden üret, sonra teori üret:** Nedene dair herhangi bir hipotez kurmadan önce, beklenmeyen davranışın tutarlı bir şekilde yeniden üretilebildiğini doğrulayın. Yeniden üretilemiyorsa, hayali bir hatayı ayıklamaya çalışmak yerine bunu açıkça belirtin.
2. **En küçük başarısızlık durumunu izole et:** Davranışı tetikleyen minimum girdi veya koşula odaklanın. İlgisiz kodları/verileri ayıklayarak yalnızca temel tetikleyiciyi bırakın.
3. **Her seferinde tek bir hipotez kurun:** Hipotezinizi açıkça belirtin (örn: "Hipotez: API yanıtı tamamen gelmeden önce veri kaydedilmeye çalışılıyor, bu yüzden boş değer dönüyor"). Doğrulanmamış birden fazla teori arasında gidip gelmeyin.
4. **Hipotezi somut kanıtlarla doğrulayın:** Kodları, günlükleri (logs) veya çıktıları fiilen okuyun; ne olması "gerektiği" hakkında soyut akıl yürütmeler yapmayın. Hipotez yanlışsa bunu açıkça belirtin ve bir sonrakine geçin; ilk tahmininizin yanlış olduğunu gizlemeyin.
5. **Sadece semptomun yerini değil, kök nedeni bulun:** Semptomları doğrudan yama yapmak yerine (örn. değerin neden null olduğunu çözmek yerine sadece null kontrolü eklemek) gerçek kök nedeni bulmalısınız. Kök nedeni bulmak için **5 Neden (5 Whys)** tekniğini kullanın. Tespit edilen beklenmedik davranışın arkasındaki zinciri bulmak için kendinize en az 5 kez "Neden?" sorusunu sorun. Bu analizi en az 3 farklı potansiyel kök neden zinciri veya ilişkili problem odağı için ayrı ayrı yapın.
6. **Raporlama (Raporu Kaydet):** Yaptığınız tüm hata analizini, test çıktılarını, ürettiğiniz hipotezleri ve en az 3 adet 5 Neden (5 Whys) analizini ilgili özelliğin klasöründe **`docs/handoff/F-XXX/debugging.md`** dosyasına kaydedin.
7. **Düzeltmeyi önerin:** Düzeltilen davranışın hangi kabul kriterini, bağlayıcı kuralı veya gereksinimi karşılaması gerektiğini açıkça belirtin. Böylece düzeltme "akla uygun görünüyor" diye değil, somut bir kritere göre doğrulanabilir olur.
8. **Düzeltmenin çalıştığının nasıl doğrulanacağını belirtin:** Hangi testin, manuel adımın veya yeniden üretim senaryosunun artık başarıyla geçmesi gerektiğini yazın. Bu doğrulama adımı tanımlanmadan hatanın düzeltildiğini beyan etmeyin.

## Kurallar
- 1-5. adımları (yeniden üretme, izole etme, hipotez kurma, doğrulama, 5 Neden analiziyle kök neden bulma) tamamlamadan asla bir düzeltme önermeyin.
- Süreç çıktısı olan tüm analizleri mutlaka **`docs/handoff/F-XXX/debugging.md`** dosyasına yazın.
- Bunun geçici bir semptom maskeleme olduğunu ve gerçek düzeltmenin ne gerektirdiğini açıkça belirtmeden asla bir semptomu maskelemeyin (hata bastırma, null olmaması gereken bir değere koruyucu null kontrolü ekleme vb.).
- Somut bir doğrulama adımı belirtmeden asla bir hatanın düzeltildiğini ilan etmeyin.
- Bildirilen davranış verilen bilgilerle yeniden üretilemiyorsa, nedene dair tahmin yürütmek yerine bunu belirtin ve eksik yeniden üretim detaylarını talep edin.

