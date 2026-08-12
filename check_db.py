import os
import sqlite3

paths = [
    'students',
    'students.db',
    'instance/students',
    'instance/students.db'
]

print("\n--- תוצאות סריקת מסדי הנתונים ---")
for p in paths:
    if os.path.exists(p):
        size = os.path.getsize(p)
        print(f"\nקובץ: {p} (גודל: {size} bytes)")
        try:
            conn = sqlite3.connect(p)
            tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            if not tables:
                print("  [קובץ ריק ללא טבלאות]")
            for t in tables:
                tname = t[0]
                cnt = conn.execute(f"SELECT COUNT() FROM [{tname}]").fetchone()[0]
                print(f"  <- טבלה: {tname} | שורות: {cnt}")
        except Exception as e:
            print(f"  שגיאה בקריאת הקובץ: {e}")

print("\n---------------------------------\n")