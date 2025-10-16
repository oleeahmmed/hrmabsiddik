"""
Demo Data Import Script for SignTech
Run: python import_demo_data.py
"""

import os
import django
from django.utils import timezone
from datetime import date, timedelta

# Django setup
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth.models import User
from core.models import Company, UserProfile, ProjectRole, Project, Task, TaskComment

def create_demo_data():
    print("🚀 Starting demo data import for SignTech...")
    
    # ==================== ১. কোম্পানি তৈরি ====================
    print("📋 Creating Company...")
    
    company, created = Company.objects.get_or_create(
        company_code="SIGNTECH",
        defaults={
            'name': 'SignTech Ltd.',
            'city': 'Dhaka',
            'country': 'Bangladesh',
            'is_active': True,
            'address_line1': '123 Tech Tower',
            'phone_number': '+880-2-XXXX-XXXX',
            'email': 'info@signtech.com',
            'website': 'https://signtech.com',
            'tax_id': 'TIN-123456789',
            'currency': 'BDT'
        }
    )
    
    if created:
        print("✅ Company created: SignTech Ltd.")
    else:
        print("ℹ️ Company already exists: SignTech Ltd.")
    
    # ==================== ২. ইউজার তৈরি ====================
    print("\n👥 Creating Users and Profiles...")
    
    users_data = [
        {
            'username': 'rahul',
            'email': 'rahul@signtech.com',
            'password': '501302aA',
            'first_name': 'Rahul',
            'last_name': 'Ahmed',
            'employee_id': 'EMP001',
            'designation': 'System Admin',
            'department': 'IT'
        },
        {
            'username': 'sumaiya',
            'email': 'sumaiya@signtech.com',
            'password': '501302aA',
            'first_name': 'Sumaiya',
            'last_name': 'Islam',
            'employee_id': 'EMP002',
            'designation': 'Project Manager',
            'department': 'Project Management'
        },
        {
            'username': 'arif',
            'email': 'arif@signtech.com',
            'password': '501302aA',
            'first_name': 'Arif',
            'last_name': 'Hasan',
            'employee_id': 'EMP003',
            'designation': 'Senior Developer',
            'department': 'Development'
        }
    ]
    
    created_users = {}
    for user_data in users_data:
        user, user_created = User.objects.get_or_create(
            username=user_data['username'],
            defaults={
                'email': user_data['email'],
                'first_name': user_data['first_name'],
                'last_name': user_data['last_name']
            }
        )
        
        if user_created:
            user.set_password(user_data['password'])
            user.save()
            print(f"✅ User created: {user.get_full_name()}")
        else:
            print(f"ℹ️ User already exists: {user.get_full_name()}")
        
        # UserProfile তৈরি করুন
        profile, profile_created = UserProfile.objects.get_or_create(
            user=user,
            defaults={
                'company': company,
                'employee_id': user_data['employee_id'],
                'designation': user_data['designation'],
                'department': user_data['department'],
                'phone_number': '+880-1XXX-XXXXXX',
                'is_active': True
            }
        )
        
        if profile_created:
            print(f"✅ Profile created: {user.get_full_name()} - {user_data['designation']}")
        else:
            print(f"ℹ️ Profile already exists: {user.get_full_name()}")
        
        created_users[user_data['username']] = user
    
    # ==================== ৩. প্রজেক্ট রোল তৈরি ====================
    print("\n🎯 Creating Project Roles...")
    
    roles_data = [
        {'role': 'admin', 'hierarchy_level': 0, 'description': 'সর্বোচ্চ অ্যাক্সেস, সবকিছু ম্যানেজ করতে পারে'},
        {'role': 'technical_lead', 'hierarchy_level': 1, 'description': 'টেকনিক্যাল দিকনির্দেশনা দেন'},
        {'role': 'project_manager', 'hierarchy_level': 2, 'description': 'প্রজেক্ট কো-অর্ডিনেট এবং ম্যানেজ করেন'},
        {'role': 'supervisor', 'hierarchy_level': 3, 'description': 'টিম সুপারভাইজ করেন'},
        {'role': 'employee', 'hierarchy_level': 4, 'description': 'সাধারণ এমপ্লয়ী, টাস্ক এক্সিকিউট করেন'}
    ]
    
    for role_data in roles_data:
        role, created = ProjectRole.objects.get_or_create(
            role=role_data['role'],
            defaults={
                'hierarchy_level': role_data['hierarchy_level'],
                'description': role_data['description']
            }
        )
        if created:
            print(f"✅ Role created: {role.get_role_display()} (Level {role.hierarchy_level})")
    
    # ==================== ৪. প্রজেক্ট তৈরি ====================
    print("\n🚀 Creating Project...")
    
    project, project_created = Project.objects.get_or_create(
        company=company,
        name='Website Redesign',
        defaults={
            'owner': created_users['rahul'],
            'technical_lead': created_users['arif'],
            'project_manager': created_users['sumaiya'],
            'description': 'Complete redesign of company website with modern UI/UX',
            'status': 'in_progress',
            'priority': 'high',
            'start_date': date(2024, 1, 1),
            'end_date': date(2024, 3, 31),
            'total_budget': 500000.00,
            'spent_budget': 125000.00,
            'is_active': True
        }
    )
    
    if project_created:
        print("✅ Project created: Website Redesign")
    else:
        print("ℹ️ Project already exists: Website Redesign")
    
    # ==================== ৫. টাস্ক তৈরি ====================
    print("\n✅ Creating Tasks...")
    
    tasks_data = [
        {
            'title': 'Design Homepage',
            'assigned_to': created_users['arif'],
            'status': 'in_progress',
            'priority': 'high',
            'due_date': date(2024, 2, 15),
            'estimated_hours': 40.00,
            'actual_hours': 25.00
        },
        {
            'title': 'Develop Backend API',
            'assigned_to': created_users['arif'],
            'status': 'todo',
            'priority': 'medium',
            'due_date': date(2024, 2, 28),
            'estimated_hours': 60.00,
            'actual_hours': 0.00
        },
        {
            'title': 'Create Content',
            'assigned_to': created_users['sumaiya'],
            'status': 'completed',
            'priority': 'low',
            'due_date': date(2024, 1, 20),
            'estimated_hours': 20.00,
            'actual_hours': 18.50
        }
    ]
    
    for task_data in tasks_data:
        task, created = Task.objects.get_or_create(
            project=project,
            title=task_data['title'],
            defaults={
                'company': company,
                'owner': created_users['rahul'],
                'assigned_by': created_users['sumaiya'],
                'assigned_to': task_data['assigned_to'],
                'description': f"Task for {task_data['title']}",
                'status': task_data['status'],
                'priority': task_data['priority'],
                'due_date': task_data['due_date'],
                'estimated_hours': task_data['estimated_hours'],
                'actual_hours': task_data['actual_hours'],
                'is_blocked': False
            }
        )
        if created:
            print(f"✅ Task created: {task_data['title']} - {task_data['status']}")
    
    # ==================== ৬. টাস্ক কমেন্ট তৈরি ====================
    print("\n💬 Creating Task Comments...")
    
    # Design Homepage টাস্ক পেতে
    design_task = Task.objects.get(title='Design Homepage')
    content_task = Task.objects.get(title='Create Content')
    
    comments_data = [
        {
            'task': design_task,
            'commented_by': created_users['arif'],
            'comment': 'Homepage design 50% completed. Working on mobile responsive layout.'
        },
        {
            'task': design_task,
            'commented_by': created_users['sumaiya'],
            'comment': 'Please ensure the design follows our new brand guidelines.'
        },
        {
            'task': content_task,
            'commented_by': created_users['sumaiya'],
            'comment': 'All content has been finalized and uploaded to the server.'
        }
    ]
    
    for comment_data in comments_data:
        comment, created = TaskComment.objects.get_or_create(
            task=comment_data['task'],
            commented_by=comment_data['commented_by'],
            comment=comment_data['comment'],
            defaults={
                'company': company,
                'owner': created_users['rahul']
            }
        )
        if created:
            print(f"✅ Comment added by {comment_data['commented_by'].get_full_name()}")
    
    # ==================== সম্পূর্ণ সারমর্ম ====================
    print("\n🎉 Demo Data Import Completed Successfully!")
    print("\n📊 Summary:")
    print(f"   • Company: 1 (SignTech Ltd.)")
    print(f"   • Users: 3 (Rahul, Sumaiya, Arif)")
    print(f"   • Project Roles: 5")
    print(f"   • Projects: 1 (Website Redesign)")
    print(f"   • Tasks: 3")
    print(f"   • Comments: 3")
    print(f"\n🔑 Login Credentials:")
    print(f"   • Rahul (Admin): username='rahul', password='501302aA'")
    print(f"   • Sumaiya (PM): username='sumaiya', password='501302aA'")
    print(f"   • Arif (Developer): username='arif', password='501302aA'")
    print(f"\n🌐 Admin Panel: http://localhost:8000/admin/")

if __name__ == "__main__":
    create_demo_data()