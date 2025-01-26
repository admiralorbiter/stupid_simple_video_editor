from getpass import getpass
import sys
from werkzeug.security import generate_password_hash
from app import app
from models.models import User, db

def create_accounts():
    with app.app_context():
        # Create Jon Lane's admin account
        username = 'jonlane'
        email = 'jlane@prepkc.org'
        password = 'nihlism'

        if User.query.filter_by(username=username).first():
            print('Error: Username jonlane already exists.')
            sys.exit(1)

        if User.query.filter_by(email=email).first():
            print('Error: Email jlane@prepkc.org already exists.')
            sys.exit(1)

        # Check if PrepKC account already exists
        if User.query.filter_by(username='prepkcadmin').first():
            print('Error: Username prepkcadmin already exists.')
            sys.exit(1)

        if User.query.filter_by(email='prepkc@gmail.com').first():
            print('Error: Email prepkc@gmail.com already exists.')
            sys.exit(1)

        new_admin = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password),
            first_name='Jon',
            last_name='Lane'
        )

        prepkc_user = User(
            username='prepkcadmin',
            email='prepkc@gmail.com',
            password_hash=generate_password_hash('Prepkc10000'),
            first_name='PrepKC',
            last_name='Admin'
        )

        db.session.add(new_admin)
        db.session.add(prepkc_user)
        db.session.commit()
        print('Both accounts created successfully.')

if __name__ == '__main__':
    create_accounts()
