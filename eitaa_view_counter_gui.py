# -*- coding: utf-8 -*-
"""
رابط گرافیکی شمارشگر بازدید کانال ایتا
========================================
این فایل یک پنجره‌ی گرافیکی (بدون نیاز به ترمینال) روی برنامه‌ی
eitaa_view_counter.py می‌سازد. کافیست این فایل را (با دبل‌کلیک، یا از
طریق IDLE / هر ویرایشگری که پایتون نصب دارد) اجرا کنید.

⚠️ فایل eitaa_view_counter.py باید در همان پوشه‌ی این فایل باشد.

نصب پیش‌نیاز (این بخش را فقط یک‌بار، از ترمینال، نیاز دارید):
    pip install playwright
    playwright install chromium

بعد از آن، دیگر نیازی به ترمینال نیست؛ فقط این فایل را اجرا کنید.
"""

import csv
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import eitaa_view_counter as core


class EitaaGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("شمارشگر بازدید کانال ایتا")
        self.geometry("720x640")

        self.log_queue = queue.Queue()
        self.confirm_event = threading.Event()
        self.worker_running = False

        self._build_ui()
        self.after(150, self._poll_log_queue)

    # ---------------------------------------------------------------
    # ساخت رابط
    # ---------------------------------------------------------------
    def _build_ui(self):
        pad = {"padx": 8, "pady": 4}

        # --- بخش لاگین ---
        login_frame = ttk.LabelFrame(self, text="مرحله ۱ (اختیاری): لاگین به ایتا")
        login_frame.pack(fill="x", **pad)

        self.login_btn = ttk.Button(login_frame, text="باز کردن مرورگر و لاگین",
                                     command=self.on_login_click)
        self.login_btn.pack(side="right", padx=8, pady=8)

        self.confirm_login_btn = ttk.Button(
            login_frame, text="ورود انجام شد، ادامه بده",
            command=self.on_confirm_login, state="disabled")
        self.confirm_login_btn.pack(side="right", padx=8, pady=8)

        status = "سشن ذخیره‌شده موجود است ✅" if Path(core.STORAGE_STATE).exists() \
            else "سشن ذخیره‌شده‌ای یافت نشد (اختیاری)"
        self.login_status_lbl = ttk.Label(login_frame, text=status)
        self.login_status_lbl.pack(side="left", padx=8)

        # --- بخش ورودی‌ها ---
        input_frame = ttk.LabelFrame(self, text="مرحله ۲: مشخصات اسکرپینگ")
        input_frame.pack(fill="x", **pad)

        ttk.Label(input_frame, text="نام کانال (بدون @):").grid(row=0, column=0, sticky="e", **pad)
        self.channel_var = tk.StringVar()
        ttk.Entry(input_frame, textvariable=self.channel_var, width=30).grid(row=0, column=1, sticky="w", **pad)

        self.mode_var = tk.StringVar(value="mid")
        ttk.Radiobutton(input_frame, text="بازه بر اساس data-mid (پیشنهادی، مطمئن‌تر)",
                         variable=self.mode_var, value="mid",
                         command=self._toggle_mode).grid(row=1, column=0, columnspan=2, sticky="w", **pad)
        ttk.Radiobutton(input_frame, text="بازه‌ی شماره پست (URL)", variable=self.mode_var,
                         value="range", command=self._toggle_mode).grid(row=2, column=0, sticky="e", **pad)
        ttk.Radiobutton(input_frame, text="فایل لیست لینک‌ها", variable=self.mode_var,
                         value="file", command=self._toggle_mode).grid(row=2, column=1, sticky="w", **pad)

        # بازه mid (پیشنهادی)
        self.mid_frame = ttk.Frame(input_frame)
        self.mid_frame.grid(row=3, column=0, columnspan=2, sticky="w")
        ttk.Label(self.mid_frame, text="data-mid پست ابتدایی:").grid(row=0, column=0, **pad)
        self.start_mid_var = tk.StringVar()
        ttk.Entry(self.mid_frame, textvariable=self.start_mid_var, width=16).grid(row=0, column=1, **pad)
        ttk.Label(self.mid_frame, text="data-mid پست انتهایی:").grid(row=0, column=2, **pad)
        self.end_mid_var = tk.StringVar()
        ttk.Entry(self.mid_frame, textvariable=self.end_mid_var, width=16).grid(row=0, column=3, **pad)
        ttk.Label(self.mid_frame,
                  text="(با راست‌کلیک روی پست → Inspect → data-mid را از تگ .bubble کپی کنید)",
                  foreground="#666").grid(row=1, column=0, columnspan=4, sticky="w", padx=8)

        # بازه شماره پست
        self.range_frame = ttk.Frame(input_frame)
        self.range_frame.grid(row=4, column=0, columnspan=2, sticky="w")
        ttk.Label(self.range_frame, text="از شماره پست:").grid(row=0, column=0, **pad)
        self.start_id_var = tk.StringVar()
        ttk.Entry(self.range_frame, textvariable=self.start_id_var, width=12).grid(row=0, column=1, **pad)
        ttk.Label(self.range_frame, text="تا شماره پست:").grid(row=0, column=2, **pad)
        self.end_id_var = tk.StringVar()
        ttk.Entry(self.range_frame, textvariable=self.end_id_var, width=12).grid(row=0, column=3, **pad)

        # فایل لیست
        self.file_frame = ttk.Frame(input_frame)
        self.file_frame.grid(row=5, column=0, columnspan=2, sticky="w")
        self.ids_file_var = tk.StringVar()
        ttk.Entry(self.file_frame, textvariable=self.ids_file_var, width=40).grid(row=0, column=0, **pad)
        ttk.Button(self.file_frame, text="انتخاب فایل...",
                   command=self.on_browse_ids_file).grid(row=0, column=1, **pad)

        ttk.Label(input_frame, text="تأخیر بین پست‌ها (ثانیه):").grid(row=6, column=0, sticky="e", **pad)
        self.delay_var = tk.StringVar(value="1.5")
        ttk.Entry(input_frame, textvariable=self.delay_var, width=8).grid(row=6, column=1, sticky="w", **pad)

        # --- فیلتر تاریخ ---
        date_frame = ttk.LabelFrame(input_frame, text="فیلتر بر اساس تاریخ پست (اختیاری)")
        date_frame.grid(row=7, column=0, columnspan=2, sticky="we", padx=8, pady=4)
        
        ttk.Label(date_frame, text="از تاریخ (مثلاً ۱ مرداد):").grid(row=0, column=0, sticky="e", **pad)
        self.start_date_var = tk.StringVar()
        ttk.Entry(date_frame, textvariable=self.start_date_var, width=16).grid(row=0, column=1, sticky="w", **pad)
        
        ttk.Label(date_frame, text="تا تاریخ (مثلاً ۱۰ شهریور):").grid(row=0, column=2, sticky="e", **pad)
        self.end_date_var = tk.StringVar()
        ttk.Entry(date_frame, textvariable=self.end_date_var, width=16).grid(row=0, column=3, sticky="w", **pad)
        
        ttk.Label(date_frame, text="(تاریخ‌های فارسی مثل '۴ مرداد' یا '1403/05/04' وارد کنید)",
                  foreground="#666").grid(row=1, column=0, columnspan=4, sticky="w", padx=8)

        self.show_browser_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(input_frame, text="نمایش مرورگر حین اجرا (برای دیباگ)",
                         variable=self.show_browser_var).grid(row=8, column=0, columnspan=2, sticky="w", **pad)

        ttk.Label(input_frame, text="فایل خروجی CSV:").grid(row=9, column=0, sticky="e", **pad)
        self.out_var = tk.StringVar(value=str(Path.cwd() / "eitaa_views.csv"))
        out_row = ttk.Frame(input_frame)
        out_row.grid(row=9, column=1, sticky="w")
        ttk.Entry(out_row, textvariable=self.out_var, width=32).pack(side="left")
        ttk.Button(out_row, text="...", width=3, command=self.on_browse_out).pack(side="left", padx=4)

        self._toggle_mode()

        # --- دکمه اجرا ---
        run_frame = ttk.Frame(self)
        run_frame.pack(fill="x", **pad)
        self.run_btn = ttk.Button(run_frame, text="شروع اسکرپینگ", command=self.on_run_click)
        self.run_btn.pack(side="right", padx=8, pady=6)
        self.progress = ttk.Progressbar(run_frame, mode="indeterminate")
        self.progress.pack(side="right", fill="x", expand=True, padx=8)

        # --- لاگ ---
        log_frame = ttk.LabelFrame(self, text="گزارش پیشرفت")
        log_frame.pack(fill="both", expand=True, **pad)
        self.log_text = tk.Text(log_frame, height=16, wrap="word")
        self.log_text.pack(fill="both", expand=True, side="left")
        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        scrollbar.pack(side="right", fill="y")
        self.log_text["yscrollcommand"] = scrollbar.set

    def _toggle_mode(self):
        mode = self.mode_var.get()
        if mode == "mid":
            self.mid_frame.grid()
            self.range_frame.grid_remove()
            self.file_frame.grid_remove()
        elif mode == "range":
            self.range_frame.grid()
            self.mid_frame.grid_remove()
            self.file_frame.grid_remove()
        else:
            self.file_frame.grid()
            self.mid_frame.grid_remove()
            self.range_frame.grid_remove()

    # ---------------------------------------------------------------
    # رویدادها
    # ---------------------------------------------------------------
    def on_browse_ids_file(self):
        path = filedialog.askopenfilename(title="انتخاب فایل لیست لینک‌ها/شماره پست‌ها",
                                           filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if path:
            self.ids_file_var.set(path)

    def on_browse_out(self):
        path = filedialog.asksaveasfilename(title="ذخیره فایل خروجی CSV", defaultextension=".csv",
                                             filetypes=[("CSV files", "*.csv")])
        if path:
            self.out_var.set(path)

    def on_login_click(self):
        if self.worker_running:
            return
        self.worker_running = True
        self.login_btn.config(state="disabled")
        self.confirm_login_btn.config(state="normal")
        self.confirm_event.clear()

        def worker():
            try:
                core.login_and_save_session(log_fn=self._log, confirm_fn=self.confirm_event.wait)
                self._log("لاگین با موفقیت کامل شد.")
                self.after(0, lambda: self.login_status_lbl.config(text="سشن ذخیره‌شده موجود است ✅"))
            except Exception as e:
                self._log(f"خطا در لاگین: {e}")
            finally:
                self.worker_running = False
                self.after(0, lambda: self.login_btn.config(state="normal"))
                self.after(0, lambda: self.confirm_login_btn.config(state="disabled"))

        threading.Thread(target=worker, daemon=True).start()

    def on_confirm_login(self):
        self.confirm_event.set()

    def on_run_click(self):
        if self.worker_running:
            messagebox.showinfo("در حال اجرا", "یک عملیات دیگر در حال اجراست، صبر کنید.")
            return

        channel = self.channel_var.get().strip().lstrip("@")
        if not channel:
            messagebox.showwarning("خطا", "نام کانال را وارد کنید.")
            return

        try:
            delay = float(self.delay_var.get())
        except ValueError:
            messagebox.showwarning("خطا", "تأخیر باید یک عدد باشد.")
            return

        post_ids = []
        start_mid = end_mid = None
        mode = self.mode_var.get()

        if mode == "mid":
            start_mid = self.start_mid_var.get().strip()
            end_mid = self.end_mid_var.get().strip()
            if not start_mid.isdigit() or not end_mid.isdigit():
                messagebox.showwarning("خطا", "data-mid ابتدا و انتها باید عدد باشند.")
                return
        elif mode == "range":
            try:
                start_id = int(self.start_id_var.get())
                end_id = int(self.end_id_var.get())
            except ValueError:
                messagebox.showwarning("خطا", "شماره پست شروع و پایان باید عدد باشند.")
                return
            if end_id < start_id:
                messagebox.showwarning("خطا", "شماره پست پایان باید بزرگ‌تر یا مساوی شروع باشد.")
                return
            post_ids = list(range(start_id, end_id + 1))
        else:
            ids_file = self.ids_file_var.get().strip()
            if not ids_file or not Path(ids_file).exists():
                messagebox.showwarning("خطا", "فایل لیست را انتخاب کنید.")
                return
            import re
            with open(ids_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    m = re.search(r"(\d+)\s*$", line)
                    if m:
                        post_ids.append(int(m.group(1)))
            if not post_ids:
                messagebox.showwarning("خطا", "هیچ شماره پستی از فایل استخراج نشد.")
                return

        out_path = self.out_var.get().strip() or "eitaa_views.csv"
        headless = not self.show_browser_var.get()
        use_login = Path(core.STORAGE_STATE).exists()
        
        # دریافت تاریخ‌های فیلتر
        start_date = self.start_date_var.get().strip() or None
        end_date = self.end_date_var.get().strip() or None

        self.worker_running = True
        self.run_btn.config(state="disabled")
        self.progress.start(12)
        self.log_text.delete("1.0", "end")

        if mode == "mid":
            self._log(f"شروع اسکرپینگ بازه data-mid {start_mid} تا {end_mid} از کانال @{channel} ...")

            def worker():
                try:
                    results = core.scrape_range_by_mid(channel, start_mid, end_mid,
                                                         use_login=use_login, headless=headless,
                                                         delay=delay, log_fn=self._log,
                                                         start_date=start_date, end_date=end_date)
                    # فیلتر تاریخ دیگر لازم نیست چون داخل scrape_range_by_mid انجام شده
                    # اما برای اطمینان از صحت کار، اگر نتیجه‌ای داشتیم دوباره فیلتر می‌کنیم
                    if start_date or end_date:
                        results = core.filter_by_date_range(results, start_date, end_date, log_fn=self._log)
                    core.save_csv_mid_range(results, out_path, log_fn=self._log)
                    self._log("\n✅ اسکرپینگ تمام شد.")
                    self.after(0, lambda: messagebox.showinfo("پایان", f"نتایج در فایل زیر ذخیره شد:\n{out_path}"))
                except Exception as e:
                    self._log(f"خطای کلی: {e}")
                    self.after(0, lambda: messagebox.showerror("خطا", str(e)))
                finally:
                    self.worker_running = False
                    self.after(0, lambda: self.run_btn.config(state="normal"))
                    self.after(0, self.progress.stop)

            threading.Thread(target=worker, daemon=True).start()
            return

        self._log(f"شروع اسکرپینگ {len(post_ids)} پست از کانال @{channel} ...")

        def worker():
            try:
                results = core.scrape_posts(channel, post_ids, use_login=use_login,
                                             headless=headless, delay=delay, log_fn=self._log)
                # اعمال فیلتر تاریخ اگر مشخص شده باشد
                if start_date or end_date:
                    results = core.filter_by_date_range(results, start_date, end_date, log_fn=self._log)
                core.save_csv(results, out_path, log_fn=self._log)
                self._log("\n✅ اسکرپینگ تمام شد.")
                self.after(0, lambda: messagebox.showinfo("پایان", f"نتایج در فایل زیر ذخیره شد:\n{out_path}"))
            except Exception as e:
                self._log(f"خطای کلی: {e}")
                self.after(0, lambda: messagebox.showerror("خطا", str(e)))
            finally:
                self.worker_running = False
                self.after(0, lambda: self.run_btn.config(state="normal"))
                self.after(0, self.progress.stop)

        threading.Thread(target=worker, daemon=True).start()

    # ---------------------------------------------------------------
    # ابزار لاگ (thread-safe)
    # ---------------------------------------------------------------
    def _log(self, msg):
        self.log_queue.put(str(msg))

    def _poll_log_queue(self):
        try:
            while True:
                msg = self.log_queue.get_nowait()
                self.log_text.insert("end", msg + "\n")
                self.log_text.see("end")
        except queue.Empty:
            pass
        self.after(150, self._poll_log_queue)


if __name__ == "__main__":
    app = EitaaGUI()
    app.mainloop()
