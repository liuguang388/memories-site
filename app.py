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
import cloudinary
import cloudinary.uploader
import cloudinary.api

# ─── App Setup ──────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent
# Persistent data directory (for Render persistent disk or local dev)
DATA_DIR = Path(os.environ.get('DATA_DIR', str(BASE_DIR)))

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    'DATABASE_URL',
    f'sqlite:///{DATA_DIR / "database.db"}'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max
app.config['UPLOAD_FOLDER'] = str(DATA_DIR / 'uploads')

# Cloudinary config (files stored in cloud, not local disk)
cloudinary.config(
    cloud_name=os.environ.get('CLOUDINARY_CLOUD_NAME', ''),
    api_key=os.environ.get('CLOUDINARY_API_KEY', ''),
    api_secret=os.environ.get('CLOUDINARY_API_SECRET', ''),
    secure=True
)

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
    password = db.Column(db.String(200), nullable=True, default=None)  # None=公开, 设置后需密码访问
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
    title = db.Column(db.String(300), nullable=False)
    artist = db.Column(db.String(200), default='')
    filename = db.Column(db.String(500), nullable=False)
    file_size = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ─── Database Init & Migration ───────────────────────────────────────────────

def init_db():
    """Initialize database tables and run schema migrations."""
    from sqlalchemy import text, inspect
    with app.app_context():
        db.create_all()
        inspector = inspect(db.engine)
        # Add missing columns to categories
        existing_cols = {c['name'] for c in inspector.get_columns('categories')}
        with db.engine.connect() as conn:
            if 'password' not in existing_cols:
                conn.execute(text('ALTER TABLE categories ADD COLUMN password VARCHAR(200)'))
                conn.commit()
                print('Migration: added categories.password', flush=True)
            if 'cover_image' not in existing_cols:
                conn.execute(text("ALTER TABLE categories ADD COLUMN cover_image VARCHAR(500) DEFAULT ''"))
                conn.commit()
                print('Migration: added categories.cover_image', flush=True)
        print('Database tables ready', flush=True)

try:
    init_db()
except Exception as e:
    print(f'WARNING: Database setup error: {e}', flush=True)

# Validate Cloudinary configuration
_cloud_name = os.environ.get('CLOUDINARY_CLOUD_NAME', '')

def cloudinary_url(filename, media_type='image'):
    """Build full Cloudinary URL from public_id."""
    if not filename:
        return ''
    if filename.startswith('http'):
        return filename
    # Map media_type to Cloudinary resource type
    resource_type = 'video' if media_type in ('video', 'audio') else 'image'
    return f'https://res.cloudinary.com/{_cloud_name}/{resource_type}/upload/{filename}'
_api_key = os.environ.get('CLOUDINARY_API_KEY', '')
_api_secret = os.environ.get('CLOUDINARY_API_SECRET', '')
if _cloud_name and _api_key and _api_secret:
    try:
        result = cloudinary.api.ping()
        if result.get('status') == 'ok':
            print(f'Cloudinary OK (cloud: {_cloud_name})', flush=True)
        else:
            print(f'WARNING: Cloudinary ping unexpected: {result}', flush=True)
    except Exception as e:
        print(f'WARNING: Cloudinary config error: {e}', flush=True)
else:
    missing = []
    if not _cloud_name: missing.append('CLOUDINARY_CLOUD_NAME')
    if not _api_key: missing.append('CLOUDINARY_API_KEY')
    if not _api_secret: missing.append('CLOUDINARY_API_SECRET')
    print(f'WARNING: Missing Cloudinary env vars: {", ".join(missing)}', flush=True)


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


class CloudinaryUploadError(Exception):
    """Raised when Cloudinary upload fails."""
    pass


def cloudinary_upload(file, folder='memories-site'):
    """Upload a file to Cloudinary. Returns (public_id, secure_url, bytes)."""
    try:
        result = cloudinary.uploader.upload(
            file,
            folder=folder,
            resource_type='auto'
        )
        return result['public_id'], result['secure_url'], result.get('bytes', 0)
    except Exception as e:
        msg = str(e)
        if 'invalid' in msg.lower() or 'api key' in msg.lower() or 'auth' in msg.lower():
            raise CloudinaryUploadError('Cloudinary 认证失败，请检查 API 密钥配置')
        elif 'size' in msg.lower() or 'too large' in msg.lower():
            raise CloudinaryUploadError('文件大小超出 Cloudinary 免费额度限制（最大 10MB）')
        elif 'format' in msg.lower() or 'not supported' in msg.lower():
            raise CloudinaryUploadError('不支持的文件格式')
        elif 'timeout' in msg.lower() or 'connection' in msg.lower():
            raise CloudinaryUploadError('上传超时，请重试')
        else:
            raise CloudinaryUploadError(f'上传失败: {msg}')


def cloudinary_thumb_url(public_id, width=600):
    """Generate Cloudinary thumbnail URL with transformation."""
    cloud_name = os.environ.get('CLOUDINARY_CLOUD_NAME', '')
    if not cloud_name:
        return ''
    return f'https://res.cloudinary.com/{cloud_name}/image/upload/w_{width},c_limit/{public_id}'


def cloudinary_destroy(public_id, resource_type='image'):
    """Delete a file from Cloudinary."""
    try:
        cloudinary.uploader.destroy(public_id, resource_type=resource_type)
    except Exception:
        pass  # silent fail - file might be already deleted


# ─── Page Routes ─────────────────────────────────────────────────────────────

@app.route('/')
def index():
    categories = Category.query.order_by(Category.sort_order.asc()).all()
    return render_template('index.html', categories=categories, is_admin=session.get('is_admin', False))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form.get('password') == ADMIN_PASSWORD:
            session['is_admin'] = True
            flash('登录成功', 'success')
            return redirect(url_for('admin'))
        flash('密码错误', 'error')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('已退出登录', 'info')
    return redirect(url_for('index'))


@app.route('/admin')
@login_required
def admin():
    categories = Category.query.order_by(Category.sort_order.asc()).all()
    return render_template('admin.html', categories=categories)


@app.route('/category/<slug>')
def category_page(slug):
    cat = Category.query.filter_by(slug=slug).first_or_404()
    # Check password protection
    if cat.password and not session.get(f'access_{cat.id}') and not session.get('is_admin'):
        return render_template('category_locked.html', category=cat)
    return render_template('category.html', category=cat)


@app.route('/category/<slug>/unlock', methods=['POST'])
def category_unlock(slug):
    cat = Category.query.filter_by(slug=slug).first_or_404()
    if request.form.get('password') == cat.password:
        session[f'access_{cat.id}'] = True
        return redirect(url_for('category_page', slug=slug))
    flash('密码错误', 'error')
    return redirect(url_for('category_page', slug=slug))


# ─── API Routes ──────────────────────────────────────────────────────────────

@app.route('/api/categories', methods=['GET'])
def api_get_categories():
    categories = Category.query.order_by(Category.sort_order.asc()).all()
    return jsonify([{
        'id': c.id,
        'name': c.name,
        'slug': c.slug,
        'description': c.description,
        'icon': c.icon,
        'sort_order': c.sort_order,
        'cover_image': c.cover_image,
        'password': c.password,
        'media_count': c.medias.count(),
        'music_count': c.music.count(),
        'created_at': c.created_at.isoformat() if c.created_at else None
    } for c in categories])


@app.route('/api/category/<slug>', methods=['GET'])
def api_get_category(slug):
    cat = Category.query.filter_by(slug=slug).first_or_404()
    # Check password protection for API access
    if cat.password and not session.get(f'access_{cat.id}') and not session.get('is_admin'):
        return jsonify({'error': '需要密码访问', 'locked': True, 'has_password': True}), 403
    medias = cat.medias.order_by(Media.sort_order.asc(), Media.created_at.desc()).all()
    music_list = cat.music.order_by(Music.created_at.desc()).all()
    return jsonify({
        'id': cat.id,
        'name': cat.name,
        'slug': cat.slug,
        'description': cat.description,
        'icon': cat.icon,
        'cover_image': cat.cover_image,
        'password': cat.password,
        'has_password': bool(cat.password),
        'medias': [{
            'id': m.id,
            'media_type': m.media_type,
            'filename': m.filename,
            'thumbnail': m.thumbnail,
            'url': cloudinary_url(m.filename, m.media_type),
            'description': m.description or '',
            'created_at': m.created_at.isoformat() if m.created_at else None
        } for m in medias],
        'music': [{
            'id': m.id,
            'title': m.title,
            'artist': m.artist,
            'filename': m.filename,
            'url': cloudinary_url(m.filename, 'audio')
        } for m in music_list]
    })


@app.route('/api/categories', methods=['POST'])
@api_login_required
def api_create_category():
    # Accept both JSON and form-data
    if request.is_json:
        data = request.json
    else:
        data = request.form
    if not data or not data.get('name'):
        return jsonify({'error': '分类名称不能为空'}), 400
    slug = data.get('slug') or data['name'].lower().replace(' ', '-')
    # Ensure unique slug
    base_slug = slug
    counter = 1
    while Category.query.filter_by(slug=slug).first():
        slug = f"{base_slug}-{counter}"
        counter += 1
    
    cover_image_url = None
    # Handle cover image upload
    cover_file = request.files.get('cover_image')
    if cover_file and cover_file.filename:
        if not allowed_file(cover_file.filename, ALLOWED_IMAGE):
            return jsonify({'error': '不支持的图片格式'}), 400
        try:
            _, cover_image_url, _ = cloudinary_upload(cover_file, folder='memories-site/covers')
        except CloudinaryUploadError as e:
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            return jsonify({'error': f'封面上传失败: {str(e)}'}), 500
    
    cat = Category(
        name=data['name'],
        slug=slug,
        description=data.get('description', ''),
        icon=data.get('icon', '📁'),
        sort_order=data.get('sort_order', 0),
        password=data.get('password') or None,
        cover_image=cover_image_url
    )
    db.session.add(cat)
    db.session.commit()
    return jsonify({'id': cat.id, 'slug': cat.slug}), 201


@app.route('/api/categories/<int:cat_id>', methods=['PUT'])
@api_login_required
def api_update_category(cat_id):
    cat = Category.query.get_or_404(cat_id)
    # Accept both JSON and form-data
    if request.is_json:
        data = request.json
    else:
        data = request.form
    if not data:
        return jsonify({'error': 'No data'}), 400

    if data.get('name'):
        cat.name = data['name']
    if data.get('description'):
        cat.description = data['description']
    if data.get('icon'):
        cat.icon = data['icon']
    if data.get('sort_order') is not None:
        cat.sort_order = int(data['sort_order'])
    # Check if password removal is requested
    if data.get('remove_password') == '1':
        cat.password = None
    elif data.get('password'):
        cat.password = data['password']

    # Handle cover image upload
    cover_file = request.files.get('cover_image')
    if cover_file and cover_file.filename:
        if not allowed_file(cover_file.filename, ALLOWED_IMAGE):
            return jsonify({'error': '不支持的图片格式'}), 400
        try:
            public_id, secure_url, _ = cloudinary_upload(cover_file, folder='memories-site/covers')
            # Delete old cover if exists
            if cat.cover_image:
                try:
                    old_id = cat.cover_image.split('/')[-1].split('.')[0]
                    cloudinary_destroy(f'memories-site/covers/{old_id}')
                except Exception:
                    pass
            cat.cover_image = secure_url
        except CloudinaryUploadError as e:
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            return jsonify({'error': f'封面上传失败: {str(e)}'}), 500

    db.session.commit()
    return jsonify({'message': '更新成功'})


@app.route('/api/categories/<int:cat_id>', methods=['DELETE'])
@api_login_required
def api_delete_category(cat_id):
    cat = Category.query.get_or_404(cat_id)
    # Delete all associated Cloudinary files
    for media in cat.medias.all():
        try:
            cloudinary_destroy(media.filename, media.media_type)
        except Exception:
            pass
    for music in cat.music.all():
        try:
            cloudinary_destroy(music.filename, 'raw')
        except Exception:
            pass
    db.session.delete(cat)
    db.session.commit()
    return jsonify({'message': '删除成功'})


@app.route('/api/categories/<int:cat_id>/upload', methods=['POST'])
@api_login_required
def api_upload_media(cat_id):
    cat = Category.query.get_or_404(cat_id)
    file = request.files.get('file')
    if not file or not file.filename:
        return jsonify({'error': '没有选择文件'}), 400

    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext in ALLOWED_IMAGE:
        media_type = 'image'
    elif ext in ALLOWED_VIDEO:
        media_type = 'video'
    else:
        return jsonify({'error': f'不支持的文件格式: .{ext}'}), 400

    try:
        public_id, secure_url, file_size = cloudinary_upload(file)
    except CloudinaryUploadError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'上传失败: {str(e)}'}), 500

    thumb_url = ''
    if media_type == 'image':
        thumb_url = cloudinary_thumb_url(public_id)
    elif media_type == 'video':
        # Video thumbnail from Cloudinary
        cloud_name = os.environ.get('CLOUDINARY_CLOUD_NAME', '')
        if cloud_name:
            thumb_url = f'https://res.cloudinary.com/{cloud_name}/video/upload/so_0,w_600/{public_id}.jpg'

    media = Media(
        category_id=cat_id,
        media_type=media_type,
        filename=public_id,
        thumbnail=thumb_url,
        description='',
        file_size=file_size,
        sort_order=cat.medias.count()
    )
    db.session.add(media)
    db.session.commit()
    return jsonify({
        'id': media.id,
        'media_type': media_type,
        'secure_url': secure_url,
        'thumbnail': thumb_url,
        'file_size': file_size
    })


@app.route('/api/media/<int:media_id>', methods=['PUT'])
@api_login_required
def api_update_media(media_id):
    media = Media.query.get_or_404(media_id)
    data = request.json
    if data:
        if 'description' in data:
            media.description = data['description']
        if 'sort_order' in data:
            media.sort_order = data['sort_order']
    db.session.commit()
    return jsonify({'message': '更新成功'})


@app.route('/api/media/<int:media_id>', methods=['DELETE'])
@api_login_required
def api_delete_media(media_id):
    media = Media.query.get_or_404(media_id)
    try:
        cloudinary_destroy(media.filename, media.media_type)
    except Exception:
        pass
    db.session.delete(media)
    db.session.commit()
    return jsonify({'message': '删除成功'})


@app.route('/api/categories/<int:cat_id>/music', methods=['POST'])
@api_login_required
def api_upload_music(cat_id):
    cat = Category.query.get_or_404(cat_id)
    file = request.files.get('file')
    if not file or not file.filename:
        return jsonify({'error': '没有选择文件'}), 400

    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in ALLOWED_MUSIC:
        return jsonify({'error': f'不支持的音频格式: .{ext}'}), 400

    title = request.form.get('title', file.filename.rsplit('.', 1)[0])
    artist = request.form.get('artist', '')

    try:
        public_id, secure_url, file_size = cloudinary_upload(file, folder='memories-site/music')
    except CloudinaryUploadError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'上传失败: {str(e)}'}), 500

    music = Music(
        category_id=cat_id,
        title=title,
        artist=artist,
        filename=public_id,
        file_size=file_size
    )
    db.session.add(music)
    db.session.commit()
    return jsonify({
        'id': music.id,
        'title': title,
        'artist': artist,
        'secure_url': secure_url,
        'file_size': file_size
    })


@app.route('/api/music/<int:music_id>', methods=['PUT'])
@api_login_required
def api_update_music(music_id):
    music = Music.query.get_or_404(music_id)
    data = request.json
    if data:
        if 'title' in data:
            music.title = data['title']
        if 'artist' in data:
            music.artist = data['artist']
    db.session.commit()
    return jsonify({'message': '更新成功'})


@app.route('/api/music/<int:music_id>', methods=['DELETE'])
@api_login_required
def api_delete_music(music_id):
    music = Music.query.get_or_404(music_id)
    try:
        cloudinary_destroy(music.filename, 'raw')
    except Exception:
        pass
    db.session.delete(music)
    db.session.commit()
    return jsonify({'message': '删除成功'})


# ─── Error Handlers ──────────────────────────────────────────────────────────

@app.errorhandler(404)
def not_found_error(e):
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Not found'}), 404
    return render_template('base.html', error='页面未找到'), 404


@app.errorhandler(500)
def internal_error(e):
    db.session.rollback()
    if request.path.startswith('/api/'):
        return jsonify({'error': f'服务器内部错误: {str(e)}'}), 500
    return render_template('base.html', error='服务器内部错误'), 500


# ─── Main ────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)
