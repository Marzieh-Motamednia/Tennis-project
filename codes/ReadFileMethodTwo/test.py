import duckdb
import pandas as pd

con = duckdb.connect('tennis.duckdb')

# استفاده از قدرت SQL برای فیلتر کردن داده‌ها قبل از ورود به رم
query = """
    SELECT * 
    FROM match_event 
    WHERE snapshot_date = '2024-02-15'
"""

# تبدیل مستقیم نتیجه به دیت‌افریم پانداز
df = con.execute(query).df()

print(f"تعداد ردیف‌های استخراج شده: {len(df)}")
print(df.head())
