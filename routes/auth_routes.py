from flask import flash, redirect, render_template, url_for
from flask_login import login_required, login_user, logout_user
from forms import LoginForm
from models.models import User
from werkzeug.security import check_password_hash

def init_auth_routes(app):
    @app.route('/login', methods=['GET', 'POST'])
    def login():
        """Handle user login"""
        form = LoginForm()
        if form.validate_on_submit():
            user = User.query.filter_by(username=form.username.data).first()
            if user and check_password_hash(user.password_hash, form.password.data):
                login_user(user)
                flash('Logged in successfully.', 'success')
                return redirect(url_for('index'))
            else:
                flash('Invalid username or password.', 'danger')
        return render_template('login.html', form=form)
    
    @app.route('/logout')
    @login_required
    def logout():
        """Handle user logout"""
        logout_user()
        flash('You have been logged out.', 'info')
        return redirect(url_for('index')) 