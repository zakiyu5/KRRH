# config.py
import os
from datetime import timedelta

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB
    
    DEFAULT_ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
    DEFAULT_ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'Admin@123')
    
    HOSPITAL_NAME = "Kayunga Regional Referral Hospital"
    HOSPITAL_CODE = "KRRH"
    
class DevelopmentConfig(Config):
    DEBUG = True
    
class ProductionConfig(Config):
    DEBUG = False
    
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}