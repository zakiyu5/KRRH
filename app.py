# app.py
import os
from datetime import datetime
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, make_response
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import csv
from io import StringIO

# Local imports
from config import config
from models import db, User, UserAccessLog, KPICategory, KPIDefinition, KPIEntry
from models import ReferralHospital, Referral, PatientSatisfactionSurvey
from models import create_initial_kpi_categories, create_initial_kpis

# Initialize Flask app
app = Flask(__name__)

# Load configuration
env = os.environ.get('FLASK_ENV', 'default')
app.config.from_object(config[env])

# Get basedir from config class
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

# ===================== AUTO DATABASE CREATION =====================

def create_directories():
    """Create necessary directories"""
    os.makedirs(os.path.join(app.config['basedir'], 'database'), exist_ok=True)
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    print("✅ Directories created successfully")

def init_database():
    """Initialize database with tables and default data"""
    with app.app_context():
        # Create tables
        db.create_all()
        print("✅ Database tables created successfully")
        
        # Create default admin if not exists
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            admin = User(
                username='admin',
                email='admin@krrh.go.ug',
                password_hash=generate_password_hash('Admin@123'),
                full_name='System Administrator',
                role='admin'
            )
            db.session.add(admin)
            db.session.commit()
            print("✅ Default admin created: admin / Admin@123")
        else:
            print("✅ Admin user already exists")
        
        # Create KPI categories
        create_initial_kpi_categories()
        print("✅ KPI categories created")
        
        # Create KPIs
        create_initial_kpis()
        print("✅ All KPIs initialized")
        
        # Create referral hospitals
        hospitals = [
            {'name': 'Mulago National Referral Hospital', 'code': 'MULAGO', 'location': 'Kampala'},
            {'name': 'Kawempe National Referral Hospital', 'code': 'KAWEMPE', 'location': 'Kawempe'},
            {'name': 'Kiruddu National Referral Hospital', 'code': 'KIRUDDU', 'location': 'Kiruddu'},
            {'name': 'Butabika National Referral Hospital', 'code': 'BUTABIKA', 'location': 'Kampala'},
            {'name': 'Naguru General Hospital', 'code': 'NAGURU', 'location': 'Naguru'},
        ]
        
        for hosp in hospitals:
            if not ReferralHospital.query.filter_by(code=hosp['code']).first():
                hospital = ReferralHospital(**hosp)
                db.session.add(hospital)
        
        db.session.commit()
        print("✅ Referral hospitals created")
        print("\n🎉 Database initialization complete!")

# ===================== USER LOADER =====================

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ===================== MIDDLEWARE =====================

@app.before_request
def log_user_activity():
    """Log user activity for authenticated users"""
    if current_user.is_authenticated:
        # Get or create access log for this session
        if 'access_log_id' not in session:
            access_log = UserAccessLog(
                user_id=current_user.id,
                ip_address=request.remote_addr,
                user_agent=request.user_agent.string if request.user_agent else 'Unknown'
            )
            db.session.add(access_log)
            db.session.commit()
            session['access_log_id'] = access_log.id

@app.after_request
def add_header(response):
    """Add headers to prevent caching"""
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '-1'
    return response

@app.context_processor
def inject_now():
    """Inject current datetime into templates"""
    return {
        'now': datetime.now(),
        'datetime': datetime  # Add datetime to context for use in templates
    }

# ===================== AUTHENTICATION ROUTES =====================

@app.route('/login', methods=['GET', 'POST'])
def login():
    """User login page"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            user.last_login = datetime.utcnow()
            db.session.commit()
            
            flash(f'Welcome back, {user.full_name}!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    """Logout user and update access log"""
    if 'access_log_id' in session:
        access_log = UserAccessLog.query.get(session['access_log_id'])
        if access_log:
            access_log.logout_time = datetime.utcnow()
            db.session.commit()
        session.pop('access_log_id', None)
    
    logout_user()
    flash('You have been logged out successfully', 'info')
    return redirect(url_for('login'))

# ===================== DASHBOARD ROUTES =====================

@app.route('/')
@login_required
def dashboard():
    """Main dashboard showing KPI overview"""
    # Get KPI categories
    categories = KPICategory.query.order_by(KPICategory.display_order).all()
    
    # Get recent KPI entries
    recent_entries = KPIEntry.query.order_by(KPIEntry.entry_date.desc()).limit(10).all()
    
    # Get pending referrals
    pending_referrals = Referral.query.filter_by(status='pending').count()
    
    return render_template('dashboard/index.html',
                          categories=categories,
                          recent_entries=recent_entries,
                          pending_referrals=pending_referrals)

@app.route('/kpi/<int:category_id>')
@login_required
def kpi_category(category_id):
    """View all KPIs in a category"""
    category = KPICategory.query.get_or_404(category_id)
    kpis = KPIDefinition.query.filter_by(category_id=category_id, is_active=True).order_by(KPIDefinition.display_order).all()
    
    # Get current month's entries
    year = request.args.get('year', datetime.now().year, type=int)
    month = request.args.get('month', datetime.now().month, type=int)
    
    entries = {}
    for kpi in kpis:
        entry = KPIEntry.query.filter_by(
            kpi_id=kpi.id,
            reporting_year=year,
            reporting_month=month
        ).first()
        
        if entry:
            entries[kpi.id] = entry
    
    return render_template('dashboard/kpi_category.html',
                          category=category,
                          kpis=kpis,
                          entries=entries,
                          year=year,
                          month=month)

@app.route('/kpi/entry/<int:kpi_id>', methods=['GET', 'POST'])
@login_required
def kpi_entry(kpi_id):
    """Enter data for a specific KPI"""
    kpi = KPIDefinition.query.get_or_404(kpi_id)
    
    if request.method == 'POST':
        year = request.form.get('year', type=int)
        month = request.form.get('month', type=int)
        numerator = request.form.get('numerator', type=float, default=0)
        denominator = request.form.get('denominator', type=float, default=1)
        notes = request.form.get('notes', '')
        
        # Check if entry already exists
        existing = KPIEntry.query.filter_by(
            kpi_id=kpi.id,
            reporting_year=year,
            reporting_month=month
        ).first()
        
        if existing:
            existing.numerator_value = numerator
            existing.denominator_value = denominator
            existing.notes = notes
            # Calculate value directly
            existing.calculated_value = kpi.calculate_value(numerator, denominator)
            db.session.commit()
            flash(f'KPI entry updated for {kpi.name}', 'success')
        else:
            # Calculate value first
            calculated = kpi.calculate_value(numerator, denominator)
            entry = KPIEntry(
                kpi_id=kpi.id,
                entered_by=current_user.id,
                reporting_year=year,
                reporting_month=month,
                numerator_value=numerator,
                denominator_value=denominator,
                calculated_value=calculated,  # Set it directly
                notes=notes
            )
            db.session.add(entry)
            db.session.commit()
            flash(f'KPI entry saved for {kpi.name}', 'success')
        
        # Log action
        if 'access_log_id' in session:
            log = UserAccessLog.query.get(session['access_log_id'])
            if log:
                log.log_action(f"Entered KPI: {kpi.name} for {year}-{month}")
                db.session.commit()
        
        return redirect(url_for('kpi_category', category_id=kpi.category_id, year=year, month=month))
    
    # GET request - show form
    year = request.args.get('year', datetime.now().year, type=int)
    month = request.args.get('month', datetime.now().month, type=int)
    
    existing_entry = KPIEntry.query.filter_by(
        kpi_id=kpi.id,
        reporting_year=year,
        reporting_month=month
    ).first()
    
    return render_template('dashboard/kpi_entry.html',
                          kpi=kpi,
                          year=year,
                          month=month,
                          entry=existing_entry,
                          datetime=datetime)

# ===================== REFERRAL ROUTES =====================

@app.route('/referrals')
@login_required
def referral_list():
    """List all referrals"""
    status = request.args.get('status', 'all')
    
    query = Referral.query
    
    if status != 'all':
        query = query.filter_by(status=status)
    
    referrals = query.order_by(Referral.referral_date.desc()).all()
    
    return render_template('referrals/index.html',
                          referrals=referrals,
                          status=status)

@app.route('/referrals/new', methods=['GET', 'POST'])
@login_required
def referral_new():
    """Create new referral"""
    if request.method == 'POST':
        referral = Referral(
            patient_id=request.form.get('patient_id'),
            patient_name=request.form.get('patient_name'),
            from_ward=request.form.get('from_ward'),
            to_hospital_id=request.form.get('to_hospital_id', type=int),
            referral_reason=request.form.get('referral_reason'),
            referral_date=datetime.strptime(request.form.get('referral_date'), '%Y-%m-%d'),
            created_by=current_user.id,
            status='pending'
        )
        
        db.session.add(referral)
        db.session.commit()
        
        # Log action
        if 'access_log_id' in session:
            log = UserAccessLog.query.get(session['access_log_id'])
            if log:
                log.log_action(f"Created referral for {referral.patient_name}")
                db.session.commit()
        
        flash(f'Referral for {referral.patient_name} created', 'success')
        return redirect(url_for('referral_list'))
    
    hospitals = ReferralHospital.query.filter_by(is_active=True).all()
    return render_template('referrals/new.html',
                          hospitals=hospitals)

@app.route('/referrals/<int:referral_id>/confirm', methods=['POST'])
@login_required
def referral_confirm(referral_id):
    """Confirm referral arrival"""
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
    """User management"""
    if current_user.role != 'admin':
        flash('Access denied', 'danger')
        return redirect(url_for('dashboard'))
    
    users = User.query.all()
    return render_template('admin/users.html', users=users)

@app.route('/admin/users/new', methods=['POST'])
@login_required
def admin_user_new():
    """Create new user"""
    if current_user.role != 'admin':
        flash('Access denied', 'danger')
        return redirect(url_for('dashboard'))
    
    user = User(
        username=request.form.get('username'),
        email=request.form.get('email'),
        full_name=request.form.get('full_name'),
        role=request.form.get('role'),
        department=request.form.get('department'),
        password_hash=generate_password_hash(request.form.get('password'))
    )
    
    db.session.add(user)
    db.session.commit()
    
    flash(f'User {user.username} created successfully', 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/users/export')
@login_required
def admin_users_export():
    """Export users list as CSV"""
    if current_user.role != 'admin':
        flash('Access denied', 'danger')
        return redirect(url_for('dashboard'))
    
    users = User.query.all()
    
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['Username', 'Full Name', 'Email', 'Role', 'Department', 'Created', 'Last Login'])
    
    for user in users:
        writer.writerow([
            user.username,
            user.full_name,
            user.email or '',
            user.role,
            user.department or '',
            user.created_at.strftime('%Y-%m-%d') if user.created_at else '',
            user.last_login.strftime('%Y-%m-%d') if user.last_login else ''
        ])
    
    output.seek(0)
    
    response = make_response(output.getvalue())
    response.headers['Content-Disposition'] = 'attachment; filename=krrh_users.csv'
    response.headers['Content-Type'] = 'text/csv'
    
    return response

@app.route('/admin/logs')
@login_required
def admin_logs():
    """View user access logs"""
    if current_user.role != 'admin':
        flash('Access denied', 'danger')
        return redirect(url_for('dashboard'))
    
    days = request.args.get('days', 7, type=int)
    since = datetime.utcnow() - timedelta(days=days)
    
    logs = UserAccessLog.query.filter(UserAccessLog.login_time >= since).order_by(UserAccessLog.login_time.desc()).all()
    
    return render_template('admin/logs.html', logs=logs, days=days)

# ===================== REPORTS ROUTES =====================

@app.route('/reports/monthly')
@login_required
def report_monthly():
    """Monthly KPI report"""
    year = request.args.get('year', datetime.now().year, type=int)
    month = request.args.get('month', datetime.now().month, type=int)
    
    categories = KPICategory.query.all()
    report_data = {}
    
    for category in categories:
        kpis = KPIDefinition.query.filter_by(category_id=category.id, is_active=True).all()
        category_data = []
        
        for kpi in kpis:
            entry = KPIEntry.query.filter_by(
                kpi_id=kpi.id,
                reporting_year=year,
                reporting_month=month
            ).first()
            
            if entry:
                category_data.append({
                    'kpi': kpi,
                    'entry': entry,
                    'status': kpi.get_status(entry.calculated_value)
                })
        
        if category_data:
            report_data[category] = category_data
    
    return render_template('reports/monthly.html',
                          report_data=report_data,
                          year=year,
                          month=month)

# ===================== API ROUTES =====================

@app.route('/api/kpi/<int:kpi_id>/trend')
@login_required
def api_kpi_trend(kpi_id):
    """Get trend data for a KPI"""
    months = request.args.get('months', 6, type=int)
    
    entries = KPIEntry.query.filter_by(kpi_id=kpi_id)\
        .order_by(KPIEntry.reporting_year.desc(), KPIEntry.reporting_month.desc())\
        .limit(months).all()
    
    data = [{
        'period': f"{e.reporting_year}-{e.reporting_month:02d}",
        'value': e.calculated_value,
        'numerator': e.numerator_value,
        'denominator': e.denominator_value
    } for e in entries]
    
    return jsonify(data)

# ===================== RECEPTION VIEW =====================

@app.route('/reception')
def reception_view():
    """Public Reception View slideshow"""
    #
    return render_template('reception/index.html', now=datetime.now())

# ===================== ERROR HANDLERS =====================

@app.errorhandler(404)
def not_found_error(error):
    return render_template('errors/404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('errors/500.html'), 500

# ===================== MAIN ENTRY POINT =====================

if __name__ == '__main__':
    print("\n" + "="*60)
    print("🏥 KRRH InsightHub V2 - Advanced KPI Management System")
    print("="*60)
    
    # Create directories
    create_directories()
    
    # Initialize database
    init_database()
    
    # Get counts
    with app.app_context():
        kpi_count = KPIDefinition.query.count()
        category_count = KPICategory.query.count()
        hospital_count = ReferralHospital.query.count()
    
    print(f"\n📊 Statistics:")
    print(f"   - KPI Categories: {category_count}")
    print(f"   - Total KPIs: {kpi_count}")
    print(f"   - Referral Hospitals: {hospital_count}")
    print(f"📁 Database: {app.config['SQLALCHEMY_DATABASE_URI']}")
    print("\n🌐 Access URLs:")
    print(f"   Login: http://127.0.0.1:8080/login")
    print(f"   Dashboard: http://127.0.0.1:8080/")
    print(f"   Reception: http://127.0.0.1:8080/reception")
    print(f"\n👤 Default Admin: admin / Admin@123")
    print("="*60 + "\n")
    
    app.run(debug=True, host='0.0.0.0', port=8080)