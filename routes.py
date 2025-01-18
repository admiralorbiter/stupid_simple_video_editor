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

    @app.route('/select-clips-folder')
    def select_clips_folder():
        """Open system folder browser dialog for clips destination"""
        try:
            root = Tk()
            root.withdraw()
            
            folder_path = filedialog.askdirectory()
            root.destroy()
            
            if folder_path:
                session['clips_folder'] = folder_path
                return jsonify({
                    'folder': folder_path,
                    'status': 'success'
                })
            return jsonify({
                'status': 'cancelled'
            })
        except Exception as e:
            try:
                root.destroy()
            except:
                pass
            return jsonify({
                'status': 'error',
                'message': str(e)
            }), 500

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
        
        print("Form data received:", {
            'video_id': video_id,
            'clip_name': clip_name,
            'start_time': start_time,
            'end_time': end_time
        })
        
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

    @app.route('/clips', methods=['GET'])
    @app.route('/clips/<int:video_id>', methods=['GET'])
    def get_clips(video_id=None):
        """Get all clips or clips for a specific video"""
        try:
            conn = get_db_connection()
            
            if video_id:
                # Get clips for specific video with video title
                clips = conn.execute('''
                    SELECT 
                        c.id,
                        c.clip_name,
                        c.start_time,
                        c.end_time,
                        c.clip_path,
                        c.created_at,
                        v.title as video_title
                    FROM clips c
                    JOIN videos v ON c.video_id = v.id
                    WHERE c.video_id = ?
                    ORDER BY c.created_at DESC
                ''', (video_id,)).fetchall()
            else:
                # Get all clips with their video titles
                clips = conn.execute('''
                    SELECT 
                        c.id,
                        c.clip_name,
                        c.start_time,
                        c.end_time,
                        c.clip_path,
                        c.created_at,
                        v.title as video_title
                    FROM clips c
                    JOIN videos v ON c.video_id = v.id
                    ORDER BY c.created_at DESC
                ''').fetchall()
            
            # Convert to list of dictionaries for easier template handling
            clips_data = [{
                'id': clip[0],
                'name': clip[1],
                'start_time': clip[2],
                'end_time': clip[3],
                'path': clip[4],
                'created_at': clip[5],
                'video_title': clip[6]
            } for clip in clips]
            
            # Return different templates based on request type
            if request.headers.get('HX-Request'):
                # Return partial template for HTMX requests
                return render_template('clips_list.html', clips=clips_data)
            else:
                # Return full page for direct visits
                return render_template('clips.html', clips=clips_data)
            
        except Exception as e:
            print(f"Error fetching clips: {str(e)}")
            return """
                <div class="alert alert-danger">
                    Error fetching clips: {str(e)}
                </div>
            """
        finally:
            conn.close() 

    @app.route('/clips/delete/<int:clip_id>', methods=['DELETE'])
    def delete_clip(clip_id):
        """Delete a clip and its file"""
        try:
            conn = get_db_connection()
            
            # Get clip info before deletion
            clip = conn.execute('SELECT * FROM clips WHERE id = ?', 
                              (clip_id,)).fetchone()
            
            if not clip:
                return """
                    <div class="alert alert-danger">
                        <i class="bi bi-exclamation-triangle me-2"></i>
                        Clip not found
                    </div>
                """
            
            # Store clip info for restoration
            deleted_clips = session.get('deleted_clips', [])
            deleted_clips.append({
                'id': clip_id,
                'path': clip['clip_path']
            })
            session['deleted_clips'] = deleted_clips
            
            # Backup clip data
            conn.execute('INSERT INTO clips_backup SELECT * FROM clips WHERE id = ?', 
                        (clip_id,))
            
            # Move file to temporary location instead of deleting
            if os.path.exists(clip['clip_path']):
                temp_path = clip['clip_path'] + '.deleted'
                os.rename(clip['clip_path'], temp_path)
            
            # Delete from database
            conn.execute('DELETE FROM clips WHERE id = ?', (clip_id,))
            conn.commit()
            
            return """
                <div class="alert alert-success">
                    <i class="bi bi-check-circle me-2"></i>
                    Clip deleted successfully
                </div>
            """
            
        except Exception as e:
            print(f"Error deleting clip: {str(e)}")
            return f"""
                <div class="alert alert-danger">
                    <i class="bi bi-exclamation-triangle me-2"></i>
                    Error deleting clip: {str(e)}
                </div>
            """
        finally:
            conn.close()

    @app.route('/clips/batch-delete', methods=['DELETE'])
    def batch_delete_clips():
        """Delete multiple clips at once"""
        print("=== Starting batch delete ===")
        print(f"Form data: {request.form}")
        print(f"Args: {request.args}")
        
        try:
            # Try to get clip IDs from both form data and query parameters
            clip_ids = request.form.getlist('clip-checkbox') or request.args.getlist('clip-checkbox')
            
            print(f"Clip IDs received: {clip_ids}")
            
            if not clip_ids:
                print("No clip IDs found in request")
                return """
                    <div class="alert alert-danger">
                        No clips selected for deletion
                    </div>
                """

            conn = get_db_connection()
            deleted_clips = []

            print(f"Processing {len(clip_ids)} clips for deletion")
            for clip_id in clip_ids:
                try:
                    print(f"Processing clip ID: {clip_id}")
                    clip = conn.execute('''
                        SELECT c.*, v.title as video_title 
                        FROM clips c 
                        JOIN videos v ON c.video_id = v.id 
                        WHERE c.id = ?
                    ''', (clip_id,)).fetchone()
                    
                    if clip:
                        print(f"Found clip: {dict(clip)}")
                        deleted_clips.append({
                            'id': clip_id,
                            'path': clip['clip_path']
                        })
                        
                        print(f"Backing up clip {clip_id}")
                        conn.execute('DELETE FROM clips_backup WHERE id = ?', (clip_id,))
                        conn.execute('INSERT INTO clips_backup SELECT * FROM clips WHERE id = ?', (clip_id,))
                        
                        if os.path.exists(clip['clip_path']):
                            temp_path = clip['clip_path'] + '.deleted'
                            print(f"Moving file from {clip['clip_path']} to {temp_path}")
                            if os.path.exists(temp_path):
                                os.remove(temp_path)
                            os.rename(clip['clip_path'], temp_path)
                        
                        print(f"Deleting clip {clip_id} from database")
                        conn.execute('DELETE FROM clips WHERE id = ?', (clip_id,))
                    else:
                        print(f"Clip {clip_id} not found in database")
                        
                except Exception as e:
                    print(f"Error processing clip {clip_id}: {str(e)}")
                    continue

            conn.commit()
            print(f"Stored {len(deleted_clips)} clips in session for restoration")
            session['deleted_clips'] = deleted_clips
            
            clips = get_clips_data()
            print("Returning updated template")
            return render_template('clips_list.html', clips=clips)
            
        except Exception as e:
            print(f"Error in batch delete: {str(e)}")
            if 'conn' in locals():
                conn.rollback()
            return f"""
                <div class="alert alert-danger">
                    <i class="bi bi-exclamation-triangle me-2"></i>
                    Error deleting clips: {str(e)}
                </div>
            """
        finally:
            if 'conn' in locals():
                conn.close()
            print("=== Batch delete completed ===")

    @app.route('/clips/restore/<int:clip_id>', methods=['POST'])
    def restore_clip(clip_id):
        """Restore a deleted clip"""
        try:
            deleted_clips = session.get('deleted_clips', [])
            clip_info = next((clip for clip in deleted_clips if int(clip['id']) == clip_id), None)
            
            if clip_info:
                conn = get_db_connection()
                try:
                    # Restore physical file
                    temp_path = clip_info['path'] + '.deleted'
                    if os.path.exists(temp_path):
                        if os.path.exists(clip_info['path']):
                            os.remove(clip_info['path'])  # Remove if exists
                        os.rename(temp_path, clip_info['path'])
                    
                    # Get the clip data from backup
                    clip_data = conn.execute('''
                        SELECT video_id, clip_name, start_time, end_time, clip_path 
                        FROM clips_backup WHERE id = ?
                    ''', (clip_id,)).fetchone()
                    
                    if clip_data:
                        # Remove any existing entry in clips table
                        conn.execute('DELETE FROM clips WHERE id = ?', (clip_id,))
                        
                        # Reinsert the clip
                        conn.execute('''
                            INSERT INTO clips 
                            (id, video_id, clip_name, start_time, end_time, clip_path)
                            VALUES (?, ?, ?, ?, ?, ?)
                        ''', (clip_id, clip_data[0], clip_data[1], clip_data[2], 
                              clip_data[3], clip_data[4]))
                        
                        # Clean up backup
                        conn.execute('DELETE FROM clips_backup WHERE id = ?', (clip_id,))
                        conn.commit()
                    
                    # Remove from deleted clips session
                    session['deleted_clips'] = [c for c in deleted_clips if int(c['id']) != clip_id]
                    
                    return render_template('clips_list.html', clips=get_clips_data())
                finally:
                    conn.close()
            
            return """
                <div class="alert alert-danger">
                    <i class="bi bi-exclamation-triangle me-2"></i>
                    Clip not found in deleted items
                </div>
            """
        except Exception as e:
            print(f"Error restoring clip: {str(e)}")
            return f"""
                <div class="alert alert-danger">
                    <i class="bi bi-exclamation-triangle me-2"></i>
                    Error restoring clip: {str(e)}
                </div>
            """ 

def get_clips_data():
    """Helper function to get formatted clips data"""
    conn = get_db_connection()
    try:
        clips = conn.execute('''
            SELECT 
                c.id,
                c.clip_name,
                c.start_time,
                c.end_time,
                c.clip_path,
                c.created_at,
                v.title as video_title
            FROM clips c
            JOIN videos v ON c.video_id = v.id
            ORDER BY c.created_at DESC
        ''').fetchall()
        
        return [{
            'id': clip[0],
            'name': clip[1],
            'start_time': clip[2],
            'end_time': clip[3],
            'path': clip[4],
            'created_at': clip[5],
            'video_title': clip[6]
        } for clip in clips]
    finally:
        conn.close() 