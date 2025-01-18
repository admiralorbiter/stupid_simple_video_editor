# app.py

from flask import Flask
from models import db, User
from flask_login import LoginManager
from forms import LoginForm
from routes import init_routes
from config import DevelopmentConfig, ProductionConfig
from dotenv import load_dotenv
import os

app = Flask(__name__)

# Load configuration based on the environment
if os.environ.get('FLASK_ENV') == 'production':
    app.config.from_object(ProductionConfig)
else:
    app.config.from_object(DevelopmentConfig)

# Initialize extensions
db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'  # Redirect to 'login' view if unauthorized
login_manager.login_message_category = 'info'

# Create the database tables
with app.app_context():
    db.create_all()

# User loader callback for Flask-Login
@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# Initialize routes
init_routes(app)

# Load environment variables from .env file
load_dotenv()

if __name__ == '__main__':
    # Use production-ready server configuration
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)