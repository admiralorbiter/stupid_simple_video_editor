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
from models.models import db, Video, Clip, ClipSegment

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
            
            video = Video.query.get_or_404(video_id)
            
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
            
            # Execute FFmpeg command
            cmd = [
                'ffmpeg', '-i', video.file_path,
                '-filter_complex', filter_complex,
                '-map', '[outv]', '-map', '[outa]',
                '-c:v', 'libx264', '-c:a', 'aac',
                '-y', output_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                print(f"FFmpeg error: {result.stderr}")
                return jsonify({
                    'status': 'error',
                    'message': f'FFmpeg error: {result.stderr}'
                }), 500

            # Create new clip
            clip = Clip(
                video_id=video_id,
                clip_name=clip_name,
                start_time=segments[0]['start'],
                end_time=segments[-1]['end'],
                clip_path=output_path
            )
            db.session.add(clip)
            db.session.flush()  # Get the clip ID before committing

            # Create segments
            for segment in segments:
                clip_segment = ClipSegment(
                    clip_id=clip.id,
                    start_time=segment['start'],
                    end_time=segment['end']
                )
                db.session.add(clip_segment)

            db.session.commit()
            return jsonify({
                'status': 'success',
                'clip_id': clip.id
            })

        except Exception as e:
            print(f"Error creating clip: {str(e)}")
            db.session.rollback()
            return jsonify({
                'status': 'error',
                'message': str(e)
            }), 500

    @app.route('/clips', methods=['GET'])
    @app.route('/clips/<int:video_id>', methods=['GET'])
    def get_clips(video_id=None):
        """Get all clips or clips for a specific video"""
        try:
            if video_id:
                clips = Clip.query.join(Video).filter(Clip.video_id == video_id)\
                    .order_by(Clip.created_at.desc()).all()
            else:
                clips = Clip.query.join(Video).order_by(Clip.created_at.desc()).all()
            
            clips_data = [{
                'id': clip.id,
                'name': clip.clip_name,
                'start_time': clip.start_time,
                'end_time': clip.end_time,
                'path': clip.clip_path,
                'created_at': clip.created_at,
                'thumbnail_path': clip.thumbnail_path,
                'video_title': clip.video.title
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

    @app.route('/clips/delete/<int:clip_id>', methods=['DELETE'])
    def delete_clip(clip_id):
        """Delete a clip and its file"""
        try:
            clip = Clip.query.get_or_404(clip_id)
            
            # Store clip info for restoration
            deleted_clips = session.get('deleted_clips', [])
            deleted_clips.append({
                'id': clip_id,
                'path': clip.clip_path
            })
            session['deleted_clips'] = deleted_clips
            
            # Move file to temporary location instead of deleting
            if os.path.exists(clip.clip_path):
                temp_path = clip.clip_path + '.deleted'
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                os.rename(clip.clip_path, temp_path)
            
            db.session.delete(clip)
            db.session.commit()
            
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
            db.session.rollback()
            return f"""
                <div class="alert alert-danger">
                    <i class="bi bi-exclamation-triangle me-2"></i>
                    Error deleting clip: {str(e)}
                </div>
            """

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

            deleted_clips = session.get('deleted_clips', [])

            for clip_id in clip_ids:
                clip = Clip.query.get_or_404(clip_id)
                
                # Store clip info for restoration
                deleted_clips.append({
                    'id': clip_id,
                    'path': clip.clip_path,
                    'batch': True,  # Mark as part of batch deletion
                    'batch_id': int(time.time())  # Add timestamp as batch ID
                })
                
                # Move file to temporary location
                if os.path.exists(clip.clip_path):
                    temp_path = clip.clip_path + '.deleted'
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
                    os.rename(clip.clip_path, temp_path)
                
                db.session.delete(clip)

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
            db.session.rollback()
            return f"""
                <div class="alert alert-danger">
                    <i class="bi bi-exclamation-triangle me-2"></i>
                    Error deleting clips: {str(e)}
                </div>
            """

    @app.route('/clips/restore-batch/<int:batch_id>', methods=['POST'])
    def restore_batch_clips(batch_id):
        """Restore a batch of deleted clips"""
        try:
            deleted_clips = session.get('deleted_clips', [])
            batch_clips = [clip for clip in deleted_clips if clip.get('batch_id') == batch_id]
            
            if batch_clips:
                restored_count = 0
                
                for clip_info in batch_clips:
                    try:
                        # Restore physical file
                        temp_path = clip_info['path'] + '.deleted'
                        if os.path.exists(temp_path):
                            if os.path.exists(clip_info['path']):
                                os.remove(clip_info['path'])
                            os.rename(temp_path, clip_info['path'])
                        
                        # Restore from database
                        clip = Clip.query.get_or_404(clip_info['id'])
                        db.session.delete(clip)
                        db.session.commit()
                        restored_count += 1
                    except Exception as e:
                        print(f"Error restoring clip {clip_info['id']}: {str(e)}")
                        continue
                
                # Update session
                session['deleted_clips'] = [c for c in deleted_clips if c.get('batch_id') != batch_id]
                db.session.commit()
                
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
            
            clip = Clip.query.get_or_404(clip_id)
            
            # Update file name if clip exists
            old_path = clip.clip_path
            new_path = old_path.replace(clip.clip_name, new_name)
            
            if os.path.exists(old_path):
                os.rename(old_path, new_path)
            
            clip.clip_name = new_name
            clip.clip_path = new_path
            db.session.commit()
            
            return jsonify({
                'status': 'success',
                'name': new_name,
                'path': new_path
            })
            
        except Exception as e:
            db.session.rollback()
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/clips/search', methods=['GET'])
    def search_clips():
        """Search clips by name"""
        query = request.args.get('q', '').strip()
        
        clips_query = Clip.query.join(Video)
        
        if query:
            clips_query = clips_query.filter(Clip.clip_name.ilike(f'%{query}%'))
        
        clips = clips_query.order_by(Clip.created_at.desc()).all()
        
        clips_data = [{
            'id': clip.id,
            'name': clip.clip_name,
            'start_time': clip.start_time,
            'end_time': clip.end_time,
            'path': clip.clip_path,
            'created_at': clip.created_at,
            'thumbnail_path': clip.thumbnail_path,
            'video_title': clip.video.title
        } for clip in clips]
        
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
        segments = sorted(segments, key=lambda x: timeToSeconds(x['start']))
        filters = []
        
        for segment in segments:
            start = timeToSeconds(segment['start'])
            end = timeToSeconds(segment['end'])
            
            if not (math.isnan(start) or math.isnan(end)):
                filters.append(f"between(t,{start},{end})")
        
        if not filters:
            raise ValueError("No valid segments provided")
            
        return f"select='{'+'.join(filters)}',setpts=N/FRAME_RATE/TB"
    except Exception as e:
        print(f"Error creating filter: {str(e)}")
        raise e
