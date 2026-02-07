import flet as ft
import yt_dlp
import os
import shutil
import traceback
import threading
import re
from urllib.parse import urlparse

# ---------- Filename sanitize ----------
def sanitize_piece(name: str, max_len: int = 30) -> str:
    """
    تنظيف جزء من الاسم (قناة أو عنوان):
    - إزالة الأحرف الممنوعة في أسماء الملفات
    - الإبقاء على العربية
    - تقصير الطول
    """
    if not name:
        return "unknown"
    # ممنوع: \ / : * ? " < > |
    name = re.sub(r'[\\/:*?"<>|]+', '', name)
    # استبدال أسطر ومسافات غريبة
    name = name.replace("\n", " ").replace("\r", " ")
    name = re.sub(r"\s+", " ", name).strip()
    # قص
    if len(name) > max_len:
        name = name[:max_len].rstrip()
    return name or "unknown"


def main(page: ft.Page):
    # إعدادات الصفحة
    page.title = "تحميل غصب PRO"
    page.theme_mode = ft.ThemeMode.DARK
    page.rtl = True
    page.vertical_alignment = ft.MainAxisAlignment.CENTER
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    page.padding = 20

    # ---------- UI Helpers ----------
    def show_snack(message: str):
        page.snack_bar = ft.SnackBar(ft.Text(message), action="فهمت")
        page.snack_bar.open = True
        page.update()

    def append_log(message: str):
        log_box.value = (log_box.value or "") + message + "\n"
        log_box.update()

    def set_status(icon: str, text: str):
        status_icon.name = icon
        status_text.value = text
        status_row.update()

    def close_dialog(dlg: ft.AlertDialog):
        dlg.open = False
        page.update()

    def show_error_dialog(title: str, details: str):
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(title),
            content=ft.Container(
                content=ft.Text(details, selectable=True),
                width=520,
            ),
            actions=[ft.TextButton("إغلاق", on_click=lambda e: close_dialog(dlg))],
        )
        page.dialog = dlg
        dlg.open = True
        page.update()

    # ---------- Storage Path ----------
    def get_dynamic_path():
        external_base = "/storage"
        try:
            if os.path.exists(external_base):
                directories = os.listdir(external_base)
                for dir_name in directories:
                    if dir_name not in ["emulated", "self", "knox"]:
                        target = f"{external_base}/{dir_name}/Download/GhasabApp"
                        os.makedirs(target, exist_ok=True)
                        return target
        except Exception:
            pass

        internal_path = "/storage/emulated/0/Download/GhasabApp"
        os.makedirs(internal_path, exist_ok=True)
        return internal_path

    # ---------- ffmpeg detect ----------
    def detect_ffmpeg():
        # نفضّل المسار القادم من Flutter (ffmpeg-kit) إن وجد
        env_ffmpeg = os.environ.get("FFMPEG_EXEC_PATH")
        if env_ffmpeg and os.path.isfile(env_ffmpeg):
            return env_ffmpeg
        return shutil.which("ffmpeg")

    def is_instagram_url(url: str) -> bool:
        try:
            host = urlparse(url).netloc.lower()
        except Exception:
            host = url.lower()
        return ("instagram.com" in host) or ("instagr.am" in host)

    def collect_download_dirs() -> list[str]:
        dirs: list[str] = []
        # مسارات داخلية شائعة
        dirs.extend([
            "/storage/emulated/0/Download",
            "/storage/emulated/0/Download/GhasabApp",
        ])

        # بطاقات التخزين الخارجية
        try:
            for dir_name in os.listdir("/storage"):
                if dir_name in ["emulated", "self", "knox"]:
                    continue
                dirs.append(f"/storage/{dir_name}/Download")
                dirs.append(f"/storage/{dir_name}/Download/GhasabApp")
        except Exception:
            pass

        # إزالة التكرار مع الحفاظ على الترتيب
        seen = set()
        result = []
        for d in dirs:
            if d not in seen:
                seen.add(d)
                result.append(d)
        return result

    def discover_cookie_candidates(save_path: str) -> list[str]:
        candidates = [
            os.path.join(save_path, "instagram_cookies.txt"),
            "/storage/emulated/0/Download/GhasabApp/instagram_cookies.txt",
            "/storage/emulated/0/Download/instagram_cookies.txt",
            "/storage/emulated/0/Download/instagram.com_cookies.txt",
            "/storage/sdcard1/Download/GhasabApp/instagram_cookies.txt",
            "/storage/sdcard1/Download/instagram_cookies.txt",
            "/storage/sdcard1/Download/instagram.com_cookies.txt",
            os.path.join(save_path, "cookies.txt"),
            "/storage/emulated/0/Download/GhasabApp/cookies.txt",
            "/storage/emulated/0/Download/cookies.txt",
            "/storage/sdcard1/Download/GhasabApp/cookies.txt",
            "/storage/sdcard1/Download/cookies.txt",
        ]

        # اكتشاف أي ملف يحتوي "cookie" داخل مجلدات التنزيلات
        dynamic_hits = []
        for base in collect_download_dirs():
            try:
                if not os.path.isdir(base):
                    continue
                for entry in os.scandir(base):
                    if not entry.is_file():
                        continue
                    name = entry.name.lower()
                    if "cookie" not in name:
                        continue
                    if not (
                        name.endswith(".txt")
                        or name.endswith(".cookies")
                        or name.endswith(".cookie")
                        or "." not in name
                    ):
                        continue
                    dynamic_hits.append(entry.path)
            except Exception:
                continue

        # ترتيب أولوية الأسماء الواضحة أولاً
        def score(path: str) -> tuple[int, str]:
            name = os.path.basename(path).lower()
            if name == "instagram_cookies.txt":
                return (0, name)
            if "instagram" in name and "cookie" in name:
                return (1, name)
            if name == "cookies.txt":
                return (2, name)
            return (3, name)

        dynamic_hits.sort(key=score)
        candidates.extend(dynamic_hits)

        # إزالة تكرار المسارات
        seen = set()
        unique = []
        for c in candidates:
            if c not in seen:
                seen.add(c)
                unique.append(c)
        return unique

    def resolve_instagram_cookie_file(save_path: str) -> str | None:
        # أولوية 1: الملف الذي اختاره المستخدم من واجهة التطبيق
        selected = (cookie_path_value.value or "").strip()
        if selected and os.path.isfile(selected):
            return selected

        # أولوية 2: اكتشاف تلقائي من مجلدات التنزيلات
        for path in discover_cookie_candidates(save_path):
            if os.path.isfile(path):
                return path
        return None

    def format_friendly_error(err: str, url: str, cookie_file: str | None) -> str:
        lower_err = (err or "").lower()

        if is_instagram_url(url):
            blocked_markers = [
                "this content may be inappropriate",
                "unavailable for certain audiences",
                "restricted video",
                "login required",
                "you need to log in",
                "private",
            ]
            if any(marker in lower_err for marker in blocked_markers):
                if cookie_file:
                    return (
                        "Instagram منع الوصول لهذا المقطع للحسابات غير الموثقة. "
                        f"تم استخدام ملف الكوكيز: {cookie_file} لكن الوصول ما زال مرفوضًا. "
                        "جرب كوكيز جديدة من حساب عمره مناسب ويتابع الحساب."
                    )
                return (
                    "هذا رابط Instagram مقيد (عمر/خصوصية). "
                    "أضف ملف كوكيز Instagram بصيغة Netscape ثم أعد المحاولة. "
                    "يمكنك اختياره من زر (اختيار ملف كوكيز Instagram) أو وضعه باسم "
                    "'instagram_cookies.txt' داخل Download/GhasabApp."
                )

        return err

    # ---------- Progress hook ----------
    def make_progress_hook():
        def hook(d):
            try:
                status = d.get("status")
                if status == "downloading":
                    downloaded = d.get("downloaded_bytes") or 0
                    total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                    speed = d.get("speed") or 0
                    eta = d.get("eta")

                    # progress
                    if total > 0:
                        frac = min(downloaded / total, 1.0)
                        progress_bar.value = frac
                        percent = int(frac * 100)
                    else:
                        progress_bar.value = None  # indeterminate
                        percent = 0

                    # speed display
                    def fmt_speed(bps: float) -> str:
                        if not bps or bps <= 0:
                            return "—"
                        units = ["B/s", "KB/s", "MB/s", "GB/s"]
                        u = 0
                        v = float(bps)
                        while v >= 1024 and u < len(units) - 1:
                            v /= 1024
                            u += 1
                        return f"{v:.1f} {units[u]}"

                    def fmt_eta(sec):
                        if sec is None:
                            return "—"
                        sec = int(sec)
                        m, s = divmod(sec, 60)
                        h, m = divmod(m, 60)
                        if h:
                            return f"{h}:{m:02d}:{s:02d}"
                        return f"{m}:{s:02d}"

                    progress_text.value = f"التقدم: {percent}%  |  السرعة: {fmt_speed(speed)}  |  المتبقي: {fmt_eta(eta)}"
                    progress_bar.update()
                    progress_text.update()

                elif status == "finished":
                    progress_bar.value = 1.0
                    progress_text.value = "تم تنزيل الملف… جارٍ الإنهاء/الدمج إن لزم."
                    progress_bar.update()
                    progress_text.update()

            except Exception:
                pass

        return hook

    # ---------- Rename hook (channel + title + sanitize) ----------
    def rename_hook(d):
        """
        بعد انتهاء التنزيل: إعادة تسمية الملف إلى:
        Channel - Title.ext  (مع تنظيف الأحرف وقص 30 لكل جزء)
        """
        if d.get("status") != "finished":
            return

        try:
            info = d.get("info_dict") or {}
            title = info.get("title") or "video"
            # اسم القناة: نفضّل uploader، وإن لم يوجد نستخدم channel
            channel = info.get("uploader") or info.get("channel") or "channel"

            title_clean = sanitize_piece(title, 30)
            channel_clean = sanitize_piece(channel, 30)

            src = d.get("filename")

            # حماية إضافية لمسارات SAF (مع لوق + استمرار بدون rename)
            if not src:
                append_log("ℹ️ rename_hook: تم تخطي إعادة التسمية — لم أستطع قراءة مسار الملف (SAF/غير متاح).")
                return

            if not os.path.isfile(src):
                append_log(f"ℹ️ rename_hook: تم تخطي إعادة التسمية — الملف غير موجود كملف فعلي: {src}")
                return

            folder = os.path.dirname(src)
            if not os.access(folder, os.W_OK):
                append_log(f"ℹ️ rename_hook: تم تخطي إعادة التسمية — لا أستطيع الكتابة داخل المجلد: {folder}")
                return

            # امتداد الملف الحالي
            ext = os.path.splitext(src)[1]  # includes dot

            # اسم جديد
            new_name = f"{channel_clean} - {title_clean}{ext}"
            dst = os.path.join(os.path.dirname(src), new_name)

            # إن كان الاسم موجود مسبقًا، أضف رقم
            if os.path.exists(dst) and src != dst:
                base = f"{channel_clean} - {title_clean}"
                i = 2
                while True:
                    candidate = os.path.join(os.path.dirname(src), f"{base} ({i}){ext}")
                    if not os.path.exists(candidate):
                        dst = candidate
                        break
                    i += 1

            if src != dst:
                os.rename(src, dst)
                append_log(f"✍️ إعادة تسمية: {os.path.basename(dst)}")

        except Exception as ex:
            append_log(f"ℹ️ rename_hook: تم تخطي إعادة التسمية — فشل rename بسبب: {ex}")
            return

    # ---------- Download worker ----------
    def do_download(url: str, mode: str):
        save_path = get_dynamic_path()   # ❌ تم التعليق — لم نعد نستخدمه
        save_path = (save_path_value.value or "").strip()  # ✔️ المسار الذي اختاره المستخدم

        # منع التحميل إذا لم يختَر المستخدم مجلد
        if not save_path:
            show_snack("اختر مجلد الحفظ أولاً!")
            set_status(ft.Icons.ERROR, "❌ لم يتم اختيار مجلد الحفظ")
            return

        # التأكد من أن المجلد موجود
        if not os.path.isdir(save_path):
            try:
                os.makedirs(save_path, exist_ok=True)
            except Exception as ex:
                show_snack("لا أستطيع إنشاء المجلد. اختر مجلدًا آخر.")
                append_log(f"⚠️ فشل إنشاء المجلد: {ex}")
                return

        # عرض مسار الحفظ
        save_path_value.value = save_path
        save_path_value.update()

        ffmpeg_path = detect_ffmpeg()
        is_video = (mode == "video")
        use_ffmpeg = bool(ffmpeg_path)
        use_instagram_cookies = is_instagram_url(url)
        cookie_file = resolve_instagram_cookie_file(save_path) if use_instagram_cookies else None

        # تحذير ffmpeg + اختيار صيغة تناسبه
        if is_video and not use_ffmpeg:
            warn = "⚠️ ffmpeg غير مثبت، سأنزّل نسخة مدمجة جاهزة (قد تكون جودة أقل). ثبّته للحصول على أعلى جودة."
            append_log(warn)
            show_snack(warn)

        # شعار/حالة بدء التحميل
        set_status(ft.Icons.DOWNLOAD_FOR_OFFLINE, "🚀 بدأ التحميل...")
        show_snack("🚀 بدأ التحميل...")

        # تصفير التقدم
        progress_bar.value = 0
        progress_text.value = "التقدم: 0%"
        page.update()

        # أعلى جودة فعلاً للفيديو
        if is_video:
            # إن توفر ffmpeg ندمج أعلى جودة، وإلا نأخذ فيديو مدمج جاهز لتجنب الخطأ
            fmt = "bestvideo*+bestaudio/best" if use_ffmpeg else "best[ext=mp4][vcodec!=none][acodec!=none]/best"
        else:
            fmt = "bestaudio/best"

        opts = {
            "outtmpl": os.path.join(save_path, "%(title)s.%(ext)s"),
            "format": fmt,
            "noplaylist": True,
            "progress_hooks": [make_progress_hook(), rename_hook],
            "quiet": True,
            "no_warnings": True,
            "ffmpeg_location": ffmpeg_path if use_ffmpeg else None,
            "merge_output_format": "mp4" if is_video and use_ffmpeg else None,
        }
        if cookie_file:
            opts["cookiefile"] = cookie_file
            append_log(f"🍪 تم تفعيل كوكيز Instagram: {cookie_file}")
        elif use_instagram_cookies:
            append_log("ℹ️ لم يتم العثور على كوكيز Instagram. سأحاول بدون تسجيل دخول.")

        opts = {k: v for k, v in opts.items() if v is not None}

        try:
            append_log(f"بدء التحميل | النوع: {mode} | المسار: {save_path}")
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])

            set_status(ft.Icons.CHECK_CIRCLE, "✅ تم التحميل بنجاح!")
            show_snack("✅ تم التحميل بنجاح!")

            append_log("✅ تم التحميل بنجاح.")
            url_input.value = ""
            progress_bar.value = 1.0
            progress_text.value = "اكتمل ✅"
            page.update()

        except Exception as ex:
            err = str(ex)
            tb = traceback.format_exc()
            friendly_err = format_friendly_error(err, url, cookie_file)

            set_status(ft.Icons.ERROR, "❌ حصل خطأ أثناء التحميل")
            show_snack(f"❌ {friendly_err}")

            append_log("❌ خطأ:")
            append_log(friendly_err)
            if friendly_err != err:
                append_log(f"التفاصيل التقنية: {err}")
            append_log(tb)

            if friendly_err == err:
                show_error_dialog("حصل خطأ أثناء التحميل", tb)
            else:
                show_error_dialog("حصل خطأ أثناء التحميل", f"{friendly_err}\n\n{tb}")

            progress_bar.value = 0
            progress_text.value = "فشل ❌"
            page.update()

    # ---------- Event handler ----------
    def download_media(e: ft.ControlEvent):
        url = (url_input.value or "").strip()
        if not url:
            show_snack("الرابط وين؟ حطه غصب!")
            return

        mode = e.control.data  # "video" or "audio"
        t = threading.Thread(target=do_download, args=(url, mode), daemon=True)
        t.start()

    # ---------- UI ----------
    def on_pick_cookie_click(e: ft.ControlEvent):
        cookie_picker.pick_files(
            allow_multiple=False,
            dialog_title="اختر ملف Instagram Cookies",
        )

    def on_cookie_picked(e: ft.FilePickerResultEvent):
        if not e.files:
            return
        picked = (e.files[0].path or "").strip()
        if not picked:
            show_snack("لم أستطع قراءة مسار الملف.")
            return
        cookie_path_value.value = picked
        cookie_path_value.update()
        append_log(f"🍪 تم اختيار ملف الكوكيز: {picked}")
        show_snack("✅ تم حفظ ملف الكوكيز.")

    def auto_detect_cookie_on_startup():
        try:
            detected = resolve_instagram_cookie_file(get_dynamic_path())
            if detected:
                cookie_path_value.value = detected
                cookie_path_value.update()
                append_log(f"🍪 تم اكتشاف ملف كوكيز تلقائيًا: {detected}")
        except Exception:
            pass

    # دالة استقبال المجلد
    def on_dir_picked(e: ft.FilePickerResultEvent):
        if not e.path:
            show_snack("لم يتم اختيار مجلد.")
            return

        save_path_value.value = e.path
        save_path_value.update()
        append_log(f"📁 تم اختيار مجلد الحفظ: {e.path}")

    cookie_picker = ft.FilePicker(on_result=on_cookie_picked)
    page.overlay.append(cookie_picker)

    # --- Directory Picker for SAF ---
    dir_picker = ft.FilePicker(on_result=on_dir_picked)
    page.overlay.append(dir_picker)

    url_input = ft.TextField(
        label="رابط الفيديو (YouTube, Insta, etc.)",
        hint_text="ألصق الرابط هنا...",
        border_radius=15,
        width=420,
        prefix_icon=ft.Icons.LINK,
    )

    cookie_path_value = ft.Text(
        "-",
        selectable=True,
        size=11,
        color=ft.Colors.BLUE_100,
    )

    cookie_hint = ft.Text(
        "التقاط تلقائي من Download لأي ملف اسمه فيه cookie، أو اختره يدويًا من الزر.",
        size=10,
        color=ft.Colors.BLUE_200,
    )

    save_path_label = ft.Text("مسار الحفظ:", size=12, color=ft.Colors.BLUE_200)
    save_path_value = ft.Text("-", selectable=True, size=12)

    progress_bar = ft.ProgressBar(width=420, value=0)
    progress_text = ft.Text("التقدم: 0%", size=12)

    status_icon = ft.Icon(ft.Icons.INFO, size=22, color=ft.Colors.BLUE_300)
    status_text = ft.Text("جاهز", size=14)
    status_row = ft.Row([status_icon, status_text], alignment=ft.MainAxisAlignment.CENTER)

    log_box = ft.TextField(
        label="سجل العمليات والأخطاء",
        multiline=True,
        min_lines=6,
        max_lines=10,
        read_only=True,
        width=520,
        border_radius=12,
    )

    page.add(
        ft.Container(
            content=ft.Column(
                [
                    ft.Icon(ft.Icons.DOWNLOAD_FOR_OFFLINE, size=80, color=ft.Colors.BLUE_400),
                    ft.Text("تحميل غصب PRO", size=30, weight="bold", color=ft.Colors.BLUE_200),
                    ft.Text("أعلى جودة + تقدم + اسم القناة والعنوان", size=12, italic=True),
                    ft.Divider(height=15, color=ft.Colors.TRANSPARENT),

                    url_input,
                    ft.Divider(height=8, color=ft.Colors.TRANSPARENT),

                    ft.Row(
                        [
                            ft.Button(
                                "اختيار ملف كوكيز Instagram",
                                on_click=on_pick_cookie_click,
                                icon=ft.Icons.COOKIE,
                                style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)),
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.CENTER,
                    ),
                    cookie_path_value,
                    cookie_hint,
                    ft.Divider(height=8, color=ft.Colors.TRANSPARENT),

                    # زر اختيار مجلد الحفظ
                    ft.Button(
                        "اختيار مجلد الحفظ",
                        icon=ft.Icons.FOLDER,
                        on_click=lambda e: dir_picker.get_directory_path(),
                        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)),
                    ),

                    ft.Row(
                        [
                            ft.Button(
                                "فيديو",
                                data="video",
                                on_click=download_media,
                                icon=ft.Icons.DOWNLOAD,
                                style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)),
                            ),
                            ft.Button(
                                "صوت",
                                data="audio",
                                on_click=download_media,
                                icon=ft.Icons.MUSIC_NOTE,
                                style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)),
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.CENTER,
                    ),

                    ft.Divider(height=10, color=ft.Colors.TRANSPARENT),
                    status_row,

                    ft.Divider(height=10, color=ft.Colors.TRANSPARENT),
                    ft.Column([save_path_label, save_path_value], horizontal_alignment=ft.CrossAxisAlignment.CENTER),

                    ft.Divider(height=10, color=ft.Colors.TRANSPARENT),
                    progress_bar,
                    progress_text,

                    ft.Divider(height=12, color=ft.Colors.TRANSPARENT),
                    log_box,
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=24,
            bgcolor=ft.Colors.BLACK12,
            border_radius=20,
            width=580,
        )
    )

    auto_detect_cookie_on_startup()

ft.run(main)