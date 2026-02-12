import flet as ft
import yt_dlp
import threading
import json
import os
import traceback

# --- الإعدادات الثابتة ---
HISTORY_FILE = "download_history.json"
# تحديد مسار التحميل (أندرويد أو ويندوز)
if os.name != 'nt':
    DOWNLOAD_PATH = "/storage/emulated/0/Download/"
else:
    DOWNLOAD_PATH = "./"

def main(page: ft.Page):
    page.title = "تحميل غصب - الإصدار النهائي"
    page.theme_mode = ft.ThemeMode.DARK
    page.scroll = ft.ScrollMode.AUTO
    page.padding = 20

    # --- 1. طلب الصلاحيات لأندرويد ---
    def request_android_permissions():
        if page.platform == ft.PagePlatform.ANDROID:
            package_name = "com.ghasab.downloader" # تأكد من مطابقة هذا الاسم في البناء
            try:
                os.system(f"am start -a android.settings.MANAGE_APP_ALL_FILES_ACCESS_PERMISSION -d package:{package_name}")
                page.snack_bar = ft.SnackBar(ft.Text("يرجى منح إذن الوصول للملفات للحفظ في المجلد العام"))
                page.snack_bar.open = True
            except: pass

    # --- 2. إدارة السجل ---
    def load_history():
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except: return []
        return []

    def save_history(data):
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    # --- 3. عناصر الواجهة ---
    url_input = ft.TextField(label="رابط الفيديو", hint_text="لصق الرابط هنا...", expand=True, border_radius=15)
    pb = ft.ProgressBar(width=400, value=0, visible=False, color="blueaccent")
    status_text = ft.Text("جاهز للفزعة...")
    history_column = ft.Column(spacing=10)
    
    history_data = load_history()

    def add_to_ui_history(title, status, error=""):
        icon = ft.icons.CHECK_CIRCLE if status == "تم" else ft.icons.ERROR
        color = "green" if status == "تم" else "red"
        history_column.controls.insert(0, ft.ListTile(
            leading=ft.Icon(icon, color=color),
            title=ft.Text(title, max_lines=1, overflow="ellipsis"),
            subtitle=ft.Text(f"الحالة: {status}" + (f"\nخطأ: {error}" if error else "")),
            is_three_line=True if error else False
        ))
        page.update()

    # تحميل السجل القديم للواجهة
    for item in history_data:
        add_to_ui_history(item['title'], item['status'], item.get('error', ""))

    # --- 4. منطق التحميل (Hook & Thread) ---
    def progress_hook(d):
        if d['status'] == 'downloading':
            downloaded = d.get('downloaded_bytes', 0)
            total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
            if total > 0:
                pb.value = downloaded / total
                status_text.value = f"جاري السحب.. { (downloaded/total)*100:.1f}%"
                page.update()

    def download_task(url):
        ydl_opts = {
            'progress_hooks': [progress_hook],
            'outtmpl': os.path.join(DOWNLOAD_PATH, '%(title)s.%(ext)s'),
            'no_overwrites': True,
            'windows_filenames': True,
            # 'cookiefile': 'cookies.txt', # فعلها إذا أردت
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                title = info.get('title', 'فيديو غير معروف')
                res_status = "تم"
                res_error = ""
        except Exception as e:
            title = url
            res_status = "فشل"
            res_error = str(e)

        # حفظ وتحديث
        new_entry = {"title": title, "status": res_status, "error": res_error}
        history_data.append(new_entry)
        save_history(history_data)
        
        pb.visible = False
        status_text.value = "تمت المهمة بنجاح ✅" if res_status == "تم" else "فشل التحميل ❌"
        add_to_ui_history(title, res_status, res_error)
        page.update()

    def on_click_download(e):
        if not url_input.value: return
        pb.visible = True
        pb.value = 0
        status_text.value = "⏳ جاري التحقق..."
        page.update()
        threading.Thread(target=download_task, args=(url_input.value,), daemon=True).start()

    # --- 5. البناء النهائي للصفحة ---
    page.add(
        ft.Text("تحميل غصب 🚀", size=35, weight="bold", color="blueaccent"),
        ft.Row([url_input, ft.IconButton(ft.icons.GET_APP, on_click=on_click_download, icon_size=35)]),
        status_text,
        pb,
        ft.Divider(),
        ft.Text("📜 السجل", size=20, weight="bold"),
        history_column
    )
    
    # اطلب الصلاحية عند الفتح
    request_android_permissions()

ft.app(target=main)
