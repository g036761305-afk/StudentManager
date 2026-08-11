import sqlite3
import os
from sqlalchemy import create_engine, text

# חיבור למסד הנתונים המקומי
local_conn = sqlite3.connect('students.db')
local_conn.row_factory = sqlite3.Row
local_cursor = local_conn.cursor()

# כתובת External Database URL של Render
CLOUD_DB_URL = "postgresql://students_db_5t2m_user:1sE8YDW4pWh3hSWQMcaU8E9sX5vNjINn@dpg-d9kgiclaeets73av85i0-a.ohio-postgres.render.com/students_db_5t2m"
cloud_engine = create_engine(CLOUD_DB_URL)

print("מתחיל בהעברת הנתונים לענן...")

# 1. העברת משתמשים
local_cursor.execute("SELECT * FROM users")
users = local_cursor.fetchall()
with cloud_engine.begin() as conn:
    for u in users:
        try:
            conn.execute(text("INSERT INTO users (username, password_hash) VALUES (:username, :password_hash) ON CONFLICT (username) DO NOTHING"), {
                "username": u["username"],
                "password_hash": u["password_hash"]
            })
        except Exception as e:
            print(f"שגיאה בהעברת משתמש {u['username']}: {e}")

print(f"הועברו {len(users)} משתמשים.")

# 2. העברת תלמידים
local_cursor.execute("SELECT * FROM students")
students = local_cursor.fetchall()

fields = [
    'last_name', 'first_name', 'tz', 'is_passport', 'passport_country', 'passport_expiry',
    'birth_date_gregorian', 'birth_date_hebrew', 'address', 'city', 'phone', 'additional_phone',
    'neighborhood', 'status', 'father_name', 'mother_name', 'mother_maiden_name',
    'previous_institution', 'voicemail', 'telephony_code', 'cycle', 'entry_date',
    'leave_date', 'wedding_date', 'strengthening', 'is_jerusalem_branch',
    'id_photo_exists', 'id_photo_path', 'avatar_path'
]

with cloud_engine.begin() as conn:
    for s in students:
        s_dict = {field: s[field] if field in s.keys() else None for field in fields}
        try:
            query = text(f'''
                INSERT INTO students ({", ".join(fields)}) 
                VALUES ({", ".join([":" + f for f in fields])})
                ON CONFLICT (tz) DO UPDATE SET 
                id_photo_exists = EXCLUDED.id_photo_exists,
                id_photo_path = EXCLUDED.id_photo_path,
                avatar_path = EXCLUDED.avatar_path
            ''')
            conn.execute(query, s_dict)
        except Exception as e:
            print(f"שגיאה בהעברת תלמיד {s['tz']}: {e}")

print(f"הועברו {len(students)} תלמידים.")

# 3. העברת תבניות מסמכים
try:
    local_cursor.execute("SELECT * FROM document_templates")
    templates = local_cursor.fetchall()
    with cloud_engine.begin() as conn:
        for t in templates:
            conn.execute(text("INSERT INTO document_templates (title, content) VALUES (:title, :content) ON CONFLICT (title) DO NOTHING"), {
                "title": t["title"],
                "content": t["content"]
            })
    print(f"הועברו {len(templates)} תבניות מסמכים.")
except Exception as e:
    print("לא נמצאו תבניות להעברה.")

local_conn.close()
print("תהליך הגירת הנתונים הושלם בהצלחה!")