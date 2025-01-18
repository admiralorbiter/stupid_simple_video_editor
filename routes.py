from flask import flash, redirect, render_template, url_for, request, session, jsonify, send_file
from flask_login import login_required, login_user, logout_user
from forms import LoginForm
from models import User, db
from werkzeug.security import check_password_hash, generate_password_hash
import os
from pathlib import Path
import mimetypes
import subprocess
import sqlite3
from tkinter import Tk, filedialog
import tkinter as tk
from datetime import datetime
import shutil  # If using the copy option

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

def init_routes(app):
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

    # Initialize videos table
    with app.app_context():
        conn = get_db_connection()
        conn.execute('''
            CREATE TABLE IF NOT EXISTS videos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                file_path TEXT UNIQUE NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        conn.close()

    @app.route('/')
    def index():
        """Render the main page with video library"""
        conn = get_db_connection()
        videos = conn.execute('SELECT * FROM videos').fetchall()
        conn.close()
        return render_template('index.html', videos=videos)

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

    @app.route('/video/<int:video_id>')
    def serve_video(video_id):
        """Serve video file directly"""
        conn = get_db_connection()
        video = conn.execute('SELECT file_path FROM videos WHERE id = ?', 
                            (video_id,)).fetchone()
        conn.close()
        
        if video is None:
            return "Video not found", 404
        
        return send_file(video['file_path'], mimetype='video/mp4')

    @app.route('/edit-video/<int:video_id>')
    def edit_video(video_id):
        """Video editing interface"""
        conn = get_db_connection()
        video = conn.execute('SELECT * FROM videos WHERE id = ?', 
                           (video_id,)).fetchone()
        conn.close()
        
        if video is None:
            flash('Video not found.', 'error')
            return redirect(url_for('index'))
        
        video = dict(video)
        # Instead of using static path, we'll use our video serve route
        video['video_url'] = url_for('serve_video', video_id=video['id'])
        
        return render_template('edit_video.html', video=video)

    @app.route('/browse-folder')
    def browse_folder():
        """Open system folder browser dialog and return selected path"""
        try:
            # Hide the main tkinter window
            root = Tk()
            root.withdraw()
            
            # Open folder selection dialog
            folder_path = filedialog.askdirectory()
            
            # Always destroy the Tk instance
            root.destroy()
            
            if folder_path:
                # Store the selected path in session
                session['selected_folder'] = folder_path
                return jsonify({
                    'folder': folder_path,
                    'status': 'success'
                })
            return jsonify({
                'status': 'cancelled'
            })
        except Exception as e:
            # Make sure to destroy the Tk instance even if an error occurs
            try:
                root.destroy()
            except:
                pass
            return jsonify({
                'status': 'error',
                'message': str(e)
            }), 500

    @app.route('/select-folder', methods=['POST'])
    def select_folder():
        """Handle the folder selection and scan for videos"""
        folder_path = session.get('selected_folder')
        
        if not folder_path or not os.path.isdir(folder_path):
            return """
                <div class="alert alert-danger">
                    No folder selected or invalid folder path.
                </div>
            """
        
        # Scan folder for videos
        videos = []
        try:
            conn = get_db_connection()
            
            for file_path in Path(folder_path).glob('*'):
                if is_video_file(str(file_path)):
                    absolute_path = str(file_path.absolute())
                    video_info = {
                        'title': file_path.stem,
                        'file_path': absolute_path,
                        'size_mb': round(os.path.getsize(file_path) / (1024 * 1024), 2),
                        'duration': get_video_duration(str(file_path))
                    }
                    
                    # Store in database with absolute path
                    cursor = conn.execute('''
                        INSERT OR IGNORE INTO videos (title, file_path)
                        VALUES (?, ?)
                        RETURNING id
                    ''', (video_info['title'], absolute_path))
                    
                    result = cursor.fetchone()
                    if result is None:  # File was already in database
                        cursor = conn.execute('''
                            SELECT id FROM videos WHERE file_path = ?
                        ''', (absolute_path,))
                        result = cursor.fetchone()
                    
                    video_info['id'] = result[0]
                    videos.append(video_info)
            
            conn.commit()
            conn.close()
            
            if not videos:
                return """
                    <div class="alert alert-info">
                        No video files found in the selected folder.
                    </div>
                """
            
            return render_template('video_list.html', videos=videos)
            
        except Exception as e:
            print(f"Error scanning folder: {str(e)}")  # Add logging
            return f"""
                <div class="alert alert-danger">
                    Error scanning folder: {str(e)}
                </div>
            """

    # Existing auth routes
    @app.route('/login', methods=['GET', 'POST'])
    def login():
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
        logout_user()
        flash('You have been logged out.', 'info')
        return redirect(url_for('index')) 

    @app.route('/create-clip', methods=['POST'])
    def create_clip():
        """Create a new clip from the video"""
        video_id = request.form.get('video_id')
        clip_name = request.form.get('clip_name')
        start_time = request.form.get('start_time')
        end_time = request.form.get('end_time')
        
        if not all([video_id, clip_name, start_time, end_time]):
            return """
                <div class="alert alert-danger">
                    All fields are required.
                </div>
            """
        
        try:
            conn = get_db_connection()
            video = conn.execute('SELECT file_path FROM videos WHERE id = ?', 
                               (video_id,)).fetchone()
            
            if not video:
                return """
                    <div class="alert alert-danger">
                        Video not found.
                    </div>
                """
            
            # Create clips directory if it doesn't exist
            clips_dir = os.path.join('static', 'clips')
            os.makedirs(clips_dir, exist_ok=True)
            
            # Generate unique filename for the clip
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            safe_name = "".join(c for c in clip_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
            output_filename = f'{safe_name}_{timestamp}.mp4'
            output_path = os.path.join(clips_dir, output_filename)
            
            # Build FFmpeg command
            command = [
                'ffmpeg',
                '-ss', start_time,
                '-to', end_time,
                '-i', video['file_path'],
                '-c', 'copy',
                '-y',  # Overwrite output file if it exists
                output_path
            ]
            
            # Execute FFmpeg command
            result = subprocess.run(command, 
                                  capture_output=True, 
                                  text=True)
            
            if result.returncode != 0:
                raise Exception(f"FFmpeg error: {result.stderr}")
            
            # Store clip information in database
            conn.execute('''
                INSERT INTO clips (video_id, clip_name, start_time, end_time, clip_path)
                VALUES (?, ?, ?, ?, ?)
            ''', (video_id, clip_name, start_time, end_time, output_path))
            conn.commit()
            
            return f"""
                <div class="alert alert-success">
                    <i class="bi bi-check-circle me-2"></i>
                    Clip "{clip_name}" created successfully!
                    <div class="mt-2">
                        <a href="/static/clips/{output_filename}" 
                           class="btn btn-sm btn-primary" 
                           target="_blank">
                            <i class="bi bi-play-fill me-1"></i>Play Clip
                        </a>
                    </div>
                </div>
            """
            
        except Exception as e:
            print(f"Error creating clip: {str(e)}")  # Add logging
            return f"""
                <div class="alert alert-danger">
                    <i class="bi bi-exclamation-triangle me-2"></i>
                    Error creating clip: {str(e)}
                </div>
            """
        finally:
            conn.close() 