"""
Eitaa Channel Post View Counter
================================
شمارشگر بازدید واقعی پست‌های کانال ایتا با استفاده از web.eitaa.com

چرا این کد لازم است؟
---------------------
صفحه‌ی eitaa.com/channel/id فقط یک پیش‌نمایش استاتیک است و عدد بازدیدش
واقعی نیست (معمولاً همیشه ۱ نشان می‌دهد). بازدید واقعی فقط در
web.eitaa.com دیده می‌شود که یک اپلیکیشن جاوااسکریپتی (SPA) است، پس
برای خواندنش باید از یک مرورگر واقعی (Playwright) استفاده کرد.

نصب پیش‌نیازها:
    pip install playwright
    playwright install chromium

⚠️ نکته‌ی مهم درباره‌ی selector ها:
    نام کلاس‌های CSS مربوط به «تعداد بازدید» در وب‌اپ ایتا را حدس زده‌ام
    (چون امکان تست زنده روی سایت را ندارم). حتماً قبل از اجرای واقعی:
    1. web.eitaa.com را در مرورگر خودتان باز کنید،
    2. روی یک پست کلیک راست کرده و «Inspect» (بازرسی) را بزنید،
    3. المنتی که عدد بازدید را نشان می‌دهد پیدا کنید و کلاس/سلکتور آن
       را در تابع extract_view_count() جایگزین کنید.

مراحل استفاده:
---------------
1) ابتدا (فقط یک‌بار) با فلگ --login وارد حساب خود شوید تا سشن ذخیره شود:
       python eitaa_view_counter.py --login

   اگر بدون لاگین هم بازدیدها درست نمایش داده شدند، نیازی به این مرحله
   نیست و می‌توانید مستقیم به مرحله‌ی بعد بروید.

2) سپس بسته به نیازتان یکی از حالت‌ها را اجرا کنید:

   الف) بازه‌ای از شماره پست‌ها:
       python eitaa_view_counter.py --channel defapressguilan \
           --start-id 94400 --end-id 94450

   ب) لیست دستی از لینک‌ها یا شماره پست‌ها (یک خط = یک پست):
       python eitaa_view_counter.py --channel defapressguilan \
           --ids-file my_links.txt

   ج) فیلتر بر اساس بازه‌ی تاریخی (بعد از استخراج، خروجی را بر اساس
      تاریخ پست فیلتر می‌کند - همچنان باید یک بازه‌ی شماره پست کلی
      یا فایل لینک به آن بدهید تا از کجا شروع کند بداند):
       python eitaa_view_counter.py --channel defapressguilan \
           --start-id 94000 --end-id 94500 \
           --start-date 2026-07-01 --end-date 2026-07-28

نتیجه در یک فایل CSV ذخیره می‌شود (پیش‌فرض: eitaa_views.csv).
"""

import argparse
import csv
import re
import sys
import time
from pathlib import Path
from datetime import datetime, timedelta

from playwright.sync_api import sync_playwright

STORAGE_STATE = "eitaa_session.json"
BASE_URL = "https://web.eitaa.com"
RETRY_WAIT_MS = 2500  # مکث اضافه (میلی‌ثانیه) وقتی بازدید خالی یا ۱ بود

# نگاشت ماه‌های فارسی به عدد (شمسی)
_PERSIAN_MONTHS = {
    "فروردین": 1, "اردیبهشت": 2, "خرداد": 3, "تیر": 4,
    "مرداد": 5, "شهریور": 6, "مهر": 7, "آبان": 8,
    "آذر": 9, "دی": 10, "بهمن": 11, "اسفند": 12,
}


def login_and_save_session(log_fn=print, confirm_fn=None):
    """یک مرورگر واقعی باز می‌کند تا کاربر دستی لاگین کند و سپس سشن را
    برای استفاده‌های بعدی ذخیره می‌کند.

    log_fn: تابعی برای چاپ پیام‌های پیشرفت (پیش‌فرض: print؛ رابط گرافیکی
        می‌تواند تابع دیگری بدهد تا پیام‌ها را در یک پنجره نشان دهد).
    confirm_fn: تابعی که باید تا زمان تأیید کاربر (بعد از لاگین دستی در
        مرورگر) مسدود بماند. اگر داده نشود، از input() خط‌فرمان استفاده
        می‌شود. رابط گرافیکی می‌تواند اینجا یک threading.Event().wait
        یا مشابه آن بدهد که با کلیک دکمه‌ی «ورود انجام شد» آزاد شود.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(BASE_URL)
        log_fn("مرورگر باز شد. لطفاً با شماره موبایل خود در ایتا وارد شوید.")
        if confirm_fn is not None:
            confirm_fn()
        else:
            input("بعد از ورود موفق، اینجا Enter را بزنید تا سشن ذخیره شود... ")
        context.storage_state(path=STORAGE_STATE)
        browser.close()
        log_fn(f"سشن ذخیره شد در: {STORAGE_STATE}")


def get_post_url(channel: str, post_id: int) -> str:
    return f"{BASE_URL}/#@{channel}_{post_id}"


# ایتا بعضی اعداد (مثل تعداد بازدید) را با ارقام فارسی/عربی نمایش می‌دهد
# (۰۱۲۳۴۵۶۷۸۹ یا ٠١٢٣٤٥٦٧٨٩) نه ارقام انگلیسی. این جدول برای تبدیل آن‌هاست.
_DIGIT_MAP = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹" "٠١٢٣٤٥٦٧٨٩",
    "01234567890123456789"
)


def normalize_digits(text: str) -> str:
    return text.translate(_DIGIT_MAP)


def parse_persian_date(date_str: str):
    """تاریخ فارسی به فرمت '۴ مرداد' یا '15 خرداد 1403' یا '1403/05/04' را به یک شیء datetime
    تبدیل می‌کند. اگر سال ذکر نشده باشد، فرض می‌شود 1403 است.
    در صورت خطا None برمی‌گرداند.
    """
    if not date_str:
        return None
    
    # حذف تگ‌های HTML احتمالی مثل <span class="i18n">۴ مرداد</span>
    date_str = re.sub(r'<[^>]+>', '', date_str)
    
    # نرمال‌سازی اعداد به انگلیسی
    date_str = normalize_digits(date_str.strip())
    
    # الگوی تاریخ عددی: YYYY/MM/DD یا YYYY-MM-DD
    match = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", date_str)
    if match:
        year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
        if 1300 <= year <= 1500 and 1 <= month <= 12 and 1 <= day <= 31:
            try:
                gregorian_date = jalali_to_gregorian(year, month, day)
                return datetime(gregorian_date[0], gregorian_date[1], gregorian_date[2])
            except Exception:
                return None
    
    # الگوی ساده: روز + ماه (مثلاً "4 مرداد")
    match = re.search(r"(\d{1,2})\s+(" + "|".join(_PERSIAN_MONTHS.keys()) + r")(?:\s+(\d{4}))?", 
                      date_str, re.IGNORECASE)
    if not match:
        # تلاش برای الگوی کامل‌تر با سال
        match = re.search(r"(\d{1,2})\s+(\w+)\s+(\d{4})", date_str)
    
    if not match:
        return None
    
    day = int(match.group(1))
    month_name = match.group(2)
    year = int(match.group(3)) if match.group(3) else 1403
    
    month_num = _PERSIAN_MONTHS.get(month_name)
    if month_num is None:
        return None
    
    # تبدیل تاریخ شمسی به میلادی برای مقایسه
    # از یک تبدیل تقریبی استفاده می‌کنیم (برای مقایسه‌ی بازه کافی است)
    try:
        gregorian_date = jalali_to_gregorian(year, month_num, day)
        return datetime(gregorian_date[0], gregorian_date[1], gregorian_date[2])
    except Exception:
        return None


def jalali_to_gregorian(jy, jm, jd):
    """تبدیل تاریخ جلالی (شمسی) به میلادی.
    ورودی: سال، ماه، روز به اعداد صحیح
    خروجی: تاپل (year, month, day) به اعداد صحیح
    """
    gy_days = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    
    jy -= 979
    jm -= 1
    jd -= 1
    
    j_day_no = 365 * jy + (jy // 33) * 8 + ((jy % 33) + 3) // 4
    j_day_no += gy_days[jm] + jd
    
    g_day_no = j_day_no + 79
    
    gy = 1600 + 400 * (g_day_no // 146097)
    g_day_no %= 146097
    
    leap = True
    if g_day_no >= 36525:
        g_day_no -= 1
        gy += 100 * (g_day_no // 36524)
        g_day_no %= 36524
        if g_day_no >= 365:
            g_day_no += 1
        else:
            leap = False
    
    gy += 4 * (g_day_no // 1461)
    g_day_no %= 1461
    
    if g_day_no >= 366:
        leap = False
        g_day_no -= 1
        gy += g_day_no // 365
        g_day_no %= 365
    
    gm = 1
    while g_day_no >= (gy_days[gm] + (1 if gm > 1 and leap else 0)):
        gm += 1
    
    gd = g_day_no - gy_days[gm - 1] - (1 if gm > 1 and leap else 0) + 1
    
    return (gy, gm, gd)


# جاوااسکریپتی که داخل صفحه اجرا می‌شود: بین همه‌ی پیام‌های کانال که در
# DOM لود شده‌اند (.bubble.channel-post)، آن پیامی که از نظر عمودی به
# مرکز صفحه نزدیک‌تر است را پیدا می‌کند. این همان پیامی است که اپ به
# آن اسکرول کرده — یعنی همان پستی که با تغییر hash قصدش را داشتیم،
# صرف‌نظر از این‌که data-mid داخلی‌اش چه عددی است.
_FIND_CENTERED_POST_JS = """
() => {
    const bubbles = Array.from(document.querySelectorAll('.bubble.channel-post'));
    if (bubbles.length === 0) return null;
    const viewportCenter = window.innerHeight / 2;
    let best = null, bestDist = Infinity;
    for (const b of bubbles) {
        const rect = b.getBoundingClientRect();
        if (rect.height === 0) continue;
        const center = rect.top + rect.height / 2;
        const dist = Math.abs(center - viewportCenter);
        if (dist < bestDist) { bestDist = dist; best = b; }
    }
    if (!best) return null;
    const viewsEl = best.querySelector('.post-views');
    const timeEl = best.querySelector('.time');
    return {
        mid: best.getAttribute('data-mid'),
        views: viewsEl ? viewsEl.textContent.trim() : null,
        date: timeEl ? (timeEl.getAttribute('title') || timeEl.textContent.trim()) : null,
    };
}
"""


def get_centered_post_info(page):
    """پیام وسط‌صفحه (یعنی همان پستی که اپ الان رویش زوم/فوکوس کرده) را
    برمی‌گرداند: {mid, views, date} یا None اگر چیزی پیدا نشد."""
    try:
        data = page.evaluate(_FIND_CENTERED_POST_JS)
    except Exception:
        return None
    if not data:
        return None
    views_raw = data.get("views")
    views = None
    if views_raw:
        digits = re.sub(r"[^\d]", "", normalize_digits(views_raw))
        if digits:
            views = int(digits)
    return {
        "mid": data.get("mid"),
        "views": views,
        "date": normalize_digits(data.get("date") or "") or None,
    }


def nudge_scroll(page):
    """یک اسکرول کوچک شبیه‌سازی می‌کند (بالا سپس پایین) تا اپ مجبور شود
    پیام‌های اطراف موقعیت فعلی را لود/رندر کند. این دقیقاً همان کاری است
    که با اسکرول کردن دستی روی صفحه اتفاق می‌افتد."""
    try:
        page.mouse.move(400, 400)
        page.mouse.wheel(0, -250)
        page.wait_for_timeout(300)
        page.mouse.wheel(0, 250)
    except Exception:
        pass


def nudge_scroll_up(page, amount=900):
    """یک اسکرول رو به بالا (برای لود تاریخچه/پیام‌های قدیمی‌تر) انجام می‌دهد."""
    try:
        page.mouse.move(400, 400)
        page.mouse.wheel(0, -amount)
    except Exception:
        pass


# جاوااسکریپتی که همه‌ی پست‌های فعلاً رندرشده در کانال را با بازدید،
# تاریخ، و یک تکه از متن (برای شناسایی راحت‌تر) برمی‌گرداند.
_COLLECT_ALL_POSTS_JS = """
() => {
    return Array.from(document.querySelectorAll('.bubble.channel-post')).map(b => {
        const viewsEl = b.querySelector('.post-views');
        const timeEl = b.querySelector('.time');
        const msgEl = b.querySelector('.message');
        return {
            mid: b.getAttribute('data-mid'),
            views: viewsEl ? viewsEl.textContent.trim() : null,
            date: timeEl ? (timeEl.getAttribute('title') || timeEl.textContent.trim()) : null,
            text: msgEl ? msgEl.textContent.trim().slice(0, 150) : null,
        };
    });
}
"""


def collect_visible_posts(page):
    """تمام پست‌هایی که الان در DOM رندر شده‌اند را برمی‌گرداند
    (لیستی از دیکشنری‌های mid/views/date/text)."""
    try:
        items = page.evaluate(_COLLECT_ALL_POSTS_JS) or []
    except Exception:
        return []
    cleaned = []
    for it in items:
        views_raw = it.get("views")
        views = None
        if views_raw:
            digits = re.sub(r"[^\d]", "", normalize_digits(views_raw))
            if digits:
                views = int(digits)
        cleaned.append({
            "mid": it.get("mid"),
            "views": views,
            "date": normalize_digits(it.get("date") or "") or None,
            "text": it.get("text"),
        })
    return cleaned


def scrape_by_date_range(channel, use_login, headless=True, delay=1.0,
                         max_idle_scrolls=30, log_fn=print,
                         start_date=None, end_date=None):
    """اسکرول از انتهای کانال به سمت بالا و جمع‌آوری پست‌ها تا زمانی که
    به اولین پست با تاریخ خارج از بازه برسیم.
    
    start_date / end_date: تاریخ شروع و پایان به فرمت فارسی (مثلاً '۴ مرداد')
    اگر None باشند، تمام پست‌ها تا ابتدای کانال جمع‌آوری می‌شوند.
    """
    collected = {}
    
    # تبدیل تاریخ‌های ورودی به datetime برای مقایسه
    start_dt = parse_persian_date(start_date) if start_date else None
    end_dt = parse_persian_date(end_date) if end_date else None
    if end_dt:
        end_dt = end_dt + timedelta(days=1)  # شامل خود روز پایان هم بشود
    
    if not start_dt and not end_dt:
        log_fn("هشدتار: هیچ تاریخی مشخص نشده است. تمام پست‌ها جمع‌آوری می‌شوند.")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        if use_login and Path(STORAGE_STATE).exists():
            context = browser.new_context(storage_state=STORAGE_STATE)
        else:
            context = browser.new_context()
        page = context.new_page()

        log_fn(f"در حال باز کردن کانال @{channel} ...")
        page.goto(f"{BASE_URL}/#@{channel}")
        page.wait_for_timeout(3000)

        idle_scrolls = 0
        scroll_round = 0
        date_out_of_range = False
        
        while True:
            batch = collect_visible_posts(page)
            new_found = False
            
            for item in batch:
                mid = item.get("mid")
                if mid and mid.isdigit() and mid not in collected:
                    post_date_str = item.get("date")
                    post_dt = parse_persian_date(post_date_str)
                    
                    # تصمیم‌گیری درباره اینکه آیا این پست را نگه داریم یا نه
                    keep_post = True
                    
                    if start_dt or end_dt:
                        if post_dt:
                            # چون داریم از انتها به بالا اسکرول می‌کنیم (تاریخ‌های قدیمی‌تر)،
                            # اگر به پستی رسیدیم که تاریخش قبل از start_date بود، یعنی از بازه گذشتیم
                            if start_dt and post_dt < start_dt:
                                date_out_of_range = True
                                log_fn(f"❌ پست #{mid} | تاریخ: {post_date_str} ({post_dt.date()}) | "
                                       f"قبل از تاریخ شروع ({start_dt.date()}) - توقف اسکرول")
                                break
                            # اگر تاریخ بعد از end_date بود، یعنی هنوز در آینده‌ایم (پست جدیدتر)
                            # این پست را نادیده بگیر ولی ادامه بده
                            if end_dt and post_dt >= end_dt:
                                keep_post = False
                                log_fn(f"⏭️ پست #{mid} | تاریخ: {post_date_str} ({post_dt.date()}) | "
                                       f"بعد از تاریخ پایان ({(end_dt - timedelta(days=1)).date()}) - نادیده گرفته شد")
                            else:
                                # داخل بازه است
                                log_fn(f"✅ پست #{mid} | تاریخ: {post_date_str} ({post_dt.date()}) | "
                                       f"داخل بازه - پذیرفته شد")
                        else:
                            # تاریخ نامعتبر یا پیدا نشد
                            log_fn(f"⚠️ پست #{mid} | تاریخ نامعتبر: {post_date_str} - نادیده گرفته شد")
                            keep_post = False
                    
                    if keep_post:
                        collected[mid] = item
                        new_found = True
                        log_fn(f"📊 پست #{mid} اضافه شد | بازدید: {item.get('views')} | تاریخ: {post_date_str}")
            
            if date_out_of_range:
                break

            log_fn(f"🔄 اسکرول #{scroll_round}: {len(collected)} پست معتبر جمع‌آوری شده تاکنون")

            idle_scrolls = 0 if new_found else idle_scrolls + 1
            if idle_scrolls >= max_idle_scrolls:
                log_fn("توقف: چند بار اسکرول شد ولی پیام جدیدی لود نشد "
                       "(احتمالاً به ابتدای کانال رسیدیم).")
                break

            nudge_scroll_up(page)
            page.wait_for_timeout(int(delay * 1000))
            scroll_round += 1

        browser.close()

    # مرتب‌سازی بر اساس mid
    results = [v for k, v in collected.items() if k.isdigit()]
    results.sort(key=lambda x: int(x["mid"]))
    return results


def scrape_range_by_mid(channel, start_mid, end_mid, use_login, headless=True,
                         delay=1.0, max_idle_scrolls=15, log_fn=print,
                         start_date=None, end_date=None):
    """به‌جای پرش مستقیم به شماره پست (که به‌خاطر لود تنبل/مجازی‌سازی
    غیرقابل‌اعتماد است)، از بالای کانال شروع به اسکرول تدریجی به بالا
    می‌کند (لود تاریخچه) و همه‌ی پست‌های بین start_mid و end_mid را
    جمع‌آوری می‌کند.

    start_mid / end_mid: مقدار data-mid پست ابتدایی و انتهایی بازه
        (با Inspect از روی خود پست‌ها گرفته می‌شود؛ ترتیبشان مهم نیست،
        خودش کوچک/بزرگ را تشخیص می‌دهد).
    
    start_date / end_date: اگر داده شوند، به محض اینکه اولین پست با تاریخ
        خارج از بازه دیده شود، اسکرول متوقف می‌شود (برای صرفه‌جویی در زمان).
    """
    lo, hi = sorted([int(start_mid), int(end_mid)])
    collected = {}
    
    # تبدیل تاریخ‌های ورودی به datetime برای مقایسه
    start_dt = parse_persian_date(start_date) if start_date else None
    end_dt = parse_persian_date(end_date) if end_date else None
    if end_dt:
        end_dt = end_dt + timedelta(days=1)  # شامل خود روز پایان هم بشود

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        if use_login and Path(STORAGE_STATE).exists():
            context = browser.new_context(storage_state=STORAGE_STATE)
        else:
            context = browser.new_context()
        page = context.new_page()

        log_fn(f"در حال باز کردن کانال @{channel} ...")
        page.goto(f"{BASE_URL}/#@{channel}")
        page.wait_for_timeout(3000)

        idle_scrolls = 0
        scroll_round = 0
        date_out_of_range = False
        while True:
            batch = collect_visible_posts(page)
            new_found = False
            for item in batch:
                mid = item.get("mid")
                if mid and mid.isdigit() and mid not in collected:
                    collected[mid] = item
                    new_found = True
                    
                    # اگر تاریخ مشخص شده، چک کن که از بازه خارج نشده باشیم
                    if start_dt or end_dt:
                        post_dt = parse_persian_date(item.get("date"))
                        if post_dt:
                            # چون داریم از انتها به بالا اسکرول می‌کنیم (تاریخ‌های قدیمی‌تر)،
                            # اگر به پستی رسیدیم که تاریخش قبل از start_date بود، یعنی از بازه گذشتیم
                            if start_dt and post_dt < start_dt:
                                date_out_of_range = True
                                log_fn(f"رسیدیم به پست با تاریخ {item.get('date')} که قبل از تاریخ شروع است. توقف اسکرول.")
                                break
                            # اگر تاریخ بعد از end_date بود، هنوز در آینده‌ایم، ادامه بده
                            # (این حالت معمولاً وقتی اتفاق می‌افتد که از پایین شروع کرده‌ایم)
            
            if date_out_of_range:
                break

            mids_int = [int(m) for m in collected if m.isdigit()]
            covered_lo = any(m <= lo for m in mids_int) if mids_int else False
            log_fn(f"اسکرول #{scroll_round}: {len(collected)} پست جمع‌آوری شده تاکنون"
                   f"{' | به ابتدای بازه رسیدیم' if covered_lo else ''}")

            if covered_lo:
                break

            idle_scrolls = 0 if new_found else idle_scrolls + 1
            if idle_scrolls >= max_idle_scrolls:
                log_fn("توقف: چند بار اسکرول شد ولی پیام جدیدی لود نشد "
                       "(احتمالاً به ابتدای کانال رسیدیم یا mid ابتدایی اشتباه است).")
                break

            nudge_scroll_up(page)
            page.wait_for_timeout(int(delay * 1000))
            scroll_round += 1

        browser.close()

    in_range = [v for k, v in collected.items() if k.isdigit() and lo <= int(k) <= hi]
    in_range.sort(key=lambda x: int(x["mid"]))
    return in_range


def save_csv_mid_range(results, out_path, log_fn=print):
    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["mid", "views", "date", "text"])
        writer.writeheader()
        writer.writerows(results)
    log_fn(f"نتایج ذخیره شد در: {out_path}")
    log_fn(f"تعداد پست‌های یافت‌شده در بازه: {len(results)}")
    total = sum(r["views"] for r in results if r["views"] is not None)
    log_fn(f"مجموع بازدید: {total}")


def wait_for_post_to_load(page, last_mid, max_attempts=6, wait_ms=900):
    """بعد از تغییر hash، منتظر می‌ماند و در صورت نیاز چند بار اسکرول
    کوچک انجام می‌دهد تا پیام موردنظر واقعاً لود/رندر شود (چون فقط تغییر
    hash کافی نیست - اپ به یک رویداد اسکرول واقعی هم نیاز دارد)."""
    info = get_centered_post_info(page)
    for attempt in range(max_attempts):
        moved = bool(info and info.get("mid") is not None and info["mid"] != last_mid)
        has_views = bool(info and info.get("views") is not None)
        if moved and has_views:
            return info
        nudge_scroll(page)
        page.wait_for_timeout(wait_ms)
        info = get_centered_post_info(page)
    return info


def scrape_posts(channel, post_ids, use_login, headless=True, delay=1.5, log_fn=print):
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        if use_login and Path(STORAGE_STATE).exists():
            context = browser.new_context(storage_state=STORAGE_STATE)
        else:
            context = browser.new_context()
        page = context.new_page()

        # اول یک‌بار خود کانال را باز می‌کنیم تا وب‌اپ کامل لود شود.
        log_fn(f"در حال باز کردن کانال @{channel} ...")
        page.goto(f"{BASE_URL}/#@{channel}")
        page.wait_for_timeout(3000)

        last_mid = None
        for pid in post_ids:
            url = get_post_url(channel, pid)
            hash_value = f"@{channel}_{pid}"
            try:
                # به‌جای رفرش کامل صفحه (page.goto) که باعث می‌شد اپ هر بار
                # از صفر لود شود (و آن toast خطا لحظه‌ای ظاهر شود)، فقط
                # هش آدرس را عوض می‌کنیم؛ دقیقاً همان کاری که وقتی داخل
                # خود اپ روی یک پست کلیک می‌کنید اتفاق می‌افتد.
                page.evaluate("h => { window.location.hash = h; }", hash_value)
                page.wait_for_timeout(int(delay * 1000))
                info = wait_for_post_to_load(page, last_mid)
                views = info["views"] if info else None
                mid = info["mid"] if info else None
                post_date = info["date"] if info else None

                if views is None:
                    flag = "no_views"      # هیچ عنصر بازدیدی پیدا نشد -> صفر در نظر می‌گیریم
                    views = 0
                elif views == 1:
                    flag = "stuck_at_one"  # با وجود اسکرول، هنوز ۱ بود -> همان ۱ حساب می‌شود
                elif mid is not None and mid == last_mid:
                    # حتی بعد از چند بار اسکرول هم شناسه‌ی پیام عوض نشد؛
                    # یعنی ناوبری واقعاً به پست جدید نرسیده و این نتیجه مشکوک است.
                    flag = "possible_nav_fail"
                else:
                    flag = "normal"

                last_mid = mid
                results.append({
                    "post_id": pid, "url": url,
                    "views": views, "date": post_date, "flag": flag,
                })
                log_fn(f"پست {pid} (mid={mid}): بازدید = {views} | تاریخ = {post_date} | وضعیت = {flag}")
            except Exception as e:
                log_fn(f"خطا در پست {pid}: {e}")
                results.append({"post_id": pid, "url": url,
                                 "views": 0, "date": None, "flag": "error"})
            time.sleep(delay)

        browser.close()
    return results


def save_csv(results, out_path, log_fn=print):
    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["post_id", "url", "views", "date", "flag"])
        writer.writeheader()
        writer.writerows(results)
    log_fn(f"نتایج ذخیره شد در: {out_path}")

    stuck_at_one = [r for r in results if r["flag"] == "stuck_at_one"]
    no_views = [r for r in results if r["flag"] in ("no_views", "error")]
    normal = [r for r in results if r["flag"] == "normal"]

    log_fn("\n--- آمار خلاصه ---")
    log_fn(f"تعداد کل پست‌های بررسی‌شده: {len(results)}")
    log_fn(f"پست‌های با بازدید عادی: {len(normal)}")
    log_fn(f"پست‌های گیر کرده روی بازدید ۱ (stuck_at_one): {len(stuck_at_one)}")
    log_fn(f"پست‌های بدون بازدید / خطا (صفر در نظر گرفته شده): {len(no_views)}")

    total = sum(r["views"] for r in results if r["views"] is not None)
    log_fn(f"مجموع بازدید {len([r for r in results if r['views'] is not None])} پست: {total}")


def filter_by_date_range(results, start_date_str, end_date_str, log_fn=print):
    """فیلتر کردن نتایج بر اساس بازه‌ی تاریخی شمسی.
    
    start_date_str و end_date_str می‌توانند به فرمت‌های زیر باشند:
    - '۴ مرداد' یا '4 مرداد'
    - '1403/05/04' یا '1403-05-04'
    - '4/5/1403'
    
    این توابع تاریخ‌های فارسی را به میلادی تبدیل کرده و مقایسه می‌کند.
    """
    if not start_date_str and not end_date_str:
        return results
    
    start_dt = parse_persian_date(start_date_str) if start_date_str else None
    end_dt = parse_persian_date(end_date_str) if end_date_str else None
    
    # اگر تاریخ پایان داده شد، یک روز به آن اضافه کن تا شامل خود آن روز هم بشود
    if end_dt:
        end_dt = end_dt + timedelta(days=1)
    
    filtered = []
    for r in results:
        post_dt = parse_persian_date(r.get("date"))
        if post_dt is None:
            continue
        
        if start_dt and post_dt < start_dt:
            continue
        if end_dt and post_dt >= end_dt:
            continue
        
        filtered.append(r)
    
    log_fn(f"\n--- فیلتر تاریخ ---")
    log_fn(f"بازه‌ی زمانی: {start_date_str or 'اول'} تا {end_date_str or 'آخر'}")
    log_fn(f"تعداد پست‌ها قبل از فیلتر: {len(results)}")
    log_fn(f"تعداد پست‌ها بعد از فیلتر: {len(filtered)}")
    
    if filtered:
        total = sum(r["views"] for r in filtered if r["views"] is not None)
        log_fn(f"مجموع بازدید پست‌های فیلترشده: {total}")
    
    return filtered


def main():
    parser = argparse.ArgumentParser(description="Eitaa channel post view counter")
    parser.add_argument("--login", action="store_true",
                         help="مرحله اول: لاگین دستی و ذخیره سشن")
    parser.add_argument("--channel", type=str, help="نام کانال (بدون @)")
    parser.add_argument("--start-id", type=int, help="شماره پست شروع")
    parser.add_argument("--end-id", type=int, help="شماره پست پایان")
    parser.add_argument("--ids-file", type=str,
                         help="فایل متنی حاوی لیست لینک‌ها یا شماره پست‌ها (هر خط یکی)")
    parser.add_argument("--start-mid", type=str,
                         help="data-mid پست ابتدایی بازه (روش پیشنهادی و مطمئن‌تر)")
    parser.add_argument("--end-mid", type=str,
                         help="data-mid پست انتهایی بازه")
    parser.add_argument("--start-date", type=str,
                         help="فیلتر تاریخ شروع بعد از استخراج (فرمت آزاد، تطبیق متنی ساده)")
    parser.add_argument("--end-date", type=str,
                         help="فیلتر تاریخ پایان بعد از استخراج")
    parser.add_argument("--headless", action="store_true", default=True)
    parser.add_argument("--show-browser", dest="headless", action="store_false",
                         help="نمایش مرورگر حین اسکرپ (برای دیباگ سلکتورها)")
    parser.add_argument("--out", type=str, default="eitaa_views.csv")
    parser.add_argument("--delay", type=float, default=1.5,
                         help="تأخیر بین درخواست‌ها به ثانیه")
    args = parser.parse_args()

    if args.login:
        login_and_save_session()
        return

    if not args.channel:
        print("لطفاً نام کانال را با --channel مشخص کنید.")
        sys.exit(1)

    if args.start_mid and args.end_mid:
        use_login = Path(STORAGE_STATE).exists()
        results = scrape_range_by_mid(args.channel, args.start_mid, args.end_mid,
                                       use_login=use_login, headless=args.headless,
                                       delay=args.delay)
        save_csv_mid_range(results, args.out)
        return

    post_ids = []
    if args.ids_file:
        with open(args.ids_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                m = re.search(r"(\d+)\s*$", line)
                if m:
                    post_ids.append(int(m.group(1)))
    elif args.start_id and args.end_id:
        post_ids = list(range(args.start_id, args.end_id + 1))
    else:
        print("باید یکی از این‌ها را مشخص کنید: --ids-file یا (--start-id و --end-id)")
        sys.exit(1)

    use_login = Path(STORAGE_STATE).exists()
    results = scrape_posts(args.channel, post_ids, use_login=use_login,
                            headless=args.headless, delay=args.delay)

    if args.start_date or args.end_date:
        results = filter_by_date_range(results, args.start_date, args.end_date)

    save_csv(results, args.out)


if __name__ == "__main__":
    main()
