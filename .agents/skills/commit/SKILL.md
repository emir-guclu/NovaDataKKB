---
name: commit
description: 'Mevcut çalışma ağacındaki değişiklikleri git diff/status kullanarak sahneler (stage) ve Conventional Commits formatında bir mesajla commitler. İstenildiğinde sadece belirli bir dosya veya yolu commitlemeyi destekler. Tetikleme ifadeleri: "/commit", "bunu commitle", "değişiklikleri commitle".'
argument-hint: 'Opsiyonel: Commitin sınırlandırılacağı dosya veya klasör yolu'
user-invocable: true
---

# Yetenek (Skill): `commit`

## Amaç
Karşılaşılan değişiklikleri en az araç çağrısıyla hızlıca Conventional Commits standartlarında yerel bir commit'e dönüştürür. Kod analizi veya gözden geçirme (code review) yapmaz.

## Ne Zaman Çağrılmalı
- Kullanıcı `/commit`, "bunu commitle" veya "değişiklikleri commitle" dediğinde.
- Kullanıcı belirli bir dosya belirttiğinde: "Sadece X dosyasındaki değişiklikleri commitle" (bu durumda sadece o dosya stage edilir ve diff alınır).

## Gerekli Girdiler
1. Opsiyonel: Sınırlandırılacak dosya veya klasör yolu.

## Süreç
1. **Durumu kontrol et:** `git status --short` çalıştırın. Değişiklik yoksa işlemi durdurun.
2. **Diff al:** `git diff` (veya yol belirtildiyse `git diff -- <yol>`) çalıştırın ve çıktıyı okuyun.
3. **Secret/Credential taraması:** Diff içinde şifre, API anahtarı, `.env` dosyası değişikliği veya hassas bilgi (`sk-`, `Bearer ` vb.) varsa **işlemi derhal durdurun** ve kullanıcıyı uyarın.
4. **Değişiklik tipini sınıflandır:**
   - Yeni dosya, bileşen, uç nokta → `feat`
   - Hata düzeltme → `fix`
   - Sadece `.md` veya döküman değişikliği → `docs`
   - Sadece test kodları → `test`
   - Refaktör veya stil düzeltmeleri → `refactor`
   - Yapılandırma, bağımlılık, CI → `chore`
5. **Commit mesajını yaz:** İngilizce dilinde Conventional Commits formatına uygun şekilde yazın:
   ```
   <type>(<scope>): <geniş zamanlı kısa açıklama, en fazla 72 karakter>

   <isteğe bağlı 1-3 satırlık detaylı gövde metni>
   ```
   - Başlık sonuna kesinlikle nokta koymayın.
   - `<scope>` etkilenen klasör/modüldür (örn. `backend/auth`, `db-schema`).
6. **Stage et (git add):**
   - Belirli bir yol verildiyse sadece o yolu ekleyin (`git add <yol>`).
   - Yol verilmediyse `git status` tarafından gösterilen izlenen (tracked) tüm değiştirilmiş dosyaları ekleyin. Körlemesine `git add .` veya `git add -A` çalıştırmayın.
7. **Commit yap:** `git commit -m "<mesaj>"` çalıştırın.
8. **Raporla:** Kısa commit hashini, kullanılan mesajı ve dahil edilen dosyaları kullanıcıya kısaca bildirin.

## Kurallar
- Kullanıcı açıkça istemedikçe asla `git push` yapmayın.
- Asla `git commit --amend` veya `rebase` işlemleri yapmayın, her zaman yeni bir commit oluşturun.
- Secret taramasına takılan hiçbir dosyayı stage etmeyin veya işlemeyin.
- Dosya bazlı isteklerde sadece belirtilen dosyayı commitleyin, diğer kirli dosyaları dahil etmeyin.
- Görüşme dili Türkçe olsa bile commit mesajı başlığı ve gövdesi her zaman İngilizce olmalıdır.