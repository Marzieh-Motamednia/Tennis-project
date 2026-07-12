import zipfile
from pathlib import Path
import os

source_dir = Path(r"") 

extract_dir = source_dir / "extracted_data"
extract_dir.mkdir(exist_ok=True)

print("شروع فرآیند اکسترکت فایل‌ها...")

# پیدا کردن تمام فایل‌های زیپ در پوشه
zip_files = list(source_dir.glob("*.zip"))
total_files = len(zip_files)

if total_files == 0:
    print("هیچ فایل زیپی در این مسیر پیدا نشد! مسیر رو دوباره چک کن.")
else:
    for index, zip_path in enumerate(zip_files, 1):
        folder_name = zip_path.stem  
        target_subfolder = extract_dir / folder_name
        target_subfolder.mkdir(exist_ok=True)
        
        print(f"[{index}/{total_files}] در حال استخراج: {zip_path.name}...")
        
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(target_subfolder)
        except Exception as e:
            print(f"❌ خطا در استخراج فایل {zip_path.name}: {e}")

print("\n🎉 کار تموم شد! همه فایل‌ها با موفقیت استخراج شدن.")
