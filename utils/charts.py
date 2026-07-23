"""
All chart builders: an interactive Plotly scenario-comparison chart for the
live dashboard (legend clicks toggle CAPEX/OPEX/co-benefit traces for free),
a matplotlib "transition infographic" for PDF export, and Gantt-style
implementation timelines (per-ward and multi-ward).
"""

from __future__ import annotations
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import plotly.graph_objects as go

SCENARIO_ORDER = ["Grey", "Hybrid", "Green"]
CO_BENEFIT_COLORS = {"Carbon_Sequestration": "#1b5e20", "Urban_Cooling": "#0d47a1", "Biodiversity_Index": "#6a1b9a"}
CO_BENEFIT_ICONS = {"Carbon_Sequestration": "🌳", "Urban_Cooling": "💧", "Biodiversity_Index": "🦋"}


def aggregate_costs_and_services(df: pd.DataFrame) -> pd.DataFrame:
    """Sum cost/co-benefit columns by Ward + Scenario across all zones."""
    numeric_cols = ["CAPEX_USD", "OPEX_USD", "NPV_USD", "Carbon_Sequestration",
                     "Urban_Cooling", "Biodiversity_Index"]
    grouped = df.groupby(["Ward", "Scenario"], as_index=False)[numeric_cols].sum()
    grouped["Scenario"] = pd.Categorical(grouped["Scenario"], categories=SCENARIO_ORDER, ordered=True)
    return grouped.sort_values(["Ward", "Scenario"])


def scenario_comparison_figure(totals: pd.DataFrame, ward: str) -> go.Figure:
    """Interactive CAPEX/OPEX + co-benefit comparison for one ward (Plotly)."""
    d = totals[totals["Ward"] == ward].sort_values("Scenario")
    fig = go.Figure()
    fig.add_bar(x=d["Scenario"], y=d["CAPEX_USD"], name="CAPEX (USD)", marker_color="#ef6c00")
    fig.add_bar(x=d["Scenario"], y=d["OPEX_USD"], name="OPEX (USD)", marker_color="#90caf9")
    for col in ["Carbon_Sequestration", "Urban_Cooling", "Biodiversity_Index"]:
        fig.add_scatter(x=d["Scenario"], y=d[col],
                         name=f"{CO_BENEFIT_ICONS[col]} {col.replace('_', ' ')}",
                         yaxis="y2", mode="lines+markers",
                         line=dict(color=CO_BENEFIT_COLORS[col], width=3))
    fig.update_layout(
        barmode="stack",
        title=f"{ward} — Cost vs. Co-benefits by Scenario",
        yaxis=dict(title="Lifecycle Cost (USD)"),
        yaxis2=dict(title="Co-benefit Index (0–100)", overlaying="y", side="right", range=[0, 100]),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        height=430, margin=dict(t=70, b=10),
    )
    return fig


def multiward_comparison_figure(totals: pd.DataFrame, wards: list[str], metric: str) -> go.Figure:
    """Grouped bar comparing a single metric (e.g. CAPEX_USD) across wards & scenarios."""
    d = totals[totals["Ward"].isin(wards)]
    fig = go.Figure()
    for scenario in SCENARIO_ORDER:
        sub = d[d["Scenario"] == scenario]
        fig.add_bar(x=sub["Ward"], y=sub[metric], name=scenario)
    fig.update_layout(
        barmode="group",
        title=f"{metric.replace('_', ' ')} by Ward & Scenario",
        height=420, legend_title="Scenario",
    )
    return fig


def transition_infographic(totals: pd.DataFrame, ward: str, show_capex=True,
                            show_opex=True, show_services=True) -> str:
    """Matplotlib bar+line infographic (CAPEX/OPEX bars, co-benefit trend lines) -> PNG path."""
    d = totals[totals["Ward"] == ward].sort_values("Scenario")
    phases = d["Scenario"].astype(str).tolist()

    fig, ax1 = plt.subplots(figsize=(9, 5))
    ax1.set_title(f"{ward} — Grey → Hybrid → Green Transition", fontsize=13, weight="bold")

    if show_capex or show_opex:
        for i, (_, row) in enumerate(d.iterrows()):
            total = 0
            if show_capex:
                ax1.bar(i, row["CAPEX_USD"], color="#ef6c00", width=0.6, edgecolor="black")
                total += row["CAPEX_USD"]
            if show_opex:
                ax1.bar(i, row["OPEX_USD"], bottom=total, color="#90caf9", width=0.6, edgecolor="black")
                total += row["OPEX_USD"]
            ax1.text(i, total * 1.02, f"${total:,.0f}", ha="center", fontsize=9)
    ax1.set_ylabel("Total Lifecycle Cost (USD)")
    ax1.set_xticks(range(len(phases)))
    ax1.set_xticklabels(phases)

    ax2 = ax1.twinx()
    if show_services:
        for col in ["Carbon_Sequestration", "Urban_Cooling", "Biodiversity_Index"]:
            values = d[col].values
            ax2.plot(range(len(phases)), values, marker="o",
                     color=CO_BENEFIT_COLORS[col],
                     label=col.replace('_', ' '))
        ax2.set_ylabel("Co-benefit Index (0–100)")
        ax2.legend(loc="upper left", fontsize=8, framealpha=0.9)

    fig.tight_layout()
    path = f"/tmp/{ward.replace(' ', '_').replace('(', '').replace(')', '')}_infographic.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def zone_gantt_chart(zones_df: pd.DataFrame, ward: str) -> str:
    """Per-zone implementation Gantt chart, bar length scaled by CAPEX budget share."""
    d = zones_df[(zones_df["Ward"] == ward) & (zones_df["Scenario"] == "Green")].copy()
    if d.empty:
        d = zones_df[zones_df["Ward"] == ward].copy()
    d = d.sort_values("CAPEX_USD", ascending=False)

    phases = ["Design & Permitting", "Procurement", "Construction", "Commissioning"]
    phase_share = np.array([0.15, 0.15, 0.55, 0.15])

    fig, ax = plt.subplots(figsize=(9, max(3, 0.5 * len(d))))
    start = 0.0
    colors = ["#8d6e63", "#ffb74d", "#4caf50", "#42a5f5"]
    for i, (phase, share, color) in enumerate(zip(phases, phase_share, colors)):
        dur = share * 12  # 12-month rollout window
        ax.barh(d["Zone"], [dur] * len(d), left=start, color=color, edgecolor="black", label=phase)
        start += dur
    ax.set_xlabel("Months")
    ax.set_title(f"{ward} — Implementation Timeline (Zone-Level)", weight="bold")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.15), ncol=4, fontsize=8)
    fig.tight_layout()
    path = f"/tmp/{ward.replace(' ', '_').replace('(', '').replace(')', '')}_gantt.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def ward_budget_gantt(totals: pd.DataFrame) -> str:
    """Ward-wide investment schedule: total CAPEX per ward staged over time."""
    ward_totals = totals.groupby("Ward", as_index=False)["CAPEX_USD"].sum().sort_values(
        "CAPEX_USD", ascending=False)

    fig, ax = plt.subplots(figsize=(9, max(3, 0.5 * len(ward_totals))))
    phases = ["Year 1 (Design)", "Year 2 (Build)", "Year 3 (Scale-up)"]
    phase_share = [0.2, 0.5, 0.3]
    colors = ["#8d6e63", "#4caf50", "#42a5f5"]
    start = np.zeros(len(ward_totals))
    for phase, share, color in zip(phases, phase_share, colors):
        widths = ward_totals["CAPEX_USD"].values * share / 1000  # thousands USD, as duration proxy
        ax.barh(ward_totals["Ward"], widths, left=start, color=color, edgecolor="black", label=phase)
        start += widths
    ax.set_xlabel("Cumulative Investment ($'000, staged)")
    ax.set_title("Ward-Wide Investment Schedule", weight="bold")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.15), ncol=3, fontsize=8)
    fig.tight_layout()
    path = "/tmp/ward_budget_gantt.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path
