from __future__ import annotations

import json
from pathlib import Path

import duckdb


ROOT = Path(__file__).resolve().parents[1]
LAKEHOUSE = ROOT / "data" / "lakehouse.duckdb"
SILVER = ROOT / "data" / "silver" / "silver.duckdb"
OUTPUT = ROOT / "tests" / "benchmark" / "questions.json"


def scalar(con, sql):
    row = con.execute(sql).fetchone()
    if not row:
        return None
    return row[0]


def row(con, sql):
    result = con.execute(sql).fetchone()
    return list(result) if result else []


def nums(values):
    out = []
    for value in values:
        if isinstance(value, (int, float)) and value is not None:
            out.append(float(value))
    return out


lake = duckdb.connect(str(LAKEHOUSE), read_only=True)
silver = duckdb.connect(str(SILVER), read_only=True)

questions = []


def add(
    qid,
    category,
    question,
    expected_tools,
    db,
    sql=None,
    must_contain_numbers=None,
    must_contain_text=None,
    verification_mode="ground_truth",
    notes=None,
):
    questions.append(
        {
            "id": qid,
            "category": category,
            "question": question,
            "expected_tools": expected_tools,
            "database": db,
            "ground_truth_query": sql,
            "must_contain_numbers": must_contain_numbers or [],
            "must_contain_text": must_contain_text or [],
            "verification_mode": verification_mode,
            "notes": notes or "",
        }
    )


# ---------------------------------------------------------------------------
# 1) SINGLE METRIC / SERIES DISCOVERY — 8
# ---------------------------------------------------------------------------

sql = """
SELECT value
FROM observations
WHERE series_id='HEALTH_MOH:hospital_beds_total'
  AND date='2024-12-31'
"""
add(
    "single_01",
    "single_metric",
    "2024 yılında Türkiye'deki toplam hastane yatağı sayısı kaçtır? Kaynağı ve birimi de belirt.",
    ["series_catalog_search"],
    "silver",
    sql,
    nums([scalar(silver, sql)]),
    ["HEALTH_MOH", "adet"],
)

metrics = [
    (
        "single_02",
        "BDDK aylık tüketici kredileri içindeki TP konut kredileri serisine göre 2026 Haziran ayında toplam konut kredisi hacmi kaç milyon TL idi?",
        "konut_kredisi_hacmi_tp",
    ),
    (
        "single_03",
        "2026 Haziran ayında konut kredisi faiz oranı kaçtı?",
        "konut_kredisi_faiz_orani",
    ),
    (
        "single_04",
        "EVDS TP.KFE.TR Türkiye Konut Fiyat Endeksi serisine göre 2026 Haziran değeri kaçtır?",
        "konut_fiyat_endeksi",
    ),
    (
        "single_05",
        "2026 Haziran ayında toplam konut satışı kaç adetti?",
        "toplam_konut_satisi",
    ),
]

for qid, question, col in metrics:
    sql = f"""
    SELECT {col}
    FROM gold_housing_credit_market
    WHERE date='2026-06-30'
    """
    add(
        qid,
        "single_metric",
        question,
        ["lakehouse_query"],
        "lakehouse",
        sql,
        nums([scalar(lake, sql)]),
    )

sql = """
SELECT toplam_kredi_hacmi
FROM gold_credit_market
WHERE date='2026-06-30'
"""
add(
    "single_06",
    "single_metric",
    "2026 Haziran ayında bankacılık sektörünün toplam kredi hacmi kaç milyon TL idi?",
    ["lakehouse_query"],
    "lakehouse",
    sql,
    nums([scalar(lake, sql)]),
)

sql = """
SELECT ticari_kredi_faiz_orani
FROM gold_credit_market
WHERE date='2026-06-30'
"""
add(
    "single_07",
    "single_metric",
    "2026 Haziran ayında ticari kredi faiz oranı kaçtı?",
    ["lakehouse_query"],
    "lakehouse",
    sql,
    nums([scalar(lake, sql)]),
)

sql = """
SELECT gold_silver_ratio
FROM gold_precious_metal_ratios_monthly
WHERE date='2026-06-30'
"""
add(
    "single_08",
    "single_metric",
    "2026 Haziran sonunda altın/gümüş oranı kaçtı?",
    ["lakehouse_query"],
    "lakehouse",
    sql,
    nums([scalar(lake, sql)]),
)


# ---------------------------------------------------------------------------
# 2) TREND / CHANGE — 7
# ---------------------------------------------------------------------------

trend_specs = [
    (
        "trend_01",
        "BDDK aylık tüketici kredileri içindeki TP konut kredileri serisine göre 2026 Ocak-Haziran arasında konut kredisi hacmi ne kadar değişti? Başlangıç, bitiş ve yüzde değişimi ver.",
        "gold_housing_credit_market",
        "konut_kredisi_hacmi_tp",
    ),
    (
        "trend_02",
        "2026 Ocak-Haziran arasında konut fiyat endeksi ne kadar değişti?",
        "gold_housing_credit_market",
        "konut_fiyat_endeksi",
    ),
    (
        "trend_03",
        "EVDS TP.BKR.TRY.18 stok konut kredisi faiz oranı 2026 Ocak-Haziran arasında nasıl değişti?",
        "SPECIAL_STOCK_RATE",
        "value",
    ),
    (
        "trend_04",
        "2026 Ocak-Haziran arasında toplam kredi hacmi ne kadar değişti?",
        "gold_credit_market",
        "toplam_kredi_hacmi",
    ),
    (
        "trend_05",
        "2026 Ocak-Haziran arasında ticari kredi faiz oranının başlangıç değerini, bitiş değerini ve dönem başından dönem sonuna oransal yüzde değişimini hesapla.",
        "gold_credit_market",
        "ticari_kredi_faiz_orani",
    ),
    (
        "trend_06",
        "2026 Ocak-Haziran arasında altın/gümüş oranındaki değişimi hesapla.",
        "gold_precious_metal_ratios_monthly",
        "gold_silver_ratio",
    ),
]

for qid, question, table, col in trend_specs:
    if table == "SPECIAL_STOCK_RATE":
        sql = """
        WITH x AS (
          SELECT
            MAX(CASE WHEN date='2026-01-31' THEN value END) AS start_value,
            MAX(CASE WHEN date='2026-06-30' THEN value END) AS end_value
          FROM observations
          WHERE series_id='EVDS:TP.BKR.TRY.18'
        )
        SELECT
          start_value,
          end_value,
          ((end_value / start_value) - 1) * 100 AS pct_change
        FROM x
        """
        values = row(silver, sql)
        add(
            qid,
            "trend_change",
            question,
            ["series_catalog_search", "change_detection"],
            "silver",
            sql,
            nums(values),
            ["TP.BKR.TRY.18"],
        )
        continue

    sql = f"""
    WITH x AS (
      SELECT
        MAX(CASE WHEN date='2026-01-31' THEN {col} END) AS start_value,
        MAX(CASE WHEN date='2026-06-30' THEN {col} END) AS end_value
      FROM {table}
    )
    SELECT
      start_value,
      end_value,
      ((end_value / start_value) - 1) * 100 AS pct_change
    FROM x
    """
    values = row(lake, sql)
    add(
        qid,
        "trend_change",
        question,
        ["lakehouse_query"],
        "lakehouse",
        sql,
        nums(values),
    )

sql = """
WITH x AS (
  SELECT
    MAX(CASE WHEN date='2020-12-31' THEN value END) AS start_value,
    MAX(CASE WHEN date='2024-12-31' THEN value END) AS end_value
  FROM observations
  WHERE series_id='HEALTH_MOH:hospital_beds_total'
)
SELECT
  start_value,
  end_value,
  ((end_value / start_value)-1)*100 AS pct_change
FROM x
"""
add(
    "trend_07",
    "trend_change",
    "Türkiye'deki toplam hastane yatağı sayısı 2020'den 2024'e ne kadar arttı? Sayısal ve yüzde değişimi ver.",
    ["series_catalog_search", "change_detection"],
    "silver",
    sql,
    nums(row(silver, sql)),
    ["HEALTH_MOH"],
)


# ---------------------------------------------------------------------------
# 3) CROSS-MARKET / ELASTICITY / RELATION — 6
# ---------------------------------------------------------------------------

relations = [
    (
        "relation_02",
        "2024-2026 döneminde BDDK TP konut kredisi hacmi ile EVDS TP.KFE.TR konut fiyat endeksi arasındaki Pearson korelasyonu nedir?",
        "konut_kredisi_hacmi_tp",
        "konut_fiyat_endeksi",
    ),
    (
        "relation_03",
        "2024-2026 döneminde BDDK TP konut kredisi hacmi ile EVDS TP.AKONUTSAT1.KTRTOPLAM toplam konut satışları arasındaki Pearson korelasyonu nedir?",
        "konut_kredisi_hacmi_tp",
        "toplam_konut_satisi",
    ),
]

sql = """
WITH housing AS (
  SELECT date, value AS housing_volume
  FROM observations
  WHERE series_id='BDDK_MONTHLY:tuketici_kredileri:tuketici_kredileri_konut'
    AND json_extract_string(dims, '$.variable')='TP'
    AND date BETWEEN '2026-01-31' AND '2026-06-30'
),
rate AS (
  SELECT date, value AS housing_rate
  FROM observations
  WHERE series_id='EVDS:TP.BKR.TRY.18'
    AND date BETWEEN '2026-01-31' AND '2026-06-30'
)
SELECT corr(housing_volume, housing_rate)
FROM housing
JOIN rate USING (date)
"""
add(
    "relation_01",
    "cross_market",
    "2026 Ocak-Haziran döneminde BDDK TP konut kredisi hacmi ile EVDS TP.BKR.TRY.18 stok konut kredisi faiz oranı arasındaki Pearson korelasyonu nedir?",
    ["series_catalog_search", "causality_check"],
    "silver",
    sql,
    nums([scalar(silver, sql)]),
)

for qid, question, x, y in relations:
    sql = f"""
    SELECT corr({x}, {y})
    FROM gold_housing_credit_market
    WHERE date BETWEEN '2024-01-31' AND '2026-06-30'
      AND {x} IS NOT NULL
      AND {y} IS NOT NULL
    """
    add(
        qid,
        "cross_market",
        question,
        ["lakehouse_query", "causality_check"],
        "lakehouse",
        sql,
        nums([scalar(lake, sql)]),
    )

sql = """
SELECT corr(toplam_kredi_hacmi, ticari_kredi_faiz_orani)
FROM gold_credit_market
WHERE date BETWEEN '2024-01-31' AND '2026-06-30'
"""
add(
    "relation_04",
    "cross_market",
    "2024-2026 döneminde toplam kredi hacmi ile ticari kredi faiz oranı arasındaki korelasyon nedir?",
    ["lakehouse_query", "causality_check"],
    "lakehouse",
    sql,
    nums([scalar(lake, sql)]),
)

sql = """
SELECT regr_slope(
    ln(konut_kredisi_hacmi_tp),
    ln(konut_fiyat_endeksi)
)
FROM gold_housing_credit_market
WHERE date BETWEEN '2024-01-31' AND '2026-06-30'
  AND konut_kredisi_hacmi_tp > 0
  AND konut_fiyat_endeksi > 0
"""
add(
    "relation_05",
    "cross_market",
    "2024-2026 döneminde BDDK TP konut kredisi hacminin EVDS TP.KFE.TR konut fiyat endeksine göre log-log esnekliğini yaklaşık hesapla.",
    ["lakehouse_query", "elasticity_and_sensitivity_analyzer"],
    "lakehouse",
    sql,
    nums([scalar(lake, sql)]),
)

sql = """
SELECT corr(gold_mom_pct_change, silver_mom_pct_change)
FROM gold_precious_metal_ratios_monthly
WHERE date BETWEEN '2021-01-31' AND '2026-06-30'
"""
add(
    "relation_06",
    "cross_market",
    "2021-2026 döneminde altın ve gümüşün aylık değişimleri arasındaki korelasyon nedir?",
    ["lakehouse_query", "causality_check"],
    "lakehouse",
    sql,
    nums([scalar(lake, sql)]),
)


# ---------------------------------------------------------------------------
# 4) FINTURK / GEO / NPL — 6
# ---------------------------------------------------------------------------

sql = """
SELECT npl_ratio * 100
FROM gold_finturk_province_credit_quality
WHERE date='2026-06-30' AND province='Ankara'
"""
add(
    "finturk_01",
    "finturk_geo",
    "2026 Haziran sonunda Ankara'nın takipteki alacak oranı (NPL ratio) nedir?",
    ["lakehouse_query"],
    "lakehouse",
    sql,
    nums([scalar(lake, sql)]),
    ["Ankara"],
)

sql = """
SELECT total_cash_loans
FROM gold_finturk_province_credit_quality
WHERE date='2026-06-30' AND province='Ankara'
"""
add(
    "finturk_02",
    "finturk_geo",
    "2026 Haziran sonunda Ankara'daki toplam nakdi kredi tutarı nedir? Birimi koru.",
    ["lakehouse_query"],
    "lakehouse",
    sql,
    nums([scalar(lake, sql)]),
    ["Ankara"],
)

sql = """
SELECT npl_ratio * 100
FROM gold_finturk_province_credit_quality
WHERE date='2026-06-30' AND province='İstanbul'
"""
add(
    "finturk_03",
    "finturk_geo",
    "2026 Haziran sonunda İstanbul'un NPL oranı nedir?",
    ["lakehouse_query"],
    "lakehouse",
    sql,
    nums([scalar(lake, sql)]),
    ["İstanbul"],
)

sql = """
SELECT province, npl_ratio * 100 AS npl_pct
FROM gold_finturk_province_credit_quality
WHERE date='2026-06-30' AND geo_level='province'
ORDER BY npl_ratio DESC
LIMIT 1
"""
top_npl = row(lake, sql)
add(
    "finturk_04",
    "finturk_geo",
    "2026 Haziran sonunda NPL oranı en yüksek il hangisidir ve oran kaçtır?",
    ["lakehouse_query", "risk_concentration_analyzer"],
    "lakehouse",
    sql,
    nums(top_npl),
    [str(top_npl[0])] if top_npl else [],
)

sql = """
SELECT province, npl_ratio * 100 AS npl_pct
FROM gold_finturk_province_credit_quality
WHERE date='2026-06-30'
  AND geo_level='province'
  AND npl_ratio IS NOT NULL
ORDER BY npl_ratio ASC
LIMIT 1
"""
low_npl = row(lake, sql)
add(
    "finturk_05",
    "finturk_geo",
    "2026 Haziran sonunda NPL oranı en düşük il hangisidir ve oran kaçtır?",
    ["lakehouse_query"],
    "lakehouse",
    sql,
    nums(low_npl),
    [str(low_npl[0])] if low_npl else [],
)

sql = """
SELECT province, total_cash_loans
FROM gold_finturk_province_credit_quality
WHERE date='2026-06-30' AND geo_level='province'
ORDER BY total_cash_loans DESC
LIMIT 1
"""
top_credit = row(lake, sql)
add(
    "finturk_06",
    "finturk_geo",
    "2026 Haziran sonunda toplam nakdi kredi hacmi en yüksek il hangisidir ve tutar nedir?",
    ["lakehouse_query", "risk_concentration_analyzer"],
    "lakehouse",
    sql,
    nums(top_credit),
    [str(top_credit[0])] if top_credit else [],
)


# ---------------------------------------------------------------------------
# 5) ANOMALY / SHOCK — 5
# ---------------------------------------------------------------------------

shock_specs = [
    (
        "anomaly_01",
        "BDDK TP konut kredisi hacminde 2021-2026 arasında en büyük aylık yüzde artış hangi ayda gerçekleşti ve oran kaçtı?",
        "gold_housing_credit_market",
        "konut_kredisi_hacmi_tp",
    ),
    (
        "anomaly_02",
        "Toplam kredi hacminde 2021-2026 arasında en büyük aylık yüzde artış hangi ayda gerçekleşti ve oran kaçtı?",
        "gold_credit_market",
        "toplam_kredi_hacmi",
    ),
    (
        "anomaly_03",
        "Konut fiyat endeksinde 2021-2026 arasında en büyük aylık yüzde değişim hangi ayda gerçekleşti?",
        "gold_housing_credit_market",
        "konut_fiyat_endeksi",
    ),
    (
        "anomaly_04",
        "Konut satışlarında 2021-2026 arasında mutlak olarak en sert aylık yüzde hareket hangi ayda gerçekleşti?",
        "gold_housing_credit_market",
        "toplam_konut_satisi",
    ),
    (
        "anomaly_05",
        "Altın/gümüş oranında 2021-2026 arasında mutlak olarak en sert aylık değişim hangi ayda gerçekleşti?",
        "gold_precious_metal_ratios_monthly",
        "gold_silver_ratio",
    ),
]

for qid, question, table, col in shock_specs:
    sql = f"""
    WITH x AS (
      SELECT
        date,
        {col},
        LAG({col}) OVER (ORDER BY date) AS prev_value
      FROM {table}
    ),
    c AS (
      SELECT
        date,
        (({col}/prev_value)-1)*100 AS pct_change
      FROM x
      WHERE prev_value IS NOT NULL AND prev_value <> 0
    )
    SELECT
      EXTRACT(YEAR FROM date) AS year,
      EXTRACT(MONTH FROM date) AS month,
      pct_change
    FROM c
    ORDER BY ABS(pct_change) DESC
    LIMIT 1
    """
    values = row(lake, sql)
    add(
        qid,
        "anomaly_shock",
        question,
        ["lakehouse_query", "anomaly_detection"],
        "lakehouse",
        sql,
        nums(values),
    )


# ---------------------------------------------------------------------------
# 6) LIVE EVDS — 3
# Exact numbers intentionally not frozen.
# ---------------------------------------------------------------------------

live_questions = [
    (
        "live_01",
        "EVDS üzerinde güncel USD/TL döviz kuru serisini bul ve en güncel mevcut gözlemi getir. Tarihi ve kaynağı açıkça yaz.",
    ),
    (
        "live_02",
        "EVDS üzerinden konut fiyat endeksi serisini bul ve en güncel mevcut değeri getir.",
    ),
    (
        "live_03",
        "EVDS üzerinden tüketici fiyat endeksi (TÜFE) serisini bul ve en güncel mevcut değeri getir.",
    ),
]

for qid, question in live_questions:
    add(
        qid,
        "live_evds",
        question,
        ["series_catalog_search", "evds_data_service"],
        "live",
        None,
        [],
        ["EVDS"],
        verification_mode="live_tool",
        notes="Canlı EVDS değeri koşu tarihine göre değişebilir; sayı sabitlenmez.",
    )


# ---------------------------------------------------------------------------
# 7) EDGE CASES — 5
# ---------------------------------------------------------------------------

add(
    "edge_01",
    "edge_case",
    "HEALTH_MOH:hospital_beds_total serisinin veri sağlığını değerlendir. Kaç gözlem var, kaç gözlem bekleniyor ve eksik oranı nedir?",
    ["data_health_report"],
    "silver",
    None,
    [6.0, 23.0, 17.0, 73.91],
    ["WARNING"],
    verification_mode="static_contract",
)

add(
    "edge_02",
    "edge_case",
    "HEALTH_MOH:hospital_beds_total için 2025 yılı değerini ver. Veri yoksa sayı uydurma ve mevcut olmadığını açıkça söyle.",
    ["series_catalog_search"],
    "silver",
    """
    SELECT COUNT(*)
    FROM observations
    WHERE series_id='HEALTH_MOH:hospital_beds_total'
      AND date='2025-12-31'
    """,
    [0.0],
    ["mevcut"],
    notes="Amaç gelecekte/veri kapsamı dışında değer uydurulmamasını ölçmek.",
)

add(
    "edge_03",
    "edge_case",
    "BDDK FinTürk nakdi kredi verisinin birimini aynen belirt; milyon TL'ye kendiliğinden dönüştürme.",
    ["series_catalog_search"],
    "silver",
    None,
    [],
    ["bin TL"],
    verification_mode="static_contract",
)

add(
    "edge_04",
    "edge_case",
    "Veri kataloğunda 'kredi' araması yap. Birden fazla seri varsa tek bir seriyi keyfi olarak doğru kabul etme; uygun adayları belirt.",
    ["series_catalog_search"],
    "silver",
    None,
    [],
    [],
    verification_mode="behavioral",
)

add(
    "edge_05",
    "edge_case",
    "NovaData veri kataloğunda 'mars nüfusu bankacılık kredisi' adlı bir seri var mı? Yoksa varmış gibi veri üretme.",
    ["series_catalog_search"],
    "silver",
    None,
    [],
    [],
    verification_mode="behavioral",
)



# ---------------------------------------------------------------------------
# BENCHMARK CONTRACT NORMALIZATION
# ---------------------------------------------------------------------------
# Some natural-language concepts have multiple valid series/methodologies.
# Pin those questions to the exact NovaData contract being verified so the
# benchmark measures correctness rather than semantic ambiguity.

by_id = {q["id"]: q for q in questions}

# Gold monthly precious-metal ratio contract.
by_id["single_08"]["question"] = (
    "Lakehouse'taki gold_precious_metal_ratios_monthly tablosuna göre "
    "2026 Haziran gold_silver_ratio değeri kaçtır?"
)

by_id["trend_06"]["question"] = (
    "Lakehouse'taki gold_precious_metal_ratios_monthly tablosuna göre "
    "2026 Ocak-Haziran arasında gold_silver_ratio değerinin "
    "başlangıç, bitiş ve oransal yüzde değişimini hesapla."
)

by_id["relation_06"]["question"] = (
    "Lakehouse'taki gold_precious_metal_ratios_monthly tablosunda "
    "2021-2026 dönemindeki gold_mom_pct_change ve "
    "silver_mom_pct_change kolonlarının Pearson korelasyonu nedir?"
)

by_id["anomaly_05"]["question"] = (
    "Lakehouse'taki gold_precious_metal_ratios_monthly tablosunda "
    "2021-2026 döneminde gold_silver_ratio_pct_change kolonunun "
    "mutlak değerce en sert aylık değişimi hangi ayda gerçekleşti?"
)

# Exact KFE contract: local canonical EVDS series, not archived legacy KFE.
by_id["trend_02"]["question"] = (
    "EVDS TP.KFE.TR Türkiye Konut Fiyat Endeksi serisine göre "
    "2026 Ocak-Haziran arasında endeks ne kadar değişti?"
)
by_id["trend_02"]["expected_tools"] = [
    "series_catalog_search",
    "change_detection",
]

# FinTürk: benchmark the canonical Gold npl_ratio metric itself rather than
# asking the agent to independently choose another NPL denominator formula.
for qid in ["finturk_01", "finturk_03", "finturk_04", "finturk_05"]:
    by_id[qid]["question"] = (
        by_id[qid]["question"]
        .replace(
            "NPL ratio",
            "Gold tablodaki npl_ratio metriği"
        )
        .replace(
            "NPL oranı",
            "Gold tablodaki npl_ratio metriği"
        )
    )

# Month names are semantic answers; requiring literal month numbers creates
# false negatives ("Kasım" vs 11, "Aralık" vs 12).
by_id["anomaly_02"]["must_contain_numbers"] = [
    2021.0,
    14.473711467828476,
]
by_id["anomaly_02"]["must_contain_text"] = ["Kasım"]

by_id["anomaly_03"]["must_contain_numbers"] = [
    2021.0,
    14.298018949181746,
]
by_id["anomaly_03"]["must_contain_text"] = ["Aralık"]

by_id["anomaly_05"]["must_contain_numbers"] = [
    2025.0,
    -19.52228888048272,
]
by_id["anomaly_05"]["must_contain_text"] = ["Aralık"]

# Missing data must be expressed as absence, not as the numeric value zero.
by_id["edge_02"]["must_contain_numbers"] = []
by_id["edge_02"]["must_contain_text"] = ["mevcut değil"]

assert len(questions) == 40, len(questions)

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
OUTPUT.write_text(
    json.dumps(questions, ensure_ascii=False, indent=2),
    encoding="utf-8",
)

from collections import Counter

counts = Counter(q["category"] for q in questions)

print(f"Wrote {len(questions)} questions -> {OUTPUT}")
for category, count in counts.items():
    print(f"{category:20s} {count}")
