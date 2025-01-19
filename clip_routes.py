from tkinter import Tk, filedialog
from flask import flash, redirect, render_template, url_for, request, session, jsonify, send_file, make_response
import os
from pathlib import Path
import subprocess
from helper import *

def init_clip_routes(app):
    @app.route('/create-clip', methods=['POST'])
    def create_clip():
        """Create a new clip from a video"""
        try:
            video_id = request.form.get('video_id')
            start_time = request.form.get('start_time')
            end_time = request.form.get('end_time')
            clip_name = request.form.get('clip_name')
            
            if not all([video_id, start_time, end_time, clip_name]):
                return """
                    <div class="alert alert-danger">
                        <i class="bi bi-exclamation-triangle me-2"></i>
                        Missing required fields
                    </div>
                """
            
            conn = get_db_connection()
            video = conn.execute('SELECT file_path FROM videos WHERE id = ?', 
                               (video_id,)).fetchone()
            
            if not video:
                return """
                    <div class="alert alert-danger">
                        <i class="bi bi-exclamation-triangle me-2"></i>
                        Video not found
                    </div>
                """
            
            # Ensure output directories exist
            ensure_thumbnail_dirs()
            
            # Generate clip
            input_path = video['file_path']
            # Format filename to use underscores instead of colons
            safe_start = start_time.replace(':', '')
            safe_end = end_time.replace(':', '')
            output_filename = f"{clip_name}_{safe_start}-{safe_end}.mp4"
            output_path = os.path.join(session.get('clips_folder', 'clips'), output_filename)
            
            # Ensure the output path uses forward slashes
            output_path = output_path.replace('\\', '/')
            
            cmd = [
                'ffmpeg', '-y',
                '-ss', start_time,
                '-i', input_path,
                '-to', end_time,
                '-c', 'copy',
                output_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                return f"""
                    <div class="alert alert-danger">
                        <i class="bi bi-exclamation-triangle me-2"></i>
                        Error creating clip: {result.stderr}
                    </div>
                """
            
            # Generate thumbnail at clip start time
            thumbnail_filename = f"{clip_name}_{safe_start}.jpg"
            thumbnail_path = f"static/thumbnails/clips/{thumbnail_filename}"
            if not generate_thumbnail(output_path, thumbnail_path, start_time):
                print(f"Failed to generate thumbnail for clip: {clip_name}")
                thumbnail_path = None
            
            # Save to database
            conn.execute('''
                INSERT INTO clips (video_id, clip_name, start_time, end_time, clip_path, thumbnail_path)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (video_id, clip_name, start_time, end_time, output_path, thumbnail_path))
            conn.commit()
            
            return """
                <div class="alert alert-success">
                    <i class="bi bi-check-circle me-2"></i>
                    Clip created successfully
                </div>
            """
            
        except Exception as e:
            print(f"Error creating clip: {str(e)}")
            return f"""
                <div class="alert alert-danger">
                    <i class="bi bi-exclamation-triangle me-2"></i>
                    Error creating clip: {str(e)}
                </div>
            """
        finally:
            if 'conn' in locals():
                conn.close()
    @app.route('/clips', methods=['GET'])
    @app.route('/clips/<int:video_id>', methods=['GET'])
    def get_clips(video_id=None):
        """Get all clips or clips for a specific video"""
        try:
            conn = get_db_connection()
            
            if video_id:
                clips = conn.execute('''
                    SELECT 
                        c.id,
                        c.clip_name,
                        c.start_time,
                        c.end_time,
                        c.clip_path,
                        c.created_at,
                        c.thumbnail_path,
                        v.title as video_title
                    FROM clips c
                    JOIN videos v ON c.video_id = v.id
                    WHERE c.video_id = ?
                    ORDER BY c.created_at DESC
                ''', (video_id,)).fetchall()
            else:
                clips = conn.execute('''
                    SELECT 
                        c.id,
                        c.clip_name,
                        c.start_time,
                        c.end_time,
                        c.clip_path,
                        c.created_at,
                        c.thumbnail_path,
                        v.title as video_title
                    FROM clips c
                    JOIN videos v ON c.video_id = v.id
                    ORDER BY c.created_at DESC
                ''').fetchall()
            
            clips_data = [{
                'id': clip[0],
                'name': clip[1],
                'start_time': clip[2],
                'end_time': clip[3],
                'path': clip[4],
                'created_at': clip[5],
                'thumbnail_path': clip[6],
                'video_title': clip[7]
            } for clip in clips]
            
            if request.headers.get('HX-Request'):
                return render_template('clips_list.html', clips=clips_data)
            else:
                return render_template('clips.html', clips=clips_data)
            
        except Exception as e:
            print(f"Error fetching clips: {str(e)}")
            return f"""
                <div class="alert alert-danger">
                    <i class="bi bi-exclamation-triangle me-2"></i>
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
            conn.execute('DELETE FROM clips_backup WHERE id = ?', (clip_id,))
            conn.execute('INSERT INTO clips_backup SELECT * FROM clips WHERE id = ?', 
                        (clip_id,))
            
            # Move file to temporary location instead of deleting
            if os.path.exists(clip['clip_path']):
                temp_path = clip['clip_path'] + '.deleted'
                # If .deleted file already exists, remove it first
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                os.rename(clip['clip_path'], temp_path)
            
            # Delete from database
            conn.execute('DELETE FROM clips WHERE id = ?', (clip_id,))
            conn.commit()
            
            # Clean up orphaned thumbnails after successful deletion
            cleanup_orphaned_thumbnails()
            
            return """
                <div class="alert alert-success">
                    <i class="bi bi-check-circle me-2"></i>
                    Clip deleted successfully
                    <button class="btn btn-link text-success" 
                            hx-post="/clips/restore/{}">
                        Undo
                    </button>
                </div>
            """.format(clip_id)
            
        except Exception as e:
            print(f"Error deleting clip: {str(e)}")
            if 'conn' in locals():
                conn.rollback()
            return f"""
                <div class="alert alert-danger">
                    <i class="bi bi-exclamation-triangle me-2"></i>
                    Error deleting clip: {str(e)}
                </div>
            """
        finally:
            if 'conn' in locals():
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
            
            # Clean up orphaned thumbnails after all deletions
            cleanup_orphaned_thumbnails()
            
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
