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
            # Get all folders with their parent relationships
            folders_query = '''
                WITH RECURSIVE folder_tree(id, name, parent_id, is_open, level) AS (
                    SELECT id, name, parent_id, is_open, 0 as level
                    FROM folders 
                    WHERE parent_id IS NULL
                    UNION ALL
                    SELECT f.id, f.name, f.parent_id, f.is_open, ft.level + 1
                    FROM folders f
                    JOIN folder_tree ft ON f.parent_id = ft.id
                )
                SELECT * FROM folder_tree
                ORDER BY level, name
            '''
            folders = conn.execute(folders_query).fetchall()

            # Get categories with their tags
            categories = conn.execute('''
                SELECT c.id, c.name, 
                       GROUP_CONCAT(t.id) as tag_ids,
                       GROUP_CONCAT(t.name) as tag_names,
                       GROUP_CONCAT(t.color) as tag_colors
                FROM tag_categories c
                LEFT JOIN tags t ON c.id = t.category_id
                GROUP BY c.id, c.name
            ''').fetchall()

            # Format categories and their tags
            formatted_categories = []
            for cat in categories:
                category = {
                    'id': cat['id'],
                    'name': cat['name'],
                    'tags': []
                }
                
                if cat['tag_ids']:
                    tag_ids = cat['tag_ids'].split(',')
                    tag_names = cat['tag_names'].split(',')
                    tag_colors = cat['tag_colors'].split(',')
                    
                    category['tags'] = [
                        {'id': tid, 'name': tname, 'color': tcolor}
                        for tid, tname, tcolor in zip(tag_ids, tag_names, tag_colors)
                    ]
                
                formatted_categories.append(category)

            # Get uncategorized tags
            uncategorized_tags = conn.execute('''
                SELECT id, name, color 
                FROM tags 
                WHERE category_id IS NULL
            ''').fetchall()

            # Get videos with their tags and create a tag color mapping
            tag_colors = {tag['name']: tag['color'] for tag in conn.execute('SELECT name, color FROM tags').fetchall()}
            
            videos = conn.execute('''
                SELECT 
                    v.*,
                    GROUP_CONCAT(t.name) as tags,
                    GROUP_CONCAT(t.color) as tag_colors,
                    (
                        SELECT GROUP_CONCAT(f.name)
                        FROM video_folders vf
                        JOIN folders f ON f.id = vf.folder_id
                        WHERE vf.video_id = v.id
                    ) as folders
                FROM videos v
                LEFT JOIN video_tags vt ON v.id = vt.video_id
                LEFT JOIN tags t ON vt.tag_id = t.id
                GROUP BY v.id
            ''').fetchall()

            return render_template('organize.html',
                                 categories=formatted_categories,
                                 tags=uncategorized_tags,
                                 folders=folders,
                                 videos=videos,
                                 tag_colors=tag_colors)
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

    @app.route('/api/categories', methods=['POST'])
    def create_category():
        """Create a new tag category"""
        data = request.json
        name = data.get('name')
        
        if not name:
            return jsonify({'status': 'error', 'message': 'Category name is required'}), 400
            
        conn = get_db_connection()
        try:
            cursor = conn.execute(
                'INSERT INTO tag_categories (name) VALUES (?)',
                (name,)
            )
            conn.commit()
            
            return jsonify({
                'status': 'success',
                'category_id': cursor.lastrowid,
                'name': name
            })
        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)}), 500
        finally:
            conn.close()

    @app.route('/api/categories/<int:category_id>', methods=['PUT', 'DELETE'])
    def manage_category(category_id):
        """Update or delete a tag category"""
        conn = get_db_connection()
        try:
            if request.method == 'DELETE':
                conn.execute('DELETE FROM tag_categories WHERE id = ?', (category_id,))
                conn.commit()
                return jsonify({'status': 'success'})
            
            elif request.method == 'PUT':
                data = request.json
                name = data.get('name')
                if not name:
                    return jsonify({'status': 'error', 'message': 'Name is required'}), 400
                
                conn.execute(
                    'UPDATE tag_categories SET name = ? WHERE id = ?',
                    (name, category_id)
                )
                conn.commit()
                return jsonify({'status': 'success'})
            
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
        category_id = data.get('category_id')
        
        if not name:
            return jsonify({'status': 'error', 'message': 'Tag name is required'}), 400
            
        conn = get_db_connection()
        try:
            existing_colors = [row['color'] for row in conn.execute(
                'SELECT color FROM tags').fetchall()]
            
            if not color:
                color = generate_distinct_color(existing_colors)
            
            cursor = conn.execute('''
                INSERT INTO tags (name, color, category_id)
                VALUES (?, ?, ?)
            ''', (name, color, category_id))
            tag_id = cursor.lastrowid
            conn.commit()
            
            return jsonify({
                'status': 'success',
                'tag': {
                    'id': tag_id,
                    'name': name,
                    'color': color,
                    'category_id': category_id
                }
            })
        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)}), 500
        finally:
            conn.close()

    @app.route('/api/tags/<int:tag_id>', methods=['PUT'])
    def update_tag(tag_id):
        """Update a tag's category"""
        data = request.json
        category_id = data.get('category_id')
        
        # Convert empty string to None for uncategorized
        if category_id == '':
            category_id = None
        
        conn = get_db_connection()
        try:
            # Verify the tag exists first
            tag = conn.execute('SELECT id FROM tags WHERE id = ?', (tag_id,)).fetchone()
            if not tag:
                return jsonify({'status': 'error', 'message': 'Tag not found'}), 404
            
            # If category_id is provided, verify it exists
            if category_id is not None:
                category = conn.execute('SELECT id FROM tag_categories WHERE id = ?', 
                                     (category_id,)).fetchone()
                if not category:
                    return jsonify({'status': 'error', 'message': 'Category not found'}), 404
            
            # Update the tag
            conn.execute('''
                UPDATE tags 
                SET category_id = ?
                WHERE id = ?
            ''', (category_id, tag_id))
            conn.commit()
            
            return jsonify({'status': 'success'})
        except Exception as e:
            conn.rollback()
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
            # Verify all video_ids exist
            for video_id in video_ids:
                video = conn.execute('SELECT id FROM videos WHERE id = ?', (video_id,)).fetchone()
                if not video:
                    return jsonify({'status': 'error', 'message': f'Video {video_id} not found'}), 404
            
            # Verify all tag_ids exist if provided
            if tag_ids:
                for tag_id in tag_ids:
                    tag = conn.execute('SELECT id FROM tags WHERE id = ?', (tag_id,)).fetchone()
                    if not tag:
                        return jsonify({'status': 'error', 'message': f'Tag {tag_id} not found'}), 404
            
            # Add tags to videos
            for video_id in video_ids:
                for tag_id in tag_ids:
                    conn.execute('''
                        INSERT OR IGNORE INTO video_tags (video_id, tag_id)
                        VALUES (?, ?)
                    ''', (video_id, tag_id))
            
            conn.commit()
            return jsonify({'status': 'success'})
        except Exception as e:
            conn.rollback()
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