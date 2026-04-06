# models.py
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
import json

db = SQLAlchemy()

# ===================== USER MANAGEMENT =====================

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone_number = db.Column(db.String(20), nullable=True)  # Added phone number
    password_hash = db.Column(db.String(200), nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(50), nullable=False, default='data_entry')  # admin, manager, data_entry
    department = db.Column(db.String(100), nullable=True)
    
    # New fields for enhanced user management
    allowed_wards = db.Column(db.Text, default='[]')  # JSON array of allowed wards
    is_active = db.Column(db.Boolean, default=True)
    is_paused = db.Column(db.Boolean, default=False)  # Account can be paused
    password_set_date = db.Column(db.DateTime, default=datetime.utcnow)
    password_expiry_days = db.Column(db.Integer, default=90)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)
    last_login = db.Column(db.DateTime, nullable=True)
    
    # Relationships
    access_logs = db.relationship('UserAccessLog', backref='user', lazy=True, cascade='all, delete-orphan')
    kpi_entries = db.relationship('KPIEntry', foreign_keys='KPIEntry.entered_by', backref='entered_by_user', lazy=True)
    verified_entries = db.relationship('KPIEntry', foreign_keys='KPIEntry.verified_by', backref='verifier', lazy=True)
    
    # Self-reference for created_by
    creator = db.relationship('User', remote_side=[id], foreign_keys=[created_by], backref='created_users')
    
    def get_allowed_wards(self):
        """Get allowed wards as list"""
        try:
            return json.loads(self.allowed_wards) if self.allowed_wards else []
        except:
            return []
    
    def set_allowed_wards(self, wards_list):
        """Set allowed wards from list"""
        self.allowed_wards = json.dumps(wards_list)
    
    def can_access_ward(self, ward_key):
        """Check if user can access a specific ward"""
        if self.role == 'admin':
            return True
        allowed = self.get_allowed_wards()
        return not allowed or ward_key in allowed
    
    def is_password_expired(self):
        """Check if password is expired"""
        if self.password_set_date:
            days_since = (datetime.utcnow() - self.password_set_date).days
            return days_since >= self.password_expiry_days
        return False
    
    def days_until_password_expiry(self):
        """Get days until password expires"""
        if self.password_set_date:
            days_since = (datetime.utcnow() - self.password_set_date).days
            return max(0, self.password_expiry_days - days_since)
        return self.password_expiry_days
    
    def __repr__(self):
        return f'<User {self.username}>'

class UserAccessLog(db.Model):
    __tablename__ = 'user_access_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    login_time = db.Column(db.DateTime, default=datetime.utcnow)
    logout_time = db.Column(db.DateTime, nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.String(200), nullable=True)
    action = db.Column(db.String(50), nullable=True)  # login, logout, password_change, session_paused, user_created, user_updated, user_deleted
    status = db.Column(db.String(20), nullable=True)  # success, failed, expired, paused
    details = db.Column(db.Text, nullable=True)  # Additional details about the action
    
    def __repr__(self):
        return f'<AccessLog User:{self.user_id} Action:{self.action} at {self.login_time}>'

# ===================== KPI DEFINITIONS =====================

class KPICategory(db.Model):
    __tablename__ = 'kpi_categories'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.Text, nullable=True)
    icon = db.Column(db.String(50), default='📊')
    display_order = db.Column(db.Integer, default=0)
    
    kpis = db.relationship('KPIDefinition', backref='category', lazy=True)
    
    def __repr__(self):
        return f'<KPICategory {self.name}>'

class KPIDefinition(db.Model):
    __tablename__ = 'kpi_definitions'
    
    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey('kpi_categories.id'), nullable=False)
    
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    
    calculation_type = db.Column(db.String(50), nullable=False)
    reporting_frequency = db.Column(db.String(20), nullable=False)
    
    numerator_field = db.Column(db.String(100), nullable=True)
    denominator_field = db.Column(db.String(100), nullable=True)
    multiplier = db.Column(db.Float, default=1.0)
    
    target_value = db.Column(db.Float, nullable=True)
    warning_threshold = db.Column(db.Float, nullable=True)
    critical_threshold = db.Column(db.Float, nullable=True)
    
    unit = db.Column(db.String(20), default='')
    decimal_places = db.Column(db.Integer, default=1)
    is_active = db.Column(db.Boolean, default=True)
    display_order = db.Column(db.Integer, default=0)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)
    
    entries = db.relationship('KPIEntry', backref='kpi', lazy=True)
    
    def calculate_value(self, numerator, denominator):
        if denominator == 0:
            return 0
        
        if self.calculation_type == 'count':
            return numerator
        elif self.calculation_type == 'percentage':
            return (numerator / denominator) * 100
        elif self.calculation_type == 'rate':
            return (numerator / denominator) * self.multiplier
        elif self.calculation_type == 'ratio':
            return numerator / denominator
        
        return 0
    
    def get_status(self, value):
        if self.target_value:
            if self.calculation_type in ['percentage', 'rate']:
                if value >= self.target_value:
                    return 'success'
                elif value >= (self.target_value * 0.8):
                    return 'warning'
                else:
                    return 'danger'
            else:
                if value <= self.target_value:
                    return 'success'
                elif value <= (self.target_value * 1.2):
                    return 'warning'
                else:
                    return 'danger'
        return 'info'
    
    def __repr__(self):
        return f'<KPIDefinition {self.name}>'

class KPIEntry(db.Model):
    __tablename__ = 'kpi_entries'
    
    id = db.Column(db.Integer, primary_key=True)
    kpi_id = db.Column(db.Integer, db.ForeignKey('kpi_definitions.id'), nullable=False)
    entered_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    reporting_year = db.Column(db.Integer, nullable=False)
    reporting_month = db.Column(db.Integer, nullable=True)
    reporting_quarter = db.Column(db.Integer, nullable=True)
    
    numerator_value = db.Column(db.Float, nullable=False, default=0)
    denominator_value = db.Column(db.Float, nullable=False, default=1)
    calculated_value = db.Column(db.Float, nullable=True)
    
    additional_data = db.Column(db.Text, nullable=True)
    
    entry_date = db.Column(db.DateTime, default=datetime.utcnow)
    notes = db.Column(db.Text, nullable=True)
    is_verified = db.Column(db.Boolean, default=False)
    verified_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    verified_at = db.Column(db.DateTime, nullable=True)
    
    def save(self):
        self.calculated_value = self.kpi.calculate_value(self.numerator_value, self.denominator_value)
        db.session.add(self)
        db.session.commit()
    
    def __repr__(self):
        return f'<KPIEntry {self.kpi.name} {self.reporting_year}-{self.reporting_month}>'

# ===================== REFERRAL TRACKING =====================

class ReferralHospital(db.Model):
    __tablename__ = 'referral_hospitals'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    code = db.Column(db.String(20), nullable=False, unique=True)
    location = db.Column(db.String(200), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    
    referrals = db.relationship('Referral', backref='to_hospital', lazy=True)
    
    def __repr__(self):
        return f'<ReferralHospital {self.name}>'

class Referral(db.Model):
    __tablename__ = 'referrals'
    
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.String(50), nullable=False)
    patient_name = db.Column(db.String(100), nullable=False)
    
    from_ward = db.Column(db.String(100), nullable=False)
    to_hospital_id = db.Column(db.Integer, db.ForeignKey('referral_hospitals.id'), nullable=False)
    referral_reason = db.Column(db.Text, nullable=False)
    
    referral_date = db.Column(db.DateTime, nullable=False)
    estimated_arrival_date = db.Column(db.DateTime, nullable=True)
    actual_arrival_date = db.Column(db.DateTime, nullable=True)
    feedback_date = db.Column(db.DateTime, nullable=True)
    
    arrival_confirmed = db.Column(db.Boolean, default=False)
    confirmation_method = db.Column(db.String(50), nullable=True)
    outcome = db.Column(db.String(100), nullable=True)
    outcome_notes = db.Column(db.Text, nullable=True)
    
    status = db.Column(db.String(50), default='pending')
    
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)
    
    creator = db.relationship('User', foreign_keys=[created_by], backref='created_referrals')
    
    @property
    def completion_rate(self):
        return self.arrival_confirmed
    
    def __repr__(self):
        return f'<Referral {self.patient_id} to {self.to_hospital.name}>'

# ===================== PATIENT SATISFACTION =====================

class PatientSatisfactionSurvey(db.Model):
    __tablename__ = 'patient_satisfaction'
    
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.String(50), nullable=False)
    ward = db.Column(db.String(100), nullable=False)
    
    survey_date = db.Column(db.DateTime, default=datetime.utcnow)
    discharge_date = db.Column(db.DateTime, nullable=True)
    
    waiting_time_rating = db.Column(db.Integer, nullable=False)
    staff_courtesy_rating = db.Column(db.Integer, nullable=False)
    cleanliness_rating = db.Column(db.Integer, nullable=False)
    communication_rating = db.Column(db.Integer, nullable=False)
    overall_rating = db.Column(db.Integer, nullable=False)
    
    would_recommend = db.Column(db.Boolean, default=True)
    comments = db.Column(db.Text, nullable=True)
    
    entered_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    entered_by_user = db.relationship('User', foreign_keys=[entered_by])
    
    @property
    def average_score(self):
        scores = [
            self.waiting_time_rating,
            self.staff_courtesy_rating,
            self.cleanliness_rating,
            self.communication_rating,
            self.overall_rating
        ]
        return sum(scores) / len(scores)
    
    def __repr__(self):
        return f'<Survey Patient:{self.patient_id} Score:{self.average_score}>'

# ===================== INITIAL DATA SETUP =====================

def create_initial_kpi_categories():
    categories = [
        {'name': 'Outpatient Department (OPD)', 'icon': '🚪', 'display_order': 1},
        {'name': 'Inpatient Department', 'icon': '🛏️', 'display_order': 2},
        {'name': 'Maternity / Obstetrics', 'icon': '🤰', 'display_order': 3},
        {'name': 'Paediatrics', 'icon': '🧒', 'display_order': 4},
        {'name': 'Surgery / Theatre', 'icon': '🔪', 'display_order': 5},
        {'name': 'Emergency / Casualty', 'icon': '🚑', 'display_order': 6},
        {'name': 'Laboratory', 'icon': '🔬', 'display_order': 7},
        {'name': 'Pharmacy', 'icon': '💊', 'display_order': 8},
        {'name': 'HIV / TB Clinic', 'icon': '❤️', 'display_order': 9},
        {'name': 'Human Resources', 'icon': '👥', 'display_order': 10},
        {'name': 'Finance & Administration', 'icon': '💰', 'display_order': 11},
    ]
    
    for cat in categories:
        if not KPICategory.query.filter_by(name=cat['name']).first():
            category = KPICategory(**cat)
            db.session.add(category)
    
    db.session.commit()

def create_initial_kpis():
    categories = {cat.name: cat.id for cat in KPICategory.query.all()}
    
    kpis = [
        # OPD
        {'category': 'Outpatient Department (OPD)', 'name': 'OPD Utilization Rate', 
         'calculation_type': 'rate', 'numerator_field': 'total_opd_visits', 
         'denominator_field': 'catchment_population', 'multiplier': 1000,
         'unit': 'per 1000', 'reporting_frequency': 'monthly'},
        
        {'category': 'Outpatient Department (OPD)', 'name': 'Average Waiting Time',
         'calculation_type': 'rate', 'numerator_field': 'total_waiting_time',
         'denominator_field': 'total_patients', 'unit': 'minutes', 'reporting_frequency': 'monthly'},
        
        {'category': 'Outpatient Department (OPD)', 'name': '% Patients Properly Triaged',
         'calculation_type': 'percentage', 'numerator_field': 'patients_triaged',
         'denominator_field': 'total_patients', 'unit': '%', 'reporting_frequency': 'monthly',
         'target_value': 95},
        
        {'category': 'Outpatient Department (OPD)', 'name': 'Referral Completion Rate',
         'calculation_type': 'percentage', 'numerator_field': 'referrals_completed',
         'denominator_field': 'total_referrals', 'unit': '%', 'reporting_frequency': 'quarterly',
         'target_value': 90},
        
        {'category': 'Outpatient Department (OPD)', 'name': 'Patient Satisfaction Score',
         'calculation_type': 'percentage', 'unit': '%', 'reporting_frequency': 'quarterly',
         'target_value': 80},
        
        # Inpatient
        {'category': 'Inpatient Department', 'name': 'Bed Occupancy Rate',
         'calculation_type': 'percentage', 'numerator_field': 'inpatient_days',
         'denominator_field': 'available_bed_days', 'unit': '%', 'reporting_frequency': 'monthly',
         'target_value': 85},
        
        {'category': 'Inpatient Department', 'name': 'Average Length of Stay',
         'calculation_type': 'rate', 'numerator_field': 'total_inpatient_days',
         'denominator_field': 'total_discharges', 'unit': 'days', 'reporting_frequency': 'monthly'},
        
        {'category': 'Inpatient Department', 'name': 'Inpatient Mortality Rate',
         'calculation_type': 'percentage', 'numerator_field': 'deaths',
         'denominator_field': 'admissions', 'unit': '%', 'reporting_frequency': 'monthly',
         'target_value': 2},
        
        {'category': 'Inpatient Department', 'name': '48-Hour Mortality Rate',
         'calculation_type': 'percentage', 'numerator_field': 'deaths_within_48h',
         'denominator_field': 'admissions', 'unit': '%', 'reporting_frequency': 'monthly',
         'target_value': 1},
        
        {'category': 'Inpatient Department', 'name': 'Readmission Rate',
         'calculation_type': 'percentage', 'numerator_field': 'readmissions',
         'denominator_field': 'discharges', 'unit': '%', 'reporting_frequency': 'quarterly',
         'target_value': 5},
        
        # Maternity
        {'category': 'Maternity / Obstetrics', 'name': 'Number of Deliveries',
         'calculation_type': 'count', 'unit': '', 'reporting_frequency': 'monthly'},
        
        {'category': 'Maternity / Obstetrics', 'name': 'Cesarean Section Rate',
         'calculation_type': 'percentage', 'numerator_field': 'c_sections',
         'denominator_field': 'total_deliveries', 'unit': '%', 'reporting_frequency': 'monthly',
         'target_value': 15},
        
        {'category': 'Maternity / Obstetrics', 'name': 'Maternal Mortality Ratio',
         'calculation_type': 'rate', 'numerator_field': 'maternal_deaths',
         'denominator_field': 'live_births', 'multiplier': 100000,
         'unit': 'per 100,000', 'reporting_frequency': 'quarterly',
         'target_value': 100},
        
        {'category': 'Maternity / Obstetrics', 'name': '% ANC 1st Visit Before 12 Weeks',
         'calculation_type': 'percentage', 'numerator_field': 'anc_before_12w',
         'denominator_field': 'total_anc_visits', 'unit': '%', 'reporting_frequency': 'monthly',
         'target_value': 70},
        
        {'category': 'Maternity / Obstetrics', 'name': 'IPT3 Coverage',
         'calculation_type': 'percentage', 'numerator_field': 'ipt3_received',
         'denominator_field': 'pregnant_women', 'unit': '%', 'reporting_frequency': 'monthly',
         'target_value': 80},
        
        {'category': 'Maternity / Obstetrics', 'name': 'Postnatal Care Within 48 Hours',
         'calculation_type': 'percentage', 'numerator_field': 'postnatal_48h',
         'denominator_field': 'deliveries', 'unit': '%', 'reporting_frequency': 'monthly',
         'target_value': 90},
        
        # Paediatrics
        {'category': 'Paediatrics', 'name': 'Under-5 Admissions',
         'calculation_type': 'count', 'unit': '', 'reporting_frequency': 'monthly'},
        
        {'category': 'Paediatrics', 'name': 'Under-5 Mortality Rate',
         'calculation_type': 'percentage', 'numerator_field': 'under5_deaths',
         'denominator_field': 'under5_admissions', 'unit': '%', 'reporting_frequency': 'monthly',
         'target_value': 3},
        
        {'category': 'Paediatrics', 'name': 'DPT3 Coverage',
         'calculation_type': 'percentage', 'numerator_field': 'dpt3_received',
         'denominator_field': 'eligible_children', 'unit': '%', 'reporting_frequency': 'monthly',
         'target_value': 90},
        
        {'category': 'Paediatrics', 'name': 'Measles Coverage',
         'calculation_type': 'percentage', 'numerator_field': 'measles_vaccinated',
         'denominator_field': 'eligible_children', 'unit': '%', 'reporting_frequency': 'monthly',
         'target_value': 90},
        
        {'category': 'Paediatrics', 'name': 'Severe Malaria Case Fatality Rate',
         'calculation_type': 'percentage', 'numerator_field': 'malaria_deaths',
         'denominator_field': 'severe_malaria_cases', 'unit': '%', 'reporting_frequency': 'monthly',
         'target_value': 2},
        
        # Surgery
        {'category': 'Surgery / Theatre', 'name': 'Number of Major Surgeries',
         'calculation_type': 'count', 'unit': '', 'reporting_frequency': 'monthly'},
        
        {'category': 'Surgery / Theatre', 'name': 'Surgical Site Infection Rate',
         'calculation_type': 'percentage', 'numerator_field': 'ssi_cases',
         'denominator_field': 'surgeries', 'unit': '%', 'reporting_frequency': 'monthly',
         'target_value': 2},
        
        {'category': 'Surgery / Theatre', 'name': 'Theatre Utilization Rate',
         'calculation_type': 'percentage', 'numerator_field': 'hours_used',
         'denominator_field': 'available_hours', 'unit': '%', 'reporting_frequency': 'monthly',
         'target_value': 75},
        
        {'category': 'Surgery / Theatre', 'name': 'Post-Operative Mortality (24 hrs)',
         'calculation_type': 'percentage', 'numerator_field': 'postop_deaths_24h',
         'denominator_field': 'surgeries', 'unit': '%', 'reporting_frequency': 'monthly',
         'target_value': 0.5},
        
        {'category': 'Surgery / Theatre', 'name': 'Cancelled Surgeries Rate',
         'calculation_type': 'percentage', 'numerator_field': 'cancelled_surgeries',
         'denominator_field': 'scheduled_surgeries', 'unit': '%', 'reporting_frequency': 'monthly',
         'target_value': 5},
        
        # Emergency
        {'category': 'Emergency / Casualty', 'name': 'Triage Compliance Rate',
         'calculation_type': 'percentage', 'numerator_field': 'triaged_correctly',
         'denominator_field': 'total_emergency', 'unit': '%', 'reporting_frequency': 'monthly',
         'target_value': 95},
        
        {'category': 'Emergency / Casualty', 'name': 'Emergency Response Time',
         'calculation_type': 'rate', 'numerator_field': 'total_response_time',
         'denominator_field': 'emergency_cases', 'unit': 'minutes', 'reporting_frequency': 'monthly',
         'target_value': 5},
        
        {'category': 'Emergency / Casualty', 'name': 'Mortality Within 24 Hours',
         'calculation_type': 'percentage', 'numerator_field': 'emergency_deaths_24h',
         'denominator_field': 'emergency_admissions', 'unit': '%', 'reporting_frequency': 'monthly',
         'target_value': 2},
        
        {'category': 'Emergency / Casualty', 'name': 'Trauma Case Fatality Rate',
         'calculation_type': 'percentage', 'numerator_field': 'trauma_deaths',
         'denominator_field': 'trauma_admissions', 'unit': '%', 'reporting_frequency': 'quarterly',
         'target_value': 3},
        
        # Laboratory
        {'category': 'Laboratory', 'name': 'Test Turnaround Time',
         'calculation_type': 'rate', 'numerator_field': 'total_turnaround_time',
         'denominator_field': 'total_tests', 'unit': 'hours', 'reporting_frequency': 'monthly',
         'target_value': 4},
        
        {'category': 'Laboratory', 'name': 'External Quality Assessment Score',
         'calculation_type': 'percentage', 'unit': '%', 'reporting_frequency': 'quarterly',
         'target_value': 90},
        
        {'category': 'Laboratory', 'name': 'Sample Rejection Rate',
         'calculation_type': 'percentage', 'numerator_field': 'rejected_samples',
         'denominator_field': 'total_samples', 'unit': '%', 'reporting_frequency': 'monthly',
         'target_value': 2},
        
        {'category': 'Laboratory', 'name': 'Equipment Downtime',
         'calculation_type': 'count', 'unit': 'days', 'reporting_frequency': 'monthly',
         'target_value': 2},
        
        # Pharmacy
        {'category': 'Pharmacy', 'name': 'Stock-Out Rate (Essential Medicines)',
         'calculation_type': 'percentage', 'numerator_field': 'days_out_of_stock',
         'denominator_field': 'total_days', 'unit': '%', 'reporting_frequency': 'monthly',
         'target_value': 2},
        
        {'category': 'Pharmacy', 'name': 'Order Fill Rate',
         'calculation_type': 'percentage', 'numerator_field': 'quantity_supplied',
         'denominator_field': 'quantity_ordered', 'unit': '%', 'reporting_frequency': 'monthly',
         'target_value': 95},
        
        {'category': 'Pharmacy', 'name': 'Expiry Rate',
         'calculation_type': 'percentage', 'numerator_field': 'expired_value',
         'denominator_field': 'total_stock_value', 'unit': '%', 'reporting_frequency': 'quarterly',
         'target_value': 1},
        
        {'category': 'Pharmacy', 'name': 'Prescription Error Rate',
         'calculation_type': 'percentage', 'numerator_field': 'prescription_errors',
         'denominator_field': 'prescriptions_reviewed', 'unit': '%', 'reporting_frequency': 'monthly',
         'target_value': 0.5},
        
        # HIV/TB
        {'category': 'HIV / TB Clinic', 'name': 'HIV Testing Yield',
         'calculation_type': 'percentage', 'numerator_field': 'positive_tests',
         'denominator_field': 'total_tested', 'unit': '%', 'reporting_frequency': 'monthly'},
        
        {'category': 'HIV / TB Clinic', 'name': 'Linkage to ART',
         'calculation_type': 'percentage', 'numerator_field': 'started_art',
         'denominator_field': 'positive_tests', 'unit': '%', 'reporting_frequency': 'monthly',
         'target_value': 95},
        
        {'category': 'HIV / TB Clinic', 'name': 'Viral Suppression Rate',
         'calculation_type': 'percentage', 'numerator_field': 'suppressed',
         'denominator_field': 'tested', 'unit': '%', 'reporting_frequency': 'quarterly',
         'target_value': 90},
        
        {'category': 'HIV / TB Clinic', 'name': 'TB Treatment Success Rate',
         'calculation_type': 'percentage', 'numerator_field': 'cured_completed',
         'denominator_field': 'total_tb_patients', 'unit': '%', 'reporting_frequency': 'quarterly',
         'target_value': 85},
        
        {'category': 'HIV / TB Clinic', 'name': 'TB Case Detection Rate',
         'calculation_type': 'percentage', 'numerator_field': 'confirmed_cases',
         'denominator_field': 'expected_cases', 'unit': '%', 'reporting_frequency': 'monthly',
         'target_value': 70},
        
        # Human Resources
        {'category': 'Human Resources', 'name': 'Staff Attendance Rate',
         'calculation_type': 'percentage', 'numerator_field': 'staff_present',
         'denominator_field': 'staff_scheduled', 'unit': '%', 'reporting_frequency': 'monthly',
         'target_value': 95},
        
        {'category': 'Human Resources', 'name': 'Staff-to-Patient Ratio',
         'calculation_type': 'ratio', 'numerator_field': 'clinical_staff',
         'denominator_field': 'patient_load', 'reporting_frequency': 'monthly'},
        
        {'category': 'Human Resources', 'name': '% Staff with CPD Training',
         'calculation_type': 'percentage', 'numerator_field': 'staff_trained',
         'denominator_field': 'total_staff', 'unit': '%', 'reporting_frequency': 'quarterly',
         'target_value': 50},
        
        {'category': 'Human Resources', 'name': 'Vacancy Rate',
         'calculation_type': 'percentage', 'numerator_field': 'unfilled_posts',
         'denominator_field': 'approved_posts', 'unit': '%', 'reporting_frequency': 'quarterly',
         'target_value': 10},
        
        # Finance
        {'category': 'Finance & Administration', 'name': 'Budget Absorption Rate',
         'calculation_type': 'percentage', 'numerator_field': 'expenditure',
         'denominator_field': 'budget_allocation', 'unit': '%', 'reporting_frequency': 'quarterly',
         'target_value': 90},
        
        {'category': 'Finance & Administration', 'name': 'Revenue Collection vs Target',
         'calculation_type': 'percentage', 'numerator_field': 'actual_revenue',
         'denominator_field': 'target_revenue', 'unit': '%', 'reporting_frequency': 'monthly',
         'target_value': 100},
        
        {'category': 'Finance & Administration', 'name': 'Audit Compliance Score',
         'calculation_type': 'percentage', 'unit': '%', 'reporting_frequency': 'annual',
         'target_value': 95},
        
        {'category': 'Finance & Administration', 'name': 'Procurement Lead Time',
         'calculation_type': 'rate', 'numerator_field': 'total_lead_days',
         'denominator_field': 'procurement_requests', 'unit': 'days', 'reporting_frequency': 'monthly',
         'target_value': 30},
    ]
    
    for kpi in kpis:
        category_name = kpi.pop('category')
        category_id = categories.get(category_name)
        
        if category_id and not KPIDefinition.query.filter_by(name=kpi['name']).first():
            kpi_def = KPIDefinition(category_id=category_id, **kpi)
            db.session.add(kpi_def)
    
    db.session.commit()