from __future__ import annotations

import datetime
import hashlib
import os
from pathlib import Path
from typing import Sequence

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[3]
CHARTS_DIR = PROJECT_ROOT / "data" / "charts"
CHARTS_DIR.mkdir(parents=True, exist_ok=True)


def _generate_filename(prefix: str, content_seed: str) -> tuple[Path, str]:
    now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    rand_hash = hashlib.md5(f"{content_seed}_{os.urandom(8)}".encode("utf-8")).hexdigest()[:8]
    filename = f"{prefix}_{now_str}_{rand_hash}.png"
    filepath = CHARTS_DIR / filename
    url = f"/static/charts/{filename}"
    return filepath, url


def generate_deflator_chart(
    dates: Sequence[str],
    nominal_values: Sequence[float],
    real_values: Sequence[float],
    series_name: str = "Seri",
    unit: str = "TL",
) -> str:
    """Nominal vs Reel Deger karsilastirmasi ve Enflasyon Erozyonu alani grafigi."""
    filepath, url = _generate_filename("deflator", series_name)

    fig, ax = plt.subplots(figsize=(10, 5), dpi=150)
    fig.patch.set_facecolor("#ffffff")
    ax.set_facecolor("#f8fafc")

    x_idx = np.arange(len(dates))
    y_nom = np.array(nominal_values, dtype=float)
    y_real = np.array(real_values, dtype=float)

    ax.plot(x_idx, y_nom, label=f"Nominal ({series_name})", color="#3b82f6", linewidth=2.5)
    ax.plot(x_idx, y_real, label=f"Reel (Enflasyondan Arındırılmış)", color="#10b981", linewidth=2.5, linestyle="--")

    ax.fill_between(
        x_idx,
        y_real,
        y_nom,
        where=(y_nom >= y_real),
        color="#ef4444",
        alpha=0.2,
        label="Enflasyon Erozyonu (Kayıp)",
    )
    ax.fill_between(
        x_idx,
        y_real,
        y_nom,
        where=(y_nom < y_real),
        color="#10b981",
        alpha=0.15,
        label="Reel Satın Alma Artışı",
    )

    step = max(1, len(dates) // 8)
    ax.set_xticks(x_idx[::step])
    ax.set_xticklabels([dates[i] for i in x_idx[::step]], rotation=30, ha="right", fontsize=9)

    ax.set_title(f"Reel Büyüme & Enflasyon Erozyon Analizi - {series_name}", fontsize=13, fontweight="bold", color="#1e293b", pad=12)
    ax.set_ylabel(f"Değer ({unit})", fontsize=10, fontweight="bold", color="#475569")
    ax.grid(True, linestyle=":", alpha=0.6, color="#cbd5e1")
    ax.legend(frameon=True, facecolor="#ffffff", edgecolor="#e2e8f0", loc="best", fontsize=9)

    plt.tight_layout()
    fig.savefig(filepath, dpi=150, bbox_inches="tight")
    plt.close(fig)

    return url


def generate_elasticity_chart(
    x_values: Sequence[float],
    y_values: Sequence[float],
    x_label: str,
    y_label: str,
    beta: float,
    r_squared: float,
    title: str | None = None,
) -> str:
    """Duyarlilik ve Esneklik icin Serpme ve OLS Regresyon Trend grafigi."""
    filepath, url = _generate_filename("elasticity", f"{x_label}_{y_label}")

    fig, ax = plt.subplots(figsize=(9, 5), dpi=150)
    fig.patch.set_facecolor("#ffffff")
    ax.set_facecolor("#f8fafc")

    x_arr = np.array(x_values, dtype=float)
    y_arr = np.array(y_values, dtype=float)

    ax.scatter(x_arr, y_arr, color="#3b82f6", alpha=0.75, edgecolors="#1d4ed8", s=50, label="Gözlemler")

    if len(x_arr) > 1 and not np.all(x_arr == x_arr[0]):
        sort_idx = np.argsort(x_arr)
        x_sorted = x_arr[sort_idx]
        poly = np.polyfit(x_arr, y_arr, 1)
        y_pred = np.polyval(poly, x_sorted)
        ax.plot(x_sorted, y_pred, color="#ef4444", linewidth=2.2, label=f"Regresyon Trendi (OLS)")

    chart_title = title or f"Duyarlılık ve Esneklik Analizi: {y_label} vs {x_label}"
    ax.set_title(chart_title, fontsize=12, fontweight="bold", color="#1e293b", pad=12)
    ax.set_xlabel(x_label, fontsize=10, fontweight="bold", color="#475569")
    ax.set_ylabel(y_label, fontsize=10, fontweight="bold", color="#475569")
    ax.grid(True, linestyle=":", alpha=0.6, color="#cbd5e1")

    info_box = f"Esneklik (β): {beta:.3f}\nBelirleme Katsayısı (R²): {r_squared:.3f}"
    ax.text(
        0.04,
        0.92,
        info_box,
        transform=ax.transAxes,
        fontsize=9,
        verticalalignment="top",
        bbox=dict(boxstyle="round,pad=0.5", facecolor="#ffffff", edgecolor="#cbd5e1", alpha=0.9),
    )

    ax.legend(frameon=True, facecolor="#ffffff", edgecolor="#e2e8f0", loc="lower right", fontsize=9)

    plt.tight_layout()
    fig.savefig(filepath, dpi=150, bbox_inches="tight")
    plt.close(fig)

    return url


def generate_concentration_chart(
    labels: Sequence[str],
    values: Sequence[float],
    cr3_pct: float,
    cr5_pct: float,
    hhi_score: float,
    dimension_name: str = "Kategori",
) -> str:
    """Konsantrasyon Analizi icin Pareto Bar & Kumulatif Lorenz Pay grafigi."""
    filepath, url = _generate_filename("concentration", dimension_name)

    fig, ax1 = plt.subplots(figsize=(10, 5), dpi=150)
    fig.patch.set_facecolor("#ffffff")
    ax1.set_facecolor("#f8fafc")

    x_idx = np.arange(len(labels))
    vals = np.array(values, dtype=float)
    total = np.sum(vals) if np.sum(vals) > 0 else 1.0
    shares_pct = (vals / total) * 100
    cum_shares = np.cumsum(shares_pct)

    bars = ax1.bar(x_idx, vals, color="#3b82f6", edgecolor="#1d4ed8", alpha=0.85, width=0.55, label="Risk / Hacim")
    ax1.set_xticks(x_idx)
    ax1.set_xticklabels(labels, rotation=25, ha="right", fontsize=9)
    ax1.set_ylabel("Hacim", fontsize=10, fontweight="bold", color="#1e293b")
    ax1.grid(axis="y", linestyle=":", alpha=0.6, color="#cbd5e1")

    ax2 = ax1.twinx()
    ax2.plot(x_idx, cum_shares, color="#ef4444", linewidth=2.5, marker="o", markersize=5, label="Kümülatif Pay (%)")
    ax2.set_ylabel("Kümülatif Pay (%)", fontsize=10, fontweight="bold", color="#ef4444")
    ax2.set_ylim(0, 105)

    if len(labels) >= 3:
        ax2.axhline(cr3_pct, color="#10b981", linestyle="--", linewidth=1.2, alpha=0.7, label=f"CR3: %{cr3_pct:.1f}")
    if len(labels) >= 5:
        ax2.axhline(cr5_pct, color="#f59e0b", linestyle="--", linewidth=1.2, alpha=0.7, label=f"CR5: %{cr5_pct:.1f}")

    hhi_status = (
        "Yüksek Yoğunlaşma" if hhi_score > 2500
        else "Orta Yoğunlaşma" if hhi_score >= 1500
        else "Düşük Yoğunlaşma / Rekabetçi"
    )
    badge_text = f"HHI: {hhi_score:.1f}\n{hhi_status}\nCR3: %{cr3_pct:.1f} | CR5: %{cr5_pct:.1f}"
    ax1.text(
        0.03,
        0.92,
        badge_text,
        transform=ax1.transAxes,
        fontsize=9,
        verticalalignment="top",
        bbox=dict(boxstyle="round,pad=0.5", facecolor="#ffffff", edgecolor="#cbd5e1", alpha=0.9),
    )

    ax1.set_title(f"Risk & Konsantrasyon Dağılımı ({dimension_name})", fontsize=12, fontweight="bold", color="#1e293b", pad=12)

    plt.tight_layout()
    fig.savefig(filepath, dpi=150, bbox_inches="tight")
    plt.close(fig)

    return url


def generate_cycle_chart(
    dates: Sequence[str],
    values: Sequence[float],
    peaks_indices: Sequence[int],
    troughs_indices: Sequence[int],
    title: str = "Döngü ve Dönüm Noktaları",
) -> str:
    """Zirve/Dip Isaretli Dongu ve Rejim Kirilim grafigi."""
    filepath, url = _generate_filename("cycle", title)

    fig, ax = plt.subplots(figsize=(11, 5), dpi=150)
    fig.patch.set_facecolor("#ffffff")
    ax.set_facecolor("#f8fafc")

    x_idx = np.arange(len(dates))
    y_vals = np.array(values, dtype=float)

    ax.plot(x_idx, y_vals, color="#3b82f6", linewidth=2.2, label="Trend / Seri Değeri")

    if len(peaks_indices) > 0:
        p_idx = [i for i in peaks_indices if 0 <= i < len(y_vals)]
        ax.scatter(
            p_idx,
            y_vals[p_idx],
            color="#10b981",
            marker="^",
            s=120,
            zorder=5,
            edgecolors="#065f46",
            label="Zirve (Peak)",
        )

    if len(troughs_indices) > 0:
        t_idx = [i for i in troughs_indices if 0 <= i < len(y_vals)]
        ax.scatter(
            t_idx,
            y_vals[t_idx],
            color="#ef4444",
            marker="v",
            s=120,
            zorder=5,
            edgecolors="#991b1b",
            label="Dip (Trough)",
        )

    step = max(1, len(dates) // 8)
    ax.set_xticks(x_idx[::step])
    ax.set_xticklabels([dates[i] for i in x_idx[::step]], rotation=30, ha="right", fontsize=9)

    ax.set_title(title, fontsize=12, fontweight="bold", color="#1e293b", pad=12)
    ax.set_ylabel("Değer", fontsize=10, fontweight="bold", color="#475569")
    ax.grid(True, linestyle=":", alpha=0.6, color="#cbd5e1")
    ax.legend(frameon=True, facecolor="#ffffff", edgecolor="#e2e8f0", loc="best", fontsize=9)

    plt.tight_layout()
    fig.savefig(filepath, dpi=150, bbox_inches="tight")
    plt.close(fig)

    return url
