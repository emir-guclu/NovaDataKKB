from duckduckgo_search import DDGS
import pandas as pd
import numpy as np

def web_search_tool(query: str, max_results: int = 3) -> str:
    """Performs a web search using DuckDuckGo and returns a summary of results."""
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        if not results:
            return "Arama sonucu bulunamadi."
        
        summary = "Web Arama Sonuclari:\n"
        for i, res in enumerate(results):
            summary += f"{i+1}. {res.get('title')}: {res.get('body')}\n"
        return summary
    except Exception as e:
        return f"Web arama hatasi: {str(e)}"

def change_detection_tool(series_data: list, threshold: float = 2.0) -> dict:
    """
    Analyzes a time series to find structural breaks or anomalies.
    """
    try:
        if not series_data or len(series_data) < 3:
            return {"error": "Analiz icin yeterli veri yok."}
            
        df = pd.DataFrame(series_data)
        if 'value' not in df.columns or 'date' not in df.columns:
            return {"error": "Veri formati hatali."}
            
        df['value'] = pd.to_numeric(df['value'], errors='coerce')
        df = df.dropna()
        
        if len(df) == 0:
            return {"error": "Gecerli veri bulunamadi."}
        
        mean = df['value'].mean()
        std = df['value'].std()
        
        if std == 0:
            return {"status": "Degisim yok.", "anomalies": []}
            
        df['z_score'] = (df['value'] - mean) / std
        anomalies = df[df['z_score'].abs() > threshold]
        
        trend = "Yatay"
        if len(df) > 4:
            first_half = df['value'].iloc[:len(df)//2].mean()
            second_half = df['value'].iloc[len(df)//2:].mean()
            if second_half > first_half * 1.05:
                trend = "Yukselis trendi"
            elif second_half < first_half * 0.95:
                trend = "Dusus trendi"
                
        results = {
            "genel_trend": trend,
            "ortalama_deger": float(mean),
            "kirilma_noktalari": []
        }
        
        for _, row in anomalies.iterrows():
            direction = "Ani Yukselis" if row['z_score'] > 0 else "Ani Dusus"
            results["kirilma_noktalari"].append({
                "tarih": row['date'],
                "deger": float(row['value']),
                "tip": direction
            })
            
        return results
    except Exception as e:
        return {"error": f"Change detection hatasi: {str(e)}"}
