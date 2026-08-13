import os
import io
import re
import requests
import threading
from datetime import datetime
import pandas as pd
from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from sqlalchemy import text, inspect

# יבוא ReportLab, BiDi ו-pyluach להפקת קובצי PDF תקינים בעברית
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

try:
    from pyluach import dates
    HAS_PYLUACH = True
except ImportError:
    HAS_PYLUACH = False

try:
    from bidi.algorithm import get_display
    HAS_BIDI = True
except ImportError:
    HAS_BIDI = False

try:
    import cloudinary
    import cloudinary.uploader
    HAS_CLOUDINARY = True
except ImportError:
    HAS_CLOUDINARY = False

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-this'

if HAS_CLOUDINARY and os.environ.get('CLOUDINARY_URL'):
    cloudinary.config(cloudinary_url=os.environ.get('CLOUDINARY_URL'))

CLOUD_RENDER_URL = os.environ.get('CLOUD_RENDER_URL', 'https://student-manager.onrender.com')

if os.environ.get('RENDER') and os.environ.get('DATABASE_URL'):
    database_url = os.environ.get('DATABASE_URL')
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    IS_LOCAL = False
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///students.db'
    IS_LOCAL = True

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- מודלים ---

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)

class Student(db.Model):
    __tablename__ = 'students'
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(100))
    last_name = db.Column(db.String(100))
    tz = db.Column(db.String(50))
    is_passport = db.Column(db.Integer, default=0)
    passport_country = db.Column(db.String(100))
    passport_expiry = db.Column(db.String(50))
    status = db.Column(db.String(50))
    birth_date_gregorian = db.Column(db.String(50))
    birth_date_hebrew = db.Column(db.String(50))
    city = db.Column(db.String(100))
    neighborhood = db.Column(db.String(100))
    address = db.Column(db.String(200))
    phone = db.Column(db.String(50))
    additional_phone = db.Column(db.String(50))
    father_name = db.Column(db.String(100))
    mother_name = db.Column(db.String(100))
    mother_maiden_name = db.Column(db.String(100))
    previous_institution = db.Column(db.String(100))
    cycle = db.Column(db.String(50))
    voicemail = db.Column(db.String(50))
    telephony_code = db.Column(db.String(50))
    strengthening = db.Column(db.String(100))
    is_jerusalem_branch = db.Column(db.Integer, default=0)
    entry_date = db.Column(db.String(50))
    leave_date = db.Column(db.String(50))
    wedding_date = db.Column(db.String(50))
    avatar_path = db.Column(db.String(500))
    id_photo_path = db.Column(db.String(500))
    id_photo_exists = db.Column(db.Integer, default=0)
    updated_at = db.Column(db.String(50), default=lambda: datetime.now().isoformat())
    is_synced = db.Column(db.Integer, default=1)

class Template(db.Model):
    __tablename__ = 'document_templates'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100))
    content = db.Column(db.Text)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

def db_auto_migrate():
    try:
        inspector = inspect(db.engine)
        if 'students' not in inspector.get_table_names():
            return
        
        existing_columns = [col['name'] for col in inspector.get_columns('students')]
        
        required_columns = {
            'is_passport': 'INTEGER DEFAULT 0',
            'passport_country': 'VARCHAR(100)',
            'passport_expiry': 'VARCHAR(50)',
            'status': 'VARCHAR(50)',
            'birth_date_gregorian': 'VARCHAR(50)',
            'birth_date_hebrew': 'VARCHAR(50)',
            'city': 'VARCHAR(100)',
            'neighborhood': 'VARCHAR(100)',
            'address': 'VARCHAR(200)',
            'phone': 'VARCHAR(50)',
            'additional_phone': 'VARCHAR(50)',
            'father_name': 'VARCHAR(100)',
            'mother_name': 'VARCHAR(100)',
            'mother_maiden_name': 'VARCHAR(100)',
            'previous_institution': 'VARCHAR(100)',
            'cycle': 'VARCHAR(50)',
            'voicemail': 'VARCHAR(50)',
            'telephony_code': 'VARCHAR(50)',
            'strengthening': 'VARCHAR(100)',
            'is_jerusalem_branch': 'INTEGER DEFAULT 0',
            'entry_date': 'VARCHAR(50)',
            'leave_date': 'VARCHAR(50)',
            'wedding_date': 'VARCHAR(50)',
            'avatar_path': 'VARCHAR(500)',
            'id_photo_path': 'VARCHAR(500)',
            'id_photo_exists': 'INTEGER DEFAULT 0',
            'updated_at': 'VARCHAR(50)',
            'is_synced': 'INTEGER DEFAULT 1'
        }
        
        with db.engine.begin() as conn:
            for col_name, col_type in required_columns.items():
                if col_name not in existing_columns:
                    try:
                        conn.execute(text(f"ALTER TABLE students ADD COLUMN {col_name} {col_type}"))
                    except Exception as ex:
                        print(f"Col {col_name} alter note: {ex}")
    except Exception as e:
        print(f"Migration error: {e}")

def push_unsynced_to_cloud():
    if not IS_LOCAL:
        return
    try:
        with app.app_context():
            unsynced_students = Student.query.filter_by(is_synced=0).all()
            if not unsynced_students:
                return

            payload = []
            for s in unsynced_students:
                payload.append({
                    'id': s.id,
                    'first_name': s.first_name,
                    'last_name': s.last_name,
                    'tz': s.tz,
                    'is_passport': s.is_passport,
                    'passport_country': s.passport_country,
                    'passport_expiry': s.passport_expiry,
                    'status': s.status,
                    'birth_date_gregorian': s.birth_date_gregorian,
                    'birth_date_hebrew': s.birth_date_hebrew,
                    'city': s.city,
                    'neighborhood': s.neighborhood,
                    'address': s.address,
                    'phone': s.phone,
                    'additional_phone': s.additional_phone,
                    'father_name': s.father_name,
                    'mother_name': s.mother_name,
                    'mother_maiden_name': s.mother_maiden_name,
                    'previous_institution': s.previous_institution,
                    'cycle': s.cycle,
                    'voicemail': s.voicemail,
                    'telephony_code': s.telephony_code,
                    'strengthening': s.strengthening,
                    'is_jerusalem_branch': s.is_jerusalem_branch,
                    'entry_date': s.entry_date,
                    'leave_date': s.leave_date,
                    'wedding_date': s.wedding_date,
                    'avatar_path': s.avatar_path,
                    'id_photo_path': s.id_photo_path,
                    'id_photo_exists': s.id_photo_exists,
                    'updated_at': s.updated_at
                })

            res = requests.post(f"{CLOUD_RENDER_URL}/api/sync-batch", json=payload, timeout=5)
            if res.status_code == 200:
                for s in unsynced_students:
                    s.is_synced = 1
                db.session.commit()
    except Exception as e:
        pass

def trigger_background_sync():
    threading.Thread(target=push_unsynced_to_cloud, daemon=True).start()

# --- נתיבים להגשת תמונות ---

@app.route('/uploads/avatars/<path:filename>')
def serve_avatar(filename):
    directories = [
        os.path.join(app.root_path, 'static', 'uploads'),
        os.path.join(app.root_path, 'uploads', 'avatars'),
        os.path.join(app.root_path, 'uploads')
    ]
    for directory in directories:
        if os.path.exists(os.path.join(directory, filename)):
            return send_from_directory(directory, filename)
    return send_from_directory(os.path.join(app.root_path, 'static', 'uploads'), filename)

@app.route('/uploads/<path:filename>')
def serve_uploads(filename):
    directories = [
        os.path.join(app.root_path, 'static', 'uploads'),
        os.path.join(app.root_path, 'uploads')
    ]
    for directory in directories:
        if os.path.exists(os.path.join(directory, filename)):
            return send_from_directory(directory, filename)
    return send_from_directory(os.path.join(app.root_path, 'static', 'uploads'), filename)

# --- נתיבי המערכת ---

@app.route('/')
@login_required
def index():
    if IS_LOCAL:
        trigger_background_sync()
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('index'))
        return render_template('login.html', error='שם משתמש או סיסמה שגויים')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/api/students', methods=['GET'])
@login_required
def get_students():
    try:
        students = Student.query.all()
        result = []
        for s in students:
            result.append({
                'id': s.id,
                'first_name': s.first_name,
                'last_name': s.last_name,
                'tz': s.tz,
                'is_passport': s.is_passport or 0,
                'passport_country': s.passport_country,
                'passport_expiry': s.passport_expiry,
                'status': s.status,
                'birth_date_gregorian': s.birth_date_gregorian,
                'birth_date_hebrew': s.birth_date_hebrew,
                'city': s.city,
                'neighborhood': s.neighborhood,
                'address': s.address,
                'phone': s.phone,
                'additional_phone': s.additional_phone,
                'father_name': s.father_name,
                'mother_name': s.mother_name,
                'mother_maiden_name': s.mother_maiden_name,
                'previous_institution': s.previous_institution,
                'cycle': s.cycle,
                'voicemail': s.voicemail,
                'telephony_code': s.telephony_code,
                'strengthening': s.strengthening,
                'is_jerusalem_branch': s.is_jerusalem_branch if s.is_jerusalem_branch is not None else 0,
                'entry_date': s.entry_date,
                'leave_date': s.leave_date,
                'wedding_date': s.wedding_date,
                'avatar_path': s.avatar_path,
                'id_photo_path': s.id_photo_path,
                'id_photo_exists': s.id_photo_exists or 0
            })
        return jsonify(result)
    except Exception as e:
        print("Error fetching students:", e)
        return jsonify([]), 500

@app.route('/api/students/save', methods=['POST'])
@login_required
def save_student():
    student_id = request.form.get('id')
    if student_id and student_id.strip() != '':
        student = db.session.get(Student, int(student_id))
    else:
        student = Student()
        db.session.add(student)

    student.first_name = request.form.get('first_name')
    student.last_name = request.form.get('last_name')
    student.tz = request.form.get('tz')
    student.is_passport = int(request.form.get('is_passport', 0))
    student.passport_country = request.form.get('passport_country')
    student.passport_expiry = request.form.get('passport_expiry')
    student.status = request.form.get('status')
    student.birth_date_gregorian = request.form.get('birth_date_gregorian')
    student.birth_date_hebrew = request.form.get('birth_date_hebrew')
    student.city = request.form.get('city')
    student.neighborhood = request.form.get('neighborhood')
    student.address = request.form.get('address')
    student.phone = request.form.get('phone')
    student.additional_phone = request.form.get('additional_phone')
    student.father_name = request.form.get('father_name')
    student.mother_name = request.form.get('mother_name')
    student.mother_maiden_name = request.form.get('mother_maiden_name')
    student.previous_institution = request.form.get('previous_institution')
    student.cycle = request.form.get('cycle')
    student.voicemail = request.form.get('voicemail')
    student.telephony_code = request.form.get('telephony_code')
    student.strengthening = request.form.get('strengthening')
    student.is_jerusalem_branch = int(request.form.get('is_jerusalem_branch', 0))
    student.entry_date = request.form.get('entry_date')
    student.leave_date = request.form.get('leave_date')
    student.wedding_date = request.form.get('wedding_date')
    student.updated_at = datetime.now().isoformat()
    student.is_synced = 0

    if 'avatar' in request.files:
        avatar = request.files['avatar']
        if avatar and avatar.filename != '':
            fname = secure_filename(avatar.filename)
            local_path = os.path.join(app.config['UPLOAD_FOLDER'], f"avatar_{fname}")
            avatar.save(local_path)
            student.avatar_path = f"/static/uploads/avatar_{fname}"

            if HAS_CLOUDINARY and os.environ.get('CLOUDINARY_URL'):
                try:
                    upload_res = cloudinary.uploader.upload(local_path, folder="student_avatars", resource_type="auto")
                    student.avatar_path = upload_res.get('secure_url', student.avatar_path)
                except Exception as ex:
                    print("Cloudinary avatar upload skipped/failed:", ex)

    if 'id_photo' in request.files:
        id_photo = request.files['id_photo']
        if id_photo and id_photo.filename != '':
            fname = secure_filename(id_photo.filename)
            local_path = os.path.join(app.config['UPLOAD_FOLDER'], f"id_{fname}")
            id_photo.save(local_path)
            student.id_photo_path = f"/static/uploads/id_{fname}"
            student.id_photo_exists = 1

            if HAS_CLOUDINARY and os.environ.get('CLOUDINARY_URL'):
                try:
                    upload_res = cloudinary.uploader.upload(local_path, folder="student_id_photos", resource_type="auto")
                    student.id_photo_path = upload_res.get('secure_url', student.id_photo_path)
                except Exception as ex:
                    print("Cloudinary ID photo upload skipped/failed:", ex)

    db.session.commit()

    if IS_LOCAL:
        trigger_background_sync()

    return jsonify({'status': 'success', 'id': student.id})

# --- ייבוא אקסל ---

@app.route('/api/import-excel', methods=['POST'])
@login_required
def import_excel():
    file = request.files.get('file') or request.files.get('excel_file')
    if not file or file.filename == '':
        return jsonify({'error': 'לא נבחר קובץ'}), 400

    try:
        df = pd.read_excel(file)
        added = 0
        updated = 0

        with db.session.no_autoflush:
            for index, row in df.iterrows():
                s_id = row.get('מזהה') or row.get('id')
                tz = str(row.get('זיהוי') or row.get('תעודת זהות') or row.get('ת"ז') or '').strip()
                if tz.endswith('.0'):
                    tz = tz[:-2]

                first_name = str(row.get('שם פרטי') or '').strip()
                last_name = str(row.get('שם משפחה') or '').strip()
                city = str(row.get('עיר') or '').strip()
                address = str(row.get('כתובת') or '').strip()
                phone = str(row.get('טלפון') or '').strip()
                if phone.endswith('.0'):
                    phone = phone[:-2]

                cycle = str(row.get('מחזור') or '').strip()
                status = str(row.get('סטטוס') or '').strip()

                # קריאת שדות תא קולי וקוד טלפוניה
                voicemail = str(row.get('תא קולי') or row.get('voicemail') or '').strip()
                telephony_code = str(row.get('קוד טלפוניה') or row.get('telephony_code') or '').strip()
                if voicemail.endswith('.0'): voicemail = voicemail[:-2]
                if telephony_code.endswith('.0'): telephony_code = telephony_code[:-2]

                if not first_name and not last_name and not tz:
                    continue

                student = None
                if s_id and str(s_id).isdigit():
                    student = db.session.get(Student, int(s_id))

                if not student and tz:
                    student = Student.query.filter_by(tz=tz).first()

                if not student:
                    student = Student()
                    db.session.add(student)
                    added += 1
                else:
                    updated += 1

                if first_name: student.first_name = first_name
                if last_name: student.last_name = last_name
                
                if tz:
                    existing_tz_owner = Student.query.filter(Student.tz == tz, Student.id != student.id).first()
                    if not existing_tz_owner:
                        student.tz = tz

                if city: student.city = city
                if address: student.address = address
                if phone: student.phone = phone
                if cycle: student.cycle = cycle
                if status: student.status = status
                if voicemail: student.voicemail = voicemail
                if telephony_code: student.telephony_code = telephony_code

                student.updated_at = datetime.now().isoformat()
                student.is_synced = 0

        db.session.commit()

        if IS_LOCAL:
            trigger_background_sync()

        return jsonify({'status': 'success', 'added': added, 'updated': updated})

    except Exception as e:
        db.session.rollback()
        print("Import Excel Error:", str(e))
        return jsonify({'error': str(e)}), 500

@app.route('/api/sync-batch', methods=['POST'])
def sync_batch():
    students_data = request.get_json() or []
    for item in students_data:
        s = db.session.get(Student, item.get('id'))
        if not s:
            s = Student(id=item.get('id'))
            db.session.add(s)

        for key, val in item.items():
            if hasattr(s, key) and key not in ['id']:
                setattr(s, key, val)
        s.is_synced = 1

    db.session.commit()
    return jsonify({'status': 'success', 'synced_count': len(students_data)})

@app.route('/api/students/delete/<int:student_id>', methods=['DELETE'])
@login_required
def delete_student(student_id):
    student = db.session.get(Student, student_id)
    if student:
        db.session.delete(student)
        db.session.commit()
        if IS_LOCAL:
            trigger_background_sync()
    return jsonify({'status': 'success'})

# --- ניהול והנפקת אישורים / תבניות ---

def get_template_replacements(student):
    return {
        '{first_name}': student.first_name or '',
        '{שם_פרטי}': student.first_name or '',
        '{שם פרטי}': student.first_name or '',
        '{last_name}': student.last_name or '',
        '{שם_משפחה}': student.last_name or '',
        '{שם משפחה}': student.last_name or '',
        '{tz}': student.tz or '',
        '{תעודת_זהות}': student.tz or '',
        '{תעודת זהות}': student.tz or '',
        '{זיהוי}': student.tz or '',
        '{סוג_זיהוי}': 'דרכון' if student.is_passport == 1 else 'ת"ז',
        '{סוג זיהוי}': 'דרכון' if student.is_passport == 1 else 'ת"ז',
        '{city}': student.city or '',
        '{עיר}': student.city or '',
        '{address}': student.address or '',
        '{כתובת}': student.address or '',
        '{phone}': student.phone or '',
        '{טלפון}': student.phone or '',
        '{cycle}': student.cycle or '',
        '{מחזור}': student.cycle or '',
        '{voicemail}': student.voicemail or '',
        '{תא_קולי}': student.voicemail or '',
        '{תא קולי}': student.voicemail or '',
        '{telephony_code}': student.telephony_code or '',
        '{קוד_טלפוניה}': student.telephony_code or '',
        '{קוד טלפוניה}': student.telephony_code or '',
        '{תאריך}': datetime.now().strftime('%d/%m/%Y')
    }

def format_bidi(text_str):
    if not text_str:
        return ""
    if HAS_BIDI:
        return get_display(str(text_str))
    words = str(text_str).split(' ')
    fixed = []
    for w in words:
        if re.search(r'[\u0590-\u05FF]', w):
            fixed.append(w[::-1])
        else:
            fixed.append(w)
    return ' '.join(fixed[::-1])

@app.route('/api/templates', methods=['GET'])
@login_required
def get_templates():
    templates = Template.query.all()
    return jsonify([{'id': t.id, 'title': t.title, 'content': t.content} for t in templates])

@app.route('/api/templates/save', methods=['POST'])
@login_required
def save_template():
    data = request.get_json() or {}
    title = data.get('title')
    content = data.get('content')
    
    template = Template.query.filter_by(title=title).first()
    if not template:
        template = Template(title=title)
        db.session.add(template)
    
    template.content = content
    db.session.commit()
    return jsonify({'status': 'success'})

@app.route('/api/generate-document', methods=['POST'])
@login_required
def generate_document():
    data = request.get_json() or {}
    student_id = data.get('student_id')
    template_id = data.get('template_id')

    student = db.session.get(Student, int(student_id)) if student_id else None
    template = db.session.get(Template, int(template_id)) if template_id else None

    if not student or not template:
        return jsonify({'error': 'תלמיד או תבנית לא נמצאו'}), 404

    content = template.content or ''
    for key, val in get_template_replacements(student).items():
        content = content.replace(key, str(val))

    return jsonify({
        'status': 'success',
        'title': template.title,
        'content': content
    })

# --- הנפקת אישור והורדת קובץ PDF מותאם ומדויק ---

@app.route('/api/students/<int:student_id>/print/<int:template_id>', methods=['GET'])
@login_required
def print_student_certificate(student_id, template_id):
    student = db.session.get(Student, student_id)
    template = db.session.get(Template, template_id)

    if not student or not template:
        return "תלמיד או תבנית לא נמצאו", 404

    content = template.content or ''
    for key, val in get_template_replacements(student).items():
        content = content.replace(key, str(val))

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4  # 595.27 x 841.89 pt

    # 1. חיפוש גמיש של תמונת נייר המכתבים
    possible_letterhead_names = [
        'letterhead.png', 'letterhead.PNG', 'Letterhead.png', 'Letterhead.PNG',
        'letterhead.jpg', 'letterhead.JPG', 'letterhead.jpeg', 'Letterhead.jpeg'
    ]
    
    letterhead_found_path = None
    for name in possible_letterhead_names:
        for folder in [os.path.join(app.root_path, 'static'), os.path.join(app.root_path, 'static', 'uploads'), app.root_path]:
            check_p = os.path.join(folder, name)
            if os.path.exists(check_p):
                letterhead_found_path = check_p
                break
        if letterhead_found_path:
            break

    has_letterhead = False
    if letterhead_found_path:
        c.drawImage(letterhead_found_path, 0, 0, width=width, height=height)
        has_letterhead = True

    # 2. טעינת גופן תואם עברית
    font_name = 'Helvetica'
    font_bold_name = 'Helvetica-Bold'
    font_paths = [
        os.path.join(app.root_path, 'static', 'Arial.ttf'),
        os.path.join(app.root_path, 'static', 'arial.ttf'),
        'C:\\Windows\\Fonts\\arial.ttf',
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        '/usr/share/fonts/truetype/freefont/FreeSans.ttf'
    ]
    for fp in font_paths:
        if os.path.exists(fp):
            try:
                pdfmetrics.registerFont(TTFont('HebrewFont', fp))
                font_name = 'HebrewFont'
                font_bold_name = 'HebrewFont'
                break
            except Exception as ex:
                print("Font registration error:", ex)

    bold_font_paths = [
        os.path.join(app.root_path, 'static', 'Arial-Bold.ttf'),
        'C:\\Windows\\Fonts\\arialbd.ttf',
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
    ]
    for bfp in bold_font_paths:
        if os.path.exists(bfp):
            try:
                pdfmetrics.registerFont(TTFont('HebrewFontBold', bfp))
                font_bold_name = 'HebrewFontBold'
                break
            except Exception:
                pass

    def draw_text(x, y, text_str, font_size=12, align='right', is_bold=False):
        f_use = font_bold_name if is_bold else font_name
        c.setFont(f_use, font_size)
        txt = format_bidi(text_str)
        if align == 'center':
            c.drawCentredString(x, y, txt)
        elif align == 'left':
            c.drawString(x, y, txt)
        else:
            c.drawRightString(x, y, txt)

    # 3. מילת בס"ד בצד ימין למעלה
    draw_text(width - 60, height - 170, 'בס"ד', font_size=11, align='right')

    # 4. תאריכים בצד שמאל למעלה (לועזי + עברי)
    date_str = datetime.now().strftime('%d/%m/%Y')
    hebrew_date_str = ''
    if HAS_PYLUACH:
        try:
            h_obj = dates.HebrewDate.today()
            hebrew_date_str = h_obj.hebrew_date_string(hebrew=True)
        except Exception as ex:
            print("Hebrew date calculation error:", ex)

    draw_text(110, height - 170, f'תאריך: {date_str}', font_size=11, align='left')
    if hebrew_date_str:
        draw_text(110, height - 188, f'תאריך עברי: {hebrew_date_str}', font_size=11, align='left')

    if not has_letterhead:
        draw_text(width / 2, height - 50, 'ע.ר. 580107613', font_size=10, align='center')

    # 5. כותרת האישור
    draw_text(width / 2, height - 260, template.title or 'אישור תלמיד', font_size=24, align='center', is_bold=True)

    # 6. גוף האישור (ממורכז במרכז הדף)
    y_pos = height - 320
    for line in content.split('\n'):
        line_clean = line.strip()
        if line_clean:
            draw_text(width / 2, y_pos, line_clean, font_size=15, align='center')
            y_pos -= 32

    # 7. חתימה וחותמת בצד שמאל בתחתית
    y_footer = max(y_pos - 40, 200)
    draw_text(180, y_footer, 'בברכה,', font_size=14, align='center')
    draw_text(180, y_footer - 22, 'גרשון אלינסון 056586829', font_size=13, align='center')

    possible_stamp_names = [
        'stamp.png', 'stamp.PNG', 'signature.png', 'signature.PNG',
        'stamp.jpg', 'signature.jpg', 'Stamp.png', 'Signature.png'
    ]
    stamp_found_path = None
    for name in possible_stamp_names:
        for folder in [os.path.join(app.root_path, 'static'), os.path.join(app.root_path, 'static', 'uploads'), app.root_path]:
            check_p = os.path.join(folder, name)
            if os.path.exists(check_p):
                stamp_found_path = check_p
                break
        if stamp_found_path:
            break

    if stamp_found_path:
        c.drawImage(stamp_found_path, 110, y_footer - 95, width=140, height=70, mask='auto')

    c.showPage()
    c.save()

    buffer.seek(0)
    filename = f"certificate_{student.tz or student_id}.pdf"

    return send_file(
        buffer,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=filename
    )

# --- ייצוא מלא לאקסל ---

@app.route('/api/export', methods=['GET', 'POST'])
@login_required
def export_excel():
    if request.method == 'POST':
        data = request.get_json() or {}
        ids = data.get('ids', [])
        if ids:
            students = Student.query.filter(Student.id.in_(ids)).all()
        else:
            students = Student.query.all()
    else:
        students = Student.query.all()

    data_list = []
    for s in students:
        data_list.append({
            'מזהה': s.id,
            'שם פרטי': s.first_name,
            'שם משפחה': s.last_name,
            'זיהוי': s.tz,
            'האם דרכון': 'כן' if s.is_passport == 1 else 'לא',
            'מדינת דרכון': s.passport_country,
            'תוקף דרכון': s.passport_expiry,
            'סטטוס': s.status,
            'תאריך לידה לועזי': s.birth_date_gregorian,
            'תאריך לידה עברי': s.birth_date_hebrew,
            'עיר': s.city,
            'שכונה': s.neighborhood,
            'כתובת': s.address,
            'טלפון': s.phone,
            'טלפון נוסף': s.additional_phone,
            'שם האב': s.father_name,
            'שם האם': s.mother_name,
            'שם משפחה קודם של האם': s.mother_maiden_name,
            'מוסד קודם': s.previous_institution,
            'מחזור': s.cycle,
            'תא קולי': s.voicemail,
            'קוד טלפוניה': s.telephony_code,
            'חיזוק': s.strengthening,
            'סניף ירושלים': 'כן' if s.is_jerusalem_branch == 1 else ('למד בעבר' if s.is_jerusalem_branch == 2 else 'לא'),
            'תאריך כניסה': s.entry_date,
            'תאריך עזיבה': s.leave_date,
            'תאריך חתונה': s.wedding_date,
            'נתיב תמונת פרופיל': s.avatar_path,
            'נתיב צילום ת"ז': s.id_photo_path
        })

    df = pd.DataFrame(data_list)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='תלמידים')
    output.seek(0)

    return send_file(output, download_name="exported_students.xlsx", as_attachment=True)

@app.route('/api/download-template', methods=['GET'])
@login_required
def download_template():
    df = pd.DataFrame([{
        'שם פרטי': 'ישראל', 'שם משפחה': 'ישראלי', 'תעודת זהות': '123456789',
        'עיר': 'ירושלים', 'טלפון': '0501234567', 'מחזור': 'א', 'סטטוס': 'רווק',
        'תא קולי': '123', 'קוד טלפוניה': '456'
    }])
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='תבנית לייבוא')
    output.seek(0)
    return send_file(output, download_name="import_template.xlsx", as_attachment=True)

@app.route('/api/users', methods=['GET'])
@login_required
def get_users():
    users = User.query.all()
    return jsonify([{'id': u.id, 'username': u.username} for u in users])

@app.route('/api/add-user', methods=['POST'])
@login_required
def add_user():
    data = request.get_json() or {}
    username = data.get('username')
    password = data.get('password')
    if User.query.filter_by(username=username).first():
        return jsonify({'error': 'User exists'}), 400
    user = User(username=username, password_hash=generate_password_hash(password))
    db.session.add(user)
    db.session.commit()
    return jsonify({'status': 'success'})

@app.route('/api/delete-user/<int:user_id>', methods=['DELETE'])
@login_required
def delete_user(user_id):
    user = db.session.get(User, user_id)
    if user and user.username != 'admin':
        db.session.delete(user)
        db.session.commit()
    return jsonify({'status': 'success'})

@app.route('/api/change-password', methods=['POST'])
@login_required
def change_password():
    data = request.get_json() or {}
    old_pass = data.get('old_password')
    new_pass = data.get('new_password')
    if check_password_hash(current_user.password_hash, old_pass):
        current_user.password_hash = generate_password_hash(new_pass)
        db.session.commit()
        return jsonify({'status': 'success'})
    return jsonify({'error': 'Wrong old password'}), 400

# --- אתחול בסיס הנתונים ---

with app.app_context():
    db.create_all()
    db_auto_migrate()
    
    admin = User.query.filter_by(username='admin').first()
    if not admin:
        admin = User(username='admin', password_hash=generate_password_hash('123456'))
        db.session.add(admin)
    else:
        admin.password_hash = generate_password_hash('123456')
        
    if not Template.query.first():
        db.session.add(Template(title="אישור לימודים", content="הרינו לאשר כי {first_name} {last_name} לומד במוסדנו."))
    
    db.session.commit()

if __name__ == '__main__':
    app.run(debug=True, port=5000)