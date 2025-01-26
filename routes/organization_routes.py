from flask import render_template, jsonify, request
from helper import get_db_connection
import json
import random
import colorsys
from models.models import db, Video, Tag, TagCategory, Folder

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
        """Organization interface for videos, tags, and folders"""
        try:
            # Get all tag categories with their tags
            categories = TagCategory.query.all()
            formatted_categories = [{
                'id': cat.id,
                'name': cat.name,
                'tags': [{
                    'id': tag.id,
                    'name': tag.name,
                    'color': tag.color
                } for tag in cat.tags]
            } for cat in categories]
            
            # Get uncategorized tags
            uncategorized_tags = Tag.query.filter_by(category_id=None).all()
            
            # Get all folders
            folders = Folder.query.order_by(Folder.position).all()
            
            # Get videos with their tags and folders
            videos = Video.query.all()
            videos_data = [{
                'id': video.id,
                'title': video.title,
                'file_path': video.file_path,
                'thumbnail_path': video.thumbnail_path,
                'tags': [{'name': tag.name, 'color': tag.color} for tag in video.tags],
                'folders': [folder.name for folder in video.folders]
            } for video in videos]
            
            # Create tag color mapping
            tag_colors = {tag.name: tag.color for tag in Tag.query.all()}
            
            return render_template('organize.html',
                               categories=formatted_categories,
                               tags=uncategorized_tags,
                               folders=folders,
                               videos=videos_data,
                               tag_colors=tag_colors)
                               
        except Exception as e:
            print(f"Error in organize route: {str(e)}")
            return str(e), 500

    @app.route('/api/folders', methods=['POST'])
    def create_folder():
        """Create a new folder"""
        data = request.json
        name = data.get('name')
        parent_id = data.get('parent_id')
        
        if not name:
            return jsonify({'status': 'error', 'message': 'Folder name is required'}), 400
            
        try:
            folder = Folder(name=name, parent_id=parent_id)
            db.session.add(folder)
            db.session.commit()
            
            return jsonify({
                'status': 'success',
                'folder': {
                    'id': folder.id,
                    'name': folder.name,
                    'parent_id': folder.parent_id
                }
            })
        except Exception as e:
            db.session.rollback()
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/api/categories', methods=['POST'])
    def create_category():
        """Create a new tag category"""
        data = request.json
        name = data.get('name')
        
        if not name:
            return jsonify({'status': 'error', 'message': 'Category name is required'}), 400
            
        try:
            category = TagCategory(name=name)
            db.session.add(category)
            db.session.commit()
            
            return jsonify({
                'status': 'success',
                'category_id': category.id,
                'name': category.name
            })
        except Exception as e:
            db.session.rollback()
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/api/categories/<int:category_id>', methods=['PUT', 'DELETE'])
    def manage_category(category_id):
        """Update or delete a tag category"""
        try:
            category = TagCategory.query.get_or_404(category_id)
            
            if request.method == 'DELETE':
                db.session.delete(category)
                db.session.commit()
                return jsonify({'status': 'success'})
            
            elif request.method == 'PUT':
                data = request.json
                name = data.get('name')
                if not name:
                    return jsonify({'status': 'error', 'message': 'Name is required'}), 400
                
                category.name = name
                db.session.commit()
                return jsonify({'status': 'success'})
            
        except Exception as e:
            db.session.rollback()
            return jsonify({'status': 'error', 'message': str(e)}), 500

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
        try:
            tag = Tag.query.get_or_404(tag_id)
            category_id = request.json.get('category_id')
            
            # Convert empty string to None for uncategorized
            if category_id == '':
                category_id = None
            elif category_id is not None:
                # Verify category exists if one is provided
                TagCategory.query.get_or_404(category_id)
            
            tag.category_id = category_id
            db.session.commit()
            
            return jsonify({'status': 'success'})
        except Exception as e:
            db.session.rollback()
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/api/videos/organize', methods=['POST'])
    def organize_videos():
        """Organize videos (add to folders and/or tags)"""
        data = request.json
        video_ids = data.get('video_ids', [])
        folder_ids = data.get('folder_ids', [])
        tag_ids = data.get('tag_ids', [])
        
        if not video_ids:
            return jsonify({'status': 'error', 'message': 'No videos selected'}), 400
            
        try:
            videos = Video.query.filter(Video.id.in_(video_ids)).all()
            if len(videos) != len(video_ids):
                return jsonify({'status': 'error', 'message': 'Some videos not found'}), 404
            
            if tag_ids:
                tags = Tag.query.filter(Tag.id.in_(tag_ids)).all()
                if len(tags) != len(tag_ids):
                    return jsonify({'status': 'error', 'message': 'Some tags not found'}), 404
                
                for video in videos:
                    video.tags.extend([tag for tag in tags if tag not in video.tags])
            
            if folder_ids:
                folders = Folder.query.filter(Folder.id.in_(folder_ids)).all()
                if len(folders) != len(folder_ids):
                    return jsonify({'status': 'error', 'message': 'Some folders not found'}), 404
                
                for video in videos:
                    video.folders.extend([folder for folder in folders if folder not in video.folders])
            
            db.session.commit()
            return jsonify({'status': 'success'})
            
        except Exception as e:
            db.session.rollback()
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/api/folders/<int:folder_id>/toggle', methods=['POST'])
    def toggle_folder(folder_id):
        """Toggle folder open/closed state"""
        try:
            folder = Folder.query.get_or_404(folder_id)
            folder.is_open = not folder.is_open
            db.session.commit()
            
            return jsonify({'status': 'success', 'is_open': folder.is_open})
        except Exception as e:
            db.session.rollback()
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/api/folders/reorder', methods=['POST'])
    def reorder_folders():
        """Update folder positions"""
        data = request.json
        folder_positions = data.get('positions', [])
        
        if not folder_positions:
            return jsonify({'status': 'error', 'message': 'No positions provided'}), 400
        
        try:
            for item in folder_positions:
                folder = Folder.query.get(item['id'])
                if folder:
                    folder.position = item['position']
                    folder.parent_id = item.get('parent_id')
            
            db.session.commit()
            return jsonify({'status': 'success'})
        except Exception as e:
            db.session.rollback()
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/api/folders/<int:folder_id>', methods=['PATCH', 'DELETE'])
    def manage_folder(folder_id):
        """Update or delete a folder"""
        try:
            folder = Folder.query.get_or_404(folder_id)

            if request.method == 'DELETE':
                # Get all descendant folders
                def get_descendants(f):
                    descendants = []
                    for child in f.children:
                        descendants.append(child)
                        descendants.extend(get_descendants(child))
                    return descendants

                folders_to_delete = [folder] + get_descendants(folder)
                
                for f in folders_to_delete:
                    db.session.delete(f)
                
                db.session.commit()
                return jsonify({'status': 'success'})
                
            elif request.method == 'PATCH':
                name = request.json.get('name')
                if not name:
                    return jsonify({'status': 'error', 'message': 'Name is required'}), 400
                
                folder.name = name
                db.session.commit()
                return jsonify({'status': 'success'})
                
        except Exception as e:
            db.session.rollback()
            return jsonify({'status': 'error', 'message': str(e)}), 500 