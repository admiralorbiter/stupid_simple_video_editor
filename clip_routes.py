from tkinter import Tk, filedialog
from flask import flash, redirect, render_template, url_for, request, session, jsonify, send_file, make_response
import os
from pathlib import Path
import subprocess
from helper import *
import time
import json
from werkzeug.utils import secure_filename
import math

def init_clip_routes(app):
    @app.route('/create-clip', methods=['POST'])
    def create_clip():
        """Create a new clip from a video"""
        try:
            video_id = request.form.get('video_id')
            clip_name = request.form.get('clip_name')
            segments_data = request.form.get('segments')
            
            print(f"Received segments data: {segments_data}")
            segments_data = json.loads(segments_data)
            segments = segments_data.get('segments', [])
            
            if not segments:
                return jsonify({
                    'status': 'error',
                    'message': 'No segments provided'
                }), 400
            
            conn = get_db_connection()
            video = conn.execute('SELECT file_path FROM videos WHERE id = ?', 
                               [video_id]).fetchone()
            
            if not video:
                return jsonify({
                    'status': 'error',
                    'message': 'Video not found'
                }), 404
            
            # Create output directory if it doesn't exist
            output_dir = os.path.join('clips', video_id)
            os.makedirs(output_dir, exist_ok=True)
            
            # Generate output path
            output_filename = secure_filename(clip_name) if clip_name else 'clippy'
            if not output_filename.endswith('.mp4'):
                output_filename += '.mp4'
            output_path = os.path.join(output_dir, output_filename)
            
            # Create FFmpeg filter for trimming
            filter_parts = []
            for i, segment in enumerate(segments):
                start = timeToSeconds(segment['start'])
                end = timeToSeconds(segment['end'])
                duration = end - start
                filter_parts.append(f"[0:v]trim=start={start}:duration={duration},setpts=PTS-STARTPTS[v{i}];")
                filter_parts.append(f"[0:a]atrim=start={start}:duration={duration},asetpts=PTS-STARTPTS[a{i}];")
            
            # Add concat if we have segments
            n_segments = len(segments)
            video_inputs = ''.join(f'[v{i}]' for i in range(n_segments))
            audio_inputs = ''.join(f'[a{i}]' for i in range(n_segments))
            filter_parts.append(f"{video_inputs}concat=n={n_segments}:v=1[outv];")
            filter_parts.append(f"{audio_inputs}concat=n={n_segments}:v=0:a=1[outa]")
            
            filter_complex = ''.join(filter_parts)
            print(f"Created filter complex: {filter_complex}")
            
            # Execute FFmpeg command
            cmd = [
                'ffmpeg', '-i', video['file_path'],
                '-filter_complex', filter_complex,
                '-map', '[outv]', '-map', '[outa]',
                '-c:v', 'libx264', '-c:a', 'aac',
                '-y', output_path
            ]
            
            print(f"Executing FFmpeg command: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                print(f"FFmpeg error: {result.stderr}")
                return jsonify({
                    'status': 'error',
                    'message': f'FFmpeg error: {result.stderr}'
                }), 500

            # Save clip info to database - matching your schema
            clip_id = conn.execute('''
                INSERT INTO clips (
                    video_id,
                    clip_name,
                    start_time,
                    end_time,
                    clip_path,
                    thumbnail_path,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, NULL, CURRENT_TIMESTAMP)
            ''', [
                video_id,
                clip_name,
                segments[0]['start'],
                segments[-1]['end'],
                output_path
            ]).lastrowid

            # Save individual segments
            for segment in segments:
                conn.execute('''
                    INSERT INTO clip_segments (
                        clip_id,
                        start_time,
                        end_time,
                        created_at
                    ) VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ''', [clip_id, segment['start'], segment['end']])

            conn.commit()
            print("Clip created successfully")
            return jsonify({
                'status': 'success',
                'clip_id': clip_id
            })

        except Exception as e:
            print(f"Error creating clip: {str(e)}")
            if 'conn' in locals():
                conn.rollback()
            return jsonify({
                'status': 'error',
                'message': str(e)
            }), 500
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
        try:
            clip_ids = request.form.getlist('clip-checkbox') or request.args.getlist('clip-checkbox')
            
            if not clip_ids:
                return """
                    <div class="alert alert-danger">
                        <i class="bi bi-exclamation-triangle me-2"></i>
                        No clips selected for deletion
                    </div>
                """

            conn = get_db_connection()
            deleted_clips = session.get('deleted_clips', [])

            for clip_id in clip_ids:
                clip = conn.execute('''
                    SELECT c.*, v.title as video_title 
                    FROM clips c 
                    JOIN videos v ON c.video_id = v.id 
                    WHERE c.id = ?
                ''', (clip_id,)).fetchone()
                
                if clip:
                    # Store clip info for restoration
                    deleted_clips.append({
                        'id': clip_id,
                        'path': clip['clip_path'],
                        'batch': True,  # Mark as part of batch deletion
                        'batch_id': int(time.time())  # Add timestamp as batch ID
                    })
                    
                    # Backup clip data
                    conn.execute('DELETE FROM clips_backup WHERE id = ?', (clip_id,))
                    conn.execute('INSERT INTO clips_backup SELECT * FROM clips WHERE id = ?', (clip_id,))
                    
                    # Move file to temporary location
                    if os.path.exists(clip['clip_path']):
                        temp_path = clip['clip_path'] + '.deleted'
                        if os.path.exists(temp_path):
                            os.remove(temp_path)
                        os.rename(clip['clip_path'], temp_path)
                    
                    conn.execute('DELETE FROM clips WHERE id = ?', (clip_id,))

            conn.commit()
            session['deleted_clips'] = deleted_clips
            
            # Clean up orphaned thumbnails
            cleanup_orphaned_thumbnails()
            
            return """
                <div class="alert alert-success">
                    <i class="bi bi-check-circle me-2"></i>
                    {} clips deleted successfully
                    <button class="btn btn-link text-success" 
                            onclick="restoreBatchClips({})">
                        Undo Batch Delete
                    </button>
                </div>
                {}
            """.format(len(clip_ids), deleted_clips[-1]['batch_id'], 
                      render_template('clips_list.html', clips=get_clips_data()))
            
        except Exception as e:
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

    @app.route('/clips/restore-batch/<int:batch_id>', methods=['POST'])
    def restore_batch_clips(batch_id):
        """Restore a batch of deleted clips"""
        try:
            deleted_clips = session.get('deleted_clips', [])
            batch_clips = [clip for clip in deleted_clips if clip.get('batch_id') == batch_id]
            
            if batch_clips:
                conn = get_db_connection()
                restored_count = 0
                
                for clip_info in batch_clips:
                    try:
                        # Restore physical file
                        temp_path = clip_info['path'] + '.deleted'
                        if os.path.exists(temp_path):
                            if os.path.exists(clip_info['path']):
                                os.remove(clip_info['path'])
                            os.rename(temp_path, clip_info['path'])
                        
                        # Restore from backup
                        clip_data = conn.execute('''
                            SELECT video_id, clip_name, start_time, end_time, clip_path 
                            FROM clips_backup WHERE id = ?
                        ''', (clip_info['id'],)).fetchone()
                        
                        if clip_data:
                            conn.execute('DELETE FROM clips WHERE id = ?', (clip_info['id'],))
                            conn.execute('''
                                INSERT INTO clips 
                                (id, video_id, clip_name, start_time, end_time, clip_path)
                                VALUES (?, ?, ?, ?, ?, ?)
                            ''', (clip_info['id'], clip_data[0], clip_data[1], 
                                  clip_data[2], clip_data[3], clip_data[4]))
                            restored_count += 1
                    except Exception as e:
                        print(f"Error restoring clip {clip_info['id']}: {str(e)}")
                        continue
                
                # Update session
                session['deleted_clips'] = [c for c in deleted_clips if c.get('batch_id') != batch_id]
                conn.commit()
                
                return render_template('clips_list.html', clips=get_clips_data())
                
            return """
                <div class="alert alert-danger">
                    <i class="bi bi-exclamation-triangle me-2"></i>
                    Batch not found in deleted items
                </div>
            """
        except Exception as e:
            return f"""
                <div class="alert alert-danger">
                    <i class="bi bi-exclamation-triangle me-2"></i>
                    Error restoring batch: {str(e)}
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

    @app.route('/clips/rename/<int:clip_id>', methods=['PATCH'])
    def rename_clip(clip_id):
        """Rename a clip"""
        try:
            new_name = request.json.get('name')
            if not new_name:
                return jsonify({'status': 'error', 'message': 'Name is required'}), 400
            
            conn = get_db_connection()
            # Get current clip info
            clip = conn.execute('SELECT clip_path, clip_name FROM clips WHERE id = ?', 
                              (clip_id,)).fetchone()
            
            if not clip:
                return jsonify({'status': 'error', 'message': 'Clip not found'}), 404
            
            # Update file name if clip exists
            old_path = clip['clip_path']
            new_path = old_path.replace(clip['clip_name'], new_name)
            
            if os.path.exists(old_path):
                os.rename(old_path, new_path)
            
            # Update database
            conn.execute('''
                UPDATE clips 
                SET clip_name = ?,
                    clip_path = ?
                WHERE id = ?
            ''', (new_name, new_path, clip_id))
            
            conn.commit()
            return jsonify({
                'status': 'success',
                'name': new_name,
                'path': new_path
            })
            
        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)}), 500
        finally:
            if 'conn' in locals():
                conn.close()

    @app.route('/clips/search', methods=['GET'])
    def search_clips():
        """Search clips by name"""
        query = request.args.get('q', '').strip()
        
        sql = '''
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
            WHERE 1=1
        '''
        params = []
        
        if query:
            sql += ' AND c.clip_name LIKE ?'
            params.append(f'%{query}%')
        
        sql += ' ORDER BY c.created_at DESC'
        
        conn = get_db_connection()
        clips = conn.execute(sql, params).fetchall()
        
        # Format clips data to match the structure expected by the template
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
        
        conn.close()
        
        return render_template('clips_list.html', clips=clips_data)

def timeToSeconds(time_str):
    """Convert time string (MM:SS) to seconds"""
    try:
        if ':' not in time_str:
            return float(time_str)
        minutes, seconds = map(float, time_str.split(':'))
        return minutes * 60 + seconds
    except ValueError as e:
        print(f"Error converting time: {time_str}")
        raise e

def create_segment_filter(segments):
    """Create FFmpeg filter complex for keeping selected segments"""
    try:
        # Sort segments by start time
        segments = sorted(segments, key=lambda x: timeToSeconds(x['start']))
        
        # Create filters to keep only the selected segments
        filters = []
        
        for segment in segments:
            start = timeToSeconds(segment['start'])
            end = timeToSeconds(segment['end'])
            
            # Only add valid segments
            if not (math.isnan(start) or math.isnan(end)):
                filters.append(f"between(t,{start},{end})")
        
        if not filters:
            raise ValueError("No valid segments provided")
            
        # Join filters with + to keep any matching segments
        return f"select='{'+'.join(filters)}',setpts=N/FRAME_RATE/TB"
    except Exception as e:
        print(f"Error creating filter: {str(e)}")
        raise e
