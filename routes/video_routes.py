import json
from flask import flash, redirect, render_template, send_from_directory, url_for, request, session, jsonify, send_file, make_response
import os
from pathlib import Path
import subprocess
from tkinter import Tk, filedialog

from gradio import Video
from helper import *
from werkzeug.utils import secure_filename
from models.models import db, Video

def init_video_routes(app):
    @app.route('/stream_video/<int:video_id>')
    def stream_video(video_id):
        """Stream video file"""
        video = Video.query.get_or_404(video_id)
        
        if not os.path.exists(video.file_path):
            return "Video file not found", 404

        def generate():
            with open(video.file_path, 'rb') as video_file:
                while True:
                    chunk = video_file.read(8192)
                    if not chunk:
                        break
                    yield chunk

        response = app.response_class(
            generate(),
            mimetype='video/mp4'
        )
        response.headers['Accept-Ranges'] = 'bytes'
        return response

    @app.route('/edit-video/<int:video_id>')
    def edit_video(video_id):
        """Video editing interface"""
        video = Video.query.get_or_404(video_id)
        
        video_data = {
            'id': video.id,
            'title': video.title,
            'file_path': video.file_path,
            'thumbnail_path': video.thumbnail_path,
            'video_url': url_for('stream_video', video_id=video.id)
        }
        
        return render_template('edit_video.html', video=video_data)

    @app.route('/browse-folder')
    def browse_folder():
        """Open system folder browser dialog and return selected path"""
        try:
            root = Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            
            folder_path = filedialog.askdirectory(parent=root)
            
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
            return jsonify({
                "error": "No folder selected or invalid folder path."
            })
        
        # Clean up thumbnails before scanning
        cleanup_thumbnails('videos')
        
        # Count total videos for progress
        total_videos = sum(1 for file in Path(folder_path).glob('*') if is_video_file(str(file)))
        
        if total_videos == 0:
            return jsonify({
                "total": 0
            })
        
        return jsonify({
            "total": total_videos
        })

    @app.route('/scan-progress', methods=['POST'])
    def scan_progress():
        """Process videos in chunks and report progress"""
        data = request.get_json()
        folder_path = session.get('selected_folder')
        processed = int(data.get('processed', 0))
        total = int(data.get('total', 0))
        
        try:
            files = [f for f in Path(folder_path).glob('*') if is_video_file(str(f))]
            chunk_size = 2  # Process 2 files at a time
            
            current_files = files[processed:processed + chunk_size]
            for file in current_files:
                absolute_path = str(file.absolute())
                
                # Generate thumbnail
                thumbnail_filename = secure_filename(f"{file.stem}_thumb.jpg")
                thumbnail_path = Path('static/thumbnails/videos') / thumbnail_filename
                relative_thumbnail_path = f'thumbnails/videos/{thumbnail_filename}'
                
                # Ensure thumbnail directory exists
                thumbnail_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Generate thumbnail using FFmpeg
                try:
                    cmd = [
                        'ffmpeg', '-y',
                        '-ss', '00:00:01',
                        '-i', absolute_path,
                        '-vframes', '1',
                        '-q:v', '2',
                        str(thumbnail_path)
                    ]
                    subprocess.run(cmd, capture_output=True, check=True)
                    has_thumbnail = True
                except subprocess.CalledProcessError as e:
                    print(f"Failed to generate thumbnail for {file}: {e}")
                    has_thumbnail = False
                    relative_thumbnail_path = None
                
                # Store in database using SQLAlchemy
                video = Video(
                    title=file.stem,
                    file_path=absolute_path,
                    thumbnail_path=relative_thumbnail_path if has_thumbnail else None
                )
                db.session.merge(video)  # Use merge to handle duplicates
                db.session.commit()
                
                processed += 1
            
            progress = int((processed / total) * 100)
            
            if processed >= total:
                # Scan complete, return the video list HTML
                videos = Video.query.order_by(Video.title).all()
                html = render_template('video_list.html', videos=videos)
                return jsonify({
                    "progress": 100,
                    "processed": processed,
                    "status": "Scan complete!",
                    "html": html
                })
            else:
                # Return progress update
                return jsonify({
                    "progress": progress,
                    "processed": processed,
                    "status": f"Processed {processed} of {total} videos..."
                })
                
        except Exception as e:
            print(f"Error during scan: {e}")
            db.session.rollback()
            return jsonify({
                "error": str(e)
            }), 500

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
        
        try:
            imported_count = 0
            skipped_count = 0
            
            for file in Path(folder_path).glob('*'):
                if is_video_file(str(file)):
                    # Check if video already exists
                    existing = Video.query.filter_by(file_path=str(file)).first()
                    
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
                        
                        video = Video(
                            title=file.stem,
                            file_path=str(file),
                            thumbnail_path=relative_thumbnail_path
                        )
                        db.session.add(video)
                        imported_count += 1
                        
                    except Exception as e:
                        print(f"Error processing {file}: {str(e)}")
                        continue
            
            db.session.commit()
            return f"""
                <div class="alert alert-success">
                    <i class="bi bi-check-circle me-2"></i>
                    Imported {imported_count} videos
                    {f'(skipped {skipped_count} existing)' if skipped_count else ''}
                </div>
            """
            
        except Exception as e:
            db.session.rollback()
            print(f"Error importing videos: {str(e)}")
            return f"""
                <div class="alert alert-danger">
                    <i class="bi bi-exclamation-triangle me-2"></i>
                    Error importing videos: {str(e)}
                </div>
            """ 