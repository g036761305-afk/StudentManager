import requests
import sqlite3
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

CLOUD_URL = "https://student-manager.onrender.com"  # ודא שזו הכתובת המדויקת בענן
LOCAL_DB = "students.db"

# הגדרת כותרת דפדפן לעקיפת חסימת 418
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

session = requests.Session()

print("--- מתחיל במשיכת נתונים מהענן למחשב המקומי ---")

try:
    # 1. התחברות למערכת בענן לקבלת הרשאה
    login_data = {'username': 'admin', 'password': '123456'}
    session.post(f"{CLOUD_URL}/login", data=login_data, headers=headers, verify=False, timeout=15)
    
    # 2. משיכת נתוני התלמידים
    response = session.get(f"{CLOUD_URL}/api/students", headers=headers, verify=False, timeout=15)
    
    if response.status_code != 200:
        print(f"שגיאה בהתחברות לענן: קוד {response.status_code}")
        exit()

    cloud_students = response.json()
    print(f"נמצאו {len(cloud_students)} תלמידים בענן.")

    conn = sqlite3.connect(LOCAL_DB)
    cursor = conn.cursor()

    added = 0
    updated = 0

    for s in cloud_students:
        s_id = s.get('id')
        cursor.execute("SELECT id FROM students WHERE id = ?", (s_id,))
        exists = cursor.fetchone()

        if not exists:
            cursor.execute("""
                INSERT INTO students (
                    id, first_name, last_name, tz, is_passport, passport_country, passport_expiry,
                    status, birth_date_gregorian, birth_date_hebrew, city, neighborhood, address,
                    phone, additional_phone, father_name, mother_name, mother_maiden_name,
                    previous_institution, cycle, voicemail, telephony_code, strengthening,
                    is_jerusalem_branch, entry_date, leave_date, wedding_date, avatar_path,
                    id_photo_path, id_photo_exists
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                s.get('id'), s.get('first_name'), s.get('last_name'), s.get('tz'), s.get('is_passport', 0),
                s.get('passport_country'), s.get('passport_expiry'), s.get('status'), s.get('birth_date_gregorian'),
                s.get('birth_date_hebrew'), s.get('city'), s.get('neighborhood'), s.get('address'),
                s.get('phone'), s.get('additional_phone'), s.get('father_name'), s.get('mother_name'),
                s.get('mother_maiden_name'), s.get('previous_institution'), s.get('cycle'), s.get('voicemail'),
                s.get('telephony_code'), s.get('strengthening'), s.get('is_jerusalem_branch', 0),
                s.get('entry_date'), s.get('leave_date'), s.get('wedding_date'), s.get('avatar_path'),
                s.get('id_photo_path'), s.get('id_photo_exists', 0)
            ))
            added += 1
        else:
            updated += 1

    conn.commit()
    conn.close()
    print(f"\nהסנכרון הושלם בהצלחה!")
    print(f"התווספו {added} תלמידים חדשים למחשב המקומי.")

except Exception as e:
    print(f"אירעה שגיאה במהלך המשיכה: {e}")