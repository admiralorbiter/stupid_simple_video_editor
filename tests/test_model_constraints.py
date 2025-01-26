import pytest
from sqlalchemy.exc import IntegrityError
from models.models import User, Video, Clip, Tag, TagCategory, db

def test_user_required_fields(app):
    """Test that required user fields raise appropriate errors"""
    with app.app_context():
        # Test missing username
        user = User(email='test@example.com', password_hash='hash')
        with pytest.raises(IntegrityError):
            db.session.add(user)
            db.session.commit()
        db.session.rollback()

        # Test missing email
        user = User(username='test', password_hash='hash')
        with pytest.raises(IntegrityError):
            db.session.add(user)
            db.session.commit()
        db.session.rollback()

def test_video_unique_file_path(app, test_video):
    """Test that video file_path must be unique"""
    with app.app_context():
        db.session.add(test_video)
        db.session.commit()

        duplicate_video = Video(
            title='Another Video',
            file_path=test_video.file_path  # Same file_path
        )
        
        with pytest.raises(IntegrityError):
            db.session.add(duplicate_video)
            db.session.commit()

def test_tag_unique_name(app, test_tag):
    """Test that tag names must be unique"""
    with app.app_context():
        db.session.add(test_tag)
        db.session.commit()

        duplicate_tag = Tag(name=test_tag.name)
        with pytest.raises(IntegrityError):
            db.session.add(duplicate_tag)
            db.session.commit()

def test_tag_category_unique_name(app, test_tag_category):
    """Test that tag category names must be unique"""
    with app.app_context():
        db.session.add(test_tag_category)
        db.session.commit()

        duplicate_category = TagCategory(name=test_tag_category.name)
        with pytest.raises(IntegrityError):
            db.session.add(duplicate_category)
            db.session.commit() 