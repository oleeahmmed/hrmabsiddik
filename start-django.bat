@echo off
cd /d C:\Users\user\Desktop\hrm
call C:\Users\user\Desktop\hrm\venv\absiddikvenv\Scripts\activate
python manage.py runserver 0.0.0.0:8000
