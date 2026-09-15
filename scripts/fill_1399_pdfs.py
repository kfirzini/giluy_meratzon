#!/usr/bin/env python3
"""Fill copies of the 2025 individual 1399 PDF from the reviewed ETH Markdown.

Run: uv run --with reportlab --with python-bidi --with pypdf python scripts/fill_1399_pdfs.py
The original template is preserved. Coordinates use points from the page top.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from bidi.algorithm import get_display
from pypdf import PdfReader, PdfWriter
from reportlab.lib.colors import Color
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "1399y-2025.pdf"
DETAILS = ROOT / "פירוט_למילוי_טופסי_1399_2025.md"
OUTPUT = ROOT / "טופסי_1399_2025_ETH"
FONT_FILE = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
FONT = "1399DejaVuSans"
INK = Color(0.04, 0.12, 0.30)
PAGE_W, PAGE_H = 595.275, 841.89


def table_rows(text: str) -> dict[str, str]:
    result = {}
    for line in text.splitlines():
        cells = [part.strip().replace("**", "") for part in line.split("|")[1:-1]]
        if len(cells) == 2:
            result[cells[0]] = cells[1]
    return result


def one_value(rows: dict[str, str], prefix: str) -> str:
    matches = [value for key, value in rows.items() if key.startswith(prefix)]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one field starting with {prefix!r}")
    return matches[0]


def number(value: str) -> str:
    match = re.search(r"\d[\d,.]*", value)
    if not match:
        raise ValueError(f"Missing numeric value: {value!r}")
    return match.group()


def amount(value: str) -> Decimal:
    return Decimal(number(value).replace(",", ""))


@dataclass
class Form:
    number: int
    quantity: str
    sale_date: str
    purchase_date: str
    sale_time: str
    sale_hash: str
    purchase_hash: str
    fields: dict[str, str]


def read_forms() -> tuple[str, str, list[Form]]:
    text = DETAILS.read_text()
    if re.search(r"\b(?:BNT|BTN|BTC)\b", text):
        raise ValueError("The input document must contain only the approved ETH forms")
    common = table_rows(text.split("## סיכום", 1)[0])
    name = common["שם המוכר"]
    identity = common["תעודת זהות"]
    if not re.fullmatch(r"\d{9}", identity):
        raise ValueError("Expected a nine-digit identity number")
    forms = []
    sections = list(re.finditer(r"^## טופס (\d+) — מכירת ([\d.]+) ETH ביום (\d{2}/\d{2}/\d{4})$", text, re.M))
    for header in sections:
        section = text[header.end():].split("\n## ", 1)[0]
        rows = table_rows(section)
        keys = {
            "sale_amount": "סעיף 1 — תמורה",
            "sale_index": "מדד מכירה ליד סעיף 1",
            "cost": "סעיף 2 — עלות",
            "purchase_index": "מדד בסיס ליד סעיף 2",
            "original_cost": "סעיף 9 —",
            "expenses": "סעיף 10 —",
            "adjusted_cost": "טור א׳, שורה 13 —",
            "inflation": "סעיף 17 —",
            "gain": "סעיף 18 —",
            "real_gain": "סעיף 24 —",
            "attributable_gain": "סעיף 24א —",
            "post_2012_gain": "סעיף 27 —",
            "gain_before_offsets": "סעיף 32 —",
            "tax_before_offsets": "סעיף 33 —",
        }
        fields = {key: number(one_value(rows, prefix)) for key, prefix in keys.items()}
        sale_date = one_value(rows, "סעיף 1 — תאריך")
        purchase_date = one_value(rows, "סעיף 2 — תאריך")
        sale_hash = re.search(r"מזהה מכירה: `([0-9a-fx]+)`", section).group(1)
        purchase_hash = re.search(r"מזהה מנת רכישה: `([0-9a-fx]+)`", section).group(1)
        sale_time = re.search(r"שעת המכירה בישראל: \*\*([\d:]+)\*\*", section).group(1)
        if sale_date != header.group(3):
            raise ValueError("Heading and sale-date field disagree")
        for date in (sale_date, purchase_date):
            datetime.strptime(date, "%d/%m/%Y")
        assert amount(fields["sale_amount"]) - amount(fields["cost"]) - amount(fields["expenses"]) == amount(fields["gain"])
        assert amount(fields["adjusted_cost"]) - amount(fields["original_cost"]) == amount(fields["inflation"])
        assert amount(fields["gain"]) - amount(fields["inflation"]) == amount(fields["real_gain"])
        forms.append(Form(int(header.group(1)), header.group(2), sale_date, purchase_date, sale_time, sale_hash, purchase_hash, fields))
    if [form.number for form in forms] != list(range(1, 7)):
        raise ValueError("Expected six consecutively numbered ETH form sections")
    if len({form.sale_hash for form in forms}) != 5:
        raise ValueError("Expected five ETH sales")
    return name, identity, forms


class Overlay:
    def __init__(self):
        self.stream = io.BytesIO()
        self.canvas = Canvas(self.stream, pagesize=(PAGE_W, PAGE_H), pageCompression=1)
        self.entries = []
        self.page = 1

    def text(self, key, value, left, right, baseline, size=10, align="center", minimum=5.5):
        visual = get_display(str(value))
        width = pdfmetrics.stringWidth(visual, FONT, size)
        if width > right - left:
            size *= (right - left) / width
            if size < minimum:
                raise ValueError(f"Text does not fit {key}: {value!r}")
            width = pdfmetrics.stringWidth(visual, FONT, size)
        x = left if align == "left" else right - width if align == "right" else (left + right - width) / 2
        self.canvas.setFillColor(INK)
        self.canvas.setFont(FONT, size)
        self.canvas.drawString(x, PAGE_H - baseline, visual)
        self.entries.append({"page": self.page, "field": key, "value": str(value), "font_size": round(size, 3), "x": round(x, 3), "baseline_from_top": baseline, "width": round(width, 3)})

    def check(self, left, top):
        self.canvas.setStrokeColor(INK)
        self.canvas.setLineWidth(1.35)
        path = self.canvas.beginPath()
        path.moveTo(left, PAGE_H - (top + 6))
        path.lineTo(left + 4.5, PAGE_H - (top + 11))
        path.lineTo(left + 15, PAGE_H - top)
        self.canvas.drawPath(path)
        self.entries.append({"page": self.page, "field": "virtual_currency_code_71", "value": True, "x": left, "y": top})

    def date(self, key, value, baseline):
        day, month, year = value.split("/")
        self.text(key + "_day", day, 231.0, 247.5, baseline, size=8.1)
        self.text(key + "_month", month, 249.0, 265.7, baseline, size=8.1)
        self.text(key + "_year", year, 266.5, 288.0, baseline, size=8.1)

    def next_page(self):
        self.canvas.showPage()
        self.page += 1

    def finish(self):
        self.canvas.save()
        self.stream.seek(0)
        return PdfReader(self.stream)


def make_overlay(form: Form, name: str, identity: str) -> Overlay:
    out = Overlay()
    f = form.fields
    out.text("tax_year", "2025", 134.5, 177.3, 86.8, size=10.5)
    out.text("transaction_code", "77", 261.8, 282.4, 86.8, size=10.5)
    out.text("seller_name", name, 435, 535, 152.3, size=11)
    out.text("identity_in_seller_box", f"ת״ז {identity}", 435, 535, 163.0, size=8.0)
    out.text("asset", f"ETH {form.quantity}", 447, 535.5, 189.8, size=8.0, minimum=6.2)
    out.text("sale_amount", f["sale_amount"], 304, 399, 233.7, size=10.5)
    out.text("sale_index", f["sale_index"], 183, 226.5, 233.5, size=7.1)
    out.date("sale_date", form.sale_date, 237.0)
    out.text("cost", f["cost"], 304, 399, 266.5, size=10.5)
    out.text("purchase_index", f["purchase_index"], 183, 226.5, 266.0, size=8.5)
    out.date("purchase_date", form.purchase_date, 270.0)
    out.text("adjusted_cost_at_purchase_row", f["adjusted_cost"], 108, 177, 266.5, size=10)
    out.text("original_cost", f["original_cost"], 304, 399, 422.0, size=10.5)
    out.text("expenses", f["expenses"], 304, 399, 444.4, size=10.5)
    out.text("adjusted_cost_total_13", f["adjusted_cost"], 108, 163, 402.6, size=10)
    out.text("inflation_17", f["inflation"], 170, 210, 467.0, size=10)
    out.text("gain_18", f["gain"], 31, 91, 467.0, size=10.5)
    out.check(441.5, 518.0)
    out.text("real_gain_24", f["real_gain"], 210, 282.5, 589.2, size=10)
    out.text("attributable_gain_24a", f["attributable_gain"], 32, 105, 589.2, size=10)
    out.text("post_2012_gain_27", f["post_2012_gain"], 144, 214.5, 644.0, size=10)
    out.text("gain_before_offsets_32", f["gain_before_offsets"], 144, 214.5, 708.0, size=10)
    out.text("tax_before_offsets_33", f["tax_before_offsets"], 144, 214.5, 739.3, size=10)

    out.next_page()
    out.text("note_sale", f"טופס {form.number} מתוך 6; מועד מכירה: {form.sale_date}; מזהה מכירה:", 59, 309, 154.9, size=6.8, align="right")
    out.text("note_sale_hash", form.sale_hash, 59, 309, 161.7, size=6.0, align="left")
    out.text("note_purchase", f"מנת רכישה מיום {form.purchase_date} | מזהה רכישה:", 59, 309, 169.4, size=6.8, align="right")
    out.text("note_purchase_hash", form.purchase_hash, 59, 309, 176.2, size=6.0, align="left")
    out.text("note_valuation", "שווי ש״ח לפי אומדני נייר העבודה; מס 25% לפני קיזוזים.", 59, 309, 183.7, size=6.8, align="right")
    out.text("note_index_base", "מדדים בבסיס ממוצע 2016 = 100. פרטים חסרים וחתימה להשלמה.", 59, 309, 190.5, size=6.8, align="right")
    return out


def main():
    if not FONT_FILE.exists():
        raise SystemExit(f"Hebrew font missing: {FONT_FILE}")
    pdfmetrics.registerFont(TTFont(FONT, str(FONT_FILE)))
    name, identity, forms = read_forms()
    template_hash = hashlib.sha256(TEMPLATE.read_bytes()).hexdigest()
    OUTPUT.mkdir(exist_ok=True)
    combined = PdfWriter()
    manifest = {"template": TEMPLATE.name, "template_sha256": template_hash, "source": DETAILS.name, "source_sha256": hashlib.sha256(DETAILS.read_bytes()).hexdigest(), "asset": "ETH", "year": 2025, "forms": [], "unfilled": ["tax_file_number", "buyer_name", "asset_location", "ownership_attribution", "related_party", "personal_exemptions", "offsets", "signature", "signature_date"]}
    readme = ["# טופסי 1399(י) מלאים — ETH — שנת 2025", "", "שישה עותקים שמולאו לפי [קובץ הפירוט](../פירוט_למילוי_טופסי_1399_2025.md). כל קובץ כולל את שני עמודי הטופס המקורי.", "", "| טופס | מועד מכירה | כמות ETH | קובץ |", "| --- | --- | ---: | --- |"]
    for form in forms:
        overlay = make_overlay(form, name, identity)
        overlay_pdf = overlay.finish()
        original = PdfReader(TEMPLATE)
        writer = PdfWriter()
        for page, extra in zip(original.pages, overlay_pdf.pages, strict=True):
            page.merge_page(extra)
            writer.add_page(page).compress_content_streams()
        writer.add_metadata({"/Title": f"1399 2025 ETH - Form {form.number}", "/Subject": "ETH sale, filled from the reviewed 2025 workpaper", "/Author": name})
        iso_date = datetime.strptime(form.sale_date, "%d/%m/%Y").strftime("%Y-%m-%d")
        filename = f"1399_2025_ETH_{form.number:02d}_{iso_date}.pdf"
        path = OUTPUT / filename
        with path.open("wb") as stream:
            writer.write(stream)
        completed = PdfReader(path)
        if len(completed.pages) != 2:
            raise ValueError(f"Wrong page count in {filename}")
        extracted = subprocess.run(
            ["pdftotext", "-layout", "-enc", "UTF-8", str(path), "-"],
            check=True, capture_output=True, text=True,
        ).stdout
        extracted = re.sub(r"[\u202a-\u202e\u2066-\u2069]", "", extracted)
        for value in set(form.fields.values()) | {identity, form.quantity, form.sale_hash, form.purchase_hash}:
            if value not in extracted:
                raise ValueError(f"Filled value missing from {filename}: {value}")
        combined.append(path, outline_item=f"ETH {form.number}: {form.sale_date}")
        manifest["forms"].append({"number": form.number, "file": filename, "sale_date": form.sale_date, "quantity": form.quantity, "sale_hash": form.sale_hash, "purchase_hash": form.purchase_hash, "fields": form.fields, "overlay_entries": overlay.entries})
        readme.append(f"| {form.number} | {form.sale_date} {form.sale_time} | {form.quantity} | [PDF]({filename}) |")
        print(f"Created {filename}")
    combined.add_metadata({"/Title": "1399 2025 ETH - Six completed forms", "/Author": name})
    combined_name = "1399_2025_ETH_כל_הטפסים.pdf"
    with (OUTPUT / combined_name).open("wb") as stream:
        combined.write(stream)
    assert len(PdfReader(OUTPUT / combined_name).pages) == 12
    assert hashlib.sha256(TEMPLATE.read_bytes()).hexdigest() == template_hash
    manifest["combined_pdf"] = combined_name
    (OUTPUT / "filled_fields.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    readme.extend(["", f"[כל ששת הטפסים בקובץ אחד — 12 עמודים]({combined_name})", "", "המכירה מ־29/01/2025 מפוצלת לטפסים 1–2 בהתאם לשתי מנות הרכישה.", "", "הסכומים הועתקו מהפירוט המאושר, כולל ההצמדה והמס לפני קיזוזים. העלויות והתמורות בפירוט מבוססות על אומדני שוק. הערה זו מופיעה גם בעמוד השני של כל טופס.", "", "מספר תיק, פרטי הרוכש, שייכות ומקום הנכס, קיזוזים ופרטים אישיים שאינם ידועים נותרו ריקים. תעודת הזהות מופיעה עם שם המוכר, בנפרד משדה מספר התיק. החתימה ותאריך החתימה נותרו למילוי בפועל.", "", "לבדיקת התאמה: [ערכי השדות שהוזנו](filled_fields.json).", ""])
    (OUTPUT / "README.md").write_text("\n".join(readme))
    print(f"Created combined PDF: {combined_name}")


if __name__ == "__main__":
    main()
