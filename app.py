from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user, login_required
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
import os
import uuid
from flask_babel import Babel, gettext as _

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'  # Change this to a strong secret key
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///rooms.db'  # Using SQLite for development
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}
app.config['BABEL_TRANSLATION_DIRECTORIES'] = 'translations' # Default language is Russian
app.config['LANGUAGES'] = {
    'ru': 'Русский',
    'en': 'English',
    'es': 'Español'
}

# Initialize Babel with a locale selector function
# babel = Babel(app, locale_selector=lambda: request.accept_languages.best_match(app.config['LANGUAGES'].keys()))
# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize extensions
db = SQLAlchemy(app)
migrate = Migrate(app, db)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    rooms = db.relationship('Room', backref='owner', lazy='dynamic')
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Room(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    price = db.Column(db.Float, nullable=False)
    area = db.Column(db.String(50), nullable=False)  # Area/Region in Dubai
    room_type = db.Column(db.String(50), nullable=False)  # Master with bathroom, without bathroom, partition
    available_from = db.Column(db.DateTime, nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    has_bathroom = db.Column(db.Boolean, default=False)
    number_of_neighbors = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    images = db.relationship('RoomImage', backref='room', cascade='all, delete-orphan')

class RoomImage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    room_id = db.Column(db.Integer, db.ForeignKey('room.id'))

@login_manager.user_loader
def load_user(id):
    return User.query.get(int(id))

# Define get_locale function first
def get_locale():
    locale = request.args.get('lang')
    if locale and locale in app.config['LANGUAGES']:
        return locale
    return request.accept_languages.best_match(app.config['LANGUAGES'].keys())

# Then initialize Babel once with the get_locale function
babel = Babel(app, locale_selector=get_locale)

# Make sure the function is available to your templates
app.jinja_env.globals['get_locale'] = get_locale
# Helper functions
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def save_image(file):
    """Save uploaded image and return filename"""
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        # Add unique identifier to prevent filename collisions
        unique_filename = f"{uuid.uuid4().hex}_{filename}"
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        file.save(file_path)
        return unique_filename
    return None

# Routes
@app.route('/')
def index():
    rooms = Room.query.order_by(Room.created_at.desc()).all()
    return render_template('index.html', rooms=rooms)

@app.route('/search', methods=['GET', 'POST'])
def search():
    if request.method == 'POST':
        area = request.form.get('area')
        room_type = request.form.get('room_type')
        has_bathroom = request.form.get('has_bathroom') == 'on'
        min_price = request.form.get('min_price')
        max_price = request.form.get('max_price')
        available_from = request.form.get('available_from')
        neighbors = request.form.get('neighbors')
        
        # Start with a base query
        query = Room.query
        
        # Apply filters
        if area:
            query = query.filter(Room.area == area)
        if room_type:
            query = query.filter(Room.room_type == room_type)
        if has_bathroom:
            query = query.filter(Room.has_bathroom == True)
        if min_price:
            query = query.filter(Room.price >= float(min_price))
        if max_price:
            query = query.filter(Room.price <= float(max_price))
        if available_from:
            available_date = datetime.strptime(available_from, '%Y-%m-%d')
            query = query.filter(Room.available_from <= available_date)
        if neighbors:
            query = query.filter(Room.number_of_neighbors <= int(neighbors))
        
        rooms = query.all()
        return render_template('search_results.html', rooms=rooms)
    
    # If GET request, display search form
    areas = db.session.query(Room.area).distinct()
    room_types = db.session.query(Room.room_type).distinct()
    return render_template('search.html', areas=areas, room_types=room_types)

@app.route('/room/<int:room_id>')
def room_detail(room_id):
    room = Room.query.get_or_404(room_id)
    return render_template('room_detail.html', room=room)

@app.route('/add_room', methods=['GET', 'POST'])
@login_required
def add_room():
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        price = float(request.form['price'])
        area = request.form['area']
        room_type = request.form['room_type']
        available_from = datetime.strptime(request.form['available_from'], '%Y-%m-%d')
        latitude = float(request.form['latitude'])
        longitude = float(request.form['longitude'])
        has_bathroom = 'has_bathroom' in request.form
        number_of_neighbors = int(request.form['number_of_neighbors'])
        
        # Create new room
        new_room = Room(
            title=title,
            description=description,
            price=price,
            area=area,
            room_type=room_type,
            available_from=available_from,
            latitude=latitude,
            longitude=longitude,
            has_bathroom=has_bathroom,
            number_of_neighbors=number_of_neighbors,
            user_id=current_user.id
        )
        
        db.session.add(new_room)
        db.session.commit()
        
        # Handle image uploads
        if 'images' in request.files:
            files = request.files.getlist('images')
            for file in files:
                filename = save_image(file)
                if filename:
                    new_image = RoomImage(filename=filename, room_id=new_room.id)
                    db.session.add(new_image)
        
        db.session.commit()
        flash(_('Room added successfully!'), 'success')
        return redirect(url_for('room_detail', room_id=new_room.id))
    
    return render_template('add_room.html')

@app.route('/edit_room/<int:room_id>', methods=['GET', 'POST'])
@login_required
def edit_room(room_id):
    room = Room.query.get_or_404(room_id)
    
    # Check if the current user is the owner
    if room.user_id != current_user.id:
        flash(_('You are not authorized to edit this room.'), 'danger')
        return redirect(url_for('room_detail', room_id=room.id))
    
    if request.method == 'POST':
        room.title = request.form['title']
        room.description = request.form['description']
        room.price = float(request.form['price'])
        room.area = request.form['area']
        room.room_type = request.form['room_type']
        room.available_from = datetime.strptime(request.form['available_from'], '%Y-%m-%d')
        room.latitude = float(request.form['latitude'])
        room.longitude = float(request.form['longitude'])
        room.has_bathroom = 'has_bathroom' in request.form
        room.number_of_neighbors = int(request.form['number_of_neighbors'])
        
        # Handle image uploads
        if 'images' in request.files:
            files = request.files.getlist('images')
            for file in files:
                filename = save_image(file)
                if filename:
                    new_image = RoomImage(filename=filename, room_id=room.id)
                    db.session.add(new_image)
        
        db.session.commit()
        flash(_('Room updated successfully!'), 'success')
        return redirect(url_for('room_detail', room_id=room.id))
    
    return render_template('edit_room.html', room=room)

@app.route('/delete_room/<int:room_id>', methods=['POST'])
@login_required
def delete_room(room_id):
    room = Room.query.get_or_404(room_id)
    
    # Check if the current user is the owner
    if room.user_id != current_user.id:
        flash(_('You are not authorized to delete this room.'), 'danger')
        return redirect(url_for('room_detail', room_id=room.id))
    
    # Delete all images from filesystem
    for image in room.images:
        try:
            os.remove(os.path.join(app.config['UPLOAD_FOLDER'], image.filename))
        except:
            pass
    
    db.session.delete(room)
    db.session.commit()
    flash(_('Room deleted successfully!'), 'success')
    return redirect(url_for('index'))

@app.route('/delete_image/<int:image_id>', methods=['POST'])
@login_required
def delete_image(image_id):
    image = RoomImage.query.get_or_404(image_id)
    room = Room.query.get(image.room_id)
    
    # Check if the current user is the owner of the room
    if room.user_id != current_user.id:
        flash(_('You are not authorized to delete this image.'), 'danger')
        return redirect(url_for('room_detail', room_id=room.id))
    
    # Delete the image from filesystem
    try:
        os.remove(os.path.join(app.config['UPLOAD_FOLDER'], image.filename))
    except:
        pass
    
    db.session.delete(image)
    db.session.commit()
    flash(_('Image deleted successfully!'), 'success')
    return redirect(url_for('edit_room', room_id=room.id))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        
        # Check if username or email already exists
        if User.query.filter_by(username=username).first():
            flash(_('Username already exists'), 'danger')
            return redirect(url_for('register'))
        if User.query.filter_by(email=email).first():
            flash(_('Email already registered'), 'danger')
            return redirect(url_for('register'))
        
        # Create new user
        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
        flash(_('Registration successful! Please log in.'), 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user = User.query.filter_by(username=username).first()
        if user is None or not user.check_password(password):
            flash(_('Invalid username or password'), 'danger')
            return redirect(url_for('login'))
        
        login_user(user)
        next_page = request.args.get('next')
        if not next_page or not next_page.startswith('/'):
            next_page = url_for('index')
        return redirect(next_page)
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/profile')
@login_required
def profile():
    rooms = Room.query.filter_by(user_id=current_user.id).all()
    return render_template('profile.html', rooms=rooms)


@app.route('/change_language/<lang>')
def change_language(lang):
    if lang in app.config['LANGUAGES']:
        redirect_url = request.referrer or url_for('index')
        # Fix - parse existing URL and replace lang parameter if it exists
        from urllib.parse import urlparse, parse_qs, urlencode

        parsed_url = urlparse(redirect_url)
        params = parse_qs(parsed_url.query)
        params['lang'] = [lang]  # Replace or add lang parameter

        # Rebuild the URL with updated parameters
        query_string = urlencode(params, doseq=True)
        redirect_url = parsed_url._replace(query=query_string).geturl()

        return redirect(redirect_url)
    return redirect(url_for('index'))



# @app.route('/change_language/<lang>')
# def change_language(lang):
#     if lang in app.config['LANGUAGES']:
#         redirect_url = request.referrer or url_for('index')
#         # Add language parameter to the URL
#         if '?' in redirect_url:
#             redirect_url = f"{redirect_url}&lang={lang}"
#         else:
#             redirect_url = f"{redirect_url}?lang={lang}"
#         return redirect(redirect_url)
#     return redirect(url_for('index'))

@app.route('/api/rooms', methods=['GET'])
def api_rooms():
    rooms = Room.query.all()
    result = []
    for room in rooms:
        result.append({
            'id': room.id,
            'title': room.title,
            'price': room.price,
            'area': room.area,
            'latitude': room.latitude,
            'longitude': room.longitude
        })
    return jsonify(result)

@app.route('/api/room/<int:room_id>', methods=['GET'])
def api_room_detail(room_id):
    room = Room.query.get_or_404(room_id)
    images = [image.filename for image in room.images]
    
    return jsonify({
        'id': room.id,
        'title': room.title,
        'description': room.description,
        'price': room.price,
        'area': room.area,
        'room_type': room.room_type,
        'available_from': room.available_from.strftime('%Y-%m-%d'),
        'latitude': room.latitude,
        'longitude': room.longitude,
        'has_bathroom': room.has_bathroom,
        'number_of_neighbors': room.number_of_neighbors,
        'images': images,
        'owner': room.owner.username
    })

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host="0.0.0.0", port=5000, debug=True)