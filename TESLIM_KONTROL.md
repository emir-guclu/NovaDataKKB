# 20 Eylül Teslim Kontrol Listesi

## Zorunlu — atlanamaz
- [ ] Üçüncü taraf LLM sağlayıcılarını kaldır (DeepSeek/NVIDIA)
- [ ] ~/nova_saklanan/0003-llm-provider-abstraction.md → docs/decisions/adr/
- [ ] README'ye "Model ve Uyum" bölümünü ekle
- [ ] grep -rni "deepseek\|nvidia" . --exclude-dir=node_modules --exclude-dir=.git --exclude-dir=data
      → SIFIR sonuç dönmeli
- [ ] README'deki canlı sistem linkini doldur
- [ ] README'deki demo video linkini doldur
- [ ] Deploy edilmiş sistemde bir soru sor, cevap ve grafik geldiğini doğrula
- [ ] pytest → 319 test, 0 kırık
- [ ] git tag v1.0 && git push --tags

## Kontrol
- [ ] docker compose up -d --build temiz bir makinede çalışıyor
- [ ] .env.example eksiksiz (FRONTEND_ORIGIN, NEXT_PUBLIC_API_BASE_URL dahil)
- [ ] KKB GitHub'da collaborator olarak ekli
