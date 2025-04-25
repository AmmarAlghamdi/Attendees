from extensions import db
from werkzeug.security import generate_password_hash
from datetime import datetime


# Association tables for many-to-many relationships
student_courses = db.Table('student_courses',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id')),
    db.Column('course_id', db.Integer, db.ForeignKey('course.id'))
)

teacher_courses = db.Table('teacher_courses',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id')),
    db.Column('course_id', db.Integer, db.ForeignKey('course.id'))
)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'student', 'doctor', 'admin'
    university_id = db.Column(db.String(20), unique=True, nullable=False)
    
    # Relationships
    enrolled_courses = db.relationship('Course', secondary=student_courses, backref='students')
    teaching_courses = db.relationship('Course', secondary=teacher_courses, backref='teachers')

    def __init__(self, username, email, password, role, university_id):
        
        self.username = username
        self.email = email
        self.password = password  
        self.role = role
        self.university_id = university_id


class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey('user.id'))  


class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    status = db.Column(db.String(20), nullable=False, default='present')  # 'present' or 'absent'
    lecture_number = db.Column(db.Integer, nullable=False)  # 1-5 for each day

    student = db.relationship('User', backref='attendances')
    course = db.relationship('Course', backref='attendances')

class Excuse(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    lecture_number = db.Column(db.Integer, nullable=False)
    date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    reason = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, approved, rejected
    
    student = db.relationship('User', backref='excuses')
    course = db.relationship('Course', backref='excuses') 