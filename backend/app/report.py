"""PDF report: insights (KPIs, top intents with notes, charts, overlaps) plus the full taxonomy overview."""
from __future__ import annotations

import io
import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.graphics.shapes import Drawing, Line, Polygon, PolyLine, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (CondPageBreak, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

from . import db, insights, language, taxonomy

TEXT: dict[str, dict[str, str]] = {
    "en": {
        "title": "Intent analysis report", "project": "Project", "dataset": "Dataset", "created": "Created",
        "interactions": "Interactions analysed", "version": "Taxonomy version", "language": "Analysis language",
        "models": "Models", "overview": "Overview", "page": "Page {n}",
        "m.processed": "Processed interactions", "m.discovered": "Unique discovered intents (L4)",
        "m.l3": "L3 categories", "m.unclassified": "Unclassified interactions",
        "m.open": "Open candidates (no L4 yet)", "m.overlapping": "Overlapping categories",
        "volume": "Intent volume", "top": "Top {n} intents by interaction volume",
        "k.topCover": "Top {n} intents cover", "k.topCoverSub": "of all analysed interactions",
        "k.for80": "Intents for 80 % coverage", "k.for80Sub": "{n} of {total} L4 intents",
        "k.longTail": "Long-tail intents", "k.longTailSub": "max. {n} interactions each",
        "k.multi": "Multi-intent interactions", "k.multiSub": "avg. {n} intents per interaction",
        "k.classified": "Classified interactions", "k.classifiedSub": "{n} with at least one L4 intent",
        "nInteractions": "{n} interactions · {share} of all interactions", "channels": "Channels",
        "segments": "Segments", "noNote": "No note generated yet (Insights tab → generate notes).",
        "outdated": "(note may be outdated)",
        "disclaimer": "Indication based on volume only. Whether an intent can actually be optimised also depends on "
                      "factors such as average handling time (AHT), after-call work (ACW), transfers, repeat contacts "
                      "and business or regulatory reasons. This data is not part of the analysis, so validate the "
                      "notes before acting on them.",
        "mix": "Top {n} share of all extracted intents",
        "mixText": "One interaction can contain several intents, so this counts intents, not interactions.",
        "other": "Other L4 intents ({n})", "none": "Not yet in an L4",
        "coverage": "Cumulative interaction coverage",
        "coverageText": "Share of analysed interactions covered by the N most frequent L4 intents (Pareto view).",
        "coverageAxis": "Number of L4 intents, by volume",
        "quality": "Discovery & taxonomy quality", "curve": "Intent discovery curve",
        "curveText": "Distinct L4 categories (current taxonomy) observed within the first N analysed interactions. "
                     "A flattening curve suggests saturation for this dataset only; it is not proof of completeness.",
        "curveAxis": "Analysed interactions",
        "overlap": "Closest categories (overlap check)",
        "overlapText": "Most similar L4 pairs within the same L2 by embedding similarity ({n} pairs compared). Pairs at "
                       "or above the merge threshold ({th}) are proposed for merging.",
        "colA": "Category A", "colB": "Category B", "colL2": "L2", "colSim": "Similarity", "colNote": "Note",
        "sameL3": "same L3", "proposed": "merge proposed", "noOverlaps": "No comparable category pairs yet.",
        "taxonomy": "Taxonomy overview", "taxCounts": "{l1} L1 · {l2} L2 · {l3} L3 · {l4} L4 categories",
        "colCategory": "Category", "colLevel": "Level", "colCount": "Interactions",
        "proposedNode": "proposed", "noData": "No analysed interactions yet.",
        "nInteractionsShort": "interactions · {share} of all", "noChildren": "No L3/L4 categories yet.",
    },
    "de": {
        "title": "Bericht zur Intent-Analyse", "project": "Projekt", "dataset": "Datensatz", "created": "Erstellt",
        "interactions": "Analysierte Interaktionen", "version": "Taxonomie-Version", "language": "Analysesprache",
        "models": "Modelle", "overview": "Überblick", "page": "Seite {n}",
        "m.processed": "Verarbeitete Interaktionen", "m.discovered": "Gefundene Intents (L4)",
        "m.l3": "L3-Kategorien", "m.unclassified": "Nicht klassifizierte Interaktionen",
        "m.open": "Offene Kandidaten (noch ohne L4)", "m.overlapping": "Überschneidende Kategorien",
        "volume": "Intent-Volumen", "top": "Top {n} Intents nach Interaktionsvolumen",
        "k.topCover": "Top {n} Intents decken ab", "k.topCoverSub": "aller analysierten Interaktionen",
        "k.for80": "Intents für 80 % Abdeckung", "k.for80Sub": "{n} von {total} L4-Intents",
        "k.longTail": "Long-Tail-Intents", "k.longTailSub": "je max. {n} Interaktionen",
        "k.multi": "Interaktionen mit mehreren Intents", "k.multiSub": "Ø {n} Intents pro Interaktion",
        "k.classified": "Klassifizierte Interaktionen", "k.classifiedSub": "{n} mit mindestens einem L4-Intent",
        "nInteractions": "{n} Interaktionen · {share} aller Interaktionen", "channels": "Kanäle",
        "segments": "Segmente", "noNote": "Noch kein Hinweis erzeugt (Auswertung → Hinweise erzeugen).",
        "outdated": "(Hinweis evtl. veraltet)",
        "disclaimer": "Hinweis auf Basis des Volumens. Ob sich ein Intent tatsächlich optimieren lässt, hängt auch von "
                      "Faktoren wie durchschnittlicher Bearbeitungszeit (AHT), Nachbearbeitungszeit (ACW), "
                      "Weiterleitungen, Wiederholungskontakten sowie fachlichen oder regulatorischen Gründen ab. Diese "
                      "Daten sind nicht Teil der Analyse – die Hinweise also prüfen, bevor Maßnahmen abgeleitet werden.",
        "mix": "Anteil der Top {n} an allen extrahierten Intents",
        "mixText": "Eine Interaktion kann mehrere Intents enthalten – gezählt werden hier Intents, nicht Interaktionen.",
        "other": "Weitere L4-Intents ({n})", "none": "Noch keiner L4 zugeordnet",
        "coverage": "Kumulierte Abdeckung der Interaktionen",
        "coverageText": "Anteil der analysierten Interaktionen, die von den N häufigsten L4-Intents abgedeckt werden "
                        "(Pareto-Sicht).",
        "coverageAxis": "Anzahl L4-Intents, nach Volumen",
        "quality": "Entdeckung & Taxonomiequalität", "curve": "Intent-Entdeckungskurve",
        "curveText": "Unterschiedliche L4-Kategorien (aktuelle Taxonomie) innerhalb der ersten N analysierten "
                     "Interaktionen. Eine abflachende Kurve deutet nur für diesen Datensatz auf Sättigung hin – sie "
                     "beweist nicht, dass die Taxonomie vollständig ist.",
        "curveAxis": "Analysierte Interaktionen",
        "overlap": "Ähnlichste Kategorien (Überschneidungsprüfung)",
        "overlapText": "Ähnlichste L4-Paare innerhalb derselben L2 nach Embedding-Ähnlichkeit ({n} Paare verglichen). "
                       "Paare ab der Zusammenführungsschwelle ({th}) werden zum Zusammenführen vorgeschlagen.",
        "colA": "Kategorie A", "colB": "Kategorie B", "colL2": "L2", "colSim": "Ähnlichkeit", "colNote": "Hinweis",
        "sameL3": "gleiche L3", "proposed": "Zusammenführung vorgeschlagen",
        "noOverlaps": "Noch keine vergleichbaren Kategoriepaare.",
        "taxonomy": "Taxonomie-Übersicht", "taxCounts": "{l1} L1 · {l2} L2 · {l3} L3 · {l4} L4 Kategorien",
        "colCategory": "Kategorie", "colLevel": "Ebene", "colCount": "Interaktionen",
        "proposedNode": "vorgeschlagen", "noData": "Noch keine analysierten Interaktionen.",
        "nInteractionsShort": "Interaktionen · {share} aller", "noChildren": "Noch keine L3/L4-Kategorien.",
    },
}
LANGUAGE_NAMES = {"de": {"en": "Englisch", "de": "Deutsch", "fr": "Französisch", "es": "Spanisch",
                         "it": "Italienisch", "nl": "Niederländisch"}}

INK = colors.HexColor("#18181b")
MUTED = colors.HexColor("#71717a")
FAINT = colors.HexColor("#a1a1aa")
LINE = colors.HexColor("#e4e4e7")
SOFT = colors.HexColor("#f4f4f5")
PAPER = colors.HexColor("#fafafa")
BLUE = colors.HexColor("#2563eb")
BLUE_SOFT = colors.HexColor("#eff6ff")
AMBER = colors.HexColor("#d97706")
AMBER_SOFT = colors.HexColor("#fef3c7")
TOP_COLORS = ["#2563eb", "#7c3aed", "#0d9488", "#d97706", "#e11d48", "#0891b2", "#65a30d", "#c026d3"]

PAGE_W, PAGE_H = A4
MARGIN = 18 * mm
CONTENT_W = PAGE_W - 2 * MARGIN

_FONTS: dict[str, str] = {}


def _fonts() -> tuple[str, str]:
    """A Unicode TrueType font (Arial on macOS, else the Vera font bundled with reportlab)."""
    if not _FONTS:
        import reportlab
        bundled = Path(reportlab.__file__).parent / "fonts"
        candidates = [(Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
                       Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf")),
                      (bundled / "Vera.ttf", bundled / "VeraBd.ttf")]
        for regular, bold in candidates:
            if regular.exists() and bold.exists():
                pdfmetrics.registerFont(TTFont("Report", str(regular)))
                pdfmetrics.registerFont(TTFont("Report-Bold", str(bold)))
                face = pdfmetrics.getFont("Report").face
                _FONTS.update(regular="Report", bold="Report-Bold",
                              pair="↔" if 0x2194 in face.charToGlyph else "/")
                break
        else:
            _FONTS.update(regular="Helvetica", bold="Helvetica-Bold", pair="/")
    return _FONTS["regular"], _FONTS["bold"]


class _Report:
    def __init__(self, lang: str):
        self.lang = lang if lang in TEXT else "en"
        self.font, self.bold = _fonts()
        self.pair = _FONTS["pair"]
        base = dict(fontName=self.font, textColor=INK, fontSize=9.5, leading=13)
        self.styles = {
            "eyebrow": ParagraphStyle("eyebrow", **{**base, "fontName": self.bold, "fontSize": 8.5, "leading": 11,
                                                    "textColor": BLUE}),
            "h1": ParagraphStyle("h1", **{**base, "fontName": self.bold, "fontSize": 22, "leading": 27}),
            "h2": ParagraphStyle("h2", **{**base, "fontName": self.bold, "fontSize": 13, "leading": 17,
                                          "spaceBefore": 14, "spaceAfter": 3}),
            "h3": ParagraphStyle("h3", **{**base, "fontName": self.bold, "fontSize": 10.5, "leading": 13.5}),
            "label": ParagraphStyle("label", **{**base, "fontName": self.bold, "fontSize": 9, "leading": 12}),
            "body": ParagraphStyle("body", **base),
            "note": ParagraphStyle("note", **{**base, "fontSize": 9, "leading": 12.5, "textColor": INK}),
            "small": ParagraphStyle("small", **{**base, "fontSize": 8.5, "leading": 11.5, "textColor": MUTED}),
            "tiny": ParagraphStyle("tiny", **{**base, "fontSize": 7.5, "leading": 10, "textColor": MUTED}),
            "caps": ParagraphStyle("caps", **{**base, "fontName": self.bold, "fontSize": 7, "leading": 9,
                                              "textColor": FAINT}),
            "kpi": ParagraphStyle("kpi", **{**base, "fontName": self.bold, "fontSize": 17, "leading": 21}),
            "count": ParagraphStyle("count", **{**base, "fontName": self.bold, "fontSize": 15, "leading": 18,
                                                "alignment": TA_RIGHT}),
            "countSub": ParagraphStyle("countSub", **{**base, "fontSize": 7.5, "leading": 10, "textColor": MUTED,
                                                      "alignment": TA_RIGHT}),
            "right": ParagraphStyle("right", **{**base, "fontSize": 8.5, "leading": 11, "alignment": TA_RIGHT}),
            "pill": ParagraphStyle("pill", **{**base, "fontName": self.bold, "fontSize": 7.5, "leading": 9,
                                              "alignment": TA_CENTER}),
        }

    def t(self, key: str, **kw) -> str:
        text = TEXT[self.lang].get(key) or TEXT["en"][key]
        return text.format(**kw) if kw else text

    def p(self, text: str, style: str = "body") -> Paragraph:
        return Paragraph(text, self.styles[style])

    def pct(self, v: float) -> str:
        s = f"{v * 100:.0f} %"
        return s if self.lang != "en" else s.replace(" %", "%")

    def num(self, v: float, digits: int = 1) -> str:
        s = f"{v:.{digits}f}"
        return s.replace(".", ",") if self.lang == "de" else s


CARD_PAD = 10
INNER_W = CONTENT_W - 2 * CARD_PAD


def _card(rows: list, widths: list[float], *, bg=colors.white, border=LINE, pad: float = CARD_PAD,
          radius: float = 6, row_gap: float = 2, extra: list | None = None,
          heights: list[float] | None = None) -> Table:
    """A rounded box; rows are stacked with small gaps and the outer padding applies to the edges only."""
    table = Table(rows, colWidths=widths, rowHeights=heights)
    style = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (-1, -1), bg),
        ("ROUNDEDCORNERS", [radius] * 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), row_gap), ("BOTTOMPADDING", (0, 0), (-1, -1), row_gap),
        ("LEFTPADDING", (0, 0), (0, -1), pad), ("RIGHTPADDING", (-1, 0), (-1, -1), pad),
        ("TOPPADDING", (0, 0), (-1, 0), pad), ("BOTTOMPADDING", (0, -1), (-1, -1), pad),
    ]
    if border is not None:
        style.append(("BOX", (0, 0), (-1, -1), 0.6, border))
    table.setStyle(TableStyle(style + (extra or [])))
    return table


def _grid(cells: list, cols: int, gap: float = 6) -> Table:
    rows = [cells[i:i + cols] for i in range(0, len(cells), cols)]
    while len(rows[-1]) < cols:
        rows[-1].append("")
    cell_w = (CONTENT_W - gap * (cols - 1)) / cols
    table = Table(rows, colWidths=[cell_w + gap] * (cols - 1) + [cell_w])
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), gap),
        ("RIGHTPADDING", (-1, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), gap),
    ]))
    return table


def _grid_cell_w(cols: int, gap: float = 6) -> float:
    return (CONTENT_W - gap * (cols - 1)) / cols


def _kpi_grid(r: _Report, tiles: list[tuple[str, str, str]], cols: int) -> Table:
    w = _grid_cell_w(cols)
    has_sub = any(sub for _, _, sub in tiles)
    cells = []
    for label, value, sub in tiles:
        rows = [[r.p(escape(label), "tiny")], [r.p(value, "kpi")]] + ([[r.p(escape(sub), "tiny")]] if has_sub else [])
        heights = [22, 23] + ([21] if has_sub else [])
        heights[0] += 9
        heights[-1] += 9
        cells.append(_card(rows, [w], bg=PAPER, pad=9, row_gap=0, heights=heights))
    return _grid(cells, cols)


def _pill(r: _Report, text: str, fg=INK, bg=SOFT, size: float = 7.5) -> Table:
    w = pdfmetrics.stringWidth(text, r.bold, size) + 12
    style = ParagraphStyle("pill", parent=r.styles["pill"], fontSize=size, textColor=fg)
    pill = Table([[Paragraph(escape(text), style)]], colWidths=[w], rowHeights=[size + 6])
    pill.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg), ("ROUNDEDCORNERS", [(size + 6) / 2] * 4),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
    ]))
    return pill


def _chips(r: _Report, title: str, items: list[str]) -> Table:
    """A caption followed by a row of rounded chips."""
    cells = [r.p(escape(title.upper()), "caps")] + [_pill(r, it, fg=MUTED, bg=SOFT, size=7) for it in items]
    widths = [pdfmetrics.stringWidth(title.upper(), r.bold, 7) + 8] + [c._colWidths[0] + 4 for c in cells[1:]]
    row = Table([cells], colWidths=widths, hAlign="LEFT")
    row.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                             ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                             ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    return row


def _share_bar(width: float, share: float, color: str) -> Drawing:
    d = Drawing(width, 6)
    d.add(Rect(0, 0, width, 5, rx=2.5, ry=2.5, fillColor=SOFT, strokeColor=None))
    if share > 0:
        d.add(Rect(0, 0, max(5, width * min(share, 1)), 5, rx=2.5, ry=2.5, fillColor=colors.HexColor(color),
                   strokeColor=None))
    return d


def _bar_chart(r: _Report, segments: list[tuple[str, int, str]], width: float = CONTENT_W) -> Drawing:
    total = sum(v for _, v, _ in segments) or 1
    row_h, label_w, value_w = 17, 185, 66
    d = Drawing(width, row_h * len(segments))
    bar_w = width - label_w - value_w
    for i, (label, value, color) in enumerate(segments):
        y = d.height - (i + 1) * row_h
        d.add(String(0, y + 5, _clip(label, 44), fontName=r.font, fontSize=8, fillColor=INK))
        d.add(Rect(label_w, y + 3, bar_w, 9, rx=3, ry=3, fillColor=SOFT, strokeColor=None))
        d.add(Rect(label_w, y + 3, max(6, bar_w * value / total), 9, rx=3, ry=3, fillColor=colors.HexColor(color),
                   strokeColor=None))
        d.add(String(width, y + 5, f"{value} · {r.pct(value / total)}", fontName=r.font, fontSize=8,
                     fillColor=MUTED, textAnchor="end"))
    return d


def _line_chart(r: _Report, xs: list[float], ys: list[float], y_max: float, y_fmt, x_label: str,
                marks: list[tuple[float, str]] | None = None, height: float = 150,
                width: float = CONTENT_W) -> Drawing:
    d = Drawing(width, height)
    left, bottom, right, top = 34, 22, 8, 8
    w, h = width - left - right, height - bottom - top
    x_max = max(xs) if xs else 1
    x_min = min(xs) if xs else 0
    sx = lambda x: left + (0 if x_max == x_min else (x - x_min) / (x_max - x_min) * w)  # noqa: E731
    sy = lambda y: bottom + (y / y_max * h if y_max else 0)  # noqa: E731
    for frac in (0, 0.5, 1):
        y = bottom + frac * h
        d.add(Line(left, y, left + w, y, strokeColor=SOFT, strokeWidth=0.8))
        d.add(String(left - 4, y - 2.5, y_fmt(frac * y_max), fontName=r.font, fontSize=7, fillColor=FAINT,
                     textAnchor="end"))
    for x, label in marks or []:
        d.add(Line(sx(x), bottom, sx(x), bottom + h, strokeColor=FAINT, strokeWidth=0.6, strokeDashArray=[2, 2]))
        d.add(String(sx(x) + 3, bottom + h - 8, label, fontName=r.font, fontSize=7, fillColor=MUTED))
    if xs:
        pts = []
        for x, y in zip(xs, ys):
            pts += [sx(x), sy(y)]
        d.add(Polygon([pts[0], bottom] + pts + [pts[-2], bottom], fillColor=BLUE_SOFT, strokeColor=None))
        d.add(PolyLine(pts, strokeColor=BLUE, strokeWidth=1.6))
        d.add(String(left, 6, f"{x_min:g}", fontName=r.font, fontSize=7, fillColor=FAINT))
        d.add(String(left + w, 6, f"{x_max:g}", fontName=r.font, fontSize=7, fillColor=FAINT, textAnchor="end"))
    d.add(String(left + w / 2, 6, x_label, fontName=r.font, fontSize=7, fillColor=MUTED, textAnchor="middle"))
    return d


def _clip(text: str, n: int) -> str:
    return text if len(text) <= n else text[:n - 1] + "…"


def _section(r: _Report, title: str, intro: str | None = None) -> list:
    out = [r.p(escape(title), "h2")]
    if intro:
        out.append(r.p(escape(intro), "small"))
        out.append(Spacer(1, 4))
    return out


def _taxonomy_cards(r: _Report, nodes: list[dict]) -> list:
    """One tinted band per L1 and one card per L2 listing its L3 and L4 categories."""
    children: dict[str | None, list[dict]] = defaultdict(list)
    for n in nodes:
        children[n["parent_id"]].append(n)
    for kids in children.values():
        kids.sort(key=lambda n: (n["level"] > 2 and -n["interaction_count"], n["id"] if n["level"] <= 2 else n["label"]))
    l3_style = ParagraphStyle("taxL3", parent=r.styles["body"], fontName=r.bold, fontSize=8.5, leading=11)
    l4_style = ParagraphStyle("taxL4", parent=r.styles["body"], fontSize=8.5, leading=11, leftIndent=11,
                              bulletIndent=2, bulletFontSize=8, bulletColor=FAINT)
    count_style = ParagraphStyle("taxCount", parent=r.styles["right"], textColor=MUTED)
    l1_title = ParagraphStyle("taxL1", parent=r.styles["h3"], fontSize=11.5, leading=14, textColor=BLUE)

    def text(node: dict, size: float = 7.5) -> str:
        label = escape(node["label"])
        if node["status"] == "proposed":
            label += f" <font color='#d97706' size='7'>· {escape(r.t('proposedNode'))}</font>"
        if node["description"]:
            label += f"<br/><font name='{r.font}' size='{size}' color='#71717a'>{escape(node['description'])}</font>"
        return label

    def count(node: dict, style=count_style) -> Paragraph:
        return Paragraph(str(node["interaction_count"]), style)

    out: list = []
    count_w = 54
    for l1 in children.get(None, []):
        band = _card([[Paragraph(text(l1, 8), l1_title),
                       Paragraph(f"<font name='{r.bold}' size='11' color='#2563eb'>{l1['interaction_count']}</font>"
                                 f"<br/><font size='7' color='#71717a'>{escape(r.t('colCount'))}</font>",
                                 r.styles["right"])]],
                     [CONTENT_W - count_w, count_w], bg=BLUE_SOFT, border=None)
        out += [CondPageBreak(45 * mm), band, Spacer(1, 6)]
        for l2 in children.get(l1["id"], []):
            rows = [[Paragraph(text(l2), r.styles["label"]), count(l2, r.styles["right"])]]
            style = [("LINEBELOW", (0, 0), (-1, 0), 0.6, LINE), ("BOTTOMPADDING", (0, 0), (-1, 0), 6)]
            l3s = children.get(l2["id"], [])
            for i, l3 in enumerate(l3s):
                rows.append([Paragraph(text(l3), l3_style), count(l3)])
                style.append(("TOPPADDING", (0, len(rows) - 1), (-1, len(rows) - 1), 7 if i == 0 else 9))
                for l4 in children.get(l3["id"], []):
                    rows.append([Paragraph(text(l4), l4_style, bulletText="•"), count(l4)])
            if not l3s:
                rows.append([r.p(escape(r.t("noChildren")), "tiny"), ""])
                style.append(("TOPPADDING", (0, 1), (-1, 1), 6))
            out += [_card(rows, [CONTENT_W - count_w, count_w], extra=style), Spacer(1, 6)]
        out.append(Spacer(1, 6))
    return out


def build(conn: sqlite3.Connection, lang: str, project_name: str, logo: Path | None = None) -> bytes:
    r = _Report(lang)
    settings = db.load_settings(conn)
    s = insights.summary(conn)
    dist = insights.intent_distribution(conn)
    notes = insights.cached_notes(conn, dist, r.lang)
    curve = insights.discovery_curve(conn)
    overlaps = insights.overlap_pairs(conn, settings.thresholds()["merge"])
    nodes = [n for n in taxonomy.tree(conn)["nodes"] if n["status"] in ("active", "proposed")]
    analysis_lang = language.get(conn)
    created = datetime.now().strftime("%d.%m.%Y %H:%M" if r.lang == "de" else "%Y-%m-%d %H:%M")

    story: list = [r.p(escape(r.t("title").upper()), "eyebrow"), Spacer(1, 2), r.p(escape(project_name), "h1"),
                   Spacer(1, 8)]
    meta = [
        (r.t("dataset"), s["dataset"] or "—"),
        (r.t("created"), created),
        (r.t("interactions"), f"{s['processed']} / {s['interactions']}"),
        (r.t("version"), f"v{s['taxonomy_version']}"),
        (r.t("language"), LANGUAGE_NAMES.get(r.lang, {}).get(analysis_lang, language.name(analysis_lang))),
        (r.t("models"), f"{settings.llm_model} · {settings.embedding_model}"),
    ]
    cells = [[r.p(escape(k.upper()), "caps"), r.p(escape(str(v)), "note")] for k, v in meta]
    col_w = INNER_W / 3
    meta_rows = []
    for i in range(0, len(cells), 3):
        chunk = cells[i:i + 3]
        meta_rows += [[c[0] for c in chunk], [c[1] for c in chunk]]
    story += [_card(meta_rows, [col_w + CARD_PAD, col_w, col_w + CARD_PAD], bg=PAPER, row_gap=1,
                    extra=[("TOPPADDING", (0, 2), (-1, 2), 9)]), Spacer(1, 4)]

    story += _section(r, r.t("overview"))
    story.append(_kpi_grid(r, [
        (r.t("m.processed"), str(s["processed"]), ""),
        (r.t("m.discovered"), str(s["discovered_intents"]), ""),
        (r.t("m.l3"), str(s["l3_nodes"]), ""),
        (r.t("m.unclassified"), str(s["unclassified"]), ""),
        (r.t("m.open"), str(s["open_candidates"]), ""),
        (r.t("m.overlapping"), str(s["overlapping_categories"]), ""),
    ], 3))

    k, n_top = dist["kpis"], dist["top_n"]
    if dist["items"]:
        story += _section(r, r.t("volume"))
        story.append(_kpi_grid(r, [
            (r.t("k.topCover", n=n_top), r.pct(k["top_coverage"]), r.t("k.topCoverSub")),
            (r.t("k.for80"), str(k["intents_for_80"] or "—"),
             r.t("k.for80Sub", n=k["intents_for_80"] or "—", total=k["active_l4"])),
            (r.t("k.longTail"), str(k["long_tail"]), r.t("k.longTailSub", n=k["long_tail_max"])),
            (r.t("k.multi"), r.pct(k["multi_intent_share"]), r.t("k.multiSub", n=r.num(k["avg_intents"]))),
            (r.t("k.classified"), r.pct(k["classified_share"]),
             r.t("k.classifiedSub", n=k["classified_interactions"])),
        ], 5))

        story += _section(r, r.t("top", n=n_top))
        for item in dist["items"][:n_top]:
            note = notes.get(item["id"])
            color = TOP_COLORS[item["rank"] - 1]
            path = " › ".join(p["label"] for p in item["path"][:-1])
            text = note["text"] if note else r.t("noNote")
            if note and note.get("stale"):
                text += " " + r.t("outdated")
            badge = Table([[Paragraph(str(item["rank"]), ParagraphStyle(
                "badge", parent=r.styles["pill"], fontSize=10, leading=12, textColor=colors.white))]],
                colWidths=[20], rowHeights=[20])
            badge.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(color)),
                                       ("ROUNDEDCORNERS", [5] * 4), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                       ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                                       ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
            count_w = 95
            head = Table([[badge, [r.p(escape(item["label"]), "h3"), Spacer(1, 1), r.p(escape(path), "tiny")],
                           [r.p(str(item["interactions"]), "count"),
                            r.p(escape(r.t("nInteractionsShort", share=r.pct(item["share"]))), "countSub")]]],
                         colWidths=[30, INNER_W - 30 - count_w, count_w])
            head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                                      ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                                      ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
            chips = []
            if item["channels"]:
                chips.append(_chips(r, r.t("channels"),
                                    [f"{c['name']} {r.pct(c['share'])}" for c in item["channels"][:3]]))
            if item["segments"]:
                chips.append(_chips(r, r.t("segments"),
                                    [f"{c['name']} {r.pct(c['share'])}" for c in item["segments"][:3]]))
            note_box = _card([[r.p(escape(r.t("colNote").upper()), "caps")],
                              [r.p(escape(text), "note" if note else "small")]],
                             [INNER_W], bg=PAPER, border=None, pad=8, radius=4, row_gap=1)
            rows = [[head], [_share_bar(INNER_W, item["share"], color)]]
            style = [("TOPPADDING", (0, 1), (-1, 1), 8), ("BOTTOMPADDING", (0, 1), (-1, 1), 4)]
            for chip in chips:
                rows.append([chip])
            rows.append([note_box])
            style.append(("TOPPADDING", (0, len(rows) - 1), (-1, len(rows) - 1), 6))
            story += [KeepTogether(_card(rows, [CONTENT_W], extra=style)), Spacer(1, 7)]
        story.append(_card([[r.p(escape(r.t("disclaimer")), "tiny")]], [CONTENT_W], bg=AMBER_SOFT, border=None,
                           pad=8, radius=4))

        segments, color_i = [], 0
        for m in dist["mix"]:
            if m["kind"] == "intent":
                segments.append((m["label"], m["intents"], TOP_COLORS[color_i % len(TOP_COLORS)]))
                color_i += 1
            elif m["kind"] == "other":
                segments.append((r.t("other", n=m.get("count", 0)), m["intents"], "#a1a1aa"))
            else:
                segments.append((r.t("none"), m["intents"], "#d4d4d8"))
        story.append(CondPageBreak(60 * mm))
        story += _section(r, r.t("mix", n=n_top), r.t("mixText"))
        story.append(_card([[_bar_chart(r, segments, INNER_W)]], [CONTENT_W]))

        cov = dist["coverage"]
        top_i = min(n_top, len(cov))
        marks = [(top_i, f"Top {top_i}: {r.pct(cov[top_i - 1])}")] if cov else []
        story.append(CondPageBreak(75 * mm))
        story += _section(r, r.t("coverage"), r.t("coverageText"))
        story.append(_card([[_line_chart(r, list(range(1, len(cov) + 1)), cov, 1.0, r.pct, r.t("coverageAxis"),
                                         marks, width=INNER_W)]], [CONTENT_W]))
    else:
        story += [Spacer(1, 6), r.p(escape(r.t("noData")), "small")]

    points = curve["points"]
    if points:
        story.append(CondPageBreak(85 * mm))
        story += _section(r, r.t("quality"))
        y_max = max(max(p["categories"] for p in points), 1)
        chart = _line_chart(r, [p["interactions"] for p in points], [p["categories"] for p in points],
                            float(y_max), lambda v: f"{v:.0f}", r.t("curveAxis"), width=INNER_W)
        story.append(_card([[r.p(escape(r.t("curve")), "label")], [r.p(escape(r.t("curveText")), "tiny")],
                            [chart]], [CONTENT_W], extra=[("TOPPADDING", (0, 2), (-1, 2), 8)]))

    story.append(CondPageBreak(50 * mm))
    story += _section(r, r.t("overlap"), r.t("overlapText", n=overlaps["compared"],
                                                 th=r.num(overlaps["merge_threshold"], 2)))
    if overlaps["pairs"]:
        sim_w = 64
        for pair in overlaps["pairs"]:
            flags = [r.t("proposed")] if pair["proposal_id"] else []
            if pair["same_l3"]:
                flags.append(r.t("sameL3"))
            over = pair["similarity"] >= overlaps["merge_threshold"]
            names = (f"{escape(pair['a']['label'])} <font color='#a1a1aa'>&nbsp;{r.pair}&nbsp;</font> "
                     f"{escape(pair['b']['label'])}")
            sub = " · ".join([pair["l2"], *flags])
            sim = _pill(r, r.num(pair["similarity"], 2), fg=AMBER if over else MUTED, bg=AMBER_SOFT if over else SOFT,
                        size=8.5)
            sim.hAlign = "RIGHT"
            story += [KeepTogether(_card([[r.p(names, "label"), sim], [r.p(escape(sub), "tiny"), ""]],
                                         [CONTENT_W - sim_w, sim_w], pad=9,
                                         extra=[("SPAN", (1, 0), (1, 1)), ("VALIGN", (1, 0), (1, 1), "MIDDLE")])),
                      Spacer(1, 5)]
    else:
        story.append(r.p(escape(r.t("noOverlaps")), "small"))

    story.append(PageBreak())
    counts = {lvl: sum(1 for n in nodes if n["level"] == lvl and n["status"] == "active") for lvl in (1, 2, 3, 4)}
    story += _section(r, r.t("taxonomy"), r.t("taxCounts", l1=counts[1], l2=counts[2], l3=counts[3], l4=counts[4]))
    story.append(Spacer(1, 4))
    story += _taxonomy_cards(r, nodes)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=MARGIN + 14 * mm,
                            bottomMargin=MARGIN, title=f"{r.t('title')} – {project_name}", author="Intent Studio")
    logo_reader = ImageReader(str(logo)) if logo and logo.exists() else None

    def frame(canvas, document) -> None:
        canvas.saveState()
        top = PAGE_H - MARGIN
        if logo_reader:
            iw, ih = logo_reader.getSize()
            h = 9 * mm
            w = min(45 * mm, h * iw / ih)
            h = w * ih / iw
            canvas.drawImage(logo_reader, MARGIN, top - h, width=w, height=h, mask="auto")
        else:
            canvas.setFillColor(BLUE)
            canvas.roundRect(MARGIN, top - 6 * mm, 6 * mm, 6 * mm, 1.5 * mm, stroke=0, fill=1)
            canvas.setFont(r.bold, 10)
            canvas.setFillColor(INK)
            canvas.drawString(MARGIN + 8 * mm, top - 4.6 * mm, "Intent Studio")
        canvas.setFont(r.font, 8)
        canvas.setFillColor(MUTED)
        canvas.drawRightString(PAGE_W - MARGIN, top - 3 * mm, r.t("title"))
        canvas.drawRightString(PAGE_W - MARGIN, top - 7 * mm, _clip(project_name, 70))
        canvas.setStrokeColor(LINE)
        canvas.setLineWidth(0.6)
        canvas.line(MARGIN, top - 11 * mm, PAGE_W - MARGIN, top - 11 * mm)
        canvas.setFont(r.font, 7.5)
        canvas.setFillColor(FAINT)
        canvas.drawString(MARGIN, MARGIN - 8 * mm, f"Intent Studio · {created}")
        canvas.drawRightString(PAGE_W - MARGIN, MARGIN - 8 * mm, r.t("page", n=document.page))
        canvas.restoreState()

    doc.build(story, onFirstPage=frame, onLaterPages=frame)
    return buf.getvalue()
