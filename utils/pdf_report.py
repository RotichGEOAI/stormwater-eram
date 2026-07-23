"""
Builds the downloadable PDF snapshot: title, cost/co-benefit chart,
executive summary (single ward or comparative across wards), zone-level
recommendations, and the implementation timeline.
"""

from __future__ import annotations
import io
import pandas as pd
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4

from . import charts as chart_utils


def _executive_summary_single(totals: pd.DataFrame, ward: str) -> list[str]:
    d = totals[totals["Ward"] == ward]
    grey = d[d["Scenario"] == "Grey"].iloc[0]
    hybrid = d[d["Scenario"] == "Hybrid"].iloc[0]
    green = d[d["Scenario"] == "Green"].iloc[0]
    return [
        f"Grey: CAPEX ${grey['CAPEX_USD']:,.0f}, OPEX ${grey['OPEX_USD']:,.0f}/yr — limited co-benefits.",
        f"Hybrid: CAPEX ${hybrid['CAPEX_USD']:,.0f}, OPEX ${hybrid['OPEX_USD']:,.0f}/yr — moderate co-benefits.",
        f"Green: CAPEX ${green['CAPEX_USD']:,.0f}, OPEX ${green['OPEX_USD']:,.0f}/yr — strongest gains "
        f"(Carbon {green['Carbon_Sequestration']:.0f}, Cooling {green['Urban_Cooling']:.0f}, "
        f"Biodiversity {green['Biodiversity_Index']:.0f}).",
        "Recommendation: phase the transition Grey \u2192 Hybrid \u2192 Green where budget allows.",
    ]


def _comparative_summary(totals: pd.DataFrame, wards: list[str]) -> list[str]:
    stats = {}
    for ward in wards:
        d = totals[totals["Ward"] == ward]
        grey = d[d["Scenario"] == "Grey"].iloc[0]
        green = d[d["Scenario"] == "Green"].iloc[0]
        stats[ward] = {
            "CAPEX": grey["CAPEX_USD"] + green["CAPEX_USD"],
            "OPEX": grey["OPEX_USD"] + green["OPEX_USD"],
            "Carbon": green["Carbon_Sequestration"],
            "Cooling": green["Urban_Cooling"],
            "Biodiversity": green["Biodiversity_Index"],
        }
    capex_leader = max(stats, key=lambda w: stats[w]["CAPEX"])
    opex_leader = max(stats, key=lambda w: stats[w]["OPEX"])
    carbon_leader = max(stats, key=lambda w: stats[w]["Carbon"])
    cooling_leader = max(stats, key=lambda w: stats[w]["Cooling"])
    biodiversity_leader = max(stats, key=lambda w: stats[w]["Biodiversity"])
    return [
        f"{capex_leader} requires the largest CAPEX investment.",
        f"{opex_leader} has the highest ongoing OPEX.",
        f"{carbon_leader} leads in carbon sequestration potential.",
        f"{cooling_leader} leads in urban cooling potential.",
        f"{biodiversity_leader} leads in biodiversity index.",
        "Recommendation: balance CAPEX/OPEX exposure against ecosystem-service gains per ward.",
    ]


def _zone_recommendations(zones_df: pd.DataFrame, ward: str) -> list[str]:
    d = zones_df[(zones_df["Ward"] == ward) & (zones_df["Scenario"] == "Green")]
    lines = []
    for _, row in d.sort_values("Average_Runoff_mm", ascending=False).iterrows():
        if row["FloodRisk"] == "High":
            lines.append(f"{row['Zone']} ({row['LandUse']}): High flood risk — prioritize green "
                          f"retrofits (bioswales/wetlands) and detention capacity.")
        elif row["FloodRisk"] == "Moderate":
            lines.append(f"{row['Zone']} ({row['LandUse']}): Moderate risk — permeable pavement "
                          f"and roadside swales likely sufficient.")
        else:
            lines.append(f"{row['Zone']} ({row['LandUse']}): Low risk — maintain current drainage, "
                          f"monitor as imperviousness grows.")
    return lines


def build_pdf(zones_df: pd.DataFrame, totals: pd.DataFrame, wards: list[str]) -> bytes:
    """Assemble the full PDF report for one ward or a multi-ward comparison."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = []

    title = ", ".join(wards) + (" — Comparative Snapshot" if len(wards) > 1 else " — Snapshot")
    elements.append(Paragraph(title, styles["Title"]))
    elements.append(Spacer(1, 12))

    primary_ward = wards[0]
    infographic_path = chart_utils.transition_infographic(totals, primary_ward)
    elements.append(Image(infographic_path, width=440, height=250))
    elements.append(Spacer(1, 14))

    elements.append(Paragraph("Executive Summary", styles["Heading2"]))
    summary_points = (_comparative_summary(totals, wards) if len(wards) > 1
                       else _executive_summary_single(totals, primary_ward))
    for point in summary_points:
        elements.append(Paragraph(point, styles["Normal"]))
        elements.append(Spacer(1, 4))
    elements.append(Spacer(1, 10))

    elements.append(Paragraph("Zone-Specific Recommendations", styles["Heading2"]))
    for point in _zone_recommendations(zones_df, primary_ward):
        elements.append(Paragraph(point, styles["Normal"]))
        elements.append(Spacer(1, 4))
    elements.append(Spacer(1, 10))

    gantt_path = chart_utils.zone_gantt_chart(zones_df, primary_ward)
    elements.append(Paragraph("Implementation Timeline", styles["Heading2"]))
    elements.append(Image(gantt_path, width=440, height=230))

    doc.build(elements)
    buffer.seek(0)
    return buffer.read()
