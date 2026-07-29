"""
سكربت جلب أسعار أسهم سوق العراق للأوراق المالية (ISX) وحفظها بصيغة JSON.

الفكرة: صفحة "الشركات" على isx-iq.net تحمّل جدول الأسعار عبر جافاسكربت،
فنستخدم Playwright (متصفح حقيقي مبرمج) بدل طلب HTTP بسيط، حتى ننتظر تحميل
الجدول فعلياً قبل ما نقرأ محتواه.

ملاحظة مهمة: ما قدرت أفحص الصفحة المُصيَّرة (Rendered DOM) مباشرة وقت
كتابة هذا السكربت (إضافة المتصفح ما كانت متوصلة بجلستي)، فالمُحدِّدات
(selectors) بالأسفل أفضل تخمين مبني على البنية النمطية لهذا النوع من
المواقع (JSP Portal قديم). يُحتمل تحتاج تعديل بسيط بعد أول تجربة فعلية -
هذا طبيعي جداً بمشاريع الاستطراف. إذا فشل، شغّل السكربت بوضع
`--debug` (يحفظ لقطة HTML كاملة + صورة شاشة بمجلد debug/) وابعثهملي
لأعدّل المُحدِّدات بدقة.

المتطلبات:
    pip install playwright
    playwright install chromium

التشغيل:
    python fetch_isx_prices.py
    python fetch_isx_prices.py --debug   # لحفظ HTML وصورة عند الفشل للتشخيص
"""

import json
import sys
import argparse
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

COMPANIES_URL = "http://www.isx-iq.net/isxportal/portal/companysList.html"
OUTPUT_FILE = Path(__file__).parent / "prices.json"
DEBUG_DIR = Path(__file__).parent / "debug"


def parse_number(text: str):
    """يحاول تحويل نص لرقم (يشيل الفواصل والمسافات)، يرجع None إذا فشل."""
    if not text:
        return None
    cleaned = text.strip().replace(",", "").replace("%", "")
    try:
        return float(cleaned)
    except ValueError:
        return None


def scrape(debug: bool = False):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
        page.goto(COMPANIES_URL, wait_until="networkidle", timeout=30000)

        # ننتظر ظهور أي جدول فيه صفوف بيانات (وليس فقط رأس الجدول)
        try:
            page.wait_for_selector("table tr td", timeout=15000)
        except Exception:
            pass  # نكمّل ونحاول نستخرج أي جدول موجود، حتى لو فاضي جزئياً

        rows_data = []

        # محاولة عامة: كل الجداول بالصفحة، ناخذ اللي فيه أكبر عدد صفوف
        # (الأرجح يكون هو جدول أسعار الأسهم).
        tables = page.query_selector_all("table")
        best_table = None
        best_row_count = 0
        for t in tables:
            trs = t.query_selector_all("tr")
            if len(trs) > best_row_count:
                best_row_count = len(trs)
                best_table = t

        if best_table:
            trs = best_table.query_selector_all("tr")
            for tr in trs:
                cells = tr.query_selector_all("td")
                if len(cells) < 2:
                    continue
                texts = [c.inner_text().strip() for c in cells]
                rows_data.append(texts)

        if debug or not rows_data:
            DEBUG_DIR.mkdir(exist_ok=True)
            page.screenshot(path=str(DEBUG_DIR / "screenshot.png"), full_page=True)
            (DEBUG_DIR / "page.html").write_text(page.content(), encoding="utf-8")
            print(f"[DEBUG] حفظت لقطة الصفحة بمجلد: {DEBUG_DIR}")

        browser.close()
        return rows_data


def build_json(rows_data):
    """
    يحاول تحويل صفوف الجدول الخام إلى قائمة أسهم منظمة.
    بما إنه ما نعرف ترتيب الأعمدة بالضبط بدون فحص حي، نحفظ الصفوف الخام
    كمان (raw) حتى تقدر تراجعها وتعدّل هذي الدالة بسهولة إذا لزم.
    """
    stocks = []
    for row in rows_data:
        if len(row) < 2:
            continue
        # نتوقع العمود الأول غالباً يكون رمز الشركة (أحرف إنجليزية كبيرة
        # بدون مسافات، طول 3-5 عادة بأسهم ISX). نستخدم هذا كفلتر تقريبي.
        symbol_candidate = row[0].strip()
        if not symbol_candidate.isalpha() or not symbol_candidate.isupper():
            continue

        stocks.append({
            "symbol": symbol_candidate,
            "raw_columns": row,  # كل الأعمدة الخام - راجعها لتحديد ترتيبها الصحيح
        })

    return stocks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    rows = scrape(debug=args.debug)
    stocks = build_json(rows)

    output = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source": COMPANIES_URL,
        "count": len(stocks),
        "stocks": stocks,
    }

    OUTPUT_FILE.write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"تم الحفظ: {OUTPUT_FILE} ({len(stocks)} سهم)")

    if len(stocks) == 0:
        print(
            "تحذير: ما طلع ولا سهم. شغّل السكربت بـ --debug وابعثلي "
            "محتوى مجلد debug/ (خصوصاً page.html) عشان أظبط المُحدِّدات.",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
