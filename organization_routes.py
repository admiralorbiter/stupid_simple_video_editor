from flask import render_template, jsonify, request
from helper import get_db_connection
import json
import random
import colorsys

def generate_distinct_color(existing_colors):
    """Generate a distinct color that's visually different from existing ones"""
    if not existing_colors:
        # Start with a vibrant color if no existing colors
        return '#2196F3'  # Material Blue
    
    # Convert hex colors to HSV for better control
    existing_hsv = [colorsys.rgb_to_hsv(*[int(c[i:i+2], 16)/255 for i in (1,3,5)]) 
                   for c in existing_colors]
    
    # Try to find a distinct hue
    best_hue = 0
    max_min_diff = 0
    
    for i in range(30):  # Try 30 different hues
        hue = i/30
        min_diff = min(abs(hue - h[0]) % 1.0 for h in existing_hsv)
        if min_diff > max_min_diff:
            max_min_diff = min_diff
            best_hue = hue
    
    # Convert back to RGB with good saturation and value
    rgb = colorsys.hsv_to_rgb(best_hue, 0.7, 0.95)
    return '#{:02x}{:02x}{:02x}'.format(int(rgb[0]*255), int(rgb[1]*255), int(rgb[2]*255))

def init_organization_routes(app):
    @app.route('/organize')
    def organize():
        """Render the organization page"""
        conn = get_db_connection()
        try:
            # Get folders and convert to dict
            folders = [dict(row) for row in conn.execute('''
                WITH RECURSIVE folder_tree AS (
                    SELECT 
                        id, 
                        name, 
                        parent_id, 
                        0 as level,
                        EXISTS (
                            SELECT 1 
                            FROM folders f2 
                            WHERE f2.parent_id = folders.id
                        ) as has_children,
                        is_open
                    FROM folders
                    WHERE parent_id IS NULL
                    UNION ALL
                    SELECT 
                        f.id, 
                        f.name, 
                        f.parent_id, 
                        ft.level + 1,
                        EXISTS (
                            SELECT 1 
                            FROM folders f2 
                            WHERE f2.parent_id = f.id
                        ) as has_children,
                        f.is_open
                    FROM folders f
                    JOIN folder_tree ft ON f.parent_id = ft.id
                )
                SELECT *
                FROM folder_tree
                ORDER BY level, name
            ''').fetchall()]
            
            # Get tags and convert to dict
            tags = [dict(row) for row in conn.execute('''
                SELECT 
                    t.*,
                    COUNT(vt.video_id) as video_count
                FROM tags t
                LEFT JOIN video_tags vt ON t.id = vt.tag_id
                GROUP BY t.id
                ORDER BY t.name
            ''').fetchall()]
            
            # Get videos and convert to dict
            videos = [dict(row) for row in conn.execute('''
                SELECT 
                    v.id,
                    v.title,
                    v.thumbnail_path,
                    GROUP_CONCAT(DISTINCT f.name) as folders,
                    json_group_array(
                        CASE 
                            WHEN t.id IS NOT NULL THEN 
                                json_object(
                                    'id', t.id,
                                    'name', t.name,
                                    'color', t.color
                                )
                            ELSE NULL
                        END
                    ) as tags
                FROM videos v
                LEFT JOIN video_folders vf ON v.id = vf.video_id
                LEFT JOIN folders f ON vf.folder_id = f.id
                LEFT JOIN video_tags vt ON v.id = vt.video_id
                LEFT JOIN tags t ON vt.tag_id = t.id
                GROUP BY v.id
                ORDER BY v.title
            ''').fetchall()]

            # Process the videos to handle tags
            for video in videos:
                try:
                    tags_json = video['tags']
                    if tags_json:
                        # Parse JSON array and filter out null values
                        tags_list = json.loads(tags_json)
                        video['tags'] = [tag for tag in tags_list if tag is not None]
                    else:
                        video['tags'] = []
                except (json.JSONDecodeError, TypeError):
                    video['tags'] = []

            return render_template('organize.html', 
                                folders=folders,
                                tags=tags,
                                videos=videos)
        finally:
            conn.close()

    @app.route('/api/folders', methods=['POST'])
    def create_folder():
        """Create a new folder"""
        data = request.json
        name = data.get('name')
        parent_id = data.get('parent_id')
        
        if not name:
            return jsonify({'status': 'error', 'message': 'Folder name is required'}), 400
            
        conn = get_db_connection()
        try:
            cursor = conn.execute('''
                INSERT INTO folders (name, parent_id)
                VALUES (?, ?)
            ''', (name, parent_id))
            folder_id = cursor.lastrowid
            conn.commit()
            
            return jsonify({
                'status': 'success',
                'folder': {
                    'id': folder_id,
                    'name': name,
                    'parent_id': parent_id
                }
            })
        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)}), 500
        finally:
            conn.close()

    @app.route('/api/tags', methods=['POST'])
    def create_tag():
        """Create a new tag with a distinct color"""
        data = request.json
        name = data.get('name')
        color = data.get('color')
        
        if not name:
            return jsonify({'status': 'error', 'message': 'Tag name is required'}), 400
            
        conn = get_db_connection()
        try:
            # Get existing tag colors
            existing_colors = [row['color'] for row in conn.execute(
                'SELECT color FROM tags').fetchall()]
            
            # Generate a distinct color if none provided
            if not color:
                color = generate_distinct_color(existing_colors)
            
            cursor = conn.execute('''
                INSERT INTO tags (name, color)
                VALUES (?, ?)
            ''', (name, color))
            tag_id = cursor.lastrowid
            conn.commit()
            
            return jsonify({
                'status': 'success',
                'tag': {
                    'id': tag_id,
                    'name': name,
                    'color': color
                }
            })
        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)}), 500
        finally:
            conn.close()

    @app.route('/api/videos/organize', methods=['POST'])
    def organize_videos():
        """Organize videos (add to folders and/or tags)"""
        data = request.json
        video_ids = data.get('video_ids', [])
        folder_ids = data.get('folder_ids', [])
        tag_ids = data.get('tag_ids', [])
        
        if not video_ids:
            return jsonify({'status': 'error', 'message': 'No videos selected'}), 400
            
        conn = get_db_connection()
        try:
            # Add to folders
            for video_id in video_ids:
                for folder_id in folder_ids:
                    conn.execute('''
                        INSERT OR IGNORE INTO video_folders (video_id, folder_id)
                        VALUES (?, ?)
                    ''', (video_id, folder_id))
                
                # Add tags
                for tag_id in tag_ids:
                    conn.execute('''
                        INSERT OR IGNORE INTO video_tags (video_id, tag_id)
                        VALUES (?, ?)
                    ''', (video_id, tag_id))
            
            conn.commit()
            return jsonify({'status': 'success'})
        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)}), 500
        finally:
            conn.close()

    @app.route('/api/folders/<int:folder_id>/toggle', methods=['POST'])
    def toggle_folder(folder_id):
        """Toggle folder open/closed state"""
        conn = get_db_connection()
        try:
            # Get current state
            cursor = conn.execute('SELECT is_open FROM folders WHERE id = ?', (folder_id,))
            current_state = cursor.fetchone()['is_open']
            
            # Toggle state
            new_state = not current_state
            conn.execute('UPDATE folders SET is_open = ? WHERE id = ?', 
                        (new_state, folder_id))
            conn.commit()
            
            return jsonify({'status': 'success', 'is_open': new_state})
        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)}), 500
        finally:
            conn.close() 