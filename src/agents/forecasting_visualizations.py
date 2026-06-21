from pathlib import Path
from typing import Dict, Any, List

import matplotlib.pyplot as plt
import pandas as pd


def generate_forecasting_visualizations(
    df: pd.DataFrame,
    product_id: str,
    region: str,
    run_id: str,
    forecast_details: Dict[str, Any],
    forecast_confidence: float,
    output_root: str = "outputs/forecasting"
) -> List[str]:
    """
    Generates visualization PNG files for Forecasting Agent.

    Charts:
    1. Demand trend with moving averages
    2. Historical vs recent demand comparison
    3. Event and promotion flags
    4. Forecast summary

    Returns:
        List of saved chart file paths as strings.
    """

    output_dir = Path(output_root) / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    df = df.copy()
    df = df.sort_values("date")

    df["ma_7"] = df["units_sold"].rolling(window=7, min_periods=1).mean()
    df["ma_14"] = df["units_sold"].rolling(window=14, min_periods=1).mean()

    chart_files = []

    safe_name = f"{product_id}_{region}".replace(" ", "_")

    # --------------------------------------------------------
    # 1. Demand trend chart
    # --------------------------------------------------------
    trend_file = output_dir / f"{safe_name}_demand_trend.png"

    plt.figure(figsize=(12, 5))
    plt.plot(df["date"], df["units_sold"], label="Daily units sold")
    plt.plot(df["date"], df["ma_7"], label="7-day moving average")
    plt.plot(df["date"], df["ma_14"], label="14-day moving average")

    event_days = df[df["event_flag"] == 1]
    if not event_days.empty:
        plt.scatter(
            event_days["date"],
            event_days["units_sold"],
            label="Event/spike days"
        )

    plt.title(f"Demand Trend - {product_id}, {region}")
    plt.xlabel("Date")
    plt.ylabel("Units sold")
    plt.legend()
    plt.tight_layout()
    plt.savefig(trend_file, dpi=150)
    plt.close()

    chart_files.append(str(trend_file))

    # --------------------------------------------------------
    # 2. Historical vs recent demand comparison
    # --------------------------------------------------------
    avg_file = output_dir / f"{safe_name}_avg_comparison.png"

    labels = [
        "Historical avg",
        "Recent 14-day avg",
        "Recent 7-day avg",
        "Forecast"
    ]

    values = [
        forecast_details["historical_avg_demand"],
        forecast_details["recent_14_avg_demand"],
        forecast_details["recent_avg_demand"],
        forecast_details["forecasted_demand"],
    ]

    plt.figure(figsize=(8, 5))
    plt.bar(labels, values)
    plt.title(f"Historical vs Recent Demand - {product_id}, {region}")
    plt.ylabel("Units")
    plt.tight_layout()
    plt.savefig(avg_file, dpi=150)
    plt.close()

    chart_files.append(str(avg_file))

    # --------------------------------------------------------
    # 3. Event and promotion flags
    # --------------------------------------------------------
    flags_file = output_dir / f"{safe_name}_event_promotion_flags.png"

    plt.figure(figsize=(12, 4))
    plt.plot(df["date"], df["event_flag"], label="Event flag")
    plt.plot(df["date"], df["promotion_flag"], label="Promotion flag")
    plt.title(f"Event and Promotion Indicators - {product_id}, {region}")
    plt.xlabel("Date")
    plt.ylabel("Flag value")
    plt.legend()
    plt.tight_layout()
    plt.savefig(flags_file, dpi=150)
    plt.close()

    chart_files.append(str(flags_file))

    # --------------------------------------------------------
    # 4. Forecast summary chart
    # --------------------------------------------------------
    summary_file = output_dir / f"{safe_name}_forecast_summary.png"

    summary_labels = [
        "Forecasted demand",
        "Forecast confidence x100"
    ]

    summary_values = [
        forecast_details["forecasted_demand"],
        forecast_confidence * 100
    ]

    plt.figure(figsize=(7, 5))
    plt.bar(summary_labels, summary_values)
    plt.title(f"Forecast Summary - {product_id}, {region}")
    plt.ylabel("Value")
    plt.tight_layout()
    plt.savefig(summary_file, dpi=150)
    plt.close()

    chart_files.append(str(summary_file))

    return chart_files
