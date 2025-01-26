import mimetypes
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
from models.models import db, Clip, Video


def get_clips_data():
    """Helper function to get formatted clips data"""
    try:
        # Use SQLAlchemy models instead of raw SQL
        clips = db.session.query(Clip, Video.title.label('video_title'))\
            .join(Video)\
            .order_by(Clip.created_at.desc())\
            .all()
        
        return [{
            'id': clip.Clip.id,
            'name': clip.Clip.clip_name,
            'start_time': clip.Clip.start_time,
            'end_time': clip.Clip.end_time,
            'path': clip.Clip.clip_path,
            'created_at': clip.Clip.created_at,
            'thumbnail_path': clip.Clip.thumbnail_path,
            'video_title': clip.video_title
        } for clip in clips]
    except Exception as e:
        print(f"Error getting clips data: {str(e)}")
        return []

def generate_thumbnail(video_path, output_path, timestamp="00:00:05"):
    """Generate a thumbnail for a video at the specified timestamp"""
    try:
        cmd = [
            'ffmpeg',
            '-ss', timestamp,
            '-i', video_path,
            '-vframes', '1',
            '-q:v', '2',
            '-y',  # Overwrite output file if it exists
            output_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"Error generating thumbnail: {result.stderr}")
            return None
        return output_path
    except Exception as e:
        print(f"Error generating thumbnail: {str(e)}")
        return None 

def ensure_thumbnail_dirs():
    """Ensure thumbnail directories exist"""
    Path('static/thumbnails/videos').mkdir(parents=True, exist_ok=True)
    Path('static/thumbnails/clips').mkdir(parents=True, exist_ok=True) 

def get_video_duration(file_path):
    """Get video duration using ffprobe"""
    cmd = [
        'ffprobe', 
        '-v', 'error',
        '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        file_path
    ]
    try:
        output = subprocess.check_output(cmd).decode().strip()
        duration = float(output)
        minutes = int(duration // 60)
        seconds = int(duration % 60)
        return f"{minutes}:{seconds:02d}"
    except:
        return "Unknown"

def is_video_file(file_path):
    """Check if file is a video based on mimetype"""
    mime_type, _ = mimetypes.guess_type(file_path)
    return mime_type and mime_type.startswith('video/')

def get_db_connection():
    """Create a database connection"""
    conn = sqlite3.connect('videos.db')
    conn.row_factory = sqlite3.Row
    return conn

def cleanup_thumbnails(directory='all'):
    """Clean up thumbnail directories"""
    try:
        if directory in ['all', 'videos']:
            video_thumb_dir = Path('static/thumbnails/videos')
            if video_thumb_dir.exists():
                shutil.rmtree(video_thumb_dir)
                video_thumb_dir.mkdir(parents=True, exist_ok=True)
        
        if directory in ['all', 'clips']:
            clips_thumb_dir = Path('static/thumbnails/clips')
            if clips_thumb_dir.exists():
                shutil.rmtree(clips_thumb_dir)
                clips_thumb_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print(f"Error cleaning up thumbnails: {str(e)}")

def delete_thumbnail(thumbnail_path):
    """Delete a specific thumbnail file"""
    if thumbnail_path:
        try:
            full_path = Path('static') / thumbnail_path
            if full_path.exists():
                full_path.unlink()
        except Exception as e:
            print(f"Error deleting thumbnail {thumbnail_path}: {str(e)}")

def cleanup_orphaned_thumbnails():
    """Clean up thumbnails that don't have corresponding clips in the database"""
    try:
        # Get all thumbnail paths from the database using SQLAlchemy
        db_thumbnails = set()
        clips = Clip.query.filter(
            Clip.thumbnail_path.isnot(None),
            Clip.clip_path.isnot(None)
        ).with_entities(Clip.thumbnail_path).distinct().all()
        
        for clip in clips:
            if clip.thumbnail_path:
                db_thumbnails.add(clip.thumbnail_path)
                db_thumbnails.add(os.path.basename(clip.thumbnail_path))
        
        # Check all thumbnails in the clips directory
        clips_thumb_dir = Path('static/thumbnails/clips')
        if clips_thumb_dir.exists():
            for thumb_file in clips_thumb_dir.glob('*'):
                relative_path = f"thumbnails/clips/{thumb_file.name}"
                if (relative_path not in db_thumbnails and 
                    thumb_file.name not in db_thumbnails):
                    print(f"Found orphaned thumbnail: {thumb_file}")
                    # Double check that no clips use this thumbnail
                    clip_count = Clip.query.filter(
                        Clip.thumbnail_path.like(f'%{thumb_file.name}%')
                    ).count()
                    
                    if clip_count == 0:
                        print(f"Deleting confirmed orphaned thumbnail: {thumb_file}")
                        thumb_file.unlink()
                    else:
                        print(f"Thumbnail still in use, keeping: {thumb_file}")
    except Exception as e:
        print(f"Error cleaning up orphaned thumbnails: {str(e)}")
