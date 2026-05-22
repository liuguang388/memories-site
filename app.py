#!/usr/bin/env python3
"""记忆时光 - 个人记忆分享网站"""

import os
import uuid
import secrets
from datetime import datetime
from functools import wraps
from pathlib import Path

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, jsonify, send_from_directory, abort
)
from werkzeug.utils import secure_filename
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from PIL import Image

# ─── App Setup ──────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', f'sqlite:///{BASE_DIR / "database.db"}')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max
app.config['UPLOAD_FOLDER'] = str(BASE_DIR / 'static' / 'uploads')

# Admin password (change this!)
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin888')

ALLOWED_IMAGE = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp'}
ALLOWED_VIDEO = {'mp4', 'webm', 'mov', 'avi', 'mkv'}
ALLOWED_MUSIC = {'mp3', 'wav', 'ogg', 'flac', 'm4a', 'aac'}

db = SQLAlchemy(app)
migrate = Migrate(app, db)


# ─── Models ──────────────────────────────────────────────────────────────────

class Category(db.Model):
    __tablename__ = 'categories'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text, default='')
    icon = db.Column(db.String(10), default='📁')
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    cover_image = db.Column(db.String(500), default='')
    medias = db.relationship('Media', backref='category', lazy='dynamic',
                             cascade='all, delete-orphan', order_by='Media.sort_order.asc()')
    music = db.relationship('Music', backref='category', lazy='dynamic',
                            cascade='all, delete-orphan')


class Media(db.Model):
    __tablename__ = 'media'
    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=False)
    media_type = db.Column(db.String(10), nullable=False)  # 'image' or 'video'
    filename = db.Column(db.String(500), nullable=False)
    thumbnail = db.Column(db.String(500), default='')
    description = db.Column(db.Text, default='')
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    file_size = db.Column(db.Integer, default=0)  # bytes


class Music(db.Model):
    __tablename__ = 'music'
    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=False)
    filename = db.Column(db.String(500), nullable=False)
    title = db.Column(db.String(200), default='')
    artist = db.Column(db.String(200), default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# Ensure tables are created (especially for SQLite on first deploy)
with app.app_context():
    db.create_all()


# ─── Auth Decorators ─────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('is_admin'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def api_login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('is_admin'):
            return jsonify({'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated


# ─── Helper Functions ────────────────────────────────────────────────────────

def allowed_file(filename, allowed_set):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_set


def save_upload(file, subfolder):
    """Save an uploaded file and return (filename, relative_path)."""
    ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
    unique_name = f"{uuid.uuid4().hex}.{ext}"
    folder = os.path.join(app.config['UPLOAD_FOLDER'], subfolder)
    os.makedirs(folder, exist_ok=True)
    filepath = os.path.join(folder, unique_name)
    file.save(filepath)
    return unique_name, f'uploads/{subfolder}/{unique_name}'


def create_thumbnail(image_path, thumb_folder, size=(600, 600)):
    """Create a thumbnail and return relative path."""
    os.makedirs(thumb_folder, exist_ok=True)
    filename = os.path.basename(image_path)
    thumb_name = f"thumb_{filename}"
    thumb_path = os.path.join(thumb_folder, thumb_name)
    try:
        img = Image.open(image_path)
        img.thumbnail(size, Image.LANCZOS)
        # Convert RGBA to RGB if necessary
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')
        img.save(thumb_path, 'JPEG', quality=85)
        return f'uploads/thumbnails/{thumb_name}'
    except Exception:
        return ''


def get_file_size(filepath):
    try:
        return os.path.getsize(filepath)
    except OSError:
        return 0


# ─── Routes: Auth ────────────────────────────────────────────────────────────

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form.get('password', '')
        if password == ADMIN_PASSWORD:
            session['is_admin'] = True
            session.permanent = True
            flash('欢迎回来，时光守护者。', 'success')
            return redirect(url_for('admin'))
        flash('密码错误，请重试。', 'error')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.pop('is_admin', None)
    return redirect(url_for('index'))


# ─── Routes: Visitor View ───────────────────────────────────────────────────

@app.route('/')
def index():
    categories = Category.query.order_by(Category.sort_order.asc()).all()
    return render_template('index.html', categories=categories, is_admin=session.get('is_admin', False))


@app.route('/category/<slug>')
def view_category(slug):
    category = Category.query.filter_by(slug=slug).first_or_404()
    medias = category.medias.order_by(Media.sort_order.asc()).all()
    music_list = category.music.all()
    return render_template('category.html', category=category, medias=medias,
                           music_list=music_list, is_admin=session.get('is_admin', False))


@app.route('/media/<int:media_id>')
def get_media_detail(media_id):
    media = Media.query.get_or_404(media_id)
    return jsonify({
        'id': media.id,
        'media_type': media.media_type,
        'url': url_for('static', filename=media.filename),
        'thumbnail': url_for('static', filename=media.thumbnail) if media.thumbnail else '',
        'description': media.description,
        'created_at': media.created_at.strftime('%Y-%m-%d %H:%M'),
        'file_size': media.file_size,
        'category_name': media.category.name
    })


# ─── Routes: Admin ──────────────────────────────────────────────────────────

@app.route('/admin')
@login_required
def admin():
    categories = Category.query.order_by(Category.sort_order.asc()).all()
    return render_template('admin.html', categories=categories)


@app.route('/api/categories', methods=['GET'])
@api_login_required
def api_categories():
    categories = Category.query.order_by(Category.sort_order.asc()).all()
    return jsonify([{
        'id': c.id,
        'name': c.name,
        'slug': c.slug,
        'description': c.description,
        'icon': c.icon,
        'sort_order': c.sort_order,
        'cover_image': c.cover_image,
        'media_count': c.medias.count(),
        'created_at': c.created_at.strftime('%Y-%m-%d %H:%M')
    } for c in categories])


@app.route('/api/categories', methods=['POST'])
@api_login_required
def api_create_category():
    name = request.form.get('name', '').strip()
    description = request.form.get('description', '').strip()
    icon = request.form.get('icon', '📁').strip()
    if not name:
        return jsonify({'error': '分类名称不能为空'}), 400
    slug = request.form.get('slug', '').strip()
    if not slug:
        # Generate slug from name (simple pinyin-like approach)
        import re
        slug = re.sub(r'[^\w\s-]', '', name).strip().lower()
        slug = re.sub(r'[-\s]+', '-', slug)
        if not slug:
            slug = uuid.uuid4().hex[:8]
    # Check uniqueness
    if Category.query.filter_by(slug=slug).first():
        return jsonify({'error': '该 slug 已存在'}), 400
    cat = Category(name=name, slug=slug, description=description, icon=icon)
    db.session.add(cat)
    db.session.commit()
    return jsonify({'id': cat.id, 'name': cat.name, 'slug': cat.slug, 'icon': cat.icon}), 201


@app.route('/api/categories/<int:cat_id>', methods=['PUT'])
@api_login_required
def api_update_category(cat_id):
    cat = Category.query.get_or_404(cat_id)
    cat.name = request.form.get('name', cat.name).strip()
    cat.description = request.form.get('description', cat.description).strip()
    cat.icon = request.form.get('icon', cat.icon).strip()
    slug = request.form.get('slug', '').strip()
    if slug and slug != cat.slug:
        if Category.query.filter_by(slug=slug).first():
            return jsonify({'error': '该 slug 已存在'}), 400
        cat.slug = slug
    cat.sort_order = int(request.form.get('sort_order', cat.sort_order))
    
    # Cover image
    if 'cover_image' in request.files:
        file = request.files['cover_image']
        if file and file.filename and allowed_file(file.filename, ALLOWED_IMAGE):
            name, rel_path = save_upload(file, 'photos')
            cat.cover_image = rel_path
    
    db.session.commit()
    return jsonify({'message': '更新成功'})


@app.route('/api/categories/<int:cat_id>', methods=['DELETE'])
@api_login_required
def api_delete_category(cat_id):
    cat = Category.query.get_or_404(cat_id)
    # Delete associated files
    for m in cat.medias.all():
        _delete_media_files(m)
    for mu in cat.music.all():
        _delete_music_file(mu)
    db.session.delete(cat)
    db.session.commit()
    return jsonify({'message': '删除成功'})


@app.route('/api/categories/<int:cat_id>/upload', methods=['POST'])
@api_login_required
def api_upload_media(cat_id):
    cat = Category.query.get_or_404(cat_id)
    if 'file' not in request.files:
        return jsonify({'error': '没有选择文件'}), 400
    
    files = request.files.getlist('file')
    if not files:
        return jsonify({'error': '没有选择文件'}), 400
    
    results = []
    sort_order = cat.medias.count()
    
    for file in files:
        if not file.filename:
            continue
        
        if allowed_file(file.filename, ALLOWED_IMAGE):
            media_type = 'image'
            subfolder = 'photos'
        elif allowed_file(file.filename, ALLOWED_VIDEO):
            media_type = 'video'
            subfolder = 'videos'
        else:
            continue
        
        filename, rel_path = save_upload(file, subfolder)
        full_path = os.path.join(app.config['UPLOAD_FOLDER'], subfolder, filename)
        file_size = get_file_size(full_path)
        
        # Create thumbnail for images
        thumbnail = ''
        if media_type == 'image':
            thumb_folder = os.path.join(app.config['UPLOAD_FOLDER'], 'thumbnails')
            thumbnail = create_thumbnail(full_path, thumb_folder)
        
        media = Media(
            category_id=cat_id,
            media_type=media_type,
            filename=rel_path,
            thumbnail=thumbnail,
            file_size=file_size,
            sort_order=sort_order
        )
        db.session.add(media)
        sort_order += 1
        results.append({
            'id': media.id,
            'media_type': media_type,
            'url': url_for('static', filename=rel_path),
            'thumbnail': url_for('static', filename=thumbnail) if thumbnail else ''
        })
    
    db.session.commit()
    return jsonify({'message': f'成功上传 {len(results)} 个文件', 'items': results}), 201


@app.route('/api/media/<int:media_id>', methods=['PUT'])
@api_login_required
def api_update_media(media_id):
    media = Media.query.get_or_404(media_id)
    media.description = request.form.get('description', media.description)
    media.sort_order = int(request.form.get('sort_order', media.sort_order))
    db.session.commit()
    return jsonify({'message': '更新成功'})


@app.route('/api/media/<int:media_id>', methods=['DELETE'])
@api_login_required
def api_delete_media(media_id):
    media = Media.query.get_or_404(media_id)
    _delete_media_files(media)
    db.session.delete(media)
    db.session.commit()
    return jsonify({'message': '删除成功'})


@app.route('/api/categories/reorder', methods=['POST'])
@api_login_required
def api_reorder_categories():
    """Reorder categories based on array of {id, sort_order}."""
    data = request.get_json()
    if not data:
        return jsonify({'error': '无效数据'}), 400
    for item in data:
        cat = Category.query.get(item['id'])
        if cat:
            cat.sort_order = item['sort_order']
    db.session.commit()
    return jsonify({'message': '排序更新成功'})


@app.route('/api/media/reorder', methods=['POST'])
@api_login_required
def api_reorder_media():
    """Reorder media items based on array of {id, sort_order}."""
    data = request.get_json()
    if not data:
        return jsonify({'error': '无效数据'}), 400
    for item in data:
        media = Media.query.get(item['id'])
        if media:
            media.sort_order = item['sort_order']
    db.session.commit()
    return jsonify({'message': '排序更新成功'})


# ─── Routes: Music ───────────────────────────────────────────────────────────

@app.route('/api/categories/<int:cat_id>/music', methods=['POST'])
@api_login_required
def api_upload_music(cat_id):
    cat = Category.query.get_or_404(cat_id)
    if 'file' not in request.files:
        return jsonify({'error': '没有选择文件'}), 400
    
    file = request.files['file']
    title = request.form.get('title', file.filename.rsplit('.', 1)[0])
    artist = request.form.get('artist', '')
    
    if not file.filename or not allowed_file(file.filename, ALLOWED_MUSIC):
        return jsonify({'error': '不支持的音乐格式'}), 400
    
    filename, rel_path = save_upload(file, 'music')
    music = Music(category_id=cat_id, filename=rel_path, title=title, artist=artist)
    db.session.add(music)
    db.session.commit()
    return jsonify({
        'id': music.id,
        'url': url_for('static', filename=rel_path),
        'title': title,
        'artist': artist
    }), 201


@app.route('/api/music/<int:music_id>', methods=['DELETE'])
@api_login_required
def api_delete_music(music_id):
    music = Music.query.get_or_404(music_id)
    _delete_music_file(music)
    db.session.delete(music)
    db.session.commit()
    return jsonify({'message': '删除成功'})


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _delete_media_files(media):
    for path in [media.filename, media.thumbnail]:
        if path:
            full = os.path.join(app.config['UPLOAD_FOLDER'], '..', path)
            try:
                os.remove(full)
            except OSError:
                pass


def _delete_music_file(music):
    full = os.path.join(app.config['UPLOAD_FOLDER'], '..', music.filename)
    try:
        os.remove(full)
    except OSError:
        pass


# ─── Serve uploaded files ───────────────────────────────────────────────────

@app.route('/uploads/<subfolder>/<filename>')
def uploaded_file(subfolder, filename):
    directory = os.path.join(app.config['UPLOAD_FOLDER'], subfolder)
    return send_from_directory(directory, filename)


# ─── Main ────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
