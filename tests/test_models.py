import pytest
from datetime import datetime, timezone
from models.models import User, Video, Clip, Folder, Tag, TagCategory, ClipSegment, db

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

def test_video_creation(test_video):
    """Test creating a new video"""
    assert test_video.title == 'Test Video'
    assert test_video.file_path == '/path/to/video.mp4'
    assert test_video.thumbnail_path == '/path/to/thumbnail.jpg'

def test_clip_creation(test_clip, test_video):
    """Test creating a new clip"""
    assert test_clip.video == test_video
    assert test_clip.clip_name == 'Test Clip'
    assert test_clip.start_time == '00:00:00'
    assert test_clip.end_time == '00:01:00'
    assert test_clip.clip_path == '/path/to/clip.mp4'
    assert test_clip.thumbnail_path == '/path/to/clip_thumbnail.jpg'

def test_folder_creation(test_folder):
    """Test creating a new folder"""
    assert test_folder.name == 'Test Folder'
    assert test_folder.is_open is False
    assert test_folder.position == 0
    assert test_folder.parent_id is None

def test_folder_hierarchy(app, test_folder):
    """Test folder parent-child relationship"""
    with app.app_context():
        db.session.add(test_folder)
        db.session.commit()

        child_folder = Folder(
            name='Child Folder',
            parent=test_folder
        )
        db.session.add(child_folder)
        db.session.commit()

        assert child_folder.parent == test_folder
        assert test_folder.children == [child_folder]

def test_tag_category_creation(test_tag_category):
    """Test creating a new tag category"""
    assert test_tag_category.name == 'Test Category'

def test_tag_creation(test_tag, test_tag_category):
    """Test creating a new tag"""
    assert test_tag.name == 'Test Tag'
    assert test_tag.color == '#ff0000'
    assert test_tag.category == test_tag_category

def test_video_tags_relationship(app, test_video, test_tag):
    """Test video-tag relationship"""
    with app.app_context():
        db.session.add_all([test_video, test_tag])
        test_video.tags.append(test_tag)
        db.session.commit()

        assert test_tag in test_video.tags
        assert test_video in test_tag.videos

def test_clip_segment_creation(test_clip_segment, test_clip):
    """Test creating a new clip segment"""
    assert test_clip_segment.clip == test_clip
    assert test_clip_segment.start_time == '00:00:00'
    assert test_clip_segment.end_time == '00:00:30'
