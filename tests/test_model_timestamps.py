import pytest
from datetime import datetime, timezone
from models.models import User, Video, db
import time

def test_user_timestamp_creation(app, test_user):
    """Test that timestamps are automatically set on creation"""
    with app.app_context():
        before_creation = datetime.now(timezone.utc)
        
        db.session.add(test_user)
        db.session.commit()
        
        # Force reload the user from the database
        db.session.refresh(test_user)
        
        after_creation = datetime.now(timezone.utc)
        
        # Basic type checks
        assert isinstance(test_user.created_at, datetime)
        assert isinstance(test_user.updated_at, datetime)
        
        # Ensure timestamps have timezone info
        assert test_user.created_at.tzinfo is not None
        assert test_user.updated_at.tzinfo is not None
        
        # Verify timestamps are within expected range
        assert before_creation <= test_user.created_at <= after_creation
        assert before_creation <= test_user.updated_at <= after_creation

def test_user_update_timestamp(app, test_user):
    """Test that updated_at is automatically updated"""
    with app.app_context():
        db.session.add(test_user)
        db.session.commit()
        
        original_created_at = test_user.created_at
        original_updated_at = test_user.updated_at
        
        # Wait a small amount of time to ensure timestamp difference
        time.sleep(0.1)
        
        test_user.first_name = "Updated"
        db.session.commit()
        
        # Verify created_at hasn't changed
        assert test_user.created_at == original_created_at
        
        # Verify updated_at has changed and is later
        assert test_user.updated_at > original_updated_at
        assert test_user.created_at < test_user.updated_at

def test_video_created_at(app, test_video):
    """Test video creation timestamp"""
    with app.app_context():
        before_creation = datetime.now(timezone.utc)
        db.session.add(test_video)
        db.session.commit()
        
        # Force reload the video from the database
        db.session.refresh(test_video)
        
        after_creation = datetime.now(timezone.utc)
        
        # Ensure created_at has timezone info
        assert test_video.created_at.tzinfo is not None
        assert before_creation <= test_video.created_at <= after_creation 