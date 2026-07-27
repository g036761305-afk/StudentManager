import os
import sqlite3
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

app = Flask(__name__)
app.secret_key = 'super_secret_local_key_change_if_needed'

DB_NAME = "students.db"
UPLOAD_FOLDER = 'uploads'

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(os.path.join(UPLOAD_FOLDER, 'id_photos'), exist_ok=True)
os.makedirs(os.path.join(UPLOAD_FOLDER, 'avatars'), exist_ok=True)
os.makedirs(os.path.join(UPLOAD_FOLDER, 'batch_photos'), exist_ok=True)

# טעינת גופנים עבריים מתוך תיקיית הפרויקט
FONT_PATH = os.path.join(os.path.dirname(__file__), 'arial.ttf')
if os.path.exists(FONT_PATH):
    pdfmetrics.registerFont(TTFont('David', FONT_PATH))
    pdfmetrics.registerFont(TTFont('David-Bold', FONT_PATH))
else:
    try:
        pdfmetrics.registerFont(TTFont('David', 'C:\\Windows\\Fonts\\arial.ttf'))
        pdfmetrics.registerFont(TTFont('David-Bold', 'C:\\Windows\\Fonts\\arialbd.ttf'))
    except:
        pass

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

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
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        )
    ''')
    
    cursor.execute("SELECT * FROM users WHERE username='מנהל ראשי'")
    if not cursor.fetchone():
        default_hash = generate_password_hash("123456")
        cursor.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", ("מנהל ראשי", default_hash))

    try: cursor.execute("ALTER TABLE students ADD COLUMN entry_date TEXT")
    except sqlite3.OperationalError: pass
    try: cursor.execute("ALTER TABLE students ADD COLUMN wedding_date TEXT")
    except sqlite3.OperationalError: pass
    try: cursor.execute("ALTER TABLE students ADD COLUMN is_jerusalem_branch INTEGER DEFAULT 0")
    except sqlite3.OperationalError: pass
    
    cursor.execute('CREATE TABLE IF NOT EXISTS document_templates (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT UNIQUE, content TEXT)')
    conn.commit()
    conn.close()

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
        
        conn = get_db_connection()
        user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        conn.close()
        
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

    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()

    if not user or not check_password_hash(user['password_hash'], old_pass):
        conn.close()
        return jsonify({"error": "הסיסמה הישנה שגויה"}), 400

    new_hash = generate_password_hash(new_pass)
    conn.execute("UPDATE users SET password_hash = ? WHERE username = ?", (new_hash, username))
    conn.commit()
    conn.close()
    return jsonify({"status": "success", "message": "הסיסמה עודכנה בהצלחה"})

@app.route('/api/add-user', methods=['POST'])
def add_user():
    data = request.json
    new_username = data.get('username', '').strip()
    new_password = data.get('password', '').strip()

    if not new_username or not new_password:
        return jsonify({"error": "יש למלא שם משתמש וסיסמה"}), 400

    conn = get_db_connection()
    try:
        new_hash = generate_password_hash(new_password)
        conn.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (new_username, new_hash))
        conn.commit()
        conn.close()
        return jsonify({"status": "success", "message": f"המשתמש '{new_username}' נוצר בהצלחה"})
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"error": "שם המשתמש כבר קיים במערכת"}), 400

@app.route('/api/users', methods=['GET'])
def get_users():
    conn = get_db_connection()
    users = conn.execute("SELECT id, username FROM users").fetchall()
    conn.close()
    return jsonify([dict(u) for u in users])

@app.route('/api/delete-user/<int:user_id>', methods=['POST', 'DELETE'])
def delete_user(user_id):
    current_username = session.get('username')
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    
    if not user:
        conn.close()
        return jsonify({"error": "משתמש לא נמצא"}), 404
        
    if user['username'] == current_username:
        conn.close()
        return jsonify({"error": "אינך יכול למחוק את המשתמש שמחובר כעת במערכת"}), 400

    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    return jsonify({"status": "success", "message": "המשתמש נמחק בהצלחה"})

def sync_id_photos_from_folder():
    id_photos_dir = os.path.join('uploads', 'id_photos')
    if not os.path.exists(id_photos_dir): return
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE students SET id_photo_exists = 0, id_photo_path = NULL")
    for filename in os.listdir(id_photos_dir):
        if filename.startswith("id_"):
            parts = filename.split('_')
            if len(parts) >= 2:
                tz_extracted = parts[1]
                db_path = f"/uploads/id_photos/{filename}"
                cursor.execute("UPDATE students SET id_photo_exists = 1, id_photo_path = ? WHERE tz = ?", (db_path, tz_extracted))
    conn.commit()
    conn.close()

@app.route('/')
def index():
    return render_template('index.html', username=session.get('username'))

@app.route('/api/students', methods=['GET'])
def get_students():
    sync_id_photos_from_folder()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM students")
    rows = cursor.fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows])

@app.route('/api/students/save', methods=['POST'])
def save_student():
    data = request.form.to_dict()
    conn = get_db_connection()
    cursor = conn.cursor()
    student_id = data.get('id')
    is_passport = int(data.get('is_passport', 0))
    is_jerusalem_branch = int(data.get('is_jerusalem_branch', 0))
    
    current_id_photo_exists = 0
    current_id_photo_path = ''
    current_avatar_path = ''
    
    if student_id:
        existing = cursor.execute("SELECT id_photo_exists, id_photo_path, avatar_path FROM students WHERE id=?", (student_id,)).fetchone()
        if existing:
            current_id_photo_exists = existing['id_photo_exists'] or 0
            current_id_photo_path = existing['id_photo_path'] or ''
            current_avatar_path = existing['avatar_path'] or ''

    id_photo_path = current_id_photo_path
    id_photo_exists = current_id_photo_exists
    
    if 'id_photo' in request.files:
        file = request.files['id_photo']
        if file and file.filename != '':
            filename = secure_filename(f"id_{data.get('tz')}_{file.filename}")
            path = os.path.join(app.config['UPLOAD_FOLDER'], 'id_photos', filename)
            file.save(path)
            id_photo_path = f"/uploads/id_photos/{filename}"
            id_photo_exists = 1

    avatar_path = current_avatar_path
    if 'avatar' in request.files:
        file = request.files['avatar']
        if file and file.filename != '':
            filename = secure_filename(f"avatar_{data.get('tz')}_{file.filename}")
            path = os.path.join(app.config['UPLOAD_FOLDER'], 'avatars', filename)
            file.save(path)
            avatar_path = f"/uploads/avatars/{filename}"

    phone = data.get('phone', '').strip()
    if phone != "" and not phone.startswith('0'): phone = "0" + phone

    additional_phone = data.get('additional_phone', '').strip()
    if additional_phone != "" and not additional_phone.startswith('0'): additional_phone = "0" + additional_phone

    wedding_date = data.get('wedding_date', '').strip()
    leave_date = data.get('leave_date', '').strip()

    if wedding_date and not leave_date:
        leave_date = wedding_date

    params = (
        data.get('last_name'), data.get('first_name'), data.get('tz'), is_passport,
        data.get('passport_country'), data.get('passport_expiry'),
        data.get('birth_date_gregorian'), data.get('birth_date_hebrew'),
        data.get('address'), data.get('city'), phone, additional_phone,
        data.get('neighborhood'), data.get('status'), data.get('father_name'), data.get('mother_name'),
        data.get('mother_maiden_name'), data.get('previous_institution'), data.get('voicemail'),
        data.get('telephony_code'), data.get('cycle'), data.get('entry_date'), leave_date, wedding_date,
        data.get('strengthening'), is_jerusalem_branch, id_photo_exists, id_photo_path, avatar_path
    )

    if student_id:
        cursor.execute('''
            UPDATE students SET 
                last_name=?, first_name=?, tz=?, is_passport=?, passport_country=?, passport_expiry=?,
                birth_date_gregorian=?, birth_date_hebrew=?, address=?, city=?, phone=?, additional_phone=?,
                neighborhood=?, status=?, father_name=?, mother_name=?, mother_maiden_name=?, previous_institution=?,
                voicemail=?, telephony_code=?, cycle=?, entry_date=?, leave_date=?, wedding_date=?, strengthening=?,
                is_jerusalem_branch=?, id_photo_exists=?, id_photo_path=?, avatar_path=?
            WHERE id=?
        ''', params + (student_id,))
    else:
        cursor.execute('''
            INSERT INTO students (
                last_name, first_name, tz, is_passport, passport_country, passport_expiry,
                birth_date_gregorian, birth_date_hebrew, address, city, phone, additional_phone,
                neighborhood, status, father_name, mother_name, mother_maiden_name, previous_institution,
                voicemail, telephony_code, cycle, entry_date, leave_date, wedding_date, strengthening,
                is_jerusalem_branch, id_photo_exists, id_photo_path, avatar_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', params)
    conn.commit()
    conn.close()
    return jsonify({"status": "success"})

@app.route('/api/students/<int:student_id>/delete-avatar', methods=['POST'])
def delete_avatar(student_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        student = cursor.execute("SELECT avatar_path FROM students WHERE id=?", (student_id,)).fetchone()
        if student and student['avatar_path']:
            full_path = student['avatar_path'].lstrip('/')
            if os.path.exists(full_path): os.remove(full_path)
            cursor.execute("UPDATE students SET avatar_path = NULL WHERE id=?", (student_id,))
            conn.commit()
        conn.close()
        return jsonify({"status": "success"})
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/api/students/<int:student_id>/delete-id-photo', methods=['POST'])
def delete_id_photo(student_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        student = cursor.execute("SELECT id_photo_path FROM students WHERE id=?", (student_id,)).fetchone()
        if student and student['id_photo_path']:
            full_path = student['id_photo_path'].lstrip('/')
            if os.path.exists(full_path):
                try: os.remove(full_path)
                except Exception: pass
            cursor.execute("UPDATE students SET id_photo_path = NULL, id_photo_exists = 0 WHERE id=?", (student_id,))
            conn.commit()
        conn.close()
        return jsonify({"status": "success"})
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/api/students/<int:student_id>/delete', methods=['DELETE'])
def delete_student(student_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM students WHERE id=?", (student_id,))
        conn.commit()
        conn.close()
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
        conn = get_db_connection()
        cursor = conn.cursor()
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
                cursor.execute('''
                    INSERT INTO students (
                        last_name, first_name, tz, is_passport, passport_country, passport_expiry,
                        birth_date_gregorian, birth_date_hebrew, address, city, neighborhood,
                        phone, additional_phone, status, father_name, mother_name, mother_maiden_name,
                        previous_institution, voicemail, telephony_code, cycle, entry_date, leave_date, wedding_date, strengthening,
                        is_jerusalem_branch, id_photo_exists, id_photo_path, avatar_path
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    str(row.get('שם משפחה', '')) if pd.notna(row.get('שם משפחה')) else '',
                    str(row.get('שם פרטי', '')) if pd.notna(row.get('שם פרטי')) else '',
                    tz_val, is_pass_val,
                    str(row.get('passport_country', '')) if pd.notna(row.get('passport_country')) and str(row.get('passport_country')) != 'nan' else '',
                    str(row.get('passport_expiry', '')) if pd.notna(row.get('passport_expiry')) and str(row.get('passport_expiry')) != 'nan' else '',
                    str(row.get('תאריך לידה לועזי', ''))[:10] if pd.notna(row.get('תאריך לידה לועזי')) and str(row.get('תאריך לידה לועזי')) != 'nan' else '',
                    str(row.get('תאריך לידה עברי', '')) if pd.notna(row.get('תאריך לידה עברי')) and str(row.get('תאריך לידה עברי')) != 'nan' else '',
                    str(row.get('כתובת', '')) if pd.notna(row.get('כתובת')) and str(row.get('כתובת')) != 'nan' else '',
                    str(row.get('עיר', '')) if pd.notna(row.get('עיר')) and str(row.get('עיר')) != 'nan' else '',
                    str(row.get('שכונה', '')) if pd.notna(row.get('שכונה')) and str(row.get('שכונה')) != 'nan' else '',
                    p_phone, p_add,
                    str(row.get('סטטוס', '')) if pd.notna(row.get('סטטוס')) and str(row.get('סטטוס')) != 'nan' else '',
                    str(row.get('שם האב', '')) if pd.notna(row.get('שם האב')) and str(row.get('שם האם')) != 'nan' else '',
                    str(row.get('שם האם', '')) if pd.notna(row.get('שם האם')) and str(row.get('שם האם')) != 'nan' else '',
                    str(row.get('לבית', '')) if pd.notna(row.get('לבית')) and str(row.get('לבית')) != 'nan' else '',
                    str(row.get('שם הישיה"ק', '')) if pd.notna(row.get('שם הישיה"ק')) and str(row.get('שם הישיה"ק')) != 'nan' else '',
                    str(row.get('תא קולי', '')).split('.')[0] if pd.notna(row.get('תא קולי')) and str(row.get('תא קולי')) != 'nan' else '',
                    str(row.get('קוד טלפוניה', '')).split('.')[0] if pd.notna(row.get('קוד טלפוניה')) and str(row.get('קוד טלפוניה')) != 'nan' else '',
                    str(row.get('מחזור', '')) if pd.notna(row.get('מחזור')) and str(row.get('מחזור')) != 'nan' else '',
                    str(row.get('תאריך כניסה', '')) if pd.notna(row.get('תאריך כניסה')) and str(row.get('תאריך כניסה')) != 'nan' else '',
                    str(row.get('תאריך עזיבה', '')) if pd.notna(row.get('תאריך עזיבה')) and str(row.get('תאריך עזיבה')) != 'nan' else '',
                    str(row.get('תאריך חתונה', '')) if pd.notna(row.get('תאריך חתונה')) and str(row.get('תאריך חתונה')) != 'nan' else '',
                    str(row.get('חיזוק', '')) if pd.notna(row.get('חיזוק')) and str(row.get('חיזוק')) != 'nan' else '',
                    0, id_photo_exists_val,
                    str(row.get('id_photo_path', '')) if pd.notna(row.get('id_photo_path')) and str(row.get('id_photo_path')) != 'nan' else '',
                    str(row.get('avatar_path', '')) if pd.notna(row.get('avatar_path')) and str(row.get('avatar_path')) != 'nan' else ''
                ))
                success_count += 1
            except sqlite3.IntegrityError: pass
        conn.commit()
        conn.close()
        return jsonify({"status": "success", "imported": success_count})
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/api/templates', methods=['GET'])
def get_templates():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM document_templates")
    rows = cursor.fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows])

@app.route('/api/templates/save', methods=['POST'])
def save_template():
    data = request.json
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO document_templates (title, content) VALUES (?, ?) ON CONFLICT(title) DO UPDATE SET content=excluded.content', (data.get('title'), data.get('content')))
    conn.commit()
    conn.close()
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
    conn = get_db_connection()
    student = conn.execute("SELECT * FROM students WHERE id=?", (student_id,)).fetchone()
    template = conn.execute("SELECT * FROM document_templates WHERE id=?", (template_id,)).fetchone()
    conn.close()
    if not student or not template: return "הנתונים לא נמצאו", 404
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    bg_path = "blank.jpg"
    if os.path.exists(bg_path): p.drawImage(bg_path, 0, 0, width=width, height=height)
    stamp_path = "stamp.png"
    if os.path.exists(stamp_path): p.drawImage(stamp_path, 75, 160, width=160, height=80, mask='auto')
    try: p.setFont('David', 12)
    except: p.setFont('Helvetica', 12)
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
    
    try: p.setFont('David-Bold', 28)
    except: p.setFont('Helvetica-Bold', 28)
    p.drawCentredString(width / 2.0, height - 320, fix_hebrew_text('אישור תלמיד'))
    
    try: p.setFont('David', 18)
    except: p.setFont('Helvetica', 18)
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
    conn = get_db_connection()
    if request.method == 'POST':
        try:
            req_data = request.get_json()
            student_ids = req_data.get('ids', [])
            if student_ids:
                placeholders = ','.join('?' for _ in student_ids)
                query = f"SELECT * FROM students WHERE id IN ({placeholders})"
                df = pd.read_sql_query(query, conn, params=student_ids)
            else: df = pd.read_sql_query("SELECT * FROM students", conn)
        except Exception as e: df = pd.read_sql_query("SELECT * FROM students", conn)
    else: df = pd.read_sql_query("SELECT * FROM students", conn)
        
    conn.close()
    
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

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)