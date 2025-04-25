from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from werkzeug.security import check_password_hash, generate_password_hash
from functools import wraps
from flask_migrate import Migrate
from flask_login import LoginManager, UserMixin, login_required
from extensions import db  
import barcode
from barcode.writer import ImageWriter
import os
from datetime import datetime
from sqlalchemy import and_, func


app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///attendance.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/barcodes'

db.init_app(app)  # ← important!
migrate = Migrate(app, db)

from models import User, Course, Attendance , Excuse 




with app.app_context():
    db.create_all()

# Login required decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        email = request.form['email']
        role = request.form['role']
        university_id = request.form['university_id']
        
        # Get selected courses
        selected_courses = request.form.getlist('courses')
        
        # Check if username already exists
        if User.query.filter_by(username=username).first():
            flash('Username already exists')
            return redirect(url_for('register'))
        
        # Create new user with proper password hashing
        hashed_password = generate_password_hash(password)
        new_user = User(
            username=username,
            password=hashed_password,
            email=email,
            role=role,
            university_id=university_id
        )
        
        db.session.add(new_user)
        db.session.commit()  # Commit to get the user ID
        
        # Handle course assignments based on role
        if role == 'student':
            # For students, enroll them in selected courses
            for course_code in selected_courses:
                course = Course.query.filter_by(code=course_code).first()
                if course:
                    new_user.enrolled_courses.append(course)
        elif role == 'doctor':
            # For doctors, assign them as course instructors
            for course_code in selected_courses:
                course = Course.query.filter_by(code=course_code).first()
                if course:
                    course.doctor_id = new_user.id
        
        db.session.commit()
        
        flash('Registration successful! Please login.')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user = User.query.filter_by(username=username).first()
        print(f"Login attempt - Username: {username}")  # Debug print
        print(f"User found in database: {user is not None}")  # Debug print
        
        if user:
            print(f"Checking password hash: {user.password}")  # Debug print
            if check_password_hash(user.password, password):
                session['user_id'] = user.id
                session['role'] = user.role
                
                if user.role == 'student':
                    return redirect(url_for('student_home'))
                elif user.role == 'doctor':
                    return redirect(url_for('doctor'))
                elif user.role == 'admin':
                    return redirect(url_for('admin'))
            else:
                print("Password check failed")  # Debug print
        
        flash('Invalid username or password')
    return render_template('login.html')

@app.route('/student')
@login_required
def student_home():
    if session.get('role') != 'student':
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    return render_template('student_dashboard.html', 
                         username=user.username,
                         enrolled_courses=user.enrolled_courses)

@app.route('/logout')
def logout():
    # Clear the session
    session.clear()
    return redirect(url_for('login'))

# Add this to initialize the courses
def init_courses():
    courses = [
        {'code': 'CPIS-382', 'name': 'CPIS 382'},
        {'code': 'CPIS-499', 'name': 'CPIS 499'},
        {'code': 'CPIS-320', 'name': 'CPIS 320'}
    ]
    
    for course_data in courses:
        if not Course.query.filter_by(code=course_data['code']).first():
            course = Course(code=course_data['code'], name=course_data['name'])
            db.session.add(course)
    
    db.session.commit()

# Add this to your app initialization
with app.app_context():
    db.create_all()
    init_courses()

# Make sure the upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

@app.route('/get_barcode')
@login_required
def get_barcode():
    user = User.query.get(session['user_id'])
    if not user:
        return jsonify({'error': 'User not found'}), 404

    # Generate barcode from university ID
    barcode_class = barcode.get_barcode_class('code128')
    barcode_filename = f"barcode_{user.university_id}"
    
    # Generate barcode image
    full_path = os.path.join(app.config['UPLOAD_FOLDER'], barcode_filename)
    barcode_class(user.university_id, writer=ImageWriter()).save(full_path)
    
    # Return the URL to the generated barcode
    barcode_url = url_for('static', filename=f'barcodes/barcode_{user.university_id}.png')
    
    return jsonify({
        'barcode_url': barcode_url,
        'university_id': user.university_id
    })

@app.route('/get_attendance_history')
@login_required
def get_attendance_history():
    user = User.query.get(session['user_id'])
    attendance_data = {}
    
    for course in user.enrolled_courses:
        attendance_records = Attendance.query.filter_by(
            student_id=user.id,
            course_id=course.id
        ).order_by(Attendance.date.desc(), Attendance.lecture_number).all()
        
        attendance_data[course.code] = [{
            'date': record.date.isoformat(),
            'lecture_number': record.lecture_number,
            'status': record.status
        } for record in attendance_records]
    
    return jsonify(attendance_data)

@app.route('/get_teacher_courses')
@login_required
def get_teacher_courses():
    user = User.query.get(session['user_id'])
    return jsonify({
        'courses': [{
            'id': course.id,
            'code': course.code
        } for course in user.taught_courses]
    })

@app.route('/get_course_students/<int:course_id>')
def get_course_students(course_id):
    if session.get('role') != 'doctor':
        return jsonify({'error': 'Unauthorized'}), 403
        
    course = Course.query.get_or_404(course_id)
    students = []
    for student in course.students:
        students.append({
            'id': student.id,
            'username': student.username,
            'university_id': student.university_id
        })
    
    return jsonify({'students': students})

@app.route('/mark_attendance')
def mark_attendance_page():
    if session.get('role') != 'doctor':
        return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    courses = Course.query.filter_by(doctor_id=user.id).all()
    return render_template('mark_attendance.html', courses=courses)

@app.route('/mark_attendance', methods=['POST'])
def mark_attendance():
    if session.get('role') != 'doctor':
        return jsonify({'error': 'Unauthorized'}), 403

    data = request.json
    course_id = data.get('course_id')
    lecture_number = data.get('lecture_number')
    current_date = datetime.now().date()

    attendance_list = data.get('attendance', [])  

    for entry in attendance_list:
        student_id = int(entry['student_id'])
        status = entry['status']  

        

        existing_record = Attendance.query.filter(
            and_(
                Attendance.student_id == student_id,
                Attendance.course_id == course_id,
                Attendance.lecture_number == lecture_number,
                func.date(Attendance.date) == current_date
            )
        ).first()


        if existing_record:
            existing_record.status = status
        else:
            new_record = Attendance(
                student_id=student_id,
                course_id=course_id,
                lecture_number=lecture_number,
                date=current_date,
                status=status
            )
            db.session.add(new_record)

    try:
        db.session.commit()
        return jsonify({'message': 'Attendance marked successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Error marking attendance: {str(e)}'}), 500

@app.route('/admin_dashboard')
@login_required
def admin():
    if session.get('role') != 'admin':
        return redirect(url_for('login'))
    
    doctors = User.query.filter_by(role='doctor').all()
    total_students = User.query.filter_by(role='student').count()
    total_doctors = User.query.filter_by(role='doctor').count()
    total_courses = Course.query.count()
    
    attendance_records = Attendance.query.all()
    total_records = len(attendance_records)
    present_count = sum(1 for record in attendance_records if record.status in ['present', 'late'])
    absent_count = total_records - present_count
    overall_attendance = round((present_count / total_records * 100) if total_records > 0 else 0, 1)
    
    courses = Course.query.all()
    course_labels = []
    course_attendance_rates = []
    
    for course in courses:
        course_records = Attendance.query.filter_by(course_id=course.id).all()
        if course_records:
            course_present = sum(1 for r in course_records if r.status == 'present')
            attendance_rate = round((course_present / len(course_records) * 100), 1)
            course_labels.append(course.code)
            course_attendance_rates.append(attendance_rate)
    
    return render_template('admin_dashboard.html',
                         doctors=doctors,
                         total_students=total_students,
                         total_doctors=total_doctors,
                         total_courses=total_courses,
                         overall_attendance=overall_attendance,
                         present_count=present_count,
                         absent_count=absent_count,
                         course_labels=course_labels,
                         course_attendance_rates=course_attendance_rates)

@app.route('/doctor')
def doctor():
    if session.get('role') != 'doctor':
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    # Get courses where this doctor is the instructor
    courses = Course.query.filter_by(doctor_id=user.id).all()
    
    return render_template('doctor_dashboard.html', 
                         username=user.username,
                         courses=courses)

@app.route('/add_course', methods=['POST'])
@login_required
def add_course():
    if session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
        
    code = request.form.get('code')
    name = request.form.get('name')
    doctor_id = request.form.get('doctor_id')
    
    if not all([code, name, doctor_id]):
        flash('All fields are required')
        return redirect(url_for('admin'))
    
    course = Course(
        code=code,
        name=name,
        doctor_id=doctor_id
    )
    
    try:
        db.session.add(course)
        db.session.commit()
        flash('Course added successfully')
    except:
        db.session.rollback()
        flash('Error adding course')
    
    return redirect(url_for('admin'))

@app.route('/get_course_analysis/<int:course_id>')
def get_course_analysis(course_id):
    if session.get('role') != 'doctor':
        return jsonify({'error': 'Unauthorized'}), 403
    
    course = Course.query.get_or_404(course_id)
    
    # Get all attendance records for this course
    attendance_records = Attendance.query.filter_by(course_id=course_id).all()
    
    # Calculate statistics
    total_students = len(course.students)
    total_lectures = len(set(record.lecture_number for record in attendance_records))
    present_count = sum(1 for record in attendance_records if record.status == 'present')
    absent_count = sum(1 for record in attendance_records if record.status == 'absent')
    
    # Calculate attendance rate
    attendance_rate = 0
    if total_lectures > 0 and total_students > 0:
        total_possible = total_lectures * total_students
        attendance_rate = (present_count / total_possible) * 100 if total_possible > 0 else 0
    
    return jsonify({
        'total_students': total_students,
        'total_lectures': total_lectures,
        'present_count': present_count,
        'absent_count': absent_count,
        'attendance_rate': round(attendance_rate, 1)
    })

@app.route('/submit_excuse', methods=['POST'])
@login_required
def submit_excuse():
    if session.get('role') != 'student':
        return jsonify({'error': 'Unauthorized'}), 403
    
    data = request.json
    student_id = session['user_id']
    
    excuse = Excuse(
        student_id=student_id,
        course_id=data['course_id'],
        lecture_number=data['lecture_number'],
        reason=data['reason']
    )
    
    db.session.add(excuse)
    db.session.commit()
    
    return jsonify({'message': 'Excuse submitted successfully'})

@app.route('/get_pending_excuses')
@login_required
def get_pending_excuses():
    if session.get('role') != 'doctor':
        return jsonify({'error': 'Unauthorized'}), 403
    
    doctor_id = session['user_id']
    doctor_courses = Course.query.filter_by(doctor_id=doctor_id).all()
    course_ids = [course.id for course in doctor_courses]
    
    pending_excuses = Excuse.query.filter(
        Excuse.course_id.in_(course_ids),
        Excuse.status == 'pending'
    ).all()
    
    excuses_data = []
    for excuse in pending_excuses:
        student = User.query.get(excuse.student_id)
        course = Course.query.get(excuse.course_id)
        excuses_data.append({
            'id': excuse.id,
            'student_name': student.username,
            'course_code': course.code,
            'lecture_number': excuse.lecture_number,
            'date': excuse.date.isoformat(),
            'reason': excuse.reason
        })
    
    return jsonify({'excuses': excuses_data})

@app.route('/handle_excuse', methods=['POST'])
@login_required
def handle_excuse():
    if session.get('role') != 'doctor':
        return jsonify({'error': 'Unauthorized'}), 403
    
    data = request.json
    excuse = Excuse.query.get(data['excuse_id'])
    
    if not excuse:
        return jsonify({'error': 'Excuse not found'}), 404

    # Update excuse status
    excuse.status = data['status']
    
    if data['status'] == 'approved':
        attendance = Attendance.query.filter(
            and_(
                Attendance.student_id == excuse.student_id,
                Attendance.course_id == excuse.course_id,
                Attendance.lecture_number == excuse.lecture_number,
                func.date(Attendance.date) == excuse.date.date()
            )
        ).first()

        if attendance:
            # Update status to 'present' if already exists
            attendance.status = 'present'
        else:
            # Create new record only if none exists
            attendance = Attendance(
                student_id=excuse.student_id,
                course_id=excuse.course_id,
                lecture_number=excuse.lecture_number,
                date=excuse.date.date(),
                status='present'
            )
            db.session.add(attendance)

    db.session.commit()
    return jsonify({'message': f'Excuse {data["status"]} successfully'})

@app.route('/get_at_risk_students/<int:course_id>')
def get_at_risk_students(course_id):
    if session.get('role') != 'doctor':
        return jsonify({'error': 'Unauthorized'}), 403
    
    course = Course.query.get_or_404(course_id)
    at_risk_students = []
    risk_threshold = 25  # 25% absence rate threshold
    
    for student in course.students:
        # Get attendance records for this student in this course
        attendance_records = Attendance.query.filter_by(
            student_id=student.id,
            course_id=course_id
        ).all()
        
        if attendance_records:
            total_lectures = len(attendance_records)
            absences = sum(1 for record in attendance_records if record.status == 'absent')
            absence_rate = (absences / total_lectures) * 100 if total_lectures > 0 else 0
            
            if absence_rate >= risk_threshold:
                at_risk_students.append({
                    'id': student.id,
                    'username': student.username,
                    'university_id': student.university_id,
                    'absence_rate': round(absence_rate, 1),
                    'total_absences': absences,
                    'total_lectures': total_lectures
                })
    
    # Sort students by absence rate (highest first)
    at_risk_students.sort(key=lambda x: x['absence_rate'], reverse=True)
    
    return jsonify({'students': at_risk_students})

@app.route('/get_absent_lectures/<int:course_id>')
@login_required
def get_absent_lectures(course_id):
    if session.get('role') != 'student':
        return jsonify({'error': 'Unauthorized'}), 403

    student_id = session['user_id']
    records = Attendance.query.filter(
        Attendance.student_id == student_id,
        Attendance.course_id == course_id,
        Attendance.status.in_(['absent', 'late'])
    ).all()

    lectures = [{
        'lecture_number': r.lecture_number,
        'date': r.date.strftime('%Y-%m-%d'),
        'status': r.status
    } for r in records]

    return jsonify({'lectures': lectures})

def init_db():
    with app.app_context():
        db.create_all()
        
        # Check if courses already exist
        if Course.query.first() is None:
            # Create default courses
            courses = [
                Course(code='CPIS-320', name='Course Name 1'),
                Course(code='CPIS-499', name='Course Name 2'),
                Course(code='CPIS-380', name='Course Name 3')
            ]
            
            db.session.add_all(courses)
            db.session.commit()
            print("Courses initialized")  # Debug print

# Add this at the bottom of the file, just before app.run()
if __name__ == '__main__':
    init_db()
    app.run(debug=True) 