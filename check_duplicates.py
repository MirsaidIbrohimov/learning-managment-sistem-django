import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from accounts.models import Profession, StudyGroup, CustomUser, CourseEnrollment
from django.db import connection

import django.db.transaction as transaction

with transaction.atomic():
    prof = Profession.objects.create(name="Test Duplicate Prof")
    
    student = CustomUser.objects.create_user(
        username="dup_student",
        password="password",
        phone="+998999999999",
        role="student",
        coins=100
    )
    
    grp1 = StudyGroup.objects.create(name="Group 1", profession=prof, start_time="08:00", end_time="10:00")
    grp2 = StudyGroup.objects.create(name="Group 2", profession=prof, start_time="10:00", end_time="12:00")
    
    grp1.students.add(student)
    grp2.students.add(student)
    
    CourseEnrollment.objects.create(user=student, profession=prof)
    
    print("--- Testing group_id = None ---")
    all_enrolled = CustomUser.objects.filter(
        enrollments__profession=prof, role='student'
    ).distinct()
    
    scope_students = all_enrolled.order_by('-coins')
    print("SQL:", scope_students.query)
    print("Results:", list(scope_students))
    
    print("--- Testing group_id set ---")
    scope_students_grp1 = grp1.students.filter(role='student').distinct().order_by('-coins')
    print("Group 1 SQL:", scope_students_grp1.query)
    print("Group 1 Results:", list(scope_students_grp1))
    
    cursor = connection.cursor()
    try:
        cursor.execute("INSERT INTO accounts_courseenrollment (user_id, profession_id, enrolled_at) VALUES (%s, %s, datetime('now'))", [student.id, prof.id])
        print("Inserted duplicate enrollment via Raw SQL!")
    except Exception as e:
        print("Could not insert duplicate enrollment (constraint holds):", e)
        
    all_enrolled2 = CustomUser.objects.filter(
        enrollments__profession=prof, role='student'
    )
    print("Without distinct:", list(all_enrolled2))
    print("With distinct:", list(all_enrolled2.distinct()))
    print("With distinct + order_by:", list(all_enrolled2.distinct().order_by('-coins')))
    
    transaction.set_rollback(True)
