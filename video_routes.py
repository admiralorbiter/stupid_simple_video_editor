from flask import flash, redirect, render_template, url_for, request, session, jsonify, send_file, make_response
import os
from pathlib import Path
import subprocess
from tkinter import Tk, filedialog
from helper import *

def init_video_routes(app):
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
        video['video_url'] = url_for('serve_video', video_id=video['id'])
        
        return render_template('edit_video.html', video=video)

    @app.route('/browse-folder')
    def browse_folder():
        """Open system folder browser dialog and return selected path"""
        try:
            root = Tk()
            root.withdraw()
            
            folder_path = filedialog.askdirectory()
            root.destroy()
            
            if folder_path:
                session['selected_folder'] = folder_path
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
                    thumbnail_path = 'static/thumbnails/videos/' + thumbnail_filename
                    relative_thumbnail_path = 'thumbnails/videos/' + thumbnail_filename
                    
                    # Generate thumbnail using FFmpeg
                    try:
                        cmd = [
                            'ffmpeg', '-y',
                            '-ss', '00:00:01',
                            '-i', absolute_path,
                            '-vframes', '1',
                            '-q:v', '2',
                            thumbnail_path.replace('/', os.path.sep)
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
                    
                    cursor = conn.execute('''
                        INSERT OR IGNORE INTO videos (title, file_path, thumbnail_path)
                        VALUES (?, ?, ?)
                        RETURNING id
                    ''', (video_info['title'], absolute_path, relative_thumbnail_path if has_thumbnail else None))
                    
                    result = cursor.fetchone()
                    if result is None:
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
                    existing = conn.execute('SELECT id FROM videos WHERE file_path = ?', 
                                         (str(file),)).fetchone()
                    
                    if existing:
                        skipped_count += 1
                        continue
                    
                    try:
                        thumbnail_filename = f"{file.stem}_thumb.jpg"
                        thumbnail_path = f"static/thumbnails/videos/{thumbnail_filename}"
                        if generate_thumbnail(str(file), thumbnail_path):
                            relative_thumbnail_path = f"thumbnails/videos/{thumbnail_filename}"
                        else:
                            relative_thumbnail_path = None
                        
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