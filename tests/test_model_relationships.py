import pytest
from models.models import User, Video, Clip, Folder, Tag, TagCategory, ClipSegment, db

def test_video_cascade_delete(app, test_video, test_clip):
    """Test that deleting a video cascades to clips"""
    with app.app_context():
        db.session.add(test_video)
        db.session.add(test_clip)
        db.session.commit()
        
        video_id = test_video.id
        clip_id = test_clip.id
        
        db.session.delete(test_video)
        db.session.commit()
        
        assert db.session.get(Video, video_id) is None
        assert db.session.get(Clip, clip_id) is None

def test_clip_cascade_delete(app, test_clip, test_clip_segment):
    """Test that deleting a clip cascades to segments"""
    with app.app_context():
        db.session.add(test_clip)
        db.session.add(test_clip_segment)
        db.session.commit()
        
        clip_id = test_clip.id
        segment_id = test_clip_segment.id
        
        db.session.delete(test_clip)
        db.session.commit()
        
        assert db.session.get(Clip, clip_id) is None
        assert db.session.get(ClipSegment, segment_id) is None

def test_video_folder_relationship(app, test_video, test_folder):
    """Test many-to-many relationship between videos and folders"""
    with app.app_context():
        db.session.add_all([test_video, test_folder])
        test_video.folders.append(test_folder)
        db.session.commit()

        # Test relationships
        assert test_folder in test_video.folders
        assert test_video in test_folder.videos

        # Test removal
        test_video.folders.remove(test_folder)
        db.session.commit()
        assert test_folder not in test_video.folders
        assert test_video not in test_folder.videos

def test_folder_recursive_delete(app):
    """Test recursive deletion of folder hierarchy"""
    with app.app_context():
        parent = Folder(name='Parent')
        child1 = Folder(name='Child1', parent=parent)
        child2 = Folder(name='Child2', parent=parent)
        grandchild = Folder(name='Grandchild', parent=child1)
        
        db.session.add(parent)
        db.session.commit()
        
        parent_id = parent.id
        child1_id = child1.id
        child2_id = child2.id
        grandchild_id = grandchild.id
        
        db.session.delete(parent)
        db.session.commit()
        
        # Use session.get instead of query.get
        assert db.session.get(Folder, parent_id) is None
        assert db.session.get(Folder, child1_id) is None
        assert db.session.get(Folder, child2_id) is None
        assert db.session.get(Folder, grandchild_id) is None 