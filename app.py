import os
import sqlite3
import urllib.request
from flask import Flask, render_template, request, jsonify, send_file, send_from_directory, session, redirect, url_for
import pandas as pd
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from pyluach import dates
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import io
import datetime
import json
from sqlalchemy import create_engine, text
import cloudinary
import cloudinary.uploader

app = Flask(__name__)
app.secret_key = 'super_secret_local_key_change_if_needed'

DB_NAME = "students.db"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(os.path.join(UPLOAD_FOLDER, 'id_photos'), exist_ok=True)
os.makedirs(os.path.join(UPLOAD_FOLDER, 'avatars'), exist_ok=True)
os.makedirs(os.path.join(UPLOAD_FOLDER, 'batch_photos'), exist_ok=True)

# הגדרת Cloudinary
cloudinary.config(
    cloud_name=os.environ.get('CLOUDINARY_CLOUD_NAME', 'tusisaci'),
    api_key=os.environ.get('CLOUDINARY_API_KEY', '483242616177883'),
    api_secret=os.environ.get('CLOUDINARY_API_SECRET', 'KoK3dOz19OY1JlLOwDEG_EFJWO8')
)

def save_uploaded_file(file, folder_name, custom_filename):
    if not file or file.filename == '':
        return None
    
    # 1. שמירה מקומית פיזית במחשב
    local_dir = os.path.join(app.config['UPLOAD_FOLDER'], folder_name)
    os.makedirs(local_dir, exist_ok=True)
    local_path = os.path.join(local_dir, custom_filename)
    file.save(local_path)
    
    # 2. העלאה ל-Cloudinary
    try:
        upload_result = cloudinary.uploader.upload(local_path, folder=folder_name)
        return upload_result.get('secure_url')
    except Exception as e:
        print(f"Error uploading to Cloudinary: {e}")
        return f"/uploads/{folder_name}/{custom_filename}"

# טעינת הפונט העברי
FONT_PATH = os.path.join(os.path.dirname(__file__), 'arial.ttf')
if os.path.exists(FONT_PATH):
    pdfmetrics.registerFont(TTFont('HebrewFont', FONT_PATH))
    DEFAULT_FONT = 'HebrewFont'
else:
    DEFAULT_FONT = 'Helvetica'

# הגדרת מסד הנתונים
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL:
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    engine = create_engine(DATABASE_URL)
else:
    engine = create_engine(f'sqlite:///{DB_NAME}')

def execute_query(query, params=None):
    if params is None:
        params = {}
    with engine.begin() as conn:
        result = conn.execute(text(query), params)
        if result.returns_rows:
            return [dict(row) for row in result.mappings()]
        return None

def int_to_gematria(num):
    gematria_map = [
        (1000, ''), (900, 'תתק'), (800, 'תת'), (700, 'תש'), (600, 'תר'), (500, 'תק'), (400, 'ת'),
        (300, 'ש'), (200, 'ר'), (100, 'ק'), (90, 'צ'), (80, 'פ'), (70, 'ע'), (60, 'ס'),
        (50, 'נ'), (40, 'מ'), (30, 'ל'), (20, 'כ'), (10, 'י'), (9, 'ט'), (8, 'ח'),
        (7, 'ז'), (6, 'ו'), (5, 'ה'), (4, 'ד'), (3, 'ג'), (2, 'ב'), (1, 'א')
    ]
    if num == 15: return 'טו'
    if num == 16: return 'טז'
    res = ''
    for val, letters in gematria_map:
        while num >= val:
            res += letters
            num -= val
    if len(res) > 1: return res[:-1] + '"' + res[-1]
    elif len(res) == 1: return res + "'"
    return res

def get_hebrew_date_string(day, month_num, year):
    months = {1: "ניסן", 2: "אייר", 3: "סיון", 4: "תמוז", 5: "אב", 6: "אלול", 7: "תשרי", 8: "חשון", 9: "כסלו", 10: "טבת", 11: "שבט", 12: "אדר", 13: "אדר ב"}
    day_heb = int_to_gematria(day)
    year_mod = year % 1000
    year_heb = int_to_gematria(year_mod)
    if year_heb.startswith('ת'): year_heb = 'ה' + year_heb
    return f"{day_heb} {months.get(month_num)} {year_heb}"

def init_db():
    with engine.begin() as conn:
        conn.execute(text('''
            CREATE TABLE IF NOT EXISTS students (
                id SERIAL PRIMARY KEY,
                last_name TEXT,
                first_name TEXT,
                tz TEXT UNIQUE,
                is_passport INTEGER DEFAULT 0,
                passport_country TEXT,
                passport_expiry TEXT,
                birth_date_gregorian TEXT,
                birth_date_hebrew TEXT,
                address TEXT,
                city TEXT,
                phone TEXT,
                additional_phone TEXT,
                neighborhood TEXT,
                status TEXT,
                father_name TEXT,
                mother_name TEXT,
                mother_maiden_name TEXT,
                previous_institution TEXT,
                voicemail TEXT,
                telephony_code TEXT,
                cycle TEXT,
                entry_date TEXT,
                leave_date TEXT,
                wedding_date TEXT,
                strengthening TEXT,
                is_jerusalem_branch INTEGER DEFAULT 0,
                id_photo_exists INTEGER DEFAULT 0,
                id_photo_path TEXT,
                avatar_path TEXT
            )
        '''))
        
        conn.execute(text('''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL
            )
        '''))
        
        res = conn.execute(text("SELECT * FROM users WHERE username = :u"), {"u": "מנהל ראשי"}).fetchone()
        if not res:
            default_hash = generate_password_hash("123456")
            conn.execute(text("INSERT INTO users (username, password_hash) VALUES (:u, :p)"), {"u": "מנהל ראשי", "p": default_hash})

        conn.execute(text('CREATE TABLE IF NOT EXISTS document_templates (id SERIAL PRIMARY KEY, title TEXT UNIQUE, content TEXT)'))

@app.before_request
def require_login():
    allowed_routes = ['login', 'static']
    if not session.get('logged_in') and request.endpoint not in allowed_routes:
        return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        users = execute_query("SELECT * FROM users WHERE username = :u", {"u": username})
        user = users[0] if users else None
        
        if user and check_password_hash(user['password_hash'], password):
            session['logged_in'] = True
            session['username'] = username
            return redirect(url_for('index'))
        else:
            error = "שם משתמש או סיסמה שגויים."
            
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/api/change-password', methods=['POST'])
def change_password():
    data = request.json
    old_pass = data.get('old_password')
    new_pass = data.get('new_password')
    username = session.get('username')

    if not username:
        return jsonify({"error": "משתמש אינו מחובר"}), 401

    users = execute_query("SELECT * FROM users WHERE username = :u", {"u": username})
    user = users[0] if users else None

    if not user or not check_password_hash(user['password_hash'], old_pass):
        return jsonify({"error": "הסיסמה הישנה שגויה"}), 400

    new_hash = generate_password_hash(new_pass)
    execute_query("UPDATE users SET password_hash = :p WHERE username = :u", {"p": new_hash, "u": username})
    return jsonify({"status": "success", "message": "הסיסמה עודכנה בהצלחה"})

@app.route('/api/add-user', methods=['POST'])
def add_user():
    data = request.json
    new_username = data.get('username', '').strip()
    new_password = data.get('password', '').strip()

    if not new_username or not new_password:
        return jsonify({"error": "יש למלא שם משתמש וסיסמה"}), 400

    try:
        new_hash = generate_password_hash(new_password)
        execute_query("INSERT INTO users (username, password_hash) VALUES (:u, :p)", {"u": new_username, "p": new_hash})
        return jsonify({"status": "success", "message": f"המשתמש '{new_username}' נוצר בהצלחה"})
    except Exception as e:
        return jsonify({"error": "שם המשתמש כבר קיים במערכת"}), 400

@app.route('/api/users', methods=['GET'])
def get_users():
    users = execute_query("SELECT id, username FROM users") or []
    return jsonify(users)

@app.route('/api/delete-user/<int:user_id>', methods=['POST', 'DELETE'])
def delete_user(user_id):
    current_username = session.get('username')
    users = execute_query("SELECT * FROM users WHERE id = :id", {"id": user_id})
    user = users[0] if users else None
    
    if not user:
        return jsonify({"error": "משתמש לא נמצא"}), 404
        
    if user['username'] == current_username:
        return jsonify({"error": "אינך יכול למחוק את המשתמש שמחובר כעת במערכת"}), 400

    execute_query("DELETE FROM users WHERE id = :id", {"id": user_id})
    return jsonify({"status": "success", "message": "המשתמש נמחק בהצלחה"})

@app.route('/')
def index():
    return render_template('index.html', username=session.get('username'))

@app.route('/api/students', methods=['GET'])
def get_students():
    rows = execute_query("SELECT * FROM students") or []
    
    # בדיקת התאמה לנתיב המקומי במידה והקובץ הורד למחשב (לתמיכה באופליין)
    for row in rows:
        # בדיקת תמונת פרופיל
        if row.get('avatar_path') and row['avatar_path'].startswith('http'):
            filename = os.path.basename(row['avatar_path'])
            local_file = os.path.join(app.config['UPLOAD_FOLDER'], 'avatars', filename)
            if os.path.exists(local_file):
                row['avatar_path'] = f"/uploads/avatars/{filename}"

        # בדיקת צילום ת"ז
        if row.get('id_photo_path') and row['id_photo_path'].startswith('http'):
            filename = os.path.basename(row['id_photo_path'])
            local_file = os.path.join(app.config['UPLOAD_FOLDER'], 'id_photos', filename)
            if os.path.exists(local_file):
                row['id_photo_path'] = f"/uploads/id_photos/{filename}"
                
    return jsonify(rows)

@app.route('/api/students/save', methods=['POST'])
def save_student():
    data = request.form.to_dict()
    student_id = data.get('id')
    is_passport = int(data.get('is_passport', 0))
    is_jerusalem_branch = int(data.get('is_jerusalem_branch', 0))
    
    current_id_photo_exists = 0
    current_id_photo_path = ''
    current_avatar_path = ''
    
    if student_id:
        existing = execute_query("SELECT id_photo_exists, id_photo_path, avatar_path FROM students WHERE id = :id", {"id": student_id})
        if existing:
            current_id_photo_exists = existing[0]['id_photo_exists'] or 0
            current_id_photo_path = existing[0]['id_photo_path'] or ''
            current_avatar_path = existing[0]['avatar_path'] or ''

    id_photo_path = current_id_photo_path
    id_photo_exists = current_id_photo_exists
    
    if 'id_photo' in request.files:
        file = request.files['id_photo']
        if file and file.filename != '':
            filename = secure_filename(f"id_{data.get('tz')}_{file.filename}")
            uploaded_url = save_uploaded_file(file, 'id_photos', filename)
            if uploaded_url:
                id_photo_path = uploaded_url
                id_photo_exists = 1

    avatar_path = current_avatar_path
    if 'avatar' in request.files:
        file = request.files['avatar']
        if file and file.filename != '':
            filename = secure_filename(f"avatar_{data.get('tz')}_{file.filename}")
            uploaded_url = save_uploaded_file(file, 'avatars', filename)
            if uploaded_url:
                avatar_path = uploaded_url

    phone = data.get('phone', '').strip()
    if phone != "" and not phone.startswith('0'): phone = "0" + phone

    additional_phone = data.get('additional_phone', '').strip()
    if additional_phone != "" and not additional_phone.startswith('0'): additional_phone = "0" + additional_phone

    wedding_date = data.get('wedding_date', '').strip()
    leave_date = data.get('leave_date', '').strip()

    if wedding_date and not leave_date:
        leave_date = wedding_date

    params = {
        "last_name": data.get('last_name'), "first_name": data.get('first_name'), "tz": data.get('tz'),
        "is_passport": is_passport, "passport_country": data.get('passport_country'), "passport_expiry": data.get('passport_expiry'),
        "birth_date_gregorian": data.get('birth_date_gregorian'), "birth_date_hebrew": data.get('birth_date_hebrew'),
        "address": data.get('address'), "city": data.get('city'), "phone": phone, "additional_phone": additional_phone,
        "neighborhood": data.get('neighborhood'), "status": data.get('status'), "father_name": data.get('father_name'),
        "mother_name": data.get('mother_name'), "mother_maiden_name": data.get('mother_maiden_name'),
        "previous_institution": data.get('previous_institution'), "voicemail": data.get('voicemail'),
        "telephony_code": data.get('telephony_code'), "cycle": data.get('cycle'), "entry_date": data.get('entry_date'),
        "leave_date": leave_date, "wedding_date": wedding_date, "strengthening": data.get('strengthening'),
        "is_jerusalem_branch": is_jerusalem_branch, "id_photo_exists": id_photo_exists,
        "id_photo_path": id_photo_path, "avatar_path": avatar_path
    }

    if student_id:
        params["id"] = student_id
        execute_query('''
            UPDATE students SET 
                last_name=:last_name, first_name=:first_name, tz=:tz, is_passport=:is_passport, passport_country=:passport_country, passport_expiry=:passport_expiry,
                birth_date_gregorian=:birth_date_gregorian, birth_date_hebrew=:birth_date_hebrew, address=:address, city=:city, phone=:phone, additional_phone=:additional_phone,
                neighborhood=:neighborhood, status=:status, father_name=:father_name, mother_name=:mother_name, mother_maiden_name=:mother_maiden_name, previous_institution=:previous_institution,
                voicemail=:voicemail, telephony_code=:telephony_code, cycle=:cycle, entry_date=:entry_date, leave_date=:leave_date, wedding_date=:wedding_date, strengthening=:strengthening,
                is_jerusalem_branch=:is_jerusalem_branch, id_photo_exists=:id_photo_exists, id_photo_path=:id_photo_path, avatar_path=:avatar_path
            WHERE id=:id
        ''', params)
    else:
        execute_query('''
            INSERT INTO students (
                last_name, first_name, tz, is_passport, passport_country, passport_expiry,
                birth_date_gregorian, birth_date_hebrew, address, city, phone, additional_phone,
                neighborhood, status, father_name, mother_name, mother_maiden_name, previous_institution,
                voicemail, telephony_code, cycle, entry_date, leave_date, wedding_date, strengthening,
                is_jerusalem_branch, id_photo_exists, id_photo_path, avatar_path
            ) VALUES (
                :last_name, :first_name, :tz, :is_passport, :passport_country, :passport_expiry,
                :birth_date_gregorian, :birth_date_hebrew, :address, :city, :phone, :additional_phone,
                :neighborhood, :status, :father_name, :mother_name, :mother_maiden_name, :previous_institution,
                :voicemail, :telephony_code, :cycle, :entry_date, :leave_date, :wedding_date, :strengthening,
                :is_jerusalem_branch, :id_photo_exists, :id_photo_path, :avatar_path
            )
        ''', params)
    return jsonify({"status": "success"})

# נתיב סנכרון והורדה אוטומטית של תמונות מהענן למחשב המקומי
@app.route('/api/sync-photos', methods=['GET', 'POST'])
def sync_photos():
    rows = execute_query("SELECT avatar_path, id_photo_path FROM students") or []
    downloaded_count = 0

    for row in rows:
        # סנכרון תמונות פרופיל
        avatar_url = row.get('avatar_path')
        if avatar_url and avatar_url.startswith('http'):
            filename = os.path.basename(avatar_url)
            local_path = os.path.join(app.config['UPLOAD_FOLDER'], 'avatars', filename)
            if not os.path.exists(local_path):
                try:
                    urllib.request.urlretrieve(avatar_url, local_path)
                    downloaded_count += 1
                except Exception as e:
                    print(f"Error downloading avatar {filename}: {e}")

        # סנכרון צילומי ת"ז
        id_photo_url = row.get('id_photo_path')
        if id_photo_url and id_photo_url.startswith('http'):
            filename = os.path.basename(id_photo_url)
            local_path = os.path.join(app.config['UPLOAD_FOLDER'], 'id_photos', filename)
            if not os.path.exists(local_path):
                try:
                    urllib.request.urlretrieve(id_photo_url, local_path)
                    downloaded_count += 1
                except Exception as e:
                    print(f"Error downloading id_photo {filename}: {e}")

    return jsonify({"status": "success", "downloaded": downloaded_count, "message": f"סונכרנו {downloaded_count} תמונות חדשות למחשב המקומי!"})

@app.route('/api/students/<int:student_id>/delete-avatar', methods=['POST'])
def delete_avatar(student_id):
    try:
        student = execute_query("SELECT avatar_path FROM students WHERE id=:id", {"id": student_id})
        if student and student[0]['avatar_path']:
            full_path = student[0]['avatar_path'].lstrip('/')
            if os.path.exists(full_path): os.remove(full_path)
            execute_query("UPDATE students SET avatar_path = NULL WHERE id=:id", {"id": student_id})
        return jsonify({"status": "success"})
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/api/students/<int:student_id>/delete-id-photo', methods=['POST'])
def delete_id_photo(student_id):
    try:
        student = execute_query("SELECT id_photo_path FROM students WHERE id=:id", {"id": student_id})
        if student and student[0]['id_photo_path']:
            full_path = student[0]['id_photo_path'].lstrip('/')
            if os.path.exists(full_path):
                try: os.remove(full_path)
                except Exception: pass
            execute_query("UPDATE students SET id_photo_path = NULL, id_photo_exists = 0 WHERE id=:id", {"id": student_id})
        return jsonify({"status": "success"})
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/api/students/<int:student_id>/delete', methods=['DELETE'])
def delete_student(student_id):
    try:
        execute_query("DELETE FROM students WHERE id=:id", {"id": student_id})
        return jsonify({"status": "success"})
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/api/download-template', methods=['GET'])
def download_template():
    template_path = os.path.join(UPLOAD_FOLDER, "template_import.xlsx")
    return send_file(template_path, as_attachment=True)

@app.route('/api/import-excel', methods=['POST'])
def import_excel():
    if 'excel_file' not in request.files: return jsonify({"error": "No file uploaded"}), 400
    file = request.files['excel_file']
    if file.filename == '': return jsonify({"error": "Empty filename"}), 400
    try:
        df = pd.read_excel(file)
        success_count = 0
        for _, row in df.iterrows():
            tz_val = str(row.get('תעודת זהות', '')).split('.')[0].strip() if pd.notna(row.get('תעודת זהות')) else None
            if not tz_val or tz_val == "" or tz_val == "nan": continue
            is_pass_val = int(row.get('is_passport', 0)) if pd.notna(row.get('is_passport')) else 0
            id_photo_exists_val = int(row.get('צילום תעודת זהות', 0)) if pd.notna(row.get('צילום תעודת זהות')) else 0
            
            p_phone = str(row.get('טלפון', '')).split('.')[0].strip() if pd.notna(row.get('טלפון')) and str(row.get('טלפון')) != 'nan' else ''
            if p_phone != "" and not p_phone.startswith('0'): p_phone = "0" + p_phone
            
            p_add = str(row.get("מס' נוסף", '')).split('.')[0].strip() if pd.notna(row.get("מס' נוסף")) and str(row.get("מס' נוסף")) != 'nan' else ''
            if p_add != "" and not p_add.startswith('0'): p_add = "0" + p_add

            try:
                execute_query('''
                    INSERT INTO students (
                        last_name, first_name, tz, is_passport, passport_country, passport_expiry,
                        birth_date_gregorian, birth_date_hebrew, address, city, neighborhood,
                        phone, additional_phone, status, father_name, mother_name, mother_maiden_name,
                        previous_institution, voicemail, telephony_code, cycle, entry_date, leave_date, wedding_date, strengthening,
                        is_jerusalem_branch, id_photo_exists, id_photo_path, avatar_path
                    ) VALUES (
                        :last_name, :first_name, :tz, :is_passport, :passport_country, :passport_expiry,
                        :birth_date_gregorian, :birth_date_hebrew, :address, :city, :neighborhood,
                        :phone, :additional_phone, :status, :father_name, :mother_name, :mother_maiden_name,
                        :previous_institution, :voicemail, :telephony_code, :cycle, :entry_date, :leave_date, :wedding_date, :strengthening,
                        :is_jerusalem_branch, :id_photo_exists, :id_photo_path, :avatar_path
                    )
                ''', {
                    "last_name": str(row.get('שם משפחה', '')) if pd.notna(row.get('שם משפחה')) else '',
                    "first_name": str(row.get('שם פרטי', '')) if pd.notna(row.get('שם פרטי')) else '',
                    "tz": tz_val, "is_passport": is_pass_val,
                    "passport_country": str(row.get('passport_country', '')) if pd.notna(row.get('passport_country')) and str(row.get('passport_country')) != 'nan' else '',
                    "passport_expiry": str(row.get('passport_expiry', '')) if pd.notna(row.get('passport_expiry')) and str(row.get('passport_expiry')) != 'nan' else '',
                    "birth_date_gregorian": str(row.get('תאריך לידה לועזי', ''))[:10] if pd.notna(row.get('תאריך לידה לועזי')) and str(row.get('תאריך לידה לועזי')) != 'nan' else '',
                    "birth_date_hebrew": str(row.get('תאריך לידה עברי', '')) if pd.notna(row.get('תאריך לידה עברי')) and str(row.get('תאריך לידה עברי')) != 'nan' else '',
                    "address": str(row.get('כתובת', '')) if pd.notna(row.get('כתובת')) and str(row.get('כתובת')) != 'nan' else '',
                    "city": str(row.get('עיר', '')) if pd.notna(row.get('עיר')) and str(row.get('עיר')) != 'nan' else '',
                    "neighborhood": str(row.get('שכונה', '')) if pd.notna(row.get('שכונה')) and str(row.get('שכונה')) != 'nan' else '',
                    "phone": p_phone, "additional_phone": p_add,
                    "status": str(row.get('סטטוס', '')) if pd.notna(row.get('סטטוס')) and str(row.get('סטטוס')) != 'nan' else '',
                    "father_name": str(row.get('שם האב', '')) if pd.notna(row.get('שם האב')) and str(row.get('שם האם')) != 'nan' else '',
                    "mother_name": str(row.get('שם האם', '')) if pd.notna(row.get('שם האם')) and str(row.get('שם האם')) != 'nan' else '',
                    "mother_maiden_name": str(row.get('לבית', '')) if pd.notna(row.get('לבית')) and str(row.get('לבית')) != 'nan' else '',
                    "previous_institution": str(row.get('שם הישיה"ק', '')) if pd.notna(row.get('שם הישיה"ק')) and str(row.get('שם הישיה"ק')) != 'nan' else '',
                    "voicemail": str(row.get('תא קולי', '')).split('.')[0] if pd.notna(row.get('תא קולי')) and str(row.get('תא קולי')) != 'nan' else '',
                    "telephony_code": str(row.get('קוד טלפוניה', '')).split('.')[0] if pd.notna(row.get('קוד טלפוניה')) and str(row.get('קוד טלפוניה')) != 'nan' else '',
                    "cycle": str(row.get('מחזור', '')) if pd.notna(row.get('מחזור')) and str(row.get('מחזור')) != 'nan' else '',
                    "entry_date": str(row.get('תאריך כניסה', '')) if pd.notna(row.get('תאריך כניסה')) and str(row.get('תאריך כניסה')) != 'nan' else '',
                    "leave_date": str(row.get('תאריך עזיבה', '')) if pd.notna(row.get('תאריך עזיבה')) and str(row.get('תאריך עזיבה')) != 'nan' else '',
                    "wedding_date": str(row.get('תאריך חתונה', '')) if pd.notna(row.get('תאריך חתונה')) and str(row.get('תאריך חתונה')) != 'nan' else '',
                    "strengthening": str(row.get('חיזוק', '')) if pd.notna(row.get('חיזוק')) and str(row.get('חיזוק')) != 'nan' else '',
                    "is_jerusalem_branch": 0, "id_photo_exists": id_photo_exists_val,
                    "id_photo_path": str(row.get('id_photo_path', '')) if pd.notna(row.get('id_photo_path')) and str(row.get('id_photo_path')) != 'nan' else '',
                    "avatar_path": str(row.get('avatar_path', '')) if pd.notna(row.get('avatar_path')) and str(row.get('avatar_path')) != 'nan' else ''
                })
                success_count += 1
            except Exception: pass
        return jsonify({"status": "success", "imported": success_count})
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/api/templates', methods=['GET'])
def get_templates():
    rows = execute_query("SELECT * FROM document_templates") or []
    return jsonify(rows)

@app.route('/api/templates/save', methods=['POST'])
def save_template():
    data = request.json
    try:
        execute_query('INSERT INTO document_templates (title, content) VALUES (:t, :c)', {"t": data.get('title'), "c": data.get('content')})
    except Exception:
        execute_query('UPDATE document_templates SET content = :c WHERE title = :t', {"t": data.get('title'), "c": data.get('content')})
    return jsonify({"status": "success"})

def fix_hebrew_text(text):
    words = text.split()
    fixed_words = []
    for word in words:
        if any(u'\u0590' <= c <= u'\u05fe' for c in word):
            clean_word = "".join([c for c in word if c.isalnum() or c in ['"', "'", '-', '.']])
            punctuation = "".join([c for c in word if not (c.isalnum() or c in ['"', "'", '-', '.'])])
            fixed_words.append(punctuation + clean_word[::-1])
        else: fixed_words.append(word)
    return " ".join(fixed_words[::-1])

@app.route('/api/students/<int:student_id>/print/<int:template_id>', methods=['GET'])
def generate_pdf(student_id, template_id):
    students = execute_query("SELECT * FROM students WHERE id=:id", {"id": student_id})
    templates = execute_query("SELECT * FROM document_templates WHERE id=:id", {"id": template_id})
    if not students or not templates: return "הנתונים לא נמצאו", 404
    student = students[0]
    template = templates[0]
    
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    bg_path = "blank.jpg"
    if os.path.exists(bg_path): p.drawImage(bg_path, 0, 0, width=width, height=height)
    stamp_path = "stamp.png"
    if os.path.exists(stamp_path): p.drawImage(stamp_path, 75, 160, width=160, height=80, mask='auto')
    
    p.setFont(DEFAULT_FONT, 12)
    p.drawRightString(width - 50, height - 190, fix_hebrew_text('בס"ד'))
    p.drawString(50, height - 190, fix_hebrew_text("ע.ר. 580107613"))
    try:
        today = dates.GregorianDate.today()
        heb_today = today.to_heb()
        date_heb = get_hebrew_date_string(heb_today.day, heb_today.month, heb_today.year)
    except: date_heb = 'כ"ז תמוז תשפ"ו'
    date_greg = datetime.date.today().strftime("%d/%m/%Y")
    p.drawString(50, height - 215, fix_hebrew_text(date_heb))
    p.drawString(50, height - 235, date_greg)
    
    p.setFont(DEFAULT_FONT, 28)
    p.drawCentredString(width / 2.0, height - 320, fix_hebrew_text('אישור תלמיד'))
    
    p.setFont(DEFAULT_FONT, 18)
    id_label = "דרכון מס'" if student['is_passport'] == 1 else "ת.ז."
    text_content = template['content']
    text_content = text_content.replace("{שם_פרטי}", student['first_name'] or '').replace("{שם_משפחה}", student['last_name'] or '').replace("{סוג_זיהוי}", id_label).replace("{תעודת_זהות}", student['tz'] or '')
    y_position = height - 420
    lines = text_content.split('\n')
    for line in lines:
        if line.strip():
            p.drawCentredString(width / 2.0, y_position, fix_hebrew_text(line))
            y_position -= 35
    p.drawString(100, 210, fix_hebrew_text("בברכה,"))
    p.drawString(60, 185, fix_hebrew_text("גרשון אלינסון 056586829"))
    p.showPage()
    p.save()
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name=f"approval_{student['tz']}.pdf", mimetype='application/pdf')

@app.route('/uploads/<path:filename>')
def serve_uploads(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/api/export', methods=['GET', 'POST'])
def export_excel():
    if request.method == 'POST':
        try:
            req_data = request.get_json()
            student_ids = req_data.get('ids', [])
            if student_ids:
                df = pd.read_sql_query("SELECT * FROM students WHERE id IN :ids", engine, params={"ids": tuple(student_ids)})
            else: df = pd.read_sql_query("SELECT * FROM students", engine)
        except Exception: df = pd.read_sql_query("SELECT * FROM students", engine)
    else: df = pd.read_sql_query("SELECT * FROM students", engine)
        
    hebrew_columns = {
        'id': 'מזהה', 'last_name': 'שם משפחה', 'first_name': 'שם פרטי', 'tz': 'תעודת זהות',
        'birth_date_gregorian': 'תאריך לידה לועזי', 'birth_date_hebrew': 'תאריך לידה עברי',
        'address': 'כתובת', 'city': 'עיר', 'phone': 'טלפון', 'additional_phone': "מס' נוסף",
        'neighborhood': 'שכונה', 'status': 'סטטוס', 'father_name': 'שם האב', 'mother_name': 'שם האם',
        'mother_maiden_name': 'לבית', 'previous_institution': 'שם הישיה"ק', 'voicemail': 'תא קולי',
        'telephony_code': 'קוד טלפוניה', 'cycle': 'מחזור', 'entry_date': 'תאריך כניסה', 'leave_date': 'תאריך עזיבה',
        'wedding_date': 'תאריך חתונה', 'strengthening': 'חיזוק', 'is_jerusalem_branch': 'סניף ירושלים', 'id_photo_exists': 'צילום תעודת זהות'
    }
    
    existing_cols = {k: v for k, v in hebrew_columns.items() if k in df.columns}
    df = df[list(existing_cols.keys())]
    df.rename(columns=existing_cols, inplace=True)
    
    output_path = "exported_students.xlsx"
    df.to_excel(output_path, index=False)
    return send_file(output_path, as_attachment=True)

init_db()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)