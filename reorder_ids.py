from sqlalchemy import create_engine, text

# חיבור למסד הנתונים בענן (PostgreSQL)
CLOUD_DB_URL = "postgresql://students_db_5t2m_user:1sE8YDW4pWh3hSWQMcaU8E9sX5vNjINn@dpg-d9kgiclaeets73av85i0-a.ohio-postgres.render.com/students_db_5t2m"
engine = create_engine(CLOUD_DB_URL)

with engine.begin() as conn:
    print("מתחיל בתהליך סידור ה-ID מחדש...")
    
    # 1. יצירת טבלה זמנית עם כל הנתונים, ממוינים לפי מחזור ושם משפחה
    conn.execute(text('''
        CREATE TEMP TABLE temp_students AS 
        SELECT 
            last_name, first_name, tz, is_passport, passport_country, passport_expiry,
            birth_date_gregorian, birth_date_hebrew, address, city, phone, additional_phone,
            neighborhood, status, father_name, mother_name, mother_maiden_name,
            previous_institution, voicemail, telephony_code, cycle, entry_date,
            leave_date, wedding_date, strengthening, is_jerusalem_branch,
            id_photo_exists, id_photo_path, avatar_path
        FROM students 
        ORDER BY cycle ASC, last_name ASC, first_name ASC;
    '''))
    
    # 2. מחיקת הנתונים המקוריים מטבלת התלמידים
    conn.execute(text("TRUNCATE TABLE students RESTART IDENTITY;"))
    
    # 3. הכנסת הנתונים הממוינים חזרה לטבלה (ה-ID ייווצר מחדש לפי הסדר: 1, 2, 3...)
    conn.execute(text('''
        INSERT INTO students (
            last_name, first_name, tz, is_passport, passport_country, passport_expiry,
            birth_date_gregorian, birth_date_hebrew, address, city, phone, additional_phone,
            neighborhood, status, father_name, mother_name, mother_maiden_name,
            previous_institution, voicemail, telephony_code, cycle, entry_date,
            leave_date, wedding_date, strengthening, is_jerusalem_branch,
            id_photo_exists, id_photo_path, avatar_path
        )
        SELECT 
            last_name, first_name, tz, is_passport, passport_country, passport_expiry,
            birth_date_gregorian, birth_date_hebrew, address, city, phone, additional_phone,
            neighborhood, status, father_name, mother_name, mother_maiden_name,
            previous_institution, voicemail, telephony_code, cycle, entry_date,
            leave_date, wedding_date, strengthening, is_jerusalem_branch,
            id_photo_exists, id_photo_path, avatar_path
        FROM temp_students;
    '''))
    
    # 4. מחיקת הטבלה הזמנית
    conn.execute(text("DROP TABLE temp_students;"))

print("ה-ID של כל התלמידים סודר מחדש בהצלחה!")