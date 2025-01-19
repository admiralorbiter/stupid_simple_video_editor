from flask import flash, redirect, render_template, url_for, request, session, jsonify, send_file, make_response
from flask_login import login_required, login_user, logout_user
from forms import LoginForm
from models import User, db
from werkzeug.security import check_password_hash, generate_password_hash
import os
from pathlib import Path
import subprocess
from tkinter import Tk, filedialog
from datetime import datetime
import shutil  # If using the copy option
from helper import *
from clip_routes import init_clip_routes
from auth_routes import init_auth_routes
from video_routes import init_video_routes
from organization_routes import init_organization_routes

def init_routes(app):
    """Initialize routes and setup database"""
    # Initialize all route groups
    init_clip_routes(app)
    init_auth_routes(app)
    init_video_routes(app)
    init_organization_routes(app)  # Add this line
    
    # Clean up orphaned thumbnails on startup
    cleanup_orphaned_thumbnails()
    
    # Clean up all thumbnails on startup
    # cleanup_thumbnails('all')

    @app.template_filter('datetime')
    def format_datetime(value):
        if value is None:
            return ""
        if isinstance(value, str):
            try:
                value = datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                return value
        return value.strftime('%Y-%m-%d %H:%M')

    @app.template_filter('duration')
    def video_duration_filter(file_path):
        return get_video_duration(file_path)

    # Initialize database tables
    with app.app_context():
        conn = get_db_connection()
        try:
            # Create videos table
            conn.execute('''
                CREATE TABLE IF NOT EXISTS videos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    file_path TEXT UNIQUE NOT NULL,
                    thumbnail_path TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Create clips table
            conn.execute('''
                CREATE TABLE IF NOT EXISTS clips (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    video_id INTEGER NOT NULL,
                    clip_name TEXT NOT NULL,
                    start_time TEXT NOT NULL,
                    end_time TEXT NOT NULL,
                    clip_path TEXT NOT NULL,
                    thumbnail_path TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (video_id) REFERENCES videos (id)
                )
            ''')
            
            # Create clips_backup table
            conn.execute('''
                CREATE TABLE IF NOT EXISTS clips_backup (
                    id INTEGER PRIMARY KEY,
                    video_id INTEGER NOT NULL,
                    clip_name TEXT NOT NULL,
                    start_time TEXT NOT NULL,
                    end_time TEXT NOT NULL,
                    clip_path TEXT NOT NULL,
                    thumbnail_path TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (video_id) REFERENCES videos (id)
                )
            ''')

            # Create folders table
            conn.execute('''
                CREATE TABLE IF NOT EXISTS folders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    parent_id INTEGER,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (parent_id) REFERENCES folders(id)
                )
            ''')

            # Create tags table
            conn.execute('''
                CREATE TABLE IF NOT EXISTS tags (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    color TEXT DEFAULT '#6c757d',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Create video_folders junction table
            conn.execute('''
                CREATE TABLE IF NOT EXISTS video_folders (
                    video_id INTEGER,
                    folder_id INTEGER,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (video_id, folder_id),
                    FOREIGN KEY (video_id) REFERENCES videos(id) ON DELETE CASCADE,
                    FOREIGN KEY (folder_id) REFERENCES folders(id) ON DELETE CASCADE
                )
            ''')

            # Create video_tags junction table
            conn.execute('''
                CREATE TABLE IF NOT EXISTS video_tags (
                    video_id INTEGER,
                    tag_id INTEGER,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (video_id, tag_id),
                    FOREIGN KEY (video_id) REFERENCES videos(id) ON DELETE CASCADE,
                    FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
                )
            ''')
            
            conn.commit()
        finally:
            conn.close()

    @app.route('/')
    def index():
        """Render the main page with video library"""
        conn = get_db_connection()
        try:
            # Get basic video info first
            videos = conn.execute('''
                SELECT 
                    id,
                    title,
                    file_path,
                    thumbnail_path,
                    (SELECT COUNT(*) FROM clips WHERE video_id = videos.id) as clip_count
                FROM videos
                ORDER BY title ASC
            ''').fetchall()
            
            videos_data = [{
                'id': video['id'],
                'title': video['title'],
                'file_path': video['file_path'],
                'thumbnail_path': video['thumbnail_path'],
                'clip_count': video['clip_count']
            } for video in videos]
            
            # Render initial page quickly
            response = make_response(render_template('index.html', videos=videos_data))
            response.headers['X-Content-Type-Options'] = 'nosniff'
            return response
            
        finally:
            conn.close()

    @app.route('/scan-folder', methods=['POST'])
    def scan_folder():
        """Scan a folder for video files and add them to the database"""
        folder_path = request.form.get('folder_path')
        
        if not os.path.isdir(folder_path):
            return "Invalid folder path", 400
            
        # Scan folder for videos
        videos = []
        for file_path in Path(folder_path).glob('*'):
            if is_video_file(str(file_path)):
                video_info = {
                    'title': file_path.stem,
                    'file_path': str(file_path),
                    'size_mb': round(os.path.getsize(file_path) / (1024 * 1024), 2),
                    'duration': get_video_duration(str(file_path))
                }
                videos.append(video_info)
                
                # Store in database
                conn = get_db_connection()
                conn.execute('''
                    INSERT OR IGNORE INTO videos (title, file_path)
                    VALUES (?, ?)
                ''', (video_info['title'], str(file_path)))
                conn.commit()
                conn.close()
        
        # Return updated video list HTML
        return render_template('video_list.html', videos=videos)

    @app.route('/delete-videos', methods=['POST'])
    def delete_videos():
        """Handle video deletion"""
        video_ids = request.json.get('video_ids', [])
        
        if not video_ids:
            return jsonify({'status': 'error', 'message': 'No videos selected'}), 400
        
        conn = get_db_connection()
        try:
            # Get video information before deletion
            videos = conn.execute('''
                SELECT id, file_path, thumbnail_path 
                FROM videos 
                WHERE id IN ({})
            '''.format(','.join('?' * len(video_ids))), video_ids).fetchall()
            
            # Delete from database
            conn.execute('''
                DELETE FROM videos 
                WHERE id IN ({})
            '''.format(','.join('?' * len(video_ids))), video_ids)
            
            conn.commit()
            
            # Return success response with deleted IDs
            return jsonify({
                'status': 'success',
                'deleted_ids': video_ids
            })
            
        except Exception as e:
            conn.rollback()
            return jsonify({
                'status': 'error',
                'message': str(e)
            }), 500
        finally:
            conn.close()