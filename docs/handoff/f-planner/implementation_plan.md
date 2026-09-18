# Query Decomposition & Analysis Planner Tool Implementasyon Plani

> **Hedef Dizin:** `backend/app/tools/analysis_planner.py`  
> **Klasor:** `docs/handoff/f-planner/`  
> **Kapsam:** Cok katmanli veri/istatistik sorularini odaklanmis alt gorevlere (`sub_tasks`), temiz arama sorgularina (`focus_query`) ve adim adim sentez rotasina ayiran **`analysis_planner`** araci.

---

## 1. Problem Tanimi ve Motivasyon

### 1.1. Mevcut Durumdaki Darbogazlar

1. **Semantik Arama Kaybi (Embedding Dilution):**
   - Kullanici tek cumlede birden fazla seri, kaynak ve analiz istegi verdiginde bu cumleyi dogrudan `series_catalog_search`e gondermek kosinus benzerligini dagitir. Ornek: "2024 yili konut kredisi faiz oranlari ile TUFE enflasyonu arasindaki korelasyonu ve BDDK takipteki krediler oranina etkisini karsilastir" sorusu tek arama sorgusu degil, bir analiz planidir.

2. **Plansiz Multi-Hop Akis:**
   - ReAct dongusunde (`loop.py`) birden fazla gosterge ve analiz tool'u plansiz calistirildiginda model hangi serilerin aranacagini, hangi sirayla veri cekilecegini ve son sentezde neyin kontrol edilecegini kacirabilir.
   - Buyuk tool sonuclarinin context'i sisirmesi bu planin dogrudan kapsami degildir. Bu is ayrica `C:\Projects\kkb\notlar\yapilacaklar_agent_ve_llm.md` icinde "tool sonucu limitleme, ozetleme ve cache katmani" maddesi olarak takip edilecektir.

3. **Eksik Kontrol Listesi ve Hallusinasyon Riski:**
   - Onceden uretilmis bir analiz checklist'i olmadiginda model eksik veri getirdiginde boslugu kendi hafizasindan doldurma egilimine girebilir. Planner, nihai cevabin hangi alt bulgulara dayanmasi gerektigini acik hale getirir.

### 1.2. Cozum: `analysis_planner` Tool'u

Planlayici arac, yalnizca soru baglami cok adimli bir analiz gerektirdiginde devreye girer:

- Teknik araclari (`target_tool`) zorla dikte etmez; LLM'in esnek tool secimini korur.
- Soruyu bagimsiz, atomik **alt gorevlere (`sub_tasks`)** boler.
- Her alt gorev icin Lakehouse, katalog aramasi veya dis kaynak aramasinda kullanilabilecek **odaklanmis aday arama ifadeleri (`focus_query`)** uretir.
- Tarih araligi, frekans, kaynak ve analiz turu gibi baglam kisitlarini ayri alanlarda korur.
- En sonda parcalarin nasil sentezlenecegini (`synthesis_guidance`) belirler.

---

## 2. Mimari Akis

### 2.1. Baglama Duyarli Routing Kurali

`analysis_planner`, her veri sorusunda otomatik calismayacak. Tool secim kurali:

1. **Basit tek seri / tek metrik sorulari:**
   - Ornek: "Konut kredisi faiz oraninin son degeri nedir?"
   - Akis: `series_catalog_search` -> uygun veri/analiz tool'u.

2. **Cok serili, cok kaynakli veya cok tool gerektiren sorular:**
   - Ornek: "2024 yilinda konut kredisi faizleri, TUFE ve takipteki krediler arasindaki iliskiyi karsilastir."
   - Akis: `analysis_planner` -> plandaki `focus_query` degerleriyle `series_catalog_search` -> uygun veri/analiz tool'lari -> sentez.

3. **Cok asamali analiz veya nedensellik/korelasyon/etki sorulari:**
   - Eger cevap birden fazla veri cekme, hizalama, hesaplama veya karsilastirma adimi gerektiriyorsa ilk adimda planner kullanilir.

### 2.2. Ornek Akis

```text
Kullanici Sorusu
  |
  v
NOVA ReAct Core (loop.py)
  |
  |-- Basit tekil seri/metrik mi?
  |     -> series_catalog_search
  |
  |-- Birden fazla seri/kaynak/analiz tool'u gerekiyor mu?
        -> analysis_planner
              |
              v
           JSON Plan
              |
              v
           sub_tasks[*].focus_query ile series_catalog_search
              |
              v
           lakehouse_query / evds_data_service / analitik tool'lar
              |
              v
           synthesis_guidance'a gore nihai cevap
```

---

## 3. Tool Veri Yapilari ve Semasi

### 3.1. Giris Semasi (`AnalysisPlannerTool.Input`)

```python
class Input(BaseModel):
    complex_query: str = Field(
        ...,
        description=(
            "Ayrisitirilacak cok adimli, cok kaynakli, cok gostergeli veya "
            "karsilastirmali kullanici sorusu."
        ),
    )
    context_hint: str | None = Field(
        default=None,
        description=(
            "Varsa ek baglam, ekli belge ozeti, kullanicinin belirttigi tarih "
            "araligi, frekans, kaynak veya analiz kisitlari."
        ),
    )
```

### 3.2. Cikis Semasi (`AnalysisPlannerTool.Output`)

```python
class SubTask(BaseModel):
    step: int = Field(..., description="Adim numarasi (1, 2, 3...)")
    objective: str = Field(
        ...,
        description="Bu adimda arastirilacak veya cozulmesi gereken alt problem",
    )
    focus_query: str = Field(
        ...,
        description=(
            "Katalog veya web aramasi icin optimize edilmis kisa aday sorgu. "
            "Genellikle 2-5 kelime olmali; tarih ve frekans gibi kisitlar bu "
            "alana sikistirilmak yerine ayri alanlarda korunmali."
        ),
    )
    expected_output: str = Field(
        ...,
        description="Bu adim tamamlandiginda elde edilmesi beklenen veri, seri veya bulgu",
    )
    constraints: list[str] = Field(
        default_factory=list,
        description="Bu alt goreve ait kaynak, kapsam, bolge, birim veya diger analiz kisitlari",
    )
    date_range: str | None = Field(
        default=None,
        description="Varsa bu alt gorevin zaman araligi. Ornek: '2024', '2023-01..2024-12'.",
    )
    frequency_hint: str | None = Field(
        default=None,
        description="Varsa beklenen veri frekansi. Ornek: 'monthly', 'weekly', 'daily'.",
    )
    analysis_type: str | None = Field(
        default=None,
        description=(
            "Alt gorevin analitik niyeti. Ornek: 'lookup', 'trend', "
            "'correlation', 'deflation', 'risk_concentration', 'comparison'."
        ),
    )


class Output(BaseModel):
    success: bool
    plan_summary: str = Field(
        ...,
        description="Analiz stratejisinin 1-2 cumlelik ozeti",
    )
    sub_tasks: list[SubTask] = Field(
        default_factory=list,
        description="Sirali alt arastirma ve hesaplama adimlari",
    )
    synthesis_guidance: str = Field(
        ...,
        description="Alt adimlar tamamlandiginda nihai cevabin nasil birlestirilecegi",
    )
    error: str | None = None
```

### 3.3. Ornek Planner Ciktisi

```json
{
  "success": true,
  "plan_summary": "Konut kredisi faizi, TUFE ve takipteki kredi oranlari ayri ayri bulunup 2024 doneminde karsilastirilacak.",
  "sub_tasks": [
    {
      "step": 1,
      "objective": "Konut kredisi faiz oranini temsil eden seriyi bul",
      "focus_query": "konut kredisi faiz",
      "expected_output": "Konut kredisi faiz serisi ve series_id",
      "constraints": ["yerel katalog oncelikli"],
      "date_range": "2024",
      "frequency_hint": "monthly",
      "analysis_type": "lookup"
    },
    {
      "step": 2,
      "objective": "TUFE enflasyon serisini bul",
      "focus_query": "TUFE endeksi",
      "expected_output": "TUFE serisi ve series_id",
      "constraints": ["EVDS veya Lakehouse"],
      "date_range": "2024",
      "frequency_hint": "monthly",
      "analysis_type": "lookup"
    },
    {
      "step": 3,
      "objective": "Takipteki krediler veya NPL oranini temsil eden seriyi bul",
      "focus_query": "takipteki krediler oran",
      "expected_output": "BDDK kredi kalite serisi ve series_id",
      "constraints": ["BDDK kaynakli seri tercih edilir"],
      "date_range": "2024",
      "frequency_hint": "monthly",
      "analysis_type": "lookup"
    },
    {
      "step": 4,
      "objective": "Serileri ortak frekansta hizalayip iliskiyi yorumla",
      "focus_query": "ortak donem korelasyon",
      "expected_output": "Korelasyon veya karsilastirma sonucu",
      "constraints": ["yalnizca tool ciktisina dayali yorum yap"],
      "date_range": "2024",
      "frequency_hint": "monthly",
      "analysis_type": "correlation"
    }
  ],
  "synthesis_guidance": "Once her seri icin kaynak ve tarih araligini belirt; sonra ortak donemdeki yon, guc ve veri sinirlarini acikla. Korelasyonu nedensellik gibi sunma."
}
```

---

## 4. Calisma Motoru ve LLM Ayrisitirma Mantigi

### 4.1. Provider Seviyesinde Structured Output Destegi

Planner'in deterministik JSON uretimi icin destek `AnalysisPlannerTool` icinde provider bypass edilerek degil, `backend/app/core/llm_provider.py` icindeki ortak `LLMProvider` arayuzune eklenerek saglanacak.

Beklenen provider gelistirmesi:

```python
class LLMProvider(ABC):
    @abstractmethod
    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> LLMResponse:
        raise NotImplementedError
```

Provider implementasyonlari:

- `KloudeksProvider.chat(...)`, `NvidiaProvider.chat(...)` ve `DeepSeekProvider.chat(...)` opsiyonel `temperature` parametresini API istegine ekler.
- `response_format` saglanirsa API istegine aynen gecilir.
- Bu degisiklik geriye uyumlu olmali; mevcut `provider.chat(messages, tools=tools_schema)` kullanimlari bozulmamalidir.

Planner kullanimi:

```python
response = provider.chat(
    messages=messages,
    tools=None,
    temperature=0.0,
    response_format={"type": "json_object"},
)
```

### 4.2. Pydantic Dogrulama ve Fallback

Planner, LLM cevabini dogrudan guvenilir kabul etmez:

1. JSON parse edilir.
2. `AnalysisPlannerTool.Output` ile Pydantic validasyonundan gecirilir.
3. JSON bozuksa, eksik alan varsa veya provider hata verirse kural tabanli fallback calisir.

Fallback minimum davranisi:

- `ve`, `ile`, `karsilastir`, `etki`, `korelasyon`, `trend`, `nedensellik`, `oran`, `endeks` gibi ayiricilarla 2-4 alt gorev uretilir.
- `focus_query` gereksiz baglaclar ve uzun tarih ifadeleri temizlenerek uretilir.
- `date_range`, `frequency_hint` ve `analysis_type` icin sadece sorudan acikca cikarilabilen bilgiler doldurulur.
- Fallback de `success=True` donebilir, ancak `plan_summary` icinde kural tabanli plan kullanildigi belirtilir.

---

## 5. Sistem Istemi ve Entegrasyon

### 5.1. `backend/app/prompts/system_prompt.md` Guncellemesi

Mevcut "once `series_catalog_search`" kurali kaldirilmayacak; baglama duyarli hale getirilecek.

Eklenecek/yumusatilacak kural:

```markdown
### Karmasik ve Cok Adimli Sorularda Planlama Kurali

Kullanicinin sorusu tek bir seri, gosterge, metrik veya kategori hakkindaysa once `series_catalog_search` kullan.

Ancak sorunun baglami:
1. Birden fazla seri, kaynak veya ekonomik/istatistiksel gostergenin birlikte bulunmasini,
2. Birden fazla analiz tool'unun sirayla calistirilmasini,
3. Korelasyon, etki, karsilastirma, nedensellik uyarisi, trend sentezi veya cok asamali arastirma yapilmasini
gerektiriyorsa, ilk adimda `analysis_planner` aracini cagir.

Planner sonucundaki `sub_tasks` listesini checklist olarak kullan. Her alt gorevdeki `focus_query` degerini arama icin baslangic noktasi yap; `constraints`, `date_range`, `frequency_hint` ve `analysis_type` alanlarini veri cekme ve sentez sirasinda koru.
```

### 5.2. `backend/app/agent/tool_registry.py` Kaydi

```python
from backend.app.tools.analysis_planner import AnalysisPlannerTool

...

registry.register(AnalysisPlannerTool())
```

Registry sirasinda `analysis_planner`, arama/planlama tool'lari arasinda erken kaydedilebilir:

```python
registry.register(AnalysisPlannerTool())
registry.register(SeriesCatalogSearchTool())
```

### 5.3. Scope Disi Isler

Bu plan `loop.py` icinde tool sonucu cache'leme, tablo ozetleme veya buyuk JSON sonuclari kisaltma isini uygulamaz. Bu konu ayri is kalemi olarak `C:\Projects\kkb\notlar\yapilacaklar_agent_ve_llm.md` dosyasinda takip edilmektedir.

---

## 6. Dogrulama ve Test Plani

### 6.1. Birim Testleri (`backend/tests/tools/test_analysis_planner.py`)

1. **Karmasik soru testi**
   - Girdi: "2024 yilinda mevduat faizleri ile tuketici kredileri arasindaki bagintiyi incele"
   - Beklenti: En az 3 mantikli `sub_tasks`; faiz, kredi ve iliski/sentez adimlari ayrilmali.

2. **Odak terimi testi**
   - `focus_query` degerleri kisa, arama motoruna uygun ve tek alt kavrama odakli olmali.
   - Tarih/frekans gibi kisitlar `focus_query` icinde kaybolmamali; `date_range` ve `frequency_hint` alanlarinda korunmali.

3. **Pydantic validasyon testi**
   - LLM JSON'u `Output` semasina valide edilmeli.
   - Eksik veya bozuk JSON'da fallback calismali.

4. **Fallback testi**
   - Provider hata firlattiginda tool patlamadan kural tabanli plan dondurmeli.

5. **Provider structured-output testi**
   - Fake provider ile `temperature=0.0` ve `response_format={"type": "json_object"}` parametrelerinin `chat` cagrisi icinde kullanildigi dogrulanmali.

### 6.2. Prompt ve Registry Testleri

1. `backend/tests/prompts/test_system_prompt_loader.py`
   - Sistem promptunda baglama duyali planner kurali bulunmali.
   - Basit tekil seri sorularinda `series_catalog_search` onceliginin korundugu metinsel olarak dogrulanmali.

2. `backend/tests/agent/test_tool_registry_defaults.py`
   - Default registry icinde `analysis_planner` bulunmali.

### 6.3. Uctan Uca Davranis Testi

Ornek soru:

```text
2024 yilinda mevduat faizleri ile tuketici kredileri arasindaki bagintiyi incele
```

Beklenen log akisi:

1. Ilk tool cagrisi `analysis_planner`.
2. Ardindan plandaki `focus_query` degerleriyle `series_catalog_search`.
3. Seri/eslesme bulunduktan sonra uygun veri cekme veya analiz tool'lari.
4. Nihai cevapta planner'in `synthesis_guidance` alanina uygun, tool ciktisina dayali ve nedensellik konusunda temkinli sentez.

Basit soru icin negatif kontrol:

```text
Konut kredisi faiz oraninin son degeri nedir?
```

Beklenti:

- Ilk tool `analysis_planner` degil, `series_catalog_search` olmali.

---

## 7. Kabul Kriterleri

- [ ] `analysis_planner` yalnizca cok adimli/cok kaynakli/cok tool gerektiren sorularda devreye girer.
- [ ] Basit tekil seri/metrik sorularinda `series_catalog_search` onceligi korunur.
- [ ] Planner ciktisi `constraints`, `date_range`, `frequency_hint` ve `analysis_type` alanlariyla baglami kaybetmez.
- [ ] Structured JSON destegi provider arayuzune geriye uyumlu sekilde eklenir.
- [ ] Tool, LLM/JSON hatalarinda kural tabanli fallback ile sonuc dondurur.
- [ ] Planda veya promptta "yuzde 100 isabet" gibi garanti iddialari bulunmaz; bunun yerine "odaklanmis aday sorgu" dili kullanilir.
- [ ] Context/cache/limit isi bu feature kapsaminda uygulanmaz; ayri backlog maddesi olarak kalir.
