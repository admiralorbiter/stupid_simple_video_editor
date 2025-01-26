from flask import flash, redirect, render_template, url_for, request, session, jsonify, send_file, make_response
from flask_login import login_required, login_user, logout_user
from forms import LoginForm
from models.models import User, db, Video, Clip, Folder, Tag, TagCategory, ClipSegment
from werkzeug.security import check_password_hash, generate_password_hash
import os
from pathlib import Path
import subprocess
from tkinter import Tk, filedialog
from datetime import datetime
import shutil  # If using the copy option
from helper import *
from routes.clip_routes import init_clip_routes
from routes.auth_routes import init_auth_routes
from routes.video_routes import init_video_routes
from routes.organization_routes import init_organization_routes

def init_routes(app):
    """Initialize routes and setup database"""
    # Initialize all route groups
    init_clip_routes(app)
    init_auth_routes(app)
    init_video_routes(app)
    init_organization_routes(app)
    
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
        db.create_all()

    @app.route('/')
    def index():
        """Render the main page with video library"""
        videos = Video.query.order_by(Video.title.asc()).all()
        
        videos_data = [{
            'id': video.id,
            'title': video.title,
            'file_path': video.file_path,
            'thumbnail_path': video.thumbnail_path,
            'clip_count': len(video.clips)
        } for video in videos]
        
        response = make_response(render_template('index.html', videos=videos_data))
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    @app.route('/scan-folder', methods=['POST'])
    def scan_folder():
        """Scan a folder for video files and add them to the database"""
        folder_path = request.form.get('folder_path')
        
        if not os.path.isdir(folder_path):
            return "Invalid folder path", 400
            
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
                
                # Store in database using SQLAlchemy
                video = Video(
                    title=video_info['title'],
                    file_path=str(file_path)
                )
                db.session.merge(video)  # merge instead of add to handle duplicates
        
        db.session.commit()
        return render_template('video_list.html', videos=videos)

    @app.route('/delete-videos', methods=['POST'])
    def delete_videos():
        """Handle video deletion"""
        video_ids = request.json.get('video_ids', [])
        
        if not video_ids:
            return jsonify({'status': 'error', 'message': 'No videos selected'}), 400
        
        try:
            videos = Video.query.filter(Video.id.in_(video_ids)).all()
            for video in videos:
                db.session.delete(video)
            
            db.session.commit()
            
            return jsonify({
                'status': 'success',
                'deleted_ids': video_ids
            })
            
        except Exception as e:
            db.session.rollback()
            return jsonify({
                'status': 'error',
                'message': str(e)
            }), 500