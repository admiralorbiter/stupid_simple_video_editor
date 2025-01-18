import pytest
from datetime import datetime, timezone
from models import User, db

@pytest.fixture
def test_user():
    user = User(
        username='testuser',
        email='test@example.com',
        password_hash='fakehash123',
        first_name='Test',
        last_name='User'
    )
    return user

def test_new_user(test_user):
    """Test creating a new user"""
    assert test_user.username == 'testuser'
    assert test_user.email == 'test@example.com'
    assert test_user.password_hash == 'fakehash123'
    assert test_user.first_name == 'Test'
    assert test_user.last_name == 'User'

def test_user_unique_constraints(test_user, app):
    """Test that unique constraints are enforced"""
    with app.app_context():
        db.session.add(test_user)
        db.session.commit()

        # Try to create another user with the same username
        duplicate_username = User(
            username='testuser',  # Same username
            email='different@example.com',
            password_hash='fakehash456'
        )

        with pytest.raises(Exception):  # SQLAlchemy will raise an error
            db.session.add(duplicate_username)
            db.session.commit()

        db.session.rollback()

        # Try to create another user with the same email
        duplicate_email = User(
            username='different',
            email='test@example.com',  # Same email
            password_hash='fakehash789'
        )

        with pytest.raises(Exception):
            db.session.add(duplicate_email)
            db.session.commit()
