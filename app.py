import os
from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import pandas as pd
import io

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-this'

# הגדרת נתיב מסד הנתונים (Render / Postgres או SQLite מקומי)
database_url = os.environ.get('DATABASE_URL', 'sqlite:///students.db')
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# הגדרת תיקיית העלאות קבצים
UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- מודלים של מסד הנתונים ---

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)

class Student(db.Model):
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
    is_jerusalem_branch = db.Column(db.Integer, default=0)  # 0=לא, 1=כן, 2=למד בעבר
    entry_date = db.Column(db.String(50))
    leave_date = db.Column(db.String(50))
    wedding_date = db.Column(db.String(50))
    avatar_path = db.Column(db.String(300))
    id_photo_path = db.Column(db.String(300))
    id_photo_exists = db.Column(db.Integer, default=0)

class Template(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100))
    content = db.Column(db.Text)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- נתיבים (API Routes) ---

@app.route('/')
@login_required
def index():
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
    students = Student.query.all()
    result = []
    for s in students:
        result.append({
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
            'id_photo_exists': s.id_photo_exists
        })
    return jsonify(result)

@app.route('/api/students/save', methods=['POST'])
@login_required
def save_student():
    student_id = request.form.get('id')
    if student_id and student_id.strip() != '':
        student = Student.query.get(int(student_id))
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

    # שמירת קבצים שהועלו
    if 'avatar' in request.files:
        avatar = request.files['avatar']
        if avatar and avatar.filename != '':
            fname = secure_filename(avatar.filename)
            path = os.path.join(app.config['UPLOAD_FOLDER'], f"avatar_{fname}")
            avatar.save(path)
            student.avatar_path = f"/static/uploads/avatar_{fname}"

    if 'id_photo' in request.files:
        id_photo = request.files['id_photo']
        if id_photo and id_photo.filename != '':
            fname = secure_filename(id_photo.filename)
            path = os.path.join(app.config['UPLOAD_FOLDER'], f"id_{fname}")
            id_photo.save(path)
            student.id_photo_path = f"/static/uploads/id_{fname}"
            student.id_photo_exists = 1

    db.session.commit()
    return jsonify({'status': 'success', 'id': student.id})

@app.route('/api/students/delete/<int:student_id>', methods=['DELETE'])
@login_required
def delete_student(student_id):
    student = Student.query.get_or_404(student_id)
    db.session.delete(student)
    db.session.commit()
    return jsonify({'status': 'success'})

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
            'שם משפחה': s.last_name,
            'שם פרטי': s.first_name,
            'זיהוי': s.tz,
            'סטטוס': s.status,
            'עיר': s.city,
            'כתובת': s.address,
            'טלפון': s.phone,
            'מחזור': s.cycle,
            'סניף ירושלים': 'כן' if s.is_jerusalem_branch == 1 else ('למד בעבר' if s.is_jerusalem_branch == 2 else 'לא')
        })

    df = pd.DataFrame(data_list)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='תלמידים')
    output.seek(0)

    return send_file(output, download_name="exported_students.xlsx", as_attachment=True)

# --- אתחול בסיס הנתונים ומשתמש ראשי ---

with app.app_context():
    db.create_all()
    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin', password_hash=generate_password_hash('123456'))
        db.session.add(admin)
        db.session.commit()

if __name__ == '__main__':
    app.run(debug=True, port=5000)