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

def init_routes(app):
    """Initialize routes and setup database"""
    # Initialize clip routes
    init_clip_routes(app)
    
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
        
        # Clean up thumbnails before scanning
        cleanup_thumbnails('videos')
        
        # Ensure thumbnail directories exist
        if not os.path.exists('static/thumbnails/videos'):
            os.makedirs('static/thumbnails/videos', exist_ok=True)
        
        # Scan folder for videos
        videos = []
        try:
            conn = get_db_connection()
            
            for file_path in Path(folder_path).glob('*'):
                if is_video_file(str(file_path)):
                    absolute_path = str(file_path.absolute())
                    
                    # Generate thumbnail
                    thumbnail_filename = f"{file_path.stem}_thumb.jpg"
                    # Use forward slashes for web paths
                    thumbnail_path = 'static/thumbnails/videos/' + thumbnail_filename
                    relative_thumbnail_path = 'thumbnails/videos/' + thumbnail_filename
                    
                    # Generate thumbnail using FFmpeg
                    try:
                        cmd = [
                            'ffmpeg', '-y',
                            '-ss', '00:00:01',  # Take thumbnail from 1 second in
                            '-i', absolute_path,
                            '-vframes', '1',
                            '-q:v', '2',
                            thumbnail_path.replace('/', os.path.sep)  # Convert to OS-specific path for ffmpeg
                        ]
                        subprocess.run(cmd, capture_output=True, check=True)
                        has_thumbnail = True
                    except subprocess.CalledProcessError:
                        print(f"Failed to generate thumbnail for {file_path}")
                        has_thumbnail = False
                        relative_thumbnail_path = None
                    
                    video_info = {
                        'title': file_path.stem,
                        'file_path': absolute_path,
                        'size_mb': round(os.path.getsize(file_path) / (1024 * 1024), 2),
                        'duration': get_video_duration(str(file_path)),
                        'thumbnail_path': relative_thumbnail_path if has_thumbnail else None
                    }
                    
                    # Store in database with absolute path and thumbnail
                    cursor = conn.execute('''
                        INSERT OR IGNORE INTO videos (title, file_path, thumbnail_path)
                        VALUES (?, ?, ?)
                        RETURNING id
                    ''', (video_info['title'], absolute_path, relative_thumbnail_path if has_thumbnail else None))
                    
                    result = cursor.fetchone()
                    if result is None:  # File was already in database
                        cursor = conn.execute('''
                            UPDATE videos 
                            SET thumbnail_path = ?
                            WHERE file_path = ?
                            RETURNING id, thumbnail_path
                        ''', (relative_thumbnail_path if has_thumbnail else None, absolute_path))
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
            print(f"Error scanning folder: {str(e)}")
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

    @app.route('/import-videos', methods=['POST'])
    def import_videos():
        """Import videos from the selected folder"""
        folder_path = session.get('video_folder')
        if not folder_path:
            return """
                <div class="alert alert-danger">
                    <i class="bi bi-exclamation-triangle me-2"></i>
                    No folder selected. Please select a folder first.
                </div>
            """
        
        conn = get_db_connection()
        try:
            imported_count = 0
            skipped_count = 0
            
            for file in Path(folder_path).glob('*'):
                if is_video_file(str(file)):
                    # Check if video already exists
                    existing = conn.execute('SELECT id FROM videos WHERE file_path = ?', 
                                         (str(file),)).fetchone()
                    
                    if existing:
                        skipped_count += 1
                        continue
                    
                    try:
                        # Generate thumbnail
                        thumbnail_filename = f"{file.stem}_thumb.jpg"
                        thumbnail_path = f"static/thumbnails/videos/{thumbnail_filename}"
                        if generate_thumbnail(str(file), thumbnail_path):
                            relative_thumbnail_path = f"thumbnails/videos/{thumbnail_filename}"
                        else:
                            relative_thumbnail_path = None
                        
                        # Insert video with thumbnail
                        conn.execute('''
                            INSERT INTO videos (title, file_path, thumbnail_path)
                            VALUES (?, ?, ?)
                        ''', (file.stem, str(file), relative_thumbnail_path))
                        
                        imported_count += 1
                        
                    except Exception as e:
                        print(f"Error processing {file}: {str(e)}")
                        continue
            
            conn.commit()
            return f"""
                <div class="alert alert-success">
                    <i class="bi bi-check-circle me-2"></i>
                    Imported {imported_count} videos
                    {f'(skipped {skipped_count} existing)' if skipped_count else ''}
                </div>
            """
            
        except Exception as e:
            print(f"Error importing videos: {str(e)}")
            return f"""
                <div class="alert alert-danger">
                    <i class="bi bi-exclamation-triangle me-2"></i>
                    Error importing videos: {str(e)}
                </div>
            """
        finally:
            conn.close()