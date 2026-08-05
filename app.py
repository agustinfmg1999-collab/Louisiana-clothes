import os
import sqlite3
import uuid
from functools import wraps
from flask import Flask, render_template_string, request, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash
import cloudinary
import cloudinary.uploader

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'louisiana_clothes_secret_key_super_segura')

ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', "14230618aF")
NUMERO_WHATSAPP_TIENDA = "5493704020319"

# Configuración de Cloudinary para imágenes permanentes
cloudinary.config( 
  cloud_name = os.environ.get('CLOUDINARY_CLOUD_NAME', ''), 
  api_key = os.environ.get('CLOUDINARY_API_KEY', ''), 
  api_secret = os.environ.get('CLOUDINARY_API_SECRET', '') 
)

DATABASE = 'louisiana.db'

# --- CONFIGURACIÓN DE BASE DE DATOS ---

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS productos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                categoria TEXT NOT NULL,
                precio REAL NOT NULL,
                imagen_url TEXT,
                descripcion TEXT,
                talles TEXT,
                colores TEXT,
                oferta INTEGER DEFAULT 0,
                precio_oferta REAL,
                destacado INTEGER DEFAULT 0,
                stock INTEGER DEFAULT 1,
                genero TEXT DEFAULT 'unisex'
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS categorias (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT UNIQUE NOT NULL,
                slug TEXT UNIQUE NOT NULL
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS banners (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                titulo TEXT,
                subtitulo TEXT,
                imagen_url TEXT NOT NULL,
                link TEXT,
                activo INTEGER DEFAULT 1
            )
        ''')
        
        categorias_defecto = [
            ('Remeras y Tops', 'remeras-tops'),
            ('Pantalones y Jeans', 'pantalones-jeans'),
            ('Vestidos y Monos', 'vestidos-monos'),
            ('Buzos y Camperas', 'buzos-camperas'),
            ('Polleras y Shorts', 'polleras-shorts'),
            ('Calzados', 'calzados'),
            ('Accesorios', 'accesorios')
        ]
        
        for cat, slug in categorias_defecto:
            cursor.execute('INSERT OR IGNORE INTO categorias (nombre, slug) VALUES (?, ?)', (cat, slug))
            
        conn.commit()

init_db()

# --- FUNCIONES AUXILIARES ---

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

# --- RUTAS PÚBLICAS ---

@app.route('/')
def index():
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT * FROM productos WHERE destacado = 1 LIMIT 8')
    destacados = cursor.fetchall()
    
    cursor.execute('SELECT * FROM productos WHERE oferta = 1 LIMIT 8')
    ofertas = cursor.fetchall()
    
    cursor.execute('SELECT * FROM banners WHERE activo = 1')
    banners = cursor.fetchall()
    
    cursor.execute('SELECT * FROM categorias')
    categorias = cursor.fetchall()
    
    return render_template_string(HTML_INDEX, 
                                  destacados=destacados, 
                                  ofertas=ofertas, 
                                  banners=banners, 
                                  categorias=categorias,
                                  whatsapp=NUMERO_WHATSAPP_TIENDA)

@app.route('/catalogo')
def catalogo():
    db = get_db()
    cursor = db.cursor()
    
    cat_filter = request.args.get('categoria')
    genero_filter = request.args.get('genero')
    search_query = request.args.get('q')
    
    query = 'SELECT * FROM productos WHERE 1=1'
    params = []
    
    if cat_filter:
        query += ' AND categoria = ?'
        params.append(cat_filter)
        
    if genero_filter:
        query += ' AND genero = ?'
        params.append(genero_filter)
        
    if search_query:
        query += ' AND (nombre LIKE ? OR descripcion LIKE ?)'
        params.append(f'%{search_query}%')
        params.append(f'%{search_query}%')
        
    cursor.execute(query, params)
    productos = cursor.fetchall()
    
    cursor.execute('SELECT * FROM categorias')
    categorias = cursor.fetchall()
    
    return render_template_string(HTML_CATALOGO, 
                                  productos=productos, 
                                  categorias=categorias, 
                                  cat_activa=cat_filter,
                                  whatsapp=NUMERO_WHATSAPP_TIENDA)

@app.route('/producto/<int:id>')
def producto_detalle(id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT * FROM productos WHERE id = ?', (id,))
    producto = cursor.fetchone()
    
    if not producto:
        return redirect(url_for('catalogo'))
        
    cursor.execute('SELECT * FROM productos WHERE categoria = ? AND id != ? LIMIT 4', (producto['categoria'], id))
    relacionados = cursor.fetchall()
    
    return render_template_string(HTML_PRODUCTO, 
                                  producto=producto, 
                                  relacionados=relacionados,
                                  whatsapp=NUMERO_WHATSAPP_TIENDA)

# --- RUTAS DE ADMINISTRACIÓN ---

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    error = None
    if request.method == 'POST':
        password = request.form.get('password')
        if password == ADMIN_PASSWORD:
            session['admin_logged_in'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            error = 'Contraseña incorrecta'
    return render_template_string(HTML_ADMIN_LOGIN, error=error)

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('admin_login'))

@app.route('/admin')
@login_required
def admin_dashboard():
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT * FROM productos ORDER BY id DESC')
    productos = cursor.fetchall()
    
    cursor.execute('SELECT * FROM categorias')
    categorias = cursor.fetchall()
    
    cursor.execute('SELECT * FROM banners')
    banners = cursor.fetchall()
    
    return render_template_string(HTML_ADMIN_DASHBOARD, 
                                  productos=productos, 
                                  categorias=categorias, 
                                  banners=banners)

@app.route('/admin/producto/nuevo', methods=['POST'])
@login_required
def admin_producto_nuevo():
    nombre = request.form.get('nombre')
    categoria = request.form.get('categoria')
    precio = float(request.form.get('precio', 0))
    descripcion = request.form.get('descripcion')
    talles = request.form.get('talles')
    colores = request.form.get('colores')
    genero = request.form.get('genero', 'unisex')
    destacado = 1 if request.form.get('destacado') else 0
    oferta = 1 if request.form.get('oferta') else 0
    precio_oferta = float(request.form.get('precio_oferta', 0)) if oferta else None
    
    imagen_url = ''
    if 'imagen' in request.files:
        file = request.files['imagen']
        if file and file.filename != '':
            upload_result = cloudinary.uploader.upload(file)
            imagen_url = upload_result.get('secure_url', '')

    db = get_db()
    cursor = db.cursor()
    cursor.execute('''
        INSERT INTO productos (nombre, categoria, precio, imagen_url, descripcion, talles, colores, oferta, precio_oferta, destacado, genero)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (nombre, categoria, precio, imagen_url, descripcion, talles, colores, oferta, precio_oferta, destacado, genero))
    db.commit()
    
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/producto/eliminar/<int:id>', methods=['POST'])
@login_required
def admin_producto_eliminar(id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute('DELETE FROM productos WHERE id = ?', (id,))
    db.commit()
    return redirect(url_for('admin_dashboard'))

# --- TEMPLATES HTML ---

HTML_INDEX = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Louisiana Clothes - Tienda de Ropa</title>
    <style>
        body { font-family: sans-serif; margin: 0; padding: 0; background: #f4f4f9; }
        header { background: #111; color: #fff; padding: 1rem; text-align: center; }
        nav a { color: #fff; margin: 0 10px; text-decoration: none; }
        .container { padding: 2rem; max-width: 1200px; margin: auto; }
        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 1.5rem; }
        .card { background: #fff; border-radius: 8px; padding: 1rem; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
        .card img { max-width: 100%; height: 200px; object-fit: cover; border-radius: 4px; }
    </style>
</head>
<body>
    <header>
        <h1>Louisiana Clothes</h1>
        <nav>
            <a href="/">Inicio</a>
            <a href="/catalogo">Catálogo</a>
            <a href="/admin">Admin</a>
        </nav>
    </header>
    <div class="container">
        <h2>Productos Destacados</h2>
        <div class="grid">
            {% for p in destacados %}
            <div class="card">
                <img src="{{ p.imagen_url or 'https://via.placeholder.com/200' }}" alt="{{ p.nombre }}">
                <h3>{{ p.nombre }}</h3>
                <p>${{ p.precio }}</p>
                <a href="/producto/{{ p.id }}">Ver Detalle</a>
            </div>
            {% endfor %}
        </div>
    </div>
</body>
</html>
"""

HTML_CATALOGO = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>Catálogo - Louisiana Clothes</title>
</head>
<body>
    <h1>Catálogo de Productos</h1>
    <a href="/">Volver al Inicio</a>
    <ul>
        {% for p in productos %}
        <li><strong>{{ p.nombre }}</strong> - ${{ p.precio }} ({{ p.categoria }})</li>
        {% endfor %}
    </ul>
</body>
</html>
"""

HTML_PRODUCTO = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>{{ producto.nombre }}</title>
</head>
<body>
    <h1>{{ producto.nombre }}</h1>
    <p>Precio: ${{ producto.precio }}</p>
    <p>{{ producto.descripcion }}</p>
    <a href="/catalogo">Volver al catálogo</a>
</body>
</html>
"""

HTML_ADMIN_LOGIN = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>Login Administración</title>
</head>
<body>
    <h2>Iniciar Sesión Administración</h2>
    {% if error %}<p style="color:red;">{{ error }}</p>{% endif %}
    <form method="POST">
        <input type="password" name="password" placeholder="Contraseña" required>
        <button type="submit">Ingresar</button>
    </form>
</body>
</html>
"""

HTML_ADMIN_DASHBOARD = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>Panel de Administración</title>
</head>
<body>
    <h1>Panel de Control</h1>
    <a href="/admin/logout">Cerrar Sesión</a>
    
    <h2>Agregar Nuevo Producto</h2>
    <form action="/admin/producto/nuevo" method="POST" enctype="multipart/form-data">
        <input type="text" name="nombre" placeholder="Nombre" required><br>
        <input type="text" name="categoria" placeholder="Categoría" required><br>
        <input type="number" step="0.01" name="precio" placeholder="Precio" required><br>
        <textarea name="descripcion" placeholder="Descripción"></textarea><br>
        <input type="text" name="talles" placeholder="Talles (S, M, L)"><br>
        <input type="text" name="colores" placeholder="Colores"><br>
        <input type="file" name="imagen" accept="image/*"><br>
        <label><input type="checkbox" name="destacado"> Destacado</label><br>
        <button type="submit">Guardar Producto</button>
    </form>

    <h2>Productos Existentes</h2>
    <ul>
        {% for p in productos %}
        <li>
            {{ p.nombre }} - ${{ p.precio }} 
            <form action="/admin/producto/eliminar/{{ p.id }}" method="POST" style="display:inline;">
                <button type="submit">Eliminar</button>
            </form>
        </li>
        {% endfor %}
    </ul>
</body>
</html>
"""

if __name__ == '__main__':
    app.run(debug=True)
