# models.py - Using names that match app.py imports
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
    phone_number = db.Column(db.String(20), nullable=True)
    password_hash = db.Column(db.String(200), nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(50), nullable=False, default='data_entry')
    department = db.Column(db.String(100), nullable=True)
    
    allowed_wards = db.Column(db.Text, default='[]')
    is_active = db.Column(db.Boolean, default=True)
    is_paused = db.Column(db.Boolean, default=False)
    password_set_date = db.Column(db.DateTime, default=datetime.utcnow)
    password_expiry_days = db.Column(db.Integer, default=90)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)
    last_login = db.Column(db.DateTime, nullable=True)
    
    access_logs = db.relationship('UserAccessLog', backref='user', lazy=True, cascade='all, delete-orphan')
    kpi_entries = db.relationship('KPIEntry', foreign_keys='KPIEntry.entered_by', backref='entered_by_user', lazy=True)
    verified_entries = db.relationship('KPIEntry', foreign_keys='KPIEntry.verified_by', backref='verifier', lazy=True)
    creator = db.relationship('User', remote_side=[id], foreign_keys=[created_by], backref='created_users')
    
    def get_allowed_wards(self):
        try:
            return json.loads(self.allowed_wards) if self.allowed_wards else []
        except:
            return []
    
    def set_allowed_wards(self, wards_list):
        self.allowed_wards = json.dumps(wards_list)
    
    def can_access_ward(self, ward_key):
        if self.role == 'admin':
            return True
        allowed = self.get_allowed_wards()
        return not allowed or ward_key in allowed
    
    def is_password_expired(self):
        if self.password_set_date:
            days_since = (datetime.utcnow() - self.password_set_date).days
            return days_since >= self.password_expiry_days
        return False
    
    def days_until_password_expiry(self):
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
    action = db.Column(db.String(50), nullable=True)
    status = db.Column(db.String(20), nullable=True)
    details = db.Column(db.Text, nullable=True)
    
    def __repr__(self):
        return f'<AccessLog User:{self.user_id}>'

# ===================== CATCHMENT POPULATION =====================

class CatchmentPopulation(db.Model):
    __tablename__ = 'catchment_population'
    
    id = db.Column(db.Integer, primary_key=True)
    year = db.Column(db.Integer, nullable=False, unique=True)
    population = db.Column(db.Integer, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    
    def __repr__(self):
        return f'<CatchmentPopulation {self.year}: {self.population}>'

# ===================== STAFF MANAGEMENT =====================

class Staff(db.Model):
    __tablename__ = 'staff'
    __table_args__ = {'extend_existing': True}
    
    id = db.Column(db.Integer, primary_key=True)
    staff_id = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    staff_type = db.Column(db.String(20), nullable=False)
    specialization = db.Column(db.String(100), nullable=True)
    department = db.Column(db.String(100), nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)
    
    performance_records = db.relationship('StaffPerformance', backref='staff', lazy=True)
    assignments = db.relationship('StaffAssignment', backref='staff', lazy=True)
    
    def __repr__(self):
        return f'<Staff {self.name}>'

class StaffPerformance(db.Model):
    __tablename__ = 'staff_performance'
    __table_args__ = {'extend_existing': True}
    
    id = db.Column(db.Integer, primary_key=True)
    staff_id = db.Column(db.Integer, db.ForeignKey('staff.id'), nullable=False)
    reporting_year = db.Column(db.Integer, nullable=False)
    reporting_month = db.Column(db.Integer, nullable=False)
    
    opd_patients = db.Column(db.Integer, default=0)
    ipd_patients = db.Column(db.Integer, default=0)
    surgeries_performed = db.Column(db.Integer, default=0)
    prescriptions = db.Column(db.Integer, default=0)
    drug_entries = db.Column(db.Integer, default=0)
    followup_reviews = db.Column(db.Integer, default=0)
    nurse_rounds = db.Column(db.Integer, default=0)
    admissions_handled = db.Column(db.Integer, default=0)
    consumables_accounted = db.Column(db.Integer, default=0)
    emr_days_worked = db.Column(db.Integer, default=0)
    emr_computer_usage = db.Column(db.Integer, default=0)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<StaffPerformance {self.reporting_year}/{self.reporting_month}>'

class StaffAssignment(db.Model):
    __tablename__ = 'staff_assignments'
    __table_args__ = {'extend_existing': True}
    
    id = db.Column(db.Integer, primary_key=True)
    staff_id = db.Column(db.Integer, db.ForeignKey('staff.id'), nullable=False)
    ward_key = db.Column(db.String(50), nullable=False)
    assigned_date = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    
    def __repr__(self):
        return f'<StaffAssignment {self.ward_key}>'

# ===================== LABORATORY MODELS =====================

class LabTestCategory(db.Model):
    __tablename__ = 'lab_test_categories'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.Text, nullable=True)
    display_order = db.Column(db.Integer, default=0)
    
    tests = db.relationship('LabTest', backref='category', lazy=True)
    
    def __repr__(self):
        return f'<LabTestCategory {self.name}>'

class LabTest(db.Model):
    __tablename__ = 'lab_tests'
    
    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey('lab_test_categories.id'), nullable=False)
    test_name = db.Column(db.String(100), nullable=False)
    unit = db.Column(db.String(20), nullable=True)
    normal_range_min = db.Column(db.Float, nullable=True)
    normal_range_max = db.Column(db.Float, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    
    results = db.relationship('LabResult', backref='test', lazy=True)
    
    def __repr__(self):
        return f'<LabTest {self.test_name}>'

class LabResult(db.Model):
    __tablename__ = 'lab_results'
    
    id = db.Column(db.Integer, primary_key=True)
    test_id = db.Column(db.Integer, db.ForeignKey('lab_tests.id'), nullable=False)
    reporting_year = db.Column(db.Integer, nullable=False)
    reporting_month = db.Column(db.Integer, nullable=False)
    total_performed = db.Column(db.Integer, default=0)
    total_positive = db.Column(db.Integer, default=0)
    total_negative = db.Column(db.Integer, default=0)
    total_invalid = db.Column(db.Integer, default=0)
    turn_around_time_hours = db.Column(db.Float, default=0)
    
    entered_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    entered_at = db.Column(db.DateTime, default=datetime.utcnow)
    notes = db.Column(db.Text, nullable=True)
    
    def __repr__(self):
        return f'<LabResult {self.test.test_name}>'

# ===================== KPI MODELS =====================

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
        return f'<KPIEntry {self.kpi.name}>'

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
        return f'<Referral {self.patient_id}>'

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
        scores = [self.waiting_time_rating, self.staff_courtesy_rating, self.cleanliness_rating, self.communication_rating, self.overall_rating]
        return sum(scores) / len(scores)
    
    def __repr__(self):
        return f'<Survey Patient:{self.patient_id}>'

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
        {'category': 'Outpatient Department (OPD)', 'name': 'OPD Utilization Rate', 
         'calculation_type': 'rate', 'numerator_field': 'total_opd_visits', 
         'denominator_field': 'catchment_population', 'multiplier': 100,
         'unit': '%', 'reporting_frequency': 'monthly', 'target_value': 80},
        
        {'category': 'Outpatient Department (OPD)', 'name': 'Average Waiting Time',
         'calculation_type': 'rate', 'numerator_field': 'total_waiting_time',
         'denominator_field': 'total_patients', 'unit': 'minutes', 'reporting_frequency': 'monthly',
         'target_value': 30},
        
        {'category': 'Outpatient Department (OPD)', 'name': '% Patients Properly Triaged',
         'calculation_type': 'percentage', 'numerator_field': 'patients_triaged',
         'denominator_field': 'total_patients', 'unit': '%', 'reporting_frequency': 'monthly',
         'target_value': 95},
    ]
    
    for kpi in kpis:
        category_name = kpi.pop('category')
        category_id = categories.get(category_name)
        
        if category_id and not KPIDefinition.query.filter_by(name=kpi['name']).first():
            kpi_def = KPIDefinition(category_id=category_id, **kpi)
            db.session.add(kpi_def)
    
    db.session.commit()

def create_initial_lab_categories():
    categories = [
        {'name': 'Malaria Tests', 'description': 'Malaria diagnostic tests', 'display_order': 1},
        {'name': 'Hematology', 'description': 'Blood cell analysis', 'display_order': 2},
        {'name': 'Serology', 'description': 'Antibody/Antigen tests', 'display_order': 3},
    ]
    
    for cat in categories:
        if not LabTestCategory.query.filter_by(name=cat['name']).first():
            category = LabTestCategory(**cat)
            db.session.add(category)
    
    db.session.commit()

def create_initial_lab_tests():
    categories = {cat.name: cat.id for cat in LabTestCategory.query.all()}
    
    tests = [
        {'category': 'Malaria Tests', 'test_name': 'Malaria Blood Film', 'unit': 'tests'},
        {'category': 'Malaria Tests', 'test_name': 'Malaria RDT', 'unit': 'tests'},
        {'category': 'Hematology', 'test_name': 'Complete Blood Count (CBC)', 'unit': 'tests'},
        {'category': 'Hematology', 'test_name': 'ESR', 'unit': 'tests'},
        {'category': 'Serology', 'test_name': 'HIV Rapid Test', 'unit': 'tests'},
        {'category': 'Serology', 'test_name': 'Hepatitis B Surface Antigen', 'unit': 'tests'},
    ]
    
    for test in tests:
        category_name = test.pop('category')
        category_id = categories.get(category_name)
        
        if category_id and not LabTest.query.filter_by(test_name=test['test_name']).first():
            lab_test = LabTest(category_id=category_id, **test)
            db.session.add(lab_test)

    db.session.commit()