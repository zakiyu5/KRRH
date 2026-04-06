# app.py - Complete Version with Enhanced User Management

import os
import json
import csv
from io import StringIO
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, make_response
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

# Local imports
from config import config
from models import db, User, UserAccessLog, KPICategory, KPIDefinition, KPIEntry
from models import ReferralHospital, Referral
from models import create_initial_kpi_categories, create_initial_kpis

# Add this for Render compatibility
import sys
import warnings

# Suppress deprecation warnings on Render
warnings.filterwarnings('ignore', category=DeprecationWarning)

# Fix for Werkzeug URL decode issue
try:
    from werkzeug.urls import url_decode
except ImportError:
    # For newer versions of Werkzeug
    from urllib.parse import unquote
    def url_decode(s, charset='utf-8', decode_keys=False, include_empty=True, 
                   separator='&', cls=None, **kwargs):
        return {k: v for k, v in [p.split('=') for p in s.split(separator)]}
    import werkzeug
    werkzeug.urls = type('obj', (object,), {'url_decode': url_decode})()

# Initialize Flask app
app = Flask(__name__)

# Load configuration
env = os.environ.get('FLASK_ENV', 'default')
app.config.from_object(config[env])

# Get basedir
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['basedir'] = basedir
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'database', 'krrh_insighthub.db')
app.config['UPLOAD_FOLDER'] = os.path.join(basedir, 'static', 'uploads')
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

# Initialize extensions
db.init_app(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'

# ===================== DATABASE INIT =====================

def create_directories():
    os.makedirs(os.path.join(app.config['basedir'], 'database'), exist_ok=True)
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    print("✅ Directories created")

def init_database():
    with app.app_context():
        db.create_all()
        print("✅ Database tables created")
        
        # Create admin
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            admin = User(
                username='admin',
                email='admin@krrh.go.ug',
                phone_number='+256700000000',
                password_hash=generate_password_hash('Admin@123'),
                full_name='System Administrator',
                role='admin',
                department='Administration',
                allowed_wards='[]',
                is_active=True,
                is_paused=False,
                password_set_date=datetime.utcnow(),
                password_expiry_days=90
            )
            db.session.add(admin)
            db.session.commit()
            print("✅ Admin created: admin / Admin@123")
        
        # Create KPI categories and KPIs
        create_initial_kpi_categories()
        create_initial_kpis()
        
        # Create referral hospitals
        hospitals = [
            {'name': 'Mulago National Referral Hospital', 'code': 'MULAGO', 'location': 'Kampala'},
            {'name': 'Kawempe National Referral Hospital', 'code': 'KAWEMPE', 'location': 'Kawempe'},
            {'name': 'Kiruddu National Referral Hospital', 'code': 'KIRUDDU', 'location': 'Kiruddu'},
        ]
        for hosp in hospitals:
            if not ReferralHospital.query.filter_by(code=hosp['code']).first():
                db.session.add(ReferralHospital(**hosp))
        db.session.commit()
        print("✅ Database initialized")

# ===================== USER LOADER =====================

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ===================== CONTEXT PROCESSOR =====================

@app.context_processor
def inject_now():
    return {'now': datetime.now(), 'datetime': datetime}

@app.context_processor
def utility_processor():
    def min_value(a, b):
        if a is None or b is None:
            return 0
        return min(a, b)
    
    def from_json(json_str):
        try:
            return json.loads(json_str) if json_str else []
        except:
            return []
    
    return {'min': min_value, 'from_json': from_json}



## context 
@app.context_processor
def utility_processor():
    def min_value(a, b):
        if a is None or b is None:
            return 0
        return min(a, b)
    
    def from_json(json_str):
        try:
            if json_str:
                return json.loads(json_str)
            return []
        except:
            return []
    
    return {'min': min_value, 'from_json': from_json}

# registering jinja filterss
app.jinja_env.filters['from_json'] = lambda s: json.loads(s) if s else []

# ===================== AUTH ROUTES =====================

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('landing.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password):
            # Check if account is paused
            if user.is_paused:
                flash('Your account has been paused. Please contact administrator.', 'danger')
                # Log failed attempt
                log = UserAccessLog(
                    user_id=user.id,
                    action='login',
                    status='paused',
                    ip_address=request.remote_addr,
                    user_agent=request.headers.get('User-Agent'),
                    details='Account paused'
                )
                db.session.add(log)
                db.session.commit()
                return render_template('landing.html')
            
            # Check if account is active
            if not user.is_active:
                flash('Your account is inactive. Please contact administrator.', 'danger')
                return render_template('landing.html')
            
            # Check password expiry
            days_since_set = (datetime.utcnow() - user.password_set_date).days if user.password_set_date else 0
            if days_since_set >= user.password_expiry_days:
                flash('Your password has expired. Please reset your password.', 'warning')
                # Log password expiry
                log = UserAccessLog(
                    user_id=user.id,
                    action='login',
                    status='expired',
                    ip_address=request.remote_addr,
                    user_agent=request.headers.get('User-Agent'),
                    details='Password expired'
                )
                db.session.add(log)
                db.session.commit()
            
            login_user(user)
            user.last_login = datetime.utcnow()
            
            # Log successful login
            log = UserAccessLog(
                user_id=user.id,
                action='login',
                status='success',
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User-Agent'),
                details=f'Logged in from {request.remote_addr}'
            )
            db.session.add(log)
            db.session.commit()
            
            flash(f'Welcome {user.full_name}!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password', 'danger')
    
    return render_template('landing.html')
    
@app.route('/logout')
@login_required
def logout():
    # Log logout
    log = UserAccessLog(
        user_id=current_user.id,
        action='logout',
        status='success',
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent'),
        details='User logged out'
    )
    db.session.add(log)
    db.session.commit()
    
    logout_user()
    flash('Logged out', 'info')
    return redirect(url_for('index'))

# ===================== DASHBOARD =====================

@app.route('/dashboard')
@login_required
def dashboard():
    categories = KPICategory.query.order_by(KPICategory.display_order).all()
    recent_entries = KPIEntry.query.order_by(KPIEntry.entry_date.desc()).limit(10).all()
    pending_referrals = Referral.query.filter_by(status='pending').count()
    
    return render_template('dashboard/index.html',
                          categories=categories,
                          recent_entries=recent_entries,
                          pending_referrals=pending_referrals)

# ===================== WARD SYSTEM - ALL DEPARTMENTS =====================

WARD_PARAMETERS = {
    'OPD': {
        'name': 'Outpatient Department (OPD)',
        'icon': '🚪',
        'description': 'Outpatient department services and performance metrics',
        'kpis': [
            {'name': 'Total OPD Visits', 'field': 'total_visits', 'unit': 'patients', 'type': 'direct'},
            {'name': 'Catchment Population', 'field': 'catchment_population', 'unit': 'people', 'type': 'direct'},
            {'name': 'OPD Utilization Rate', 'field': 'utilization_rate', 'unit': '%', 'type': 'calculated'},
            {'name': 'Total Waiting Time (mins)', 'field': 'total_waiting_time', 'unit': 'minutes', 'type': 'direct'},
            {'name': 'Average Waiting Time', 'field': 'waiting_time', 'unit': 'minutes', 'type': 'calculated'},
            {'name': 'Patients Properly Triaged', 'field': 'triaged_correct', 'unit': 'patients', 'type': 'direct'},
            {'name': '% Patients Properly Triaged', 'field': 'triaged_rate', 'unit': '%', 'type': 'calculated'},
            {'name': 'Referrals Completed', 'field': 'referrals_completed', 'unit': 'patients', 'type': 'direct'},
            {'name': 'Total Referrals', 'field': 'total_referrals', 'unit': 'patients', 'type': 'direct'},
            {'name': 'Referral Completion Rate', 'field': 'referral_completion', 'unit': '%', 'type': 'calculated'},
            {'name': 'Satisfied Patients', 'field': 'satisfied_patients', 'unit': 'patients', 'type': 'direct'},
            {'name': 'Total Surveys', 'field': 'total_surveys', 'unit': 'surveys', 'type': 'direct'},
            {'name': 'Patient Satisfaction Score', 'field': 'satisfaction', 'unit': '%', 'type': 'calculated'},
        ]
    },
    'Inpatient': {
        'name': 'Inpatient Department',
        'icon': '🛏️',
        'description': 'General wards and inpatient care',
        'kpis': [
            {'name': 'Admissions', 'field': 'admissions', 'unit': 'patients', 'type': 'direct'},
            {'name': 'Discharges', 'field': 'discharges', 'unit': 'patients', 'type': 'direct'},
            {'name': 'Inpatient Days', 'field': 'inpatient_days', 'unit': 'days', 'type': 'direct'},
            {'name': 'Available Bed Days', 'field': 'available_bed_days', 'unit': 'days', 'type': 'direct'},
            {'name': 'Bed Occupancy Rate', 'field': 'occupancy_rate', 'unit': '%', 'type': 'calculated'},
            {'name': 'Total Inpatient Days', 'field': 'total_inpatient_days', 'unit': 'days', 'type': 'direct'},
            {'name': 'Average Length of Stay', 'field': 'avg_los', 'unit': 'days', 'type': 'calculated'},
            {'name': 'Deaths', 'field': 'deaths', 'unit': 'patients', 'type': 'direct'},
            {'name': 'Inpatient Mortality Rate', 'field': 'mortality_rate', 'unit': '%', 'type': 'calculated'},
            {'name': 'Deaths Within 48h', 'field': 'deaths_48h', 'unit': 'patients', 'type': 'direct'},
            {'name': '48-Hour Mortality Rate', 'field': 'mortality_48h', 'unit': '%', 'type': 'calculated'},
            {'name': 'Readmissions', 'field': 'readmissions', 'unit': 'patients', 'type': 'direct'},
            {'name': 'Readmission Rate', 'field': 'readmission_rate', 'unit': '%', 'type': 'calculated'},
        ]
    },
    'Maternity': {
        'name': 'Maternity / Obstetrics',
        'icon': '🤰',
        'description': 'Maternal health and delivery services',
        'kpis': [
            {'name': 'Total Deliveries', 'field': 'deliveries', 'unit': 'births', 'type': 'direct'},
            {'name': 'Normal Deliveries', 'field': 'normal_deliveries', 'unit': 'births', 'type': 'direct'},
            {'name': 'C-Sections', 'field': 'c_sections', 'unit': 'procedures', 'type': 'direct'},
            {'name': 'C-Section Rate', 'field': 'csection_rate', 'unit': '%', 'type': 'calculated'},
            {'name': 'Maternal Deaths', 'field': 'maternal_deaths', 'unit': 'deaths', 'type': 'direct'},
            {'name': 'Live Births', 'field': 'live_births', 'unit': 'births', 'type': 'direct'},
            {'name': 'Maternal Mortality Ratio', 'field': 'maternal_mortality', 'unit': 'per 100,000', 'type': 'calculated'},
            {'name': 'ANC Before 12 Weeks', 'field': 'anc_before_12w', 'unit': 'patients', 'type': 'direct'},
            {'name': 'Total ANC Visits', 'field': 'total_anc', 'unit': 'visits', 'type': 'direct'},
            {'name': '% ANC 1st Visit Before 12 Weeks', 'field': 'anc_early_rate', 'unit': '%', 'type': 'calculated'},
            {'name': 'IPT3 Received', 'field': 'ipt3_received', 'unit': 'women', 'type': 'direct'},
            {'name': 'Pregnant Women', 'field': 'pregnant_women', 'unit': 'women', 'type': 'direct'},
            {'name': 'IPT3 Coverage', 'field': 'ipt3_coverage', 'unit': '%', 'type': 'calculated'},
            {'name': 'Postnatal Within 48h', 'field': 'postnatal_48h', 'unit': 'mothers', 'type': 'direct'},
            {'name': 'Postnatal Care Within 48 Hours', 'field': 'postnatal_coverage', 'unit': '%', 'type': 'calculated'},
        ]
    },
    'Paediatrics': {
        'name': 'Paediatrics',
        'icon': '🧒',
        'description': 'Child health and pediatric services',
        'kpis': [
            {'name': 'Under-5 Admissions', 'field': 'under5_admissions', 'unit': 'patients', 'type': 'direct'},
            {'name': 'Under-5 Deaths', 'field': 'under5_deaths', 'unit': 'deaths', 'type': 'direct'},
            {'name': 'Under-5 Mortality Rate', 'field': 'under5_mortality', 'unit': '%', 'type': 'calculated'},
            {'name': 'DPT3 Received', 'field': 'dpt3_received', 'unit': 'children', 'type': 'direct'},
            {'name': 'Eligible Children', 'field': 'eligible_children', 'unit': 'children', 'type': 'direct'},
            {'name': 'DPT3 Coverage', 'field': 'dpt3_coverage', 'unit': '%', 'type': 'calculated'},
            {'name': 'Measles Vaccinated', 'field': 'measles_vaccinated', 'unit': 'children', 'type': 'direct'},
            {'name': 'Measles Coverage', 'field': 'measles_coverage', 'unit': '%', 'type': 'calculated'},
            {'name': 'Severe Malaria Cases', 'field': 'severe_malaria', 'unit': 'cases', 'type': 'direct'},
            {'name': 'Malaria Deaths', 'field': 'malaria_deaths', 'unit': 'deaths', 'type': 'direct'},
            {'name': 'Severe Malaria Case Fatality Rate', 'field': 'malaria_fatality', 'unit': '%', 'type': 'calculated'},
        ]
    },
    'Surgery': {
        'name': 'Surgery / Theatre',
        'icon': '🔪',
        'description': 'Surgical services and operating theatre',
        'kpis': [
            {'name': 'Major Surgeries', 'field': 'major_surgeries', 'unit': 'procedures', 'type': 'direct'},
            {'name': 'Minor Surgeries', 'field': 'minor_surgeries', 'unit': 'procedures', 'type': 'direct'},
            {'name': 'Total Surgeries', 'field': 'surgeries', 'unit': 'procedures', 'type': 'direct'},
            {'name': 'SSI Cases', 'field': 'ssi_cases', 'unit': 'cases', 'type': 'direct'},
            {'name': 'Surgical Site Infection Rate', 'field': 'ssi_rate', 'unit': '%', 'type': 'calculated'},
            {'name': 'Hours Used', 'field': 'hours_used', 'unit': 'hours', 'type': 'direct'},
            {'name': 'Available Hours', 'field': 'available_hours', 'unit': 'hours', 'type': 'direct'},
            {'name': 'Theatre Utilization Rate', 'field': 'theatre_utilization', 'unit': '%', 'type': 'calculated'},
            {'name': 'Post-op Deaths', 'field': 'postop_deaths', 'unit': 'deaths', 'type': 'direct'},
            {'name': 'Post-Operative Mortality (24 hrs)', 'field': 'postop_mortality', 'unit': '%', 'type': 'calculated'},
            {'name': 'Cancelled Surgeries', 'field': 'cancelled', 'unit': 'procedures', 'type': 'direct'},
            {'name': 'Scheduled Surgeries', 'field': 'scheduled', 'unit': 'procedures', 'type': 'direct'},
            {'name': 'Cancelled Surgeries Rate', 'field': 'cancellation_rate', 'unit': '%', 'type': 'calculated'},
        ]
    },
    'Emergency': {
        'name': 'Emergency / Casualty',
        'icon': '🚑',
        'description': 'Emergency department and trauma services',
        'kpis': [
            {'name': 'Emergency Cases', 'field': 'emergency_cases', 'unit': 'patients', 'type': 'direct'},
            {'name': 'Triaged Correctly', 'field': 'triaged_correct', 'unit': 'patients', 'type': 'direct'},
            {'name': 'Triage Compliance Rate', 'field': 'triage_compliance', 'unit': '%', 'type': 'calculated'},
            {'name': 'Total Response Time', 'field': 'total_response_time', 'unit': 'minutes', 'type': 'direct'},
            {'name': 'Emergency Response Time', 'field': 'response_time', 'unit': 'minutes', 'type': 'calculated'},
            {'name': 'Deaths Within 24h', 'field': 'deaths_24h', 'unit': 'deaths', 'type': 'direct'},
            {'name': 'Mortality Within 24 Hours', 'field': 'emergency_mortality', 'unit': '%', 'type': 'calculated'},
            {'name': 'Trauma Cases', 'field': 'trauma_cases', 'unit': 'patients', 'type': 'direct'},
            {'name': 'Trauma Deaths', 'field': 'trauma_deaths', 'unit': 'deaths', 'type': 'direct'},
            {'name': 'Trauma Case Fatality Rate', 'field': 'trauma_fatality', 'unit': '%', 'type': 'calculated'},
        ]
    },
    'Laboratory': {
        'name': 'Laboratory',
        'icon': '🔬',
        'description': 'Diagnostic laboratory services',
        'kpis': [
            {'name': 'Total Tests', 'field': 'total_tests', 'unit': 'tests', 'type': 'direct'},
            {'name': 'Total Turnaround Time', 'field': 'total_turnaround', 'unit': 'hours', 'type': 'direct'},
            {'name': 'Test Turnaround Time', 'field': 'turnaround_time', 'unit': 'hours', 'type': 'calculated'},
            {'name': 'External Quality Assessment Score', 'field': 'eqa_score', 'unit': '%', 'type': 'direct'},
            {'name': 'Rejected Samples', 'field': 'rejected', 'unit': 'samples', 'type': 'direct'},
            {'name': 'Total Samples', 'field': 'total_samples', 'unit': 'samples', 'type': 'direct'},
            {'name': 'Sample Rejection Rate', 'field': 'rejection_rate', 'unit': '%', 'type': 'calculated'},
            {'name': 'Equipment Downtime', 'field': 'downtime', 'unit': 'days', 'type': 'direct'},
        ]
    },
    'Pharmacy': {
        'name': 'Pharmacy',
        'icon': '💊',
        'description': 'Medication supply and pharmaceutical services',
        'kpis': [
            {'name': 'Patients Served', 'field': 'patients_served', 'unit': 'patients', 'type': 'direct'},
            {'name': 'Days Out of Stock', 'field': 'days_out_of_stock', 'unit': 'days', 'type': 'direct'},
            {'name': 'Total Days', 'field': 'total_days', 'unit': 'days', 'type': 'direct'},
            {'name': 'Stock-Out Rate', 'field': 'stockout_rate', 'unit': '%', 'type': 'calculated'},
            {'name': 'Quantity Supplied', 'field': 'quantity_supplied', 'unit': 'units', 'type': 'direct'},
            {'name': 'Quantity Ordered', 'field': 'quantity_ordered', 'unit': 'units', 'type': 'direct'},
            {'name': 'Order Fill Rate', 'field': 'fill_rate', 'unit': '%', 'type': 'calculated'},
            {'name': 'Expired Value', 'field': 'expired_value', 'unit': 'UGX', 'type': 'direct'},
            {'name': 'Total Stock Value', 'field': 'total_stock_value', 'unit': 'UGX', 'type': 'direct'},
            {'name': 'Expiry Rate', 'field': 'expiry_rate', 'unit': '%', 'type': 'calculated'},
            {'name': 'Prescription Errors', 'field': 'errors', 'unit': 'errors', 'type': 'direct'},
            {'name': 'Total Prescriptions', 'field': 'prescriptions', 'unit': 'scripts', 'type': 'direct'},
            {'name': 'Prescription Error Rate', 'field': 'error_rate', 'unit': '%', 'type': 'calculated'},
        ]
    },
    'HIV_TB': {
        'name': 'HIV / TB Clinic',
        'icon': '❤️',
        'description': 'HIV and Tuberculosis services',
        'kpis': [
            {'name': 'Patients Tested', 'field': 'tested', 'unit': 'patients', 'type': 'direct'},
            {'name': 'Positive Tests', 'field': 'positive', 'unit': 'patients', 'type': 'direct'},
            {'name': 'HIV Testing Yield', 'field': 'hiv_yield', 'unit': '%', 'type': 'calculated'},
            {'name': 'Started ART', 'field': 'started_art', 'unit': 'patients', 'type': 'direct'},
            {'name': 'Linkage to ART', 'field': 'art_linkage', 'unit': '%', 'type': 'calculated'},
            {'name': 'Virally Suppressed', 'field': 'suppressed', 'unit': 'patients', 'type': 'direct'},
            {'name': 'Viral Suppression Rate', 'field': 'viral_suppression', 'unit': '%', 'type': 'calculated'},
            {'name': 'Cured + Completed', 'field': 'cured_completed', 'unit': 'patients', 'type': 'direct'},
            {'name': 'Total TB Cases', 'field': 'total_tb', 'unit': 'cases', 'type': 'direct'},
            {'name': 'TB Treatment Success Rate', 'field': 'tb_success', 'unit': '%', 'type': 'calculated'},
            {'name': 'Confirmed TB Cases', 'field': 'confirmed', 'unit': 'cases', 'type': 'direct'},
            {'name': 'Expected TB Cases', 'field': 'expected', 'unit': 'cases', 'type': 'direct'},
            {'name': 'TB Case Detection Rate', 'field': 'tb_detection', 'unit': '%', 'type': 'calculated'},
        ]
    },
    'HR': {
        'name': 'Human Resources',
        'icon': '👥',
        'description': 'Staff management and human resource metrics',
        'kpis': [
            {'name': 'Staff Present', 'field': 'staff_present', 'unit': 'staff', 'type': 'direct'},
            {'name': 'Staff Scheduled', 'field': 'staff_scheduled', 'unit': 'staff', 'type': 'direct'},
            {'name': 'Staff Attendance Rate', 'field': 'attendance_rate', 'unit': '%', 'type': 'calculated'},
            {'name': 'Clinical Staff', 'field': 'clinical_staff', 'unit': 'staff', 'type': 'direct'},
            {'name': 'Patient Load', 'field': 'patient_load', 'unit': 'patients', 'type': 'direct'},
            {'name': 'Staff-to-Patient Ratio', 'field': 'staff_patient_ratio', 'unit': 'ratio', 'type': 'calculated'},
            {'name': 'CPD Trained', 'field': 'cpd_trained', 'unit': 'staff', 'type': 'direct'},
            {'name': 'Total Staff', 'field': 'total_staff', 'unit': 'staff', 'type': 'direct'},
            {'name': '% Staff with CPD Training', 'field': 'cpd_training_rate', 'unit': '%', 'type': 'calculated'},
            {'name': 'Unfilled Posts', 'field': 'unfilled_posts', 'unit': 'posts', 'type': 'direct'},
            {'name': 'Approved Posts', 'field': 'approved_posts', 'unit': 'posts', 'type': 'direct'},
            {'name': 'Vacancy Rate', 'field': 'vacancy_rate', 'unit': '%', 'type': 'calculated'},
            {'name': 'EMR Doctors Using', 'field': 'emr_doctors', 'unit': 'doctors', 'type': 'direct'},
            {'name': 'Total Doctors', 'field': 'total_doctors', 'unit': 'doctors', 'type': 'direct'},
            {'name': 'EMR Utilization (Doctors)', 'field': 'emr_doctors_rate', 'unit': '%', 'type': 'calculated'},
            {'name': 'EMR Nurses Using', 'field': 'emr_nurses', 'unit': 'nurses', 'type': 'direct'},
            {'name': 'Total Nurses', 'field': 'total_nurses', 'unit': 'nurses', 'type': 'direct'},
            {'name': 'EMR Utilization (Nurses)', 'field': 'emr_nurses_rate', 'unit': '%', 'type': 'calculated'},
        ]
    },
    'Finance': {
        'name': 'Finance & Administration',
        'icon': '💰',
        'description': 'Financial management and budget performance',
        'kpis': [
            {'name': 'Actual Expenditure', 'field': 'actual_expenditure', 'unit': 'UGX', 'type': 'direct'},
            {'name': 'Budget Allocation', 'field': 'budget_allocation', 'unit': 'UGX', 'type': 'direct'},
            {'name': 'Budget Absorption Rate', 'field': 'budget_absorption', 'unit': '%', 'type': 'calculated'},
            {'name': 'Actual Revenue', 'field': 'actual_revenue', 'unit': 'UGX', 'type': 'direct'},
            {'name': 'Revenue Target', 'field': 'revenue_target', 'unit': 'UGX', 'type': 'direct'},
            {'name': 'Revenue Collection vs Target', 'field': 'revenue_collection_rate', 'unit': '%', 'type': 'calculated'},
            {'name': 'Compliant Items', 'field': 'items_compliant', 'unit': 'items', 'type': 'direct'},
            {'name': 'Total Audit Items', 'field': 'total_audit_items', 'unit': 'items', 'type': 'direct'},
            {'name': 'Audit Compliance Score', 'field': 'audit_compliance', 'unit': '%', 'type': 'calculated'},
            {'name': 'Total Lead Days', 'field': 'total_lead_days', 'unit': 'days', 'type': 'direct'},
            {'name': 'Procurement Count', 'field': 'procurement_count', 'unit': 'orders', 'type': 'direct'},
            {'name': 'Procurement Lead Time', 'field': 'procurement_lead_time', 'unit': 'days', 'type': 'calculated'},
            {'name': 'Total Operational Cost', 'field': 'total_operational_cost', 'unit': 'UGX', 'type': 'direct'},
            {'name': 'Total Patients', 'field': 'total_patients', 'unit': 'patients', 'type': 'direct'},
            {'name': 'Cost per Patient', 'field': 'cost_per_patient', 'unit': 'UGX', 'type': 'calculated'},
            {'name': 'Cash Inflow', 'field': 'cash_inflow', 'unit': 'UGX', 'type': 'direct'},
            {'name': 'Cash Outflow', 'field': 'cash_outflow', 'unit': 'UGX', 'type': 'direct'},
            {'name': 'Cash Flow Ratio', 'field': 'cash_flow_ratio', 'unit': '%', 'type': 'calculated'},
        ]
    },
    'Clinical_EMR': {
        'name': 'Clinical Utilization & EMR Analytics',
        'icon': '📊',
        'description': 'Doctor and nurse productivity tracking with EMR usage analytics',
        'kpis': [
            {'name': 'Total OPD Patients Seen', 'field': 'opd_patients_seen', 'unit': 'patients', 'type': 'direct'},
            {'name': 'Total IPD Patients Seen', 'field': 'ipd_patients_seen', 'unit': 'patients', 'type': 'direct'},
            {'name': 'Total Major Surgeries', 'field': 'major_surgeries', 'unit': 'surgeries', 'type': 'direct'},
            {'name': 'Total Minor Surgeries', 'field': 'minor_surgeries', 'unit': 'surgeries', 'type': 'direct'},
            {'name': 'Total Prescriptions', 'field': 'prescriptions_done', 'unit': 'prescriptions', 'type': 'direct'},
            {'name': 'Drugs Entered in EMR', 'field': 'drugs_emr', 'unit': 'entries', 'type': 'direct'},
            {'name': 'Patients Reviewed on Follow-up', 'field': 'followup_reviews', 'unit': 'patients', 'type': 'direct'},
            {'name': 'Patients Received (IPD)', 'field': 'patients_received_ipd', 'unit': 'patients', 'type': 'direct'},
            {'name': 'Patients Served (IPD/OPD)', 'field': 'patients_served_nurses', 'unit': 'patients', 'type': 'direct'},
            {'name': 'Nurse Rounds Conducted', 'field': 'nurse_rounds', 'unit': 'rounds', 'type': 'direct'},
            {'name': 'Times Involved in Admissions', 'field': 'admissions_involvement', 'unit': 'times', 'type': 'direct'},
            {'name': 'Times Accounted for Consumables', 'field': 'consumables_accounted', 'unit': 'times', 'type': 'direct'},
            {'name': 'Days Worked in EMR', 'field': 'emr_days_worked', 'unit': 'days', 'type': 'direct'},
            {'name': 'Times Computers Used (EMR)', 'field': 'emr_computer_usage', 'unit': 'sessions', 'type': 'direct'},
            {'name': 'Drug Consumption Variation', 'field': 'drug_consumption_var', 'unit': '%', 'type': 'direct'},
            {'name': 'Average Daily Doctor Patients', 'field': 'avg_daily_doctor_patients', 'unit': 'patients/day', 'type': 'calculated'},
            {'name': 'Doctor Productivity Score', 'field': 'doctor_productivity', 'unit': 'score', 'type': 'calculated'},
            {'name': 'Average Daily Nurse Rounds', 'field': 'avg_daily_nurse_rounds', 'unit': 'rounds/day', 'type': 'calculated'},
            {'name': 'Nurse Productivity Score', 'field': 'nurse_productivity', 'unit': 'score', 'type': 'calculated'},
            {'name': 'EMR Utilization Rate', 'field': 'emr_utilization_rate', 'unit': '%', 'type': 'calculated'},
            {'name': 'Doctor-to-Patient Ratio', 'field': 'doctor_patient_ratio', 'unit': 'ratio', 'type': 'calculated'},
            {'name': 'Nurse-to-Patient Ratio', 'field': 'nurse_patient_ratio', 'unit': 'ratio', 'type': 'calculated'},
            {'name': 'Surgical Load Index', 'field': 'surgical_load_index', 'unit': 'score', 'type': 'calculated'},
            {'name': 'Highest OPD Presenter (Doctor)', 'field': 'top_doctor_opd', 'unit': 'patients', 'type': 'direct'},
            {'name': 'Top Doctor Name', 'field': 'top_doctor_name', 'unit': '', 'type': 'direct'},
            {'name': 'Highest Nurse Rounds', 'field': 'top_nurse_rounds', 'unit': 'rounds', 'type': 'direct'},
            {'name': 'Top Nurse Name', 'field': 'top_nurse_name', 'unit': '', 'type': 'direct'},
            {'name': 'Highest Surgical Load', 'field': 'top_surgical_load', 'unit': 'surgeries', 'type': 'direct'},
            {'name': 'Top Surgeon Name', 'field': 'top_surgeon_name', 'unit': '', 'type': 'direct'},
            {'name': 'Highest Drug Administration', 'field': 'top_drug_admin', 'unit': 'admin', 'type': 'direct'},
            {'name': 'Top Clinician Name', 'field': 'top_clinician_name', 'unit': '', 'type': 'direct'},
        ]
    }
}

# Define formulas for calculated KPIs
KPI_FORMULAS = {
    'OPD': {
        'utilization_rate': {'numerator': 'total_visits', 'denominator': 'catchment_population', 'multiplier': 100},
        'waiting_time': {'numerator': 'total_waiting_time', 'denominator': 'total_visits', 'multiplier': 1},
        'triaged_rate': {'numerator': 'triaged_correct', 'denominator': 'total_visits', 'multiplier': 100},
        'referral_completion': {'numerator': 'referrals_completed', 'denominator': 'total_referrals', 'multiplier': 100},
        'satisfaction': {'numerator': 'satisfied_patients', 'denominator': 'total_surveys', 'multiplier': 100},
    },
    'Maternity': {
        'csection_rate': {'numerator': 'c_sections', 'denominator': 'deliveries', 'multiplier': 100},
        'maternal_mortality': {'numerator': 'maternal_deaths', 'denominator': 'live_births', 'multiplier': 100000},
        'anc_early_rate': {'numerator': 'anc_before_12w', 'denominator': 'total_anc', 'multiplier': 100},
        'ipt3_coverage': {'numerator': 'ipt3_received', 'denominator': 'pregnant_women', 'multiplier': 100},
        'postnatal_coverage': {'numerator': 'postnatal_48h', 'denominator': 'deliveries', 'multiplier': 100},
    },
    'Inpatient': {
        'occupancy_rate': {'numerator': 'inpatient_days', 'denominator': 'available_bed_days', 'multiplier': 100},
        'avg_los': {'numerator': 'total_inpatient_days', 'denominator': 'discharges', 'multiplier': 1},
        'mortality_rate': {'numerator': 'deaths', 'denominator': 'admissions', 'multiplier': 100},
        'mortality_48h': {'numerator': 'deaths_48h', 'denominator': 'admissions', 'multiplier': 100},
        'readmission_rate': {'numerator': 'readmissions', 'denominator': 'discharges', 'multiplier': 100},
    },
    'Paediatrics': {
        'under5_mortality': {'numerator': 'under5_deaths', 'denominator': 'under5_admissions', 'multiplier': 100},
        'dpt3_coverage': {'numerator': 'dpt3_received', 'denominator': 'eligible_children', 'multiplier': 100},
        'measles_coverage': {'numerator': 'measles_vaccinated', 'denominator': 'eligible_children', 'multiplier': 100},
        'malaria_fatality': {'numerator': 'malaria_deaths', 'denominator': 'severe_malaria', 'multiplier': 100},
    },
    'Surgery': {
        'ssi_rate': {'numerator': 'ssi_cases', 'denominator': 'surgeries', 'multiplier': 100},
        'theatre_utilization': {'numerator': 'hours_used', 'denominator': 'available_hours', 'multiplier': 100},
        'postop_mortality': {'numerator': 'postop_deaths', 'denominator': 'surgeries', 'multiplier': 100},
        'cancellation_rate': {'numerator': 'cancelled', 'denominator': 'scheduled', 'multiplier': 100},
    },
    'Emergency': {
        'triage_compliance': {'numerator': 'triaged_correct', 'denominator': 'emergency_cases', 'multiplier': 100},
        'response_time': {'numerator': 'total_response_time', 'denominator': 'emergency_cases', 'multiplier': 1},
        'emergency_mortality': {'numerator': 'deaths_24h', 'denominator': 'emergency_cases', 'multiplier': 100},
        'trauma_fatality': {'numerator': 'trauma_deaths', 'denominator': 'trauma_cases', 'multiplier': 100},
    },
    'Laboratory': {
        'turnaround_time': {'numerator': 'total_turnaround', 'denominator': 'total_tests', 'multiplier': 1},
        'rejection_rate': {'numerator': 'rejected', 'denominator': 'total_samples', 'multiplier': 100},
    },
    'Pharmacy': {
        'stockout_rate': {'numerator': 'days_out_of_stock', 'denominator': 'total_days', 'multiplier': 100},
        'fill_rate': {'numerator': 'quantity_supplied', 'denominator': 'quantity_ordered', 'multiplier': 100},
        'expiry_rate': {'numerator': 'expired_value', 'denominator': 'total_stock_value', 'multiplier': 100},
        'error_rate': {'numerator': 'errors', 'denominator': 'prescriptions', 'multiplier': 100},
    },
    'HIV_TB': {
        'hiv_yield': {'numerator': 'positive', 'denominator': 'tested', 'multiplier': 100},
        'art_linkage': {'numerator': 'started_art', 'denominator': 'positive', 'multiplier': 100},
        'viral_suppression': {'numerator': 'suppressed', 'denominator': 'tested', 'multiplier': 100},
        'tb_success': {'numerator': 'cured_completed', 'denominator': 'total_tb', 'multiplier': 100},
        'tb_detection': {'numerator': 'confirmed', 'denominator': 'expected', 'multiplier': 100},
    },
    'HR': {
        'attendance_rate': {'numerator': 'staff_present', 'denominator': 'staff_scheduled', 'multiplier': 100},
        'staff_patient_ratio': {'numerator': 'clinical_staff', 'denominator': 'patient_load', 'multiplier': 1},
        'cpd_training_rate': {'numerator': 'cpd_trained', 'denominator': 'total_staff', 'multiplier': 100},
        'vacancy_rate': {'numerator': 'unfilled_posts', 'denominator': 'approved_posts', 'multiplier': 100},
        'emr_doctors_rate': {'numerator': 'emr_doctors', 'denominator': 'total_doctors', 'multiplier': 100},
        'emr_nurses_rate': {'numerator': 'emr_nurses', 'denominator': 'total_nurses', 'multiplier': 100},
    },
    'Finance': {
        'budget_absorption': {'numerator': 'actual_expenditure', 'denominator': 'budget_allocation', 'multiplier': 100},
        'revenue_collection_rate': {'numerator': 'actual_revenue', 'denominator': 'revenue_target', 'multiplier': 100},
        'audit_compliance': {'numerator': 'items_compliant', 'denominator': 'total_audit_items', 'multiplier': 100},
        'procurement_lead_time': {'numerator': 'total_lead_days', 'denominator': 'procurement_count', 'multiplier': 1},
        'cost_per_patient': {'numerator': 'total_operational_cost', 'denominator': 'total_patients', 'multiplier': 1},
        'cash_flow_ratio': {'numerator': 'cash_inflow', 'denominator': 'cash_outflow', 'multiplier': 100},
    },
    'Clinical_EMR': {
        'avg_daily_doctor_patients': {'numerator': 'opd_patients_seen', 'denominator': 'emr_days_worked', 'multiplier': 1},
        'doctor_productivity': {'numerator': 'doctor_productivity_total', 'denominator': 'emr_days_worked', 'multiplier': 1},
        'avg_daily_nurse_rounds': {'numerator': 'nurse_rounds', 'denominator': 'emr_days_worked', 'multiplier': 1},
        'nurse_productivity': {'numerator': 'nurse_productivity_total', 'denominator': 'emr_days_worked', 'multiplier': 1},
        'emr_utilization_rate': {'numerator': 'emr_computer_usage', 'denominator': 'emr_days_worked', 'multiplier': 100},
        'doctor_patient_ratio': {'numerator': 'opd_patients_seen', 'denominator': 'total_doctors_emr', 'multiplier': 1},
        'nurse_patient_ratio': {'numerator': 'patients_served_nurses', 'denominator': 'total_nurses_emr', 'multiplier': 1},
        'surgical_load_index': {'numerator': 'major_surgeries', 'denominator': 'minor_surgeries', 'multiplier': 100},
    }
}

# Ward Data Model
class WardData(db.Model):
    __tablename__ = 'ward_data'
    id = db.Column(db.Integer, primary_key=True)
    ward_name = db.Column(db.String(50), nullable=False)
    reporting_year = db.Column(db.Integer, nullable=False)
    reporting_month = db.Column(db.Integer, nullable=False)
    data = db.Column(db.Text, nullable=False)
    entered_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    entered_at = db.Column(db.DateTime, default=datetime.utcnow)
    notes = db.Column(db.Text, nullable=True)
    user = db.relationship('User', foreign_keys=[entered_by])

# Create table
with app.app_context():
    db.create_all()

@app.route('/wards')
@login_required
def wards_list():
    return render_template('wards/list.html', wards=WARD_PARAMETERS, now=datetime.now())

@app.route('/wards/<ward_key>/dashboard')
@login_required
def ward_dashboard(ward_key):
    # Check if user has access to this ward
    if not current_user.can_access_ward(ward_key) and current_user.role != 'admin':
        flash('You do not have permission to access this department', 'danger')
        return redirect(url_for('wards_list'))
    
    if ward_key not in WARD_PARAMETERS:
        flash('Ward not found', 'danger')
        return redirect(url_for('wards_list'))
    
    ward = WARD_PARAMETERS[ward_key]
    year = request.args.get('year', datetime.now().year, type=int)
    month = request.args.get('month', datetime.now().month, type=int)
    
    existing = WardData.query.filter_by(ward_name=ward_key, reporting_year=year, reporting_month=month).first()
    
    if existing:
        current_data = json.loads(existing.data)
        entered_by = existing.user.full_name if existing.user else 'Unknown'
        entered_at = existing.entered_at
    else:
        current_data = {}
        entered_by = None
        entered_at = None
    
    # Get historical data
    historical = WardData.query.filter_by(ward_name=ward_key).order_by(
        WardData.reporting_year.desc(), WardData.reporting_month.desc()).limit(12).all()
    
    historical_data = []
    for h in historical:
        data = json.loads(h.data)
        data['_year'] = h.reporting_year
        data['_month'] = h.reporting_month
        data['_month_name'] = datetime(h.reporting_year, h.reporting_month, 1).strftime('%b %Y')
        historical_data.append(data)
    historical_data.reverse()
    
    # Get only calculated KPIs for cards display
    display_kpis = [k for k in ward['kpis'] if k.get('type') == 'calculated' or k.get('type') == 'direct']
    card_kpis = [k for k in ward['kpis'] if k.get('type') == 'calculated']
    
    months = ['January', 'February', 'March', 'April', 'May', 'June', 
              'July', 'August', 'September', 'October', 'November', 'December']
    
    # Generate year range from 2022 to 2035
    year_range = list(range(2022, 2036))
    
    # Special template for Clinical_EMR
    if ward_key == 'Clinical_EMR':
        return render_template('wards/clinical_emr_dashboard.html',
                              ward_key=ward_key, ward=ward, kpis=display_kpis,
                              card_kpis=card_kpis,
                              current_data=current_data, historical_data=historical_data,
                              entered_by=entered_by, entered_at=entered_at,
                              year=year, month=month, months=months, 
                              year_range=year_range,
                              now=datetime.now())
    
    return render_template('wards/dashboard.html',
                          ward_key=ward_key, ward=ward, kpis=display_kpis,
                          card_kpis=card_kpis,
                          current_data=current_data, historical_data=historical_data,
                          entered_by=entered_by, entered_at=entered_at,
                          year=year, month=month, months=months, 
                          year_range=year_range,
                          now=datetime.now())

@app.route('/wards/<ward_key>/entry', methods=['GET', 'POST'])
@login_required
def ward_entry(ward_key):
    # Check if user has access to this ward
    if not current_user.can_access_ward(ward_key) and current_user.role != 'admin':
        flash('You do not have permission to enter data for this department', 'danger')
        return redirect(url_for('wards_list'))
    
    if ward_key not in WARD_PARAMETERS:
        flash('Ward not found', 'danger')
        return redirect(url_for('wards_list'))
    
    ward = WARD_PARAMETERS[ward_key]
    formulas = KPI_FORMULAS.get(ward_key, {})
    
    if request.method == 'POST':
        year = request.form.get('year', type=int)
        month = request.form.get('month', type=int)
        notes = request.form.get('notes', '')
        
        # Collect all raw data from form (all direct input fields)
        raw_data = {}
        for kpi in ward['kpis']:
            if kpi.get('type') == 'direct':
                value = request.form.get(kpi['field'], 0)
                try:
                    raw_data[kpi['field']] = float(value) if '.' in value else int(value)
                except:
                    raw_data[kpi['field']] = 0
        
        # Calculate percentages for fields that have formulas
        calculated_data = raw_data.copy()
        for formula_field, formula in formulas.items():
            numerator = raw_data.get(formula['numerator'], 0)
            denominator = raw_data.get(formula['denominator'], 0)
            if denominator > 0:
                calculated_data[formula_field] = (numerator / denominator) * formula['multiplier']
            else:
                calculated_data[formula_field] = 0
        
        # Save calculated data
        existing = WardData.query.filter_by(
            ward_name=ward_key, 
            reporting_year=year, 
            reporting_month=month
        ).first()
        
        if existing:
            existing.data = json.dumps(calculated_data)
            existing.notes = notes
            existing.entered_at = datetime.utcnow()
            flash(f'Data updated for {ward["name"]}', 'success')
        else:
            new_entry = WardData(
                ward_name=ward_key,
                reporting_year=year,
                reporting_month=month,
                data=json.dumps(calculated_data),
                entered_by=current_user.id,
                notes=notes
            )
            db.session.add(new_entry)
            flash(f'Data saved for {ward["name"]}', 'success')
        
        db.session.commit()
        return redirect(url_for('ward_dashboard', ward_key=ward_key, year=year, month=month))
    
    year = request.args.get('year', datetime.now().year, type=int)
    month = request.args.get('month', datetime.now().month, type=int)
    
    existing = WardData.query.filter_by(
        ward_name=ward_key, 
        reporting_year=year, 
        reporting_month=month
    ).first()
    existing_data = json.loads(existing.data) if existing else {}
    
    months = ['January', 'February', 'March', 'April', 'May', 'June', 
              'July', 'August', 'September', 'October', 'November', 'December']
    
    # Generate year range from 2022 to 2035
    year_range = list(range(2022, 2036))
    
    # Get only direct input fields for the entry form
    input_kpis = [k for k in ward['kpis'] if k.get('type') == 'direct']
    
    # Use special template for Clinical_EMR
    if ward_key == 'Clinical_EMR':
        return render_template('wards/clinical_emr_entry.html',
                              ward_key=ward_key,
                              ward=ward,
                              input_kpis=input_kpis,
                              formulas=formulas,
                              existing_data=existing_data,
                              year=year,
                              month=month,
                              months=months,
                              year_range=year_range,
                              now=datetime.now())
    
    return render_template('wards/entry.html',
                          ward_key=ward_key,
                          ward=ward,
                          input_kpis=input_kpis,
                          formulas=formulas,
                          existing_data=existing_data,
                          year=year,
                          month=month,
                          months=months,
                          year_range=year_range,
                          now=datetime.now())

@app.route('/wards/<ward_key>/export')
@login_required
def ward_export(ward_key):
    if ward_key not in WARD_PARAMETERS:
        flash('Ward not found', 'danger')
        return redirect(url_for('wards_list'))
    
    if current_user.role != 'admin':
        flash('Export restricted to administrators', 'warning')
        return redirect(url_for('ward_dashboard', ward_key=ward_key))
    
    ward = WARD_PARAMETERS[ward_key]
    data = WardData.query.filter_by(ward_name=ward_key).order_by(
        WardData.reporting_year.desc(), WardData.reporting_month.desc()).all()
    
    output = StringIO()
    writer = csv.writer(output)
    header = ['Year', 'Month'] + [p['name'] for p in ward['kpis'] if p.get('type') == 'calculated'] + ['Notes', 'Entered By', 'Date']
    writer.writerow(header)
    
    for d in data:
        row_data = json.loads(d.data)
        row = [d.reporting_year, d.reporting_month]
        for p in ward['kpis']:
            if p.get('type') == 'calculated':
                row.append(row_data.get(p['field'], 0))
        row.append(d.notes or '')
        row.append(d.user.full_name if d.user else 'Unknown')
        row.append(d.entered_at.strftime('%Y-%m-%d') if d.entered_at else '')
        writer.writerow(row)
    
    output.seek(0)
    response = make_response(output.getvalue())
    response.headers['Content-Disposition'] = f'attachment; filename={ward_key}_data_export.csv'
    response.headers['Content-Type'] = 'text/csv'
    return response

# ===================== REFERRAL ROUTES =====================

@app.route('/referrals')
@login_required
def referral_list():
    status = request.args.get('status', 'all')
    query = Referral.query
    if status != 'all':
        query = query.filter_by(status=status)
    referrals = query.order_by(Referral.referral_date.desc()).all()
    return render_template('referrals/index.html', referrals=referrals, status=status)

@app.route('/referrals/new', methods=['GET', 'POST'])
@login_required
def referral_new():
    if request.method == 'POST':
        referral = Referral(
            patient_id=request.form.get('patient_id'),
            patient_name=request.form.get('patient_name'),
            from_ward=request.form.get('from_ward'),
            to_hospital_id=request.form.get('to_hospital_id', type=int),
            referral_reason=request.form.get('referral_reason'),
            referral_date=datetime.strptime(request.form.get('referral_date'), '%Y-%m-%d'),
            created_by=current_user.id, status='pending'
        )
        db.session.add(referral)
        db.session.commit()
        flash(f'Referral for {referral.patient_name} created', 'success')
        return redirect(url_for('referral_list'))
    
    hospitals = ReferralHospital.query.filter_by(is_active=True).all()
    return render_template('referrals/new.html', hospitals=hospitals)

@app.route('/referrals/<int:referral_id>/confirm', methods=['POST'])
@login_required
def referral_confirm(referral_id):
    referral = Referral.query.get_or_404(referral_id)
    referral.arrival_confirmed = True
    referral.actual_arrival_date = datetime.strptime(request.form.get('arrival_date'), '%Y-%m-%d')
    referral.status = 'confirmed'
    referral.confirmation_method = request.form.get('confirmation_method')
    db.session.commit()
    flash(f'Referral arrival confirmed for {referral.patient_name}', 'success')
    return redirect(url_for('referral_list'))

# ===================== ADMIN ROUTES =====================

@app.route('/admin/users')
@login_required
def admin_users():
    if current_user.role != 'admin':
        flash('Access denied', 'danger')
        return redirect(url_for('dashboard'))
    users = User.query.all()
    return render_template('admin/users.html', users=users, now=datetime.now())

@app.route('/admin/users/new', methods=['POST'])
@login_required
def admin_user_new():
    if current_user.role != 'admin':
        flash('Access denied', 'danger')
        return redirect(url_for('dashboard'))
    
    # Validate password match
    if request.form.get('password') != request.form.get('confirm_password'):
        flash('Passwords do not match', 'danger')
        return redirect(url_for('admin_users'))
    
    # Check if user exists
    if User.query.filter_by(username=request.form.get('username')).first():
        flash('Username already exists', 'danger')
        return redirect(url_for('admin_users'))
    
    if User.query.filter_by(email=request.form.get('email')).first():
        flash('Email already registered', 'danger')
        return redirect(url_for('admin_users'))
    
    # Get allowed wards
    allowed_wards = request.form.getlist('allowed_wards')
    
    user = User(
        username=request.form.get('username'),
        full_name=request.form.get('full_name'),
        email=request.form.get('email'),
        phone_number=request.form.get('phone_number'),
        role=request.form.get('role'),
        department=request.form.get('department'),
        allowed_wards=json.dumps(allowed_wards) if allowed_wards else '[]',
        password_hash=generate_password_hash(request.form.get('password')),
        password_set_date=datetime.utcnow(),
        password_expiry_days=int(request.form.get('password_expiry_days', 90)),
        created_by=current_user.id,
        is_active=True,
        is_paused=False
    )
    
    db.session.add(user)
    db.session.commit()
    
    # Log the action
    log = UserAccessLog(
        user_id=user.id,
        action='user_created',
        status='success',
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent'),
        details=f'User created by {current_user.username}'
    )
    db.session.add(log)
    db.session.commit()
    
    flash(f'User {user.username} created successfully', 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/users/<int:user_id>/edit')
@login_required
def admin_user_edit_json(user_id):
    """Get user data for editing"""
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    
    user = User.query.get_or_404(user_id)
    return jsonify({
        'id': user.id,
        'username': user.username,
        'full_name': user.full_name,
        'email': user.email,
        'phone_number': user.phone_number,
        'role': user.role,
        'department': user.department,
        'allowed_wards': json.loads(user.allowed_wards) if user.allowed_wards else [],
        'password_expiry_days': user.password_expiry_days
    })

@app.route('/admin/users/<int:user_id>/update', methods=['POST'])
@login_required
def admin_user_update(user_id):
    """Update user information"""
    if current_user.role != 'admin':
        flash('Access denied', 'danger')
        return redirect(url_for('admin_users'))
    
    user = User.query.get_or_404(user_id)
    
    user.username = request.form.get('username')
    user.full_name = request.form.get('full_name')
    user.email = request.form.get('email')
    user.phone_number = request.form.get('phone_number')
    user.role = request.form.get('role')
    user.department = request.form.get('department')
    user.password_expiry_days = request.form.get('password_expiry_days', type=int)
    
    db.session.commit()
    
    # Log the action
    log = UserAccessLog(
        user_id=user.id,
        action='user_updated',
        status='success',
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent'),
        details=f'User updated by {current_user.username}'
    )
    db.session.add(log)
    db.session.commit()
    
    flash(f'User {user.username} updated successfully', 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/users/<int:user_id>/pause')
@login_required
def admin_user_pause(user_id):
    """Pause user account"""
    if current_user.role != 'admin':
        flash('Access denied', 'danger')
        return redirect(url_for('admin_users'))
    
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('You cannot pause your own account', 'danger')
        return redirect(url_for('admin_users'))
    
    user.is_paused = True
    user.is_active = False
    
    # Log the action
    log = UserAccessLog(
        user_id=user.id,
        action='session_paused',
        status='paused',
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent'),
        details=f'Account paused by {current_user.username}'
    )
    db.session.add(log)
    db.session.commit()
    
    flash(f'User {user.username} account paused', 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/users/<int:user_id>/resume')
@login_required
def admin_user_resume(user_id):
    """Resume user account"""
    if current_user.role != 'admin':
        flash('Access denied', 'danger')
        return redirect(url_for('admin_users'))
    
    user = User.query.get_or_404(user_id)
    user.is_paused = False
    user.is_active = True
    
    # Log the action
    log = UserAccessLog(
        user_id=user.id,
        action='session_resumed',
        status='success',
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent'),
        details=f'Account resumed by {current_user.username}'
    )
    db.session.add(log)
    db.session.commit()
    
    flash(f'User {user.username} account resumed', 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/users/<int:user_id>/reset-password')
@login_required
def admin_user_reset_password(user_id):
    """Reset user password"""
    if current_user.role != 'admin':
        flash('Access denied', 'danger')
        return redirect(url_for('admin_users'))
    
    user = User.query.get_or_404(user_id)
    new_password = request.args.get('password')
    
    if new_password and len(new_password) >= 8:
        user.password_hash = generate_password_hash(new_password)
        user.password_set_date = datetime.utcnow()
        
        # Log password reset
        log = UserAccessLog(
            user_id=user.id,
            action='password_change',
            status='success',
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent'),
            details=f'Password reset by {current_user.username}'
        )
        db.session.add(log)
        db.session.commit()
        
        flash(f'Password reset for {user.username}', 'success')
    else:
        flash('Password must be at least 8 characters', 'danger')
    
    return redirect(url_for('admin_users'))

@app.route('/admin/users/<int:user_id>/delete')
@login_required
def admin_user_delete(user_id):
    """Delete user account"""
    if current_user.role != 'admin':
        flash('Access denied', 'danger')
        return redirect(url_for('admin_users'))
    
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('You cannot delete your own account', 'danger')
        return redirect(url_for('admin_users'))
    
    username = user.username
    
    # Log before deletion
    log = UserAccessLog(
        user_id=user.id,
        action='user_deleted',
        status='success',
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent'),
        details=f'User deleted by {current_user.username}'
    )
    db.session.add(log)
    db.session.commit()
    
    db.session.delete(user)
    db.session.commit()
    
    flash(f'User {username} deleted', 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/users/export')
@login_required
def admin_users_export():
    if current_user.role != 'admin':
        flash('Access denied', 'danger')
        return redirect(url_for('dashboard'))
    
    users = User.query.all()
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['Username', 'Full Name', 'Email', 'Phone', 'Role', 'Department', 'Status', 'Last Login', 'Created At'])
    for user in users:
        status = 'Paused' if user.is_paused else ('Active' if user.is_active else 'Inactive')
        writer.writerow([
            user.username, 
            user.full_name, 
            user.email or '', 
            user.phone_number or '',
            user.role,
            user.department or '',
            status,
            user.last_login.strftime('%Y-%m-%d %H:%M') if user.last_login else '',
            user.created_at.strftime('%Y-%m-%d') if user.created_at else ''
        ])
    output.seek(0)
    response = make_response(output.getvalue())
    response.headers['Content-Disposition'] = 'attachment; filename=krrh_users.csv'
    response.headers['Content-Type'] = 'text/csv'
    return response

@app.route('/admin/logs')
@login_required
def admin_logs():
    if current_user.role != 'admin':
        flash('Access denied', 'danger')
        return redirect(url_for('dashboard'))
    days = request.args.get('days', 30, type=int)
    since = datetime.utcnow() - timedelta(days=days)
    logs = UserAccessLog.query.filter(UserAccessLog.login_time >= since).order_by(UserAccessLog.login_time.desc()).all()
    return render_template('admin/logs.html', logs=logs, days=days, now=datetime.now())

# ===================== API ENDPOINTS =====================

@app.route('/api/ward-data/<ward_key>')
@login_required
def api_ward_data(ward_key):
    """API endpoint for executive dashboard"""
    if ward_key not in WARD_PARAMETERS:
        return jsonify({})
    
    year = request.args.get('year', datetime.now().year, type=int)
    month = request.args.get('month', datetime.now().month, type=int)
    
    existing = WardData.query.filter_by(
        ward_name=ward_key, 
        reporting_year=year, 
        reporting_month=month
    ).first()
    
    if existing:
        return jsonify(json.loads(existing.data))
    return jsonify({})

# ===================== EXECUTIVE DASHBOARD =====================

@app.route('/executive-dashboard')
@login_required
def executive_dashboard():
    """Executive Dashboard - PowerBI style overview"""
    return render_template('executive_dashboard.html', now=datetime.now())

# ===================== RECEPTION =====================

@app.route('/reception')
def reception_view():
    return render_template('reception/index.html', now=datetime.now())

# ===================== ERROR HANDLERS =====================

@app.errorhandler(404)
def not_found_error(error):
    return render_template('errors/404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('errors/500.html'), 500

# ===================== MAIN =====================

if __name__ == '__main__':
    print("\n" + "="*60)
    print("🏥 KRRH InsightHub - Hospital Management System")
    print("="*60)
    
    create_directories()
    init_database()

    print(f"\n🌐 Access URLs:")
    print(f"   Home: http://127.0.0.1:8080/")
    print(f"   Login: http://127.0.0.1:8080/login")
    print(f"   Dashboard: http://127.0.0.1:8080/dashboard")
    print(f"   Wards: http://127.0.0.1:8080/wards")
    print(f"   Executive Dashboard: http://127.0.0.1:8080/executive-dashboard")
    print(f"   Admin Users: http://127.0.0.1:8080/admin/users")
    print(f"   Reception: http://127.0.0.1:8080/reception")
    print(f"\n👤 Default Admin: admin / Admin@123")
    print("="*60 + "\n")
    
    app.run(debug=True, host='0.0.0.0', port=8080)

