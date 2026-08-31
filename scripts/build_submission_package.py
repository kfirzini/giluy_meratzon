#!/usr/bin/env python3
"""Build an upload-oriented voluntary-disclosure document package."""

from __future__ import annotations

import csv
import html
import shutil
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "הגשה_למערכת"
CHROMIUM = shutil.which("chromium") or shutil.which("google-chrome")
PDFUNITE = shutil.which("pdfunite")


ETH_WALLETS = [
    "0x677878F16c6c7D6fA72510F7fbE355D1eaE276D0",
    "0x31aeaB4FF2D0bB779f4a274b75D598d7c426E974",
    "0xf6E3900686f06eCa98e3a1595F7f82588329DE95",
    "0xB3EBE04E4a61cdFc5DbE7fa98f96A7ff22e51817",
    "0xDd99152be8F2C02ce69F5710d38C7c8b1E10aA5f",
]

BTC_YPUB = (
    "ypub6XPHKsYPMiNMmfWsdb1PWaJnfmzhAzsrxvTkBqc6hELD9YE7EYM7iHsQrL9gYPNR9cYx"
    "ZnFh89Ygh4tR3BMbc5gmvJqnPZ68hLaqY8iWguj"
)


def read_csv(relative_path: str) -> list[dict[str, str]]:
    with (ROOT / relative_path).open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def fmt_nis(value: str | float) -> str:
    return f"{float(value):,.2f} ₪"


def short_hash(value: str) -> str:
    if len(value) <= 22:
        return value
    return f"{value[:12]}…{value[-8:]}"


def page(title: str, body: str, *, landscape: bool = False) -> str:
    orientation = "landscape" if landscape else "portrait"
    return f"""<!doctype html>
<html lang="he" dir="rtl">
<head>
<meta charset="utf-8">
<title>{html.escape(title)}</title>
<style>
@page {{ size: A4 {orientation}; margin: 14mm 14mm 16mm; }}
* {{ box-sizing: border-box; }}
body {{ font-family: "Noto Sans Hebrew", "DejaVu Sans", sans-serif; color: #111;
       font-size: 10.5pt; line-height: 1.5; margin: 0; }}
h1 {{ font-size: 14pt; margin: 0 0 5mm; font-weight: 700; }}
h2 {{ font-size: 11.5pt; margin: 5mm 0 2mm; break-after: avoid; }}
h3 {{ font-size: 11.5pt; margin: 4mm 0 1.5mm; break-after: avoid; }}
p {{ margin: 0 0 2.5mm; }}
.ltr {{ direction: ltr; unicode-bidi: embed; font-family: "DejaVu Sans Mono", monospace; }}
.address {{ direction: ltr; unicode-bidi: embed; font-family: "DejaVu Sans Mono", monospace;
            font-size: 8.4pt; overflow-wrap: anywhere; padding: 1mm 0; margin-bottom: 1mm; }}
table {{ width: 100%; border-collapse: collapse; margin: 2.5mm 0 5mm; font-size: 9pt; }}
th, td {{ border: 1px solid #777; padding: 1.6mm 1.8mm; vertical-align: top; }}
th {{ font-weight: 700; }}
tr {{ break-inside: avoid; }}
.num {{ direction: ltr; text-align: center; white-space: nowrap; }}
.small {{ font-size: 8.2pt; line-height: 1.35; }}
.note {{ border: 1px solid #999; padding: 2.5mm 3mm; margin: 4mm 0; }}
.signature {{ margin-top: 12mm; }}
.page-break {{ break-before: page; }}
.avoid {{ break-inside: avoid; }}
ul {{ margin: 1mm 0 3mm; padding-right: 6mm; }}
</style>
</head>
<body>
{body}
</body>
</html>"""


def render_pdf(html_text: str, target: Path, temp_dir: Path) -> None:
    if not CHROMIUM:
        raise RuntimeError("Chromium is required to render the PDFs")
    source = temp_dir / f"{target.stem}.html"
    source.write_text(html_text, encoding="utf-8")
    target.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            CHROMIUM,
            "--headless",
            "--no-sandbox",
            "--disable-gpu",
            "--no-pdf-header-footer",
            f"--print-to-pdf={target}",
            source.as_uri(),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def request_letter() -> str:
    body = f"""
<h1>מכתב בקשה לגילוי מרצון</h1>
<p>31.08.2026</p>
<p>לכבוד<br><b>רשות המסים בישראל</b></p>
<h2>הנדון: בקשה לגילוי מרצון בגין רווחים מנכסים דיגיטליים</h2>
<p>אני מבקש להסדיר במסגרת הליך גילוי מרצון את הדיווח ואת חבות המס בגין רווחים ממימוש נכסים
דיגיטליים שלא דווחו בשנות המס 2020–2024.</p>
<p>מקור הנכסים הוא בעיקר ברכישות שביצעתי בשנת 2017 מאחי, סער. התמורה שולמה בשש העברות
בנקאיות בסכום כולל של 38,060 ₪, ולאחר מכן הועברו הנכסים לארנקים שלי. בשנת 2020 התקבלו
בארנקים גם נכסים דיגיטליים נוספים. בשל חלוף הזמן, בחלק מן המקרים לא ניתן היה לשחזר התאמה
חד־ערכית בין כל תשלום בנקאי לבין קבלת מטבע מסוימת; מגבלה זו מפורטת במסמך מקור ההון.</p>
<p>לפי נייר העבודה המצורף, הרווח החייב המצטבר לשנות המס 2020–2024 הוא 67,277.65 ₪ וקרן המס
המחושבת בשיעור 25% היא 16,819.41 ₪. החישוב נערך בשיטת FIFO ומבוסס על הנתונים והאסמכתאות
שניתן היה לאתר.</p>
<p>השווי המשוער של כלל הנכסים הדיגיטליים בסמוך למועד הגשת הבקשה הוא 179,390 ₪. אבקש כי
הבקשה תטופל במסלול הירוק, ככל שהיא עומדת בקריטריונים שנקבעו על ידי רשות המסים.</p>
<p>שנת המס 2025 אינה נכללת בחישובים המצורפים לבקשה זו. הפעילות והרווחים מנכסים דיגיטליים
בשנת 2025 ייכללו בדוח השנתי לשנת 2025 שיוגש במסגרת תיק העוסק המורשה.</p>
<p>לבקשה מצורפים נספח ב׳ החתום, פירוט הנכסים והארנקים, נייר עבודה לחישוב המס, הסבר בדבר
מקור ההון ואסמכתאות להעברות הבנקאיות.</p>
<div class="signature"><p>בכבוד רב,</p></div>
"""
    return page("מכתב בקשה לגילוי מרצון", body)


def digital_assets() -> str:
    wallet_blocks = "".join(f'<div class="address">{html.escape(address)}</div>' for address in ETH_WALLETS)
    body = f"""
<h1>נכסים דיגיטליים — ארנקים ויתרות</h1>
<h2>תיאור הפעילות</h2>
<p>הנכסים הדיגיטליים נרכשו בעיקר בשנת 2017 ונכסים נוספים התקבלו בשנת 2020. בשנות המס
2020–2024 בוצעו מימושים של ETH, המפורטים בנייר העבודה לחישוב המס.</p>
<h2>ארנקי Ethereum</h2>
{wallet_blocks}
<h2>ארנק Bitcoin</h2>
<p>המפתח הציבורי המורחב (ypub) ששימש לאיתור כתובות הקבלה בארנק:</p>
<div class="address">{BTC_YPUB}</div>
<h2>יתרות ושווי משוער בסמוך למועד ההגשה</h2>
<table>
<thead><tr><th>נכס</th><th>כמות</th><th>שווי משוער</th></tr></thead>
<tbody>
<tr><td>ETH, כולל יתרה נזילה ו־staking</td><td class="num">22.5324744013 ETH</td><td class="num">164,417.74 ₪</td></tr>
<tr><td>BTC</td><td class="num">0.06431685 BTC</td><td class="num">14,972.26 ₪</td></tr>
<tr><th>סה״כ</th><th></th><th class="num">179,390.00 ₪</th></tr>
</tbody></table>
<div class="note">יתרת ה־ETH כוללת 1.3494989809 ETH נזיל ו־21.1829754204 ETH ב־staking,
כולל תגמולים שנצברו ונצברו מחדש. השווי הוא אומדן נקודתי המשתנה בהתאם למחירי השוק.</div>
<h2>תחום התקופה בבקשה</h2>
<p>המסמכים המצורפים לבקשה מרכזים את שנות המס 2020–2024. שנת 2025 תדווח במסגרת הדוח
השנתי לשנת 2025.</p>
"""
    return page("נכסים דיגיטליים — ארנקים ויתרות", body)


def tax_workpaper() -> str:
    annual = [
        row
        for row in read_csv("transactions_data/tax/tax_by_year.csv")
        if row["coin_type"] == "ALL" and 2020 <= int(row["tax_year"]) <= 2024
    ]
    sales = [
        row
        for row in read_csv("transactions_data/tax/tax_by_transaction.csv")
        if 2020 <= int(row["tax_year"]) <= 2024
    ]
    allocations = [
        row
        for row in read_csv("transactions_data/tax/fifo_allocations.csv")
        if 2020 <= int(row["tax_year"]) <= 2024
    ]

    annual_rows = "".join(
        "<tr>"
        f'<td class="num">{r["tax_year"]}</td>'
        f'<td class="num">{r["sale_transactions"]}</td>'
        f'<td class="num">{fmt_nis(r["net_sale_proceeds_nis"])}</td>'
        f'<td class="num">{fmt_nis(r["fifo_cost_basis_nis"])}</td>'
        f'<td class="num">{fmt_nis(r["taxable_annual_gain_nis"])}</td>'
        f'<td class="num">{fmt_nis(r["tax_owed_25_percent_nis"])}</td>'
        "</tr>"
        for r in annual
    )

    sale_rows = "".join(
        "<tr>"
        f'<td class="num">{r["tax_year"]}</td>'
        f'<td class="num">{r["sale_date"][:10]}</td>'
        f'<td class="num">{r["quantity_sold"]}</td>'
        f'<td class="num">{fmt_nis(r["gross_sale_value_nis"])}</td>'
        f'<td class="num">{fmt_nis(r["sale_expenses_nis"])}</td>'
        f'<td class="num">{fmt_nis(r["net_sale_proceeds_nis"])}</td>'
        f'<td class="num">{fmt_nis(r["fifo_cost_basis_nis"])}</td>'
        f'<td class="num">{fmt_nis(r["gain_loss_nis"])}</td>'
        f'<td class="ltr small">{html.escape(short_hash(r["sale_transaction_hash"]))}</td>'
        "</tr>"
        for r in sales
    )

    allocation_rows = "".join(
        "<tr>"
        f'<td class="num">{r["tax_year"]}</td>'
        f'<td class="num">{r["sale_date"][:10]}</td>'
        f'<td class="ltr small">{html.escape(short_hash(r["sale_transaction_hash"]))}</td>'
        f'<td class="num">{r["purchase_date"][:10]}</td>'
        f'<td class="ltr small">{html.escape(short_hash(r["purchase_transaction_hash"]))}</td>'
        f'<td class="num">{r["quantity_matched"]}</td>'
        f'<td class="num">{fmt_nis(r["purchase_cost_nis"])}</td>'
        f'<td class="num">{fmt_nis(r["net_sale_proceeds_nis"])}</td>'
        f'<td class="num">{fmt_nis(r["gain_loss_nis"])}</td>'
        "</tr>"
        for r in allocations
    )

    body = f"""
<h1>נייר עבודה לחישוב המס — 2020–2024</h1>
<h2>עקרונות החישוב</h2>
<ul>
<li>עלות המלאי חושבה בשיטת FIFO בנפרד לכל נכס.</li>
<li>קרן המס חושבה בשיעור 25% מן הרווח החייב בכל שנת מס.</li>
<li>השווי בשקלים מבוסס על מחיר שוק היסטורי: מחיר Coinbase בדולר כפול שער USD/ILS של Frankfurter.</li>
<li>עמלות רשת במכירה הוערכו במועד העסקה ונוכו מן התמורה.</li>
<li>הסכומים אינם כוללים ריבית, הצמדה, קנסות או חיובים נוספים.</li>
</ul>
<h2>סיכום לפי שנת מס</h2>
<table><thead><tr><th>שנה</th><th>מכירות</th><th>תמורה נטו</th><th>עלות FIFO</th><th>רווח חייב</th><th>קרן מס 25%</th></tr></thead>
<tbody>{annual_rows}
<tr><th>סה״כ</th><th class="num">28</th><th class="num">77,117.44 ₪</th><th class="num">9,839.79 ₪</th><th class="num">67,277.65 ₪</th><th class="num">16,819.41 ₪</th></tr>
</tbody></table>
<div class="note">הרכישות משנת 2020 אינן נכללות בעלות שיוחסה למכירות באותה שנה, משום שעל פי FIFO
העלות למכירות אלה נלקחה מן המלאי המוקדם שנרכש בשנת 2017. שנת 2025 אינה נכללת בנייר עבודה זה.</div>
<div class="page-break"></div>
<h1>נספח א׳ — פירוט מכירות</h1>
<p class="small">כל הסכומים בשקלים חדשים. מזהי העסקאות מוצגים בצורה מקוצרת לצורך קריאות; המזהים המלאים נשמרו בקובצי העבודה.</p>
<table class="small"><thead><tr><th>שנה</th><th>תאריך</th><th>כמות ETH</th><th>תמורה ברוטו</th><th>הוצאות</th><th>תמורה נטו</th><th>עלות FIFO</th><th>רווח/הפסד</th><th>מזהה עסקה</th></tr></thead>
<tbody>{sale_rows}</tbody></table>
<div class="page-break"></div>
<h1>נספח ב׳ — הקצאות FIFO</h1>
<p class="small">כל שורה מקשרת חלק מכמות שנמכרה למנת רכישה קודמת.</p>
<table class="small"><thead><tr><th>שנה</th><th>מועד מכירה</th><th>עסקת מכירה</th><th>מועד רכישה</th><th>עסקת רכישה</th><th>כמות מותאמת</th><th>עלות רכישה</th><th>תמורה נטו</th><th>רווח/הפסד</th></tr></thead>
<tbody>{allocation_rows}</tbody></table>
"""
    return page("נייר עבודה לחישוב המס — 2020–2024", body, landscape=True)


def capital_source() -> str:
    body = f"""
<h1>מקור ההון ורכישת הנכסים הדיגיטליים</h1>
<h2>מקור הנכסים</h2>
<p>בשנת 2017 רכשתי מטבעות דיגיטליים מאחי, סער. התשלומים הועברו אליו באמצעות העברות בנקאיות,
ולאחר ביצוע התשלומים הועברו המטבעות לארנקים שלי. הפעולות הטכניות הנוגעות לרכישה ולהעברה
לארנקים לא בוצעו על ידי.</p>
<h2>העברות בנקאיות בשנת 2017</h2>
<table><thead><tr><th>תאריך</th><th>אסמכתא</th><th>סכום</th></tr></thead><tbody>
<tr><td class="num">04.06.2017</td><td class="num">2000</td><td class="num">6,000.00 ₪</td></tr>
<tr><td class="num">12.06.2017</td><td class="num">31971</td><td class="num">6,000.00 ₪</td></tr>
<tr><td class="num">26.07.2017</td><td class="num">16337</td><td class="num">18,000.00 ₪</td></tr>
<tr><td class="num">03.12.2017</td><td class="num">27791</td><td class="num">2,760.00 ₪</td></tr>
<tr><td class="num">10.12.2017</td><td class="num">135627</td><td class="num">2,300.00 ₪</td></tr>
<tr><td class="num">12.12.2017</td><td class="num">38809</td><td class="num">3,000.00 ₪</td></tr>
<tr><th>סה״כ</th><th></th><th class="num">38,060.00 ₪</th></tr>
</tbody></table>
<h2>תמצית השחזור בין התשלומים לקבלת המטבעות</h2>
<table class="small"><thead><tr><th>תשלום</th><th>קבלת מטבעות משויכת</th><th>ארנק יעד</th><th>הערה</th></tr></thead><tbody>
<tr><td>שתי העברות יוני — 12,000 ₪</td><td>13.652 ETH ביום 12.07.2017; וכן 30 EOS ו־100 BNT בימים 22–23.07.2017</td><td class="ltr">0xDd99…aA5f</td><td>השיוך מוצג ברמת הקבוצה משום ששני התשלומים זהים.</td></tr>
<tr><td>26.07.2017 — 18,000 ₪</td><td>15.90946423 ETH בארבע קבלות בין 20.08.2017 ל־10.09.2017</td><td class="ltr">0xDd99…aA5f</td><td>ארבע הקבלות התקבלו במסגרת אותה רכישה.</td></tr>
<tr><td>03.12.2017 — 2,760 ₪</td><td>0.643 ETH בשתי קבלות ביום 02.12.2017</td><td class="ltr">0x6778…76D0</td><td>לא אותר מידע המאפשר לפרט מעבר לכך את יתרת התמורה.</td></tr>
<tr><td>10.12.2017 ו־12.12.2017 — 5,300 ₪</td><td>0.791 ETH ו־0.0608089 BTC ביום 14.12.2017</td><td class="ltr">0x31ae…E974<br>3MsK…26t</td><td>השיוך מוצג ברמת הקבוצה.</td></tr>
</tbody></table>
<h2>רכישות נוספות בשנת 2020</h2>
<table><thead><tr><th>מועד</th><th>קבלת מטבעות</th><th>ארנק יעד</th><th>תיעוד</th></tr></thead><tbody>
<tr><td class="num">10.01.2020</td><td class="num">10 ETHBNT</td><td class="ltr">0x6778…76D0</td><td>מתועד בקבלה בארנק; לא אותרה אסמכתת תשלום נפרדת.</td></tr>
<tr><td class="num">02.10.2020</td><td class="num">3.415584523606 ETH</td><td class="ltr">0x31ae…E974</td><td>שתי קבלות באותו יום; לא אותרה אסמכתת תשלום נפרדת.</td></tr>
</tbody></table>
<h2>מגבלות השחזור</h2>
<p>ההתאמות מבוססות על מועדי ההעברות, סכומיהן והיסטוריית קבלת המטבעות. בהעברה בנקאית
ובקבלה בארנק אין מזהה רכישה משותף, ולכן חלק מן ההתאמות אינן הוכחה חד־ערכית לכך שתשלום מסוים
מימן קבלה מסוימת. אסמכתאות הבנק עצמן מצורפות מיד לאחר מסמך זה.</p>
"""
    return page("מקור ההון ורכישת הנכסים הדיגיטליים", body)


def write_readme() -> None:
    text = """# מפת ההעלאה למערכת — בקשת גילוי מרצון

העלה כל קובץ לשדה ששמו זהה לשם התיקייה:

| שדה במערכת | קובץ להעלאה |
|---|---|
| נכסים דיגיטליים | `01_נכסים_דיגיטליים/נכסים_דיגיטליים_ארנקים_ויתרות.pdf` |
| ניירות עבודה לחישוב המס | `02_ניירות_עבודה_לחישוב_המס/נייר_עבודה_לחישוב_המס_2020-2024.pdf` |
| מכתב הבקשה | `03_מכתב_הבקשה/מכתב_בקשה_לגילוי_מרצון.pdf` |
| כללי | אין חובה לפי צילום המסך; להשאיר ריק אם המערכת מאפשרת |
| טופס הצהרה לבקשת גילוי מרצון — נספח ב׳ | `05_נספח_ב/נספח_ב_חתום.pdf` |
| מקורות ההון המדווח בבקשה — מטבעות דיגיטליים | `06_מקורות_ההון/מקור_ההון_ואסמכתאות_בנק.pdf` |

## שתי בדיקות שחייבים לבצע לפני השליחה

1. נספח ב׳ החתום מציין בטקסט מכירות בשנים 2020–2025, בעוד טבלת החבות והחבילה המצורפת מתייחסות לשנים 2020–2024 ושנת 2025 אמורה להיכלל בדוח השנתי. יש לוודא שזה הניסוח הרצוי; הקובץ החתום לא שונה.
2. בקובץ העבודה `transactions_data/tax/tax_by_year.csv` קיימות גם תנועות שסווגו אוטומטית כמכירות בשנת 2017 (רווח 46.33 ₪ וקרן מס 11.58 ₪). הן אינן מופיעות בנספח ב׳ החתום או בחבילה, שעוקבת אחריו. יש לוודא אם אלה אכן מכירות חייבות או פעולות טכניות לפני הגשה.

קובץ README זה נועד למיפוי ובקרה בלבד ואינו מיועד להעלאה לרשות המסים.
"""
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "README_לפני_העלאה.md").write_text(text, encoding="utf-8")
    general = OUT / "04_כללי"
    general.mkdir(parents=True, exist_ok=True)
    (general / "אין_מסמך_להעלאה.txt").write_text(
        "לפי צילום המסך, השדה 'כללי' אינו מסומן כחובה. אין להעלות קובץ זה.\n",
        encoding="utf-8",
    )


def build() -> None:
    if not PDFUNITE:
        raise RuntimeError("pdfunite is required to merge the source-of-capital evidence")

    targets = {
        "digital": OUT / "01_נכסים_דיגיטליים" / "נכסים_דיגיטליים_ארנקים_ויתרות.pdf",
        "tax": OUT / "02_ניירות_עבודה_לחישוב_המס" / "נייר_עבודה_לחישוב_המס_2020-2024.pdf",
        "letter": OUT / "03_מכתב_הבקשה" / "מכתב_בקשה_לגילוי_מרצון.pdf",
        "annex": OUT / "05_נספח_ב" / "נספח_ב_חתום.pdf",
        "capital": OUT / "06_מקורות_ההון" / "מקור_ההון_ואסמכתאות_בנק.pdf",
    }

    # Snap-packaged Chromium cannot read arbitrary /tmp paths, so keep the
    # transient HTML/PDF files inside the repository it can already access.
    with tempfile.TemporaryDirectory(prefix=".giluy-submission-", dir=ROOT) as temp_name:
        temp_dir = Path(temp_name)
        render_pdf(digital_assets(), targets["digital"], temp_dir)
        render_pdf(tax_workpaper(), targets["tax"], temp_dir)
        render_pdf(request_letter(), targets["letter"], temp_dir)

        capital_intro = temp_dir / "capital_intro.pdf"
        render_pdf(capital_source(), capital_intro, temp_dir)
        targets["capital"].parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                PDFUNITE,
                str(capital_intro),
                str(ROOT / "files_to_submit" / "bank_transfers.pdf"),
                str(targets["capital"]),
            ],
            check=True,
        )

    targets["annex"].parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "files_to_submit" / "nispachB_full.pdf", targets["annex"])
    write_readme()


if __name__ == "__main__":
    build()
