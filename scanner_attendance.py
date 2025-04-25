
import json
import time
from datetime import datetime, timedelta
from extensions import db
from models import User, Course, Attendance
from app import app  # Ensure app context is imported
from sqlalchemy import and_ , func

SCHEDULE_FILE = 'schedule.json'
LATE_THRESHOLD_MINUTES = 15

def load_schedule():
    with open(SCHEDULE_FILE, 'r') as f:
        return json.load(f)

def get_current_course(schedule):
    now = datetime.now()
    current_day = now.strftime('%A')
    current_time = now.strftime('%H:%M')

    for course in schedule.get(current_day, []):
        if course['start_time'] <= current_time <= course['end_time']:
            return course
    return None

def mark_attendance(university_id):
    with app.app_context():
        now = datetime.now()
        today = now.date()

        # Load current lecture
        schedule = load_schedule()
        current_course_info = get_current_course(schedule)
        if not current_course_info:
            print("⏰ No class is active right now.")
            return

        course = Course.query.filter_by(code=current_course_info['subject']).first()
        if not course:
            print("❌ Course not found in DB.")
            return

        student = User.query.filter_by(university_id=university_id, role='student').first()
        if not student:
            print("❌ Student not found.")
            return

        if course not in student.enrolled_courses:
            print("🚫 Student not enrolled in this course.")
            return

    

        already_marked = Attendance.query.filter(and_(
            Attendance.student_id == student.id,
            Attendance.course_id == course.id,
            Attendance.lecture_number == current_course_info['lecture_number'],
            func.date(Attendance.date) == today
        )).first()


        if already_marked:
            print("✅ Already marked.")
            return

        is_late = (now.time() > (datetime.strptime(current_course_info['start_time'], "%H:%M") + timedelta(minutes=LATE_THRESHOLD_MINUTES)).time())
        
        if is_late:
            status = "late"
        else:
            status = "present"

        attendance = Attendance(
            student_id=student.id,
            course_id=course.id,
            date=today,
            status=status,
            lecture_number=current_course_info['lecture_number']
        )
        db.session.add(attendance)
        db.session.commit()

        print("⚠️ Late" if is_late else "✅ Attendance marked for:", student.username)

if __name__ == '__main__':
    print("📡 Scanner ready. Awaiting scans...")
    while True:
        try:
            scanned_id = input("Scan ID: ").strip()
            if scanned_id:
                mark_attendance(scanned_id)
        except KeyboardInterrupt:
            print("\n🛑 Scanner stopped.")
            break
