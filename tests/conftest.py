# conftest.py

import pytest
import sys
import os
import sqlite3

# Add the project root directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app as flask_app
from models.models import db, User, Video, Clip, Folder, Tag, TagCategory, ClipSegment
from config import TestingConfig

@pytest.fixture
def app():
    # Configure the app for testing
    flask_app.config.from_object(TestingConfig)
    
    # Enable SQLite to handle timezone-aware datetime
    flask_app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'connect_args': {
            'detect_types': sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
            'isolation_level': None
        }
    }
    
    def _fk_pragma_on_connect(dbapi_con, con_record):
        dbapi_con.execute('PRAGMA foreign_keys=ON')
        dbapi_con.execute('PRAGMA timezone=UTC')
    
    with flask_app.app_context():
        from sqlalchemy import event
        engine = db.engine
        event.listen(engine, 'connect', _fk_pragma_on_connect)
        
        db.create_all()
        yield flask_app
        db.session.remove()
        db.drop_all()

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def runner(app):
    return app.test_cli_runner()

@pytest.fixture
def test_user():
    return User(
        username='testuser',
        email='test@example.com',
        password_hash='fakehash123',
        first_name='Test',
        last_name='User'
    )

@pytest.fixture
def test_video():
    return Video(
        title='Test Video',
        file_path='/path/to/video.mp4',
        thumbnail_path='/path/to/thumbnail.jpg'
    )

@pytest.fixture
def test_clip(test_video):
    return Clip(
        video=test_video,
        clip_name='Test Clip',
        start_time='00:00:00',
        end_time='00:01:00',
        clip_path='/path/to/clip.mp4',
        thumbnail_path='/path/to/clip_thumbnail.jpg'
    )

@pytest.fixture
def test_folder():
    return Folder(
        name='Test Folder',
        is_open=False,
        position=0
    )

@pytest.fixture
def test_tag_category():
    return TagCategory(name='Test Category')

@pytest.fixture
def test_tag(test_tag_category):
    return Tag(
        name='Test Tag',
        color='#ff0000',
        category=test_tag_category
    )

@pytest.fixture
def test_clip_segment(test_clip):
    return ClipSegment(
        clip=test_clip,
        start_time='00:00:00',
        end_time='00:00:30'
    )

@pytest.fixture
def db_session(app):
    """Create a fresh database session for a test."""
    with app.app_context():
        connection = db.engine.connect()
        transaction = connection.begin()
        
        # Create a session bound to this connection
        session = db.create_scoped_session(
            options={"bind": connection, "binds": {}}
        )
        
        # Replace the global session with our test session
        old_session = db.session
        db.session = session
        
        db.create_all()
        
        yield session
        
        # Cleanup
        transaction.rollback()
        connection.close()
        session.remove()
        
        # Restore the original session
        db.session = old_session

@pytest.fixture
def populated_db(db_session, test_user, test_video, test_clip, test_folder, 
                test_tag_category, test_tag, test_clip_segment):
    """Fixture that provides a database populated with test data."""
    db_session.add_all([
        test_user, 
        test_video, 
        test_clip, 
        test_folder,
        test_tag_category,
        test_tag,
        test_clip_segment
    ])
    db_session.commit()
    return db_session
