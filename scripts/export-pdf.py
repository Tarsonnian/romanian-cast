#!/usr/bin/env python3
"""Export the CAST catalog as a print-ready PDF."""

from __future__ import annotations

import json
import shutil
from datetime import date
from pathlib import Path

from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Flowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "src" / "data" / "actors.json"
PHOTO_DIR = ROOT / "public" / "photos"
OUT_DESKTOP = Path("/Users/substratum/Desktop/CAST-Romanian-screen-actors.pdf")
OUT_PROJECT = ROOT / "CAST-Romanian-screen-actors.pdf"
FONT = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"

INK = HexColor("#1c1612")
MUTED = HexColor("#6b5e52")
RULE = HexColor("#d9cfc4")
GOLD = HexColor("#c99430")
CARD = HexColor("#fffaf4")
BG_DARK = HexColor("#1a1410")

pdfmetrics.registerFont(TTFont("Cast", FONT))


def age_of(birth: str | None) -> str:
    if not birth:
        return "—"
    try:
        y, m, d = (int(p) for p in birth[:10].split("-"))
        today = date(2026, 11, 24)
        age = today.year - y - ((today.month, today.day) < (m, d))
        return str(age)
    except ValueError:
        return "—"


def gender_of(g: str) -> str:
    return {"female": "Female", "male": "Male", "nonbinary": "Non-binary"}.get(g, "—")


def credits_of(credits: list[dict], limit: int = 2) -> str:
    if not credits:
        return "Credits not listed in public data"
    parts = []
    for c in credits[:limit]:
        title = (c.get("title") or "").replace("&", "&amp;").replace("<", "&lt;")
        parts.append(f"{title} ({c.get('year')})")
    return " · ".join(parts)


def letter_key(name: str) -> str:
    ch = name[:1].upper()
    ch = ch.translate(str.maketrans("ĂÂÎȘŢȚÁÉÍÓÚ", "AAISTTAEIOU"))
    return ch if "A" <= ch <= "Z" else "#"


class ActorCard(Flowable):
    def __init__(self, actor: dict, width: float, height: float):
        super().__init__()
        self.actor = actor
        self.width = width
        self.height = height

    def draw(self):
        c = self.canv
        c.setFillColor(CARD)
        c.roundRect(0, 0, self.width, self.height, 4, fill=1, stroke=0)
        c.setStrokeColor(RULE)
        c.setLineWidth(0.4)
        c.roundRect(0, 0, self.width, self.height, 4, fill=0, stroke=1)

        photo_h = self.height - 28 * mm
        photo_w = self.width - 8
        x = 4
        y = 24 * mm
        path = PHOTO_DIR / f"{self.actor['id']}.jpg"
        c.saveState()
        p = c.beginPath()
        p.roundRect(x, y, photo_w, photo_h, 3)
        c.clipPath(p, stroke=0, fill=0)
        if path.exists():
            try:
                c.drawImage(
                    str(path),
                    x,
                    y,
                    width=photo_w,
                    height=photo_h,
                    preserveAspectRatio=True,
                    anchor="c",
                    mask="auto",
                )
            except Exception:
                c.setFillColor(HexColor("#2a221c"))
                c.rect(x, y, photo_w, photo_h, fill=1, stroke=0)
        else:
            c.setFillColor(HexColor("#2a221c"))
            c.rect(x, y, photo_w, photo_h, fill=1, stroke=0)
        c.restoreState()

        c.setFillColor(INK)
        c.setFont("Cast", 9)
        name = self.actor["name"]
        if c.stringWidth(name, "Cast", 9) > photo_w:
            while name and c.stringWidth(name + "…", "Cast", 9) > photo_w:
                name = name[:-1]
            name = name + "…"
        c.drawString(x, 16.5 * mm, name)

        c.setFillColor(MUTED)
        c.setFont("Cast", 7.5)
        meta_bits = []
        if self.actor.get("birthDate"):
            meta_bits.append(age_of(self.actor.get("birthDate")) + " yrs")
        meta_bits.append(gender_of(self.actor.get("gender")))
        c.drawString(x, 12.2 * mm, " · ".join(meta_bits))

        c.setFont("Cast", 6.5)
        credits = credits_of(self.actor.get("credits") or [])
        max_w = photo_w
        line1, line2 = credits, ""
        if c.stringWidth(credits, "Cast", 6.5) > max_w:
            words = credits.split(" ")
            acc: list[str] = []
            for w in words:
                trial = " ".join(acc + [w]).strip()
                if c.stringWidth(trial, "Cast", 6.5) <= max_w:
                    acc.append(w)
                    line1 = trial
                else:
                    line2 = " ".join(words[len(acc) :])
                    break
            if c.stringWidth(line2, "Cast", 6.5) > max_w:
                while line2 and c.stringWidth(line2 + "…", "Cast", 6.5) > max_w:
                    line2 = line2[:-1]
                line2 = line2 + "…"
        c.drawString(x, 8.2 * mm, line1)
        if line2:
            c.drawString(x, 5.2 * mm, line2)


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(MUTED)
    canvas.setFont("Cast", 6.5)
    canvas.drawString(16 * mm, 12 * mm, "CAST  ·  Internal casting use  ·  Photos from TMDB")
    canvas.drawString(
        16 * mm,
        8.2 * mm,
        "This product uses the TMDB API but is not endorsed or certified by TMDB",
    )
    canvas.drawRightString(A4[0] - 16 * mm, 10 * mm, str(doc.page))
    canvas.setFillColor(GOLD)
    canvas.rect(0, A4[1] - 3, A4[0], 3, fill=1, stroke=0)
    canvas.restoreState()


def cover_page(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(BG_DARK)
    canvas.rect(0, 0, A4[0], A4[1], fill=1, stroke=0)
    canvas.setFillColor(GOLD)
    canvas.rect(0, A4[1] - 4, A4[0], 4, fill=1, stroke=0)
    canvas.setFillColor(HexColor("#f4e6c8"))
    canvas.setFont("Cast", 11)
    canvas.drawString(28 * mm, A4[1] - 40 * mm, "SUBSTRATUM  ·  CASTING")
    canvas.setFillColor(white)
    canvas.setFont("Cast", 48)
    canvas.drawString(28 * mm, A4[1] - 78 * mm, "CAST.")
    canvas.setFillColor(GOLD)
    canvas.setFont("Cast", 16)
    canvas.drawString(28 * mm, A4[1] - 96 * mm, "Romanian screen actors, 2016–2026")
    canvas.restoreState()
    footer(canvas, doc)


def main() -> None:
    payload = json.loads(DB.read_text(encoding="utf-8"))
    actors = sorted(payload["actors"], key=lambda a: a["name"].casefold())
    styles = getSampleStyleSheet()
    letter_style = ParagraphStyle(
        "LetterLight",
        parent=styles["Normal"],
        fontName="Cast",
        fontSize=16,
        textColor=GOLD,
        spaceBefore=4,
        spaceAfter=6,
        leading=20,
    )
    cover_stats = ParagraphStyle(
        "CoverStats",
        parent=styles["Normal"],
        fontName="Cast",
        fontSize=12,
        textColor=HexColor("#f4e6c8"),
        leading=18,
    )
    cover_note = ParagraphStyle(
        "CoverNote",
        parent=styles["Normal"],
        fontName="Cast",
        fontSize=10,
        textColor=HexColor("#cbbba8"),
        leading=14,
    )

    doc = SimpleDocTemplate(
        str(OUT_PROJECT),
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title="CAST — Romanian screen actors 2016–2026",
        author="Substratum Pictures",
    )

    usable_w = A4[0] - 32 * mm
    cols, rows = 3, 3
    gap = 4 * mm
    card_w = (usable_w - 2) / cols
    card_h = 78 * mm

    story: list = [
        Spacer(1, 100 * mm),
        Paragraph(
            f"{payload['count']} actors&nbsp;&nbsp;&nbsp;"
            f"{payload['withPhoto']} portraits&nbsp;&nbsp;&nbsp;"
            f"{payload['withRecentCredits']} with credits since 2016",
            cover_stats,
        ),
        Spacer(1, 10 * mm),
        Paragraph(
            "Internal production catalog. Headshots from TMDB where available; initials "
            "placeholders otherwise. This product uses the TMDB API but is not endorsed "
            "or certified by TMDB. Confirm availability and image rights before attaching "
            "anyone to a project.",
            cover_note,
        ),
        PageBreak(),
    ]

    def emit_table(rows_data: list[list[Flowable]]) -> None:
        if not rows_data:
            return
        t = Table(rows_data, colWidths=[card_w] * cols)
        t.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 2),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                    ("TOPPADDING", (0, 0), (-1, -1), 2),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ]
            )
        )
        story.append(t)

    current = None
    buf: list[list[Flowable]] = []
    row: list[Flowable] = []
    for actor in actors:
        key = letter_key(actor["name"])
        if key != current:
            if row:
                while len(row) < cols:
                    row.append(Spacer(card_w, 1))
                buf.append(row)
                row = []
            emit_table(buf)
            buf = []
            current = key
            story.append(Paragraph(key, letter_style))
        row.append(ActorCard(actor, card_w - 4, card_h))
        if len(row) == cols:
            buf.append(row)
            row = []
            if len(buf) >= rows:
                emit_table(buf)
                buf = []
    if row:
        while len(row) < cols:
            row.append(Spacer(card_w, 1))
        buf.append(row)
    emit_table(buf)

    print(f"Building PDF ({len(actors)} actors)…")
    doc.build(story, onFirstPage=cover_page, onLaterPages=footer)
    OUT_DESKTOP.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(OUT_PROJECT, OUT_DESKTOP)
    print(f"Wrote {OUT_PROJECT}")
    print(f"Copied {OUT_DESKTOP}")
    print(f"Size {OUT_PROJECT.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
