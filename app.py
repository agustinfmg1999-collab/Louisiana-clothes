import os
import secrets
import urllib.parse
from datetime import date
import cloudinary
import cloudinary.uploader
from flask import Flask, Response, render_template, request, redirect, url_for, session
from flask_wtf import CSRFProtect
from werkzeug.security import generate_password_hash, check_password_hash

import sqlite3

# Dependencia para PostgreSQL en Render con fallback a SQLite local
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    POSTGRES_AVAILABLE = True
except ImportError:
    POSTGRES_AVAILABLE = False

app = Flask(__name__)
# Recargar plantillas cuando cambian (útil en desarrollo; costo mínimo en producción)
app.config['TEMPLATES_AUTO_RELOAD'] = True

# --- SECRETOS OBLIGATORIOS (sin defaults hardcodeados) ---
app.secret_key = os.environ.get('SECRET_KEY')
if not app.secret_key:
    raise RuntimeError(
        "Falta la variable de entorno SECRET_KEY. Configurala en Render "
        "(Environment > Add Environment Variable) antes de iniciar la app."
    )

ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD')
if not ADMIN_PASSWORD:
    raise RuntimeError(
        "Falta la variable de entorno ADMIN_PASSWORD. Configurala en Render "
        "antes de iniciar la app."
    )

NUMERO_WHATSAPP_TIENDA = "5493704020319"

# --- URL PÚBLICA Y SEO ---
# URL canónica de la tienda (Railway). Si algún día cambiás a un dominio propio,
# actualizala acá o definí la variable de entorno SITE_URL en Railway.
SITE_URL = os.environ.get('SITE_URL', 'https://louisiana-clothes.up.railway.app').rstrip('/')
# Token que entrega Google Search Console para verificar la propiedad (etiqueta HTML)
GOOGLE_SITE_VERIFICATION = os.environ.get('GOOGLE_SITE_VERIFICATION', '')

# Plantillas de páginas privadas: no deben aparecer en los buscadores
PLANTILLAS_PRIVADAS = {'admin_dashboard.html', 'admin_login.html', 'cart.html', 'login.html', 'register.html'}

# --- SEGURIDAD DE COOKIES / SESIÓN ---
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
# En Render (HTTPS) dejá esto en '1'. Solo pasalo a '0' si probás en local por http://
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('SESSION_COOKIE_SECURE', '1') == '1'

# --- PROTECCIÓN CSRF ---
csrf = CSRFProtect(app)

# --- CONFIGURACIÓN DE CLOUDINARY ---
cloudinary.config(
    cloud_name=os.environ.get('CLOUDINARY_CLOUD_NAME'),
    api_key=os.environ.get('CLOUDINARY_API_KEY'),
    api_secret=os.environ.get('CLOUDINARY_API_SECRET'),
    secure=True
)

# SVG removido: puede contener JS embebido (riesgo XSS almacenado)
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

# --- HELPER DE SUBIDA A CLOUDINARY ---
def upload_to_cloudinary(file_obj):
    """Sube un archivo a Cloudinary y retorna su URL segura (None si falla)."""
    if file_obj and allowed_file(file_obj.filename):
        try:
            response = cloudinary.uploader.upload(file_obj, folder="louisiana_clothes")
            return response.get('secure_url')
        except Exception:
            app.logger.exception("Error al subir imagen a Cloudinary")
            return None
    return None

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def safe_http_url(url):
    """Devuelve la URL solo si es http(s), si no devuelve None.
    Evita guardar esquemas peligrosos (javascript:, data:, etc.)."""
    if not url:
        return None
    url = url.strip()
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme in ('http', 'https') and parsed.netloc:
        return url
    return None

# --- CONFIGURACIÓN DE BASE DE DATOS (POSTGRESQL / SQLITE FALLBACK) ---
DATABASE_URL = os.environ.get('DATABASE_URL')

# Ruta absoluta: así funciona aunque la app se ejecute desde otro directorio
SQLITE_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'louisiana.db')

def get_db():
    if DATABASE_URL and POSTGRES_AVAILABLE:
        db_uri = DATABASE_URL
        if db_uri.startswith("postgres://"):
            db_uri = db_uri.replace("postgres://", "postgresql://", 1)
        conn = psycopg2.connect(db_uri, cursor_factory=RealDictCursor)
        return conn, 'postgres'
    else:
        conn = sqlite3.connect(SQLITE_DB)
        conn.row_factory = sqlite3.Row
        return conn, 'sqlite'

def get_placeholder(db_type):
    return '%s' if db_type == 'postgres' else '?'

def init_db():
    conn, db_type = get_db()
    cursor = conn.cursor()

    if db_type == 'postgres':
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS usuarios (
                id SERIAL PRIMARY KEY,
                nombre TEXT NOT NULL,
                celular TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS productos (
                id SERIAL PRIMARY KEY,
                nombre TEXT NOT NULL,
                categoria TEXT NOT NULL,
                precio REAL NOT NULL,
                stock_talles TEXT NOT NULL,
                descripcion TEXT,
                imagen TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS compras (
                id SERIAL PRIMARY KEY,
                usuario_nombre TEXT NOT NULL,
                usuario_celular TEXT NOT NULL,
                detalle_items TEXT NOT NULL,
                total REAL NOT NULL,
                estado TEXT DEFAULT 'Pendiente',
                fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS configuracion (
                clave TEXT PRIMARY KEY,
                valor TEXT NOT NULL
            )
        ''')
        cursor.execute("INSERT INTO configuracion (clave, valor) VALUES (%s, %s) ON CONFLICT (clave) DO NOTHING",
                       ('portada_mujer', 'https://images.unsplash.com/photo-1515886657613-9f3515b0c78f?auto=format&fit=crop&q=80&w=1000'))
        cursor.execute("INSERT INTO configuracion (clave, valor) VALUES (%s, %s) ON CONFLICT (clave) DO NOTHING",
                       ('portada_hero', 'https://images.unsplash.com/photo-1490481651871-ab68de25d43d?auto=format&fit=crop&q=80&w=1600'))

        cursor.execute('SELECT COUNT(*) FROM productos')
        if cursor.fetchone()['count'] == 0:
            productos_iniciales = [
                ('Vestido Lino Tierra', 'mujer', 68000.00, 'XS:2, S:8, M:4, L:0', 'Vestido midi fluido de lino natural, fresco y elegante.', 'https://images.unsplash.com/photo-1572804013309-59a88b7e92f1?auto=format&fit=crop&q=80&w=800'),
                ('Suéter Tejido Artesanal', 'mujer', 55000.00, 'S:6, M:0, L:4', 'Suéter en tono terracota con textura acanalada.', 'https://images.unsplash.com/photo-1576995853123-5a10305d93c0?auto=format&fit=crop&q=80&w=800')
            ]
            for p in productos_iniciales:
                cursor.execute('''
                    INSERT INTO productos (nombre, categoria, precio, stock_talles, descripcion, imagen)
                    VALUES (%s, %s, %s, %s, %s, %s)
                ''', p)
    else:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                celular TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS productos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                categoria TEXT NOT NULL,
                precio REAL NOT NULL,
                stock_talles TEXT NOT NULL,
                descripcion TEXT,
                imagen TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS compras (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario_nombre TEXT NOT NULL,
                usuario_celular TEXT NOT NULL,
                detalle_items TEXT NOT NULL,
                total REAL NOT NULL,
                estado TEXT DEFAULT 'Pendiente',
                fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS configuracion (
                clave TEXT PRIMARY KEY,
                valor TEXT NOT NULL
            )
        ''')
        cursor.execute("INSERT OR IGNORE INTO configuracion (clave, valor) VALUES ('portada_mujer', 'https://images.unsplash.com/photo-1515886657613-9f3515b0c78f?auto=format&fit=crop&q=80&w=1000')")
        cursor.execute("INSERT OR IGNORE INTO configuracion (clave, valor) VALUES ('portada_hero', 'https://images.unsplash.com/photo-1490481651871-ab68de25d43d?auto=format&fit=crop&q=80&w=1600')")

        cursor.execute('SELECT COUNT(*) FROM productos')
        if cursor.fetchone()[0] == 0:
            productos_iniciales = [
                ('Vestido Lino Tierra', 'mujer', 68000.00, 'XS:2, S:8, M:4, L:0', 'Vestido midi fluido de lino natural, fresco y elegante.', 'https://images.unsplash.com/photo-1572804013309-59a88b7e92f1?auto=format&fit=crop&q=80&w=800'),
                ('Suéter Tejido Artesanal', 'mujer', 55000.00, 'S:6, M:0, L:4', 'Suéter en tono terracota con textura acanalada.', 'https://images.unsplash.com/photo-1576995853123-5a10305d93c0?auto=format&fit=crop&q=80&w=800')
            ]
            cursor.executemany('''
                INSERT INTO productos (nombre, categoria, precio, stock_talles, descripcion, imagen)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', productos_iniciales)

    conn.commit()
    conn.close()

init_db()

# --- FUNCIONES AUXILIARES ---

def parse_stock_string(stock_str):
    stock_dict = {}
    if not stock_str:
        return stock_dict
    for item in stock_str.split(','):
        if ':' in item:
            parts = item.split(':')
            talle = parts[0].strip().upper()
            try:
                cant = int(parts[1].strip())
                stock_dict[talle] = max(0, cant)
            except ValueError:
                pass
    return stock_dict

def dict_to_stock_str(stock_dict):
    return ", ".join([f"{k}:{v}" for k, v in stock_dict.items()])

def get_all_products():
    conn, db_type = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM productos ORDER BY id DESC")
        rows = cursor.fetchall()
    finally:
        conn.close()

    productos = []
    for r in rows:
        raw_img = r['imagen'] or ''
        lista_imagenes = [img.strip() for img in raw_img.split(',') if img.strip()]

        if not lista_imagenes:
            lista_imagenes = ["https://via.placeholder.com/800"]

        productos.append({
            'id': r['id'],
            'nombre': r['nombre'],
            'categoria': r['categoria'],
            'precio': r['precio'],
            'stock_talles': parse_stock_string(r['stock_talles']),
            'descripcion': r['descripcion'],
            'imagen': lista_imagenes[0],
            'imagenes': lista_imagenes
        })
    return productos

def get_portadas():
    conn, db_type = get_db()
    try:
        cursor = conn.cursor()
        ph = get_placeholder(db_type)
        query = f"SELECT clave, valor FROM configuracion WHERE clave IN ({ph}, {ph})"
        cursor.execute(query, ('portada_hero', 'portada_mujer'))
        portadas = {row['clave']: row['valor'] for row in cursor.fetchall()}
    finally:
        conn.close()
    return portadas

def flash_error(msg):
    """Guarda un mensaje de error para mostrarlo tras un redirect."""
    session['flash_error'] = msg

def get_sales_counts():
    """Cuenta cuántas veces se vendió cada producto (lee el detalle de las compras)."""
    conn, db_type = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT detalle_items FROM compras")
        filas = cursor.fetchall()
    finally:
        conn.close()

    conteo = {}
    for r in filas:
        detalle = r['detalle_items'] or ''
        for linea in detalle.splitlines():
            linea = linea.strip()
            if linea.startswith('- '):
                nombre = linea[2:].split(' (Talle:')[0].strip()
                if nombre:
                    conteo[nombre] = conteo.get(nombre, 0) + 1
    return conteo

# --- RENDERIZADO DE PLANTILLAS ---

def render_page(template, **context):
    cart = session.get('cart', {})
    context['cart_count'] = sum(cart.values())
    context['user_logged'] = session.get('user', None)
    context['whatsapp'] = NUMERO_WHATSAPP_TIENDA

    # Contexto SEO: URL pública, verificación de Google y noindex en páginas privadas
    context['site_url'] = SITE_URL
    context['google_verification'] = GOOGLE_SITE_VERIFICATION
    context['noindex'] = template in PLANTILLAS_PRIVADAS
    context['og_image'] = get_portadas().get('portada_hero') or 'https://images.unsplash.com/photo-1490481651871-ab68de25d43d?auto=format&fit=crop&q=80&w=1600'

    # Si no se pasó un error explícito, usar el flash guardado en sesión (si existe)
    flash = session.pop('flash_error', None)
    if not context.get('error'):
        context['error'] = flash

    return render_template(template, **context)

# --- RUTAS PRINCIPALES ---

@app.route('/')
def index():
    cat = request.args.get('categoria', '')
    talle_filtro = request.args.get('talle', '')
    q = request.args.get('q', '').strip()

    # La tienda es 100% indumentaria femenina
    if cat == 'hombre':
        return redirect(url_for('index'))

    productos = [p for p in get_all_products() if p['categoria'] == 'mujer']
    portadas = get_portadas()

    todos_talles = sorted(list(set(
        talle for p in productos for talle in p['stock_talles'].keys()
    )))

    if cat:
        productos = [p for p in productos if p['categoria'] == cat]

    if talle_filtro:
        productos = [p for p in productos if p['stock_talles'].get(talle_filtro, 0) > 0]

    if q:
        busqueda = q.lower()
        productos = [p for p in productos
                     if busqueda in p['nombre'].lower()
                     or busqueda in (p['descripcion'] or '').lower()
                     or busqueda in p['categoria'].lower()]
    else:
        # Sin filtros: ordenar por ventas (los más vendidos primero)
        conteo_ventas = get_sales_counts()
        productos.sort(key=lambda p: (-conteo_ventas.get(p['nombre'], 0), -p['id']))

    return render_page(
        'catalog.html',
        productos=productos,
        cat_actual=cat,
        talle_actual=talle_filtro,
        q_actual=q,
        todos_talles=todos_talles,
        portadas=portadas
    )

# --- SEO: ROBOTS.TXT Y SITEMAP.XML ---

@app.route('/robots.txt')
def robots_txt():
    lineas = [
        'User-agent: *',
        'Disallow: /admin',
        'Disallow: /cart',
        'Disallow: /login',
        'Disallow: /register',
        '',
        f'Sitemap: {SITE_URL}/sitemap.xml',
    ]
    return Response('\n'.join(lineas) + '\n', mimetype='text/plain')

@app.route('/sitemap.xml')
def sitemap_xml():
    hoy = date.today().isoformat()
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f'  <url><loc>{SITE_URL}/</loc><lastmod>{hoy}</lastmod><changefreq>daily</changefreq><priority>1.0</priority></url>\n'
        '</urlset>'
    )
    return Response(xml, mimetype='application/xml')

# --- RUTAS DE CARRITO ---

@app.route('/add_to_cart/<int:product_id>', methods=['POST'])
def add_to_cart(product_id):
    talle = request.form.get('talle')
    if not talle:
        return redirect(url_for('index'))

    productos_dict = {p['id']: p for p in get_all_products()}
    producto = productos_dict.get(product_id)
    if not producto:
        flash_error("El producto seleccionado ya no está disponible.")
        return redirect(url_for('index'))

    stock_disponible = producto['stock_talles'].get(talle, 0)
    if stock_disponible <= 0:
        flash_error(f'El talle {talle} de "{producto["nombre"]}" está agotado.')
        return redirect(url_for('index'))

    cart = session.get('cart', {})
    item_key = f"{product_id}_{talle}"
    cantidad_actual = cart.get(item_key, 0)

    if cantidad_actual + 1 > stock_disponible:
        flash_error(f'No hay más stock disponible del talle {talle} para "{producto["nombre"]}".')
        return redirect(url_for('index'))

    cart[item_key] = cantidad_actual + 1
    session['cart'] = cart
    return redirect(url_for('cart_view'))

@app.route('/cart')
def cart_view():
    cart = session.get('cart', {})
    productos_dict = {p['id']: p for p in get_all_products()}

    items = []
    total = 0.0

    for item_key, cantidad in cart.items():
        try:
            p_id_str, talle = item_key.split('_', 1)
            p_id = int(p_id_str)
            if p_id in productos_dict:
                producto = productos_dict[p_id]
                subtotal = producto['precio'] * cantidad
                total += subtotal
                items.append({
                    'item_key': item_key,
                    'producto': producto,
                    'talle': talle,
                    'cantidad': cantidad,
                    'subtotal': subtotal
                })
        except ValueError:
            continue

    return render_page('cart.html', items=items, total=total)

@app.route('/remove_from_cart/<item_key>', methods=['POST'])
def remove_from_cart(item_key):
    cart = session.get('cart', {})
    if item_key in cart:
        del cart[item_key]
        session['cart'] = cart
    return redirect(url_for('cart_view'))

# --- FINALIZACIÓN DE COMPRA (CHECKOUT) ---

@app.route('/checkout', methods=['POST'])
def checkout():
    user = session.get('user')
    cart = session.get('cart', {})
    if not user or not cart:
        return redirect(url_for('cart_view'))

    conn, db_type = get_db()
    try:
        cursor = conn.cursor()
        ph = get_placeholder(db_type)

        # Toda la operación ocurre en UNA transacción:
        # - se releen y bloquean las filas (FOR UPDATE en PostgreSQL)
        # - se valida el stock con los valores frescos de la BD
        # - se descuenta el stock y se registra la compra
        # Si algo falla, se hace rollback y no queda nada a medias.
        if db_type == 'sqlite':
            conn.execute('BEGIN IMMEDIATE')

        lock = ' FOR UPDATE' if db_type == 'postgres' else ''
        cursor.execute(f"SELECT * FROM productos{lock}")
        productos_db = {}
        for r in cursor.fetchall():
            productos_db[r['id']] = {
                'id': r['id'],
                'nombre': r['nombre'],
                'precio': r['precio'],
                'stock_talles': parse_stock_string(r['stock_talles']),
            }

        items_texto = []
        total = 0.0
        afectados = {}

        for item_key, cantidad in cart.items():
            try:
                p_id_str, talle = item_key.split('_', 1)
                p_id = int(p_id_str)
            except ValueError:
                continue

            p = productos_db.get(p_id)
            if not p or p['stock_talles'].get(talle, 0) < cantidad:
                nombre = p['nombre'] if p else 'uno de los productos'
                conn.rollback()
                flash_error(f'El stock de "{nombre}" (talle {talle}) cambió. Por favor revisá tu carrito.')
                return redirect(url_for('cart_view'))

            subtotal = p['precio'] * cantidad
            total += subtotal
            items_texto.append(f"- {p['nombre']} (Talle: {talle}) x{cantidad} = ${subtotal:,.2f}")

            p['stock_talles'][talle] = max(0, p['stock_talles'][talle] - cantidad)
            afectados[p_id] = p

        if not items_texto:
            conn.rollback()
            return redirect(url_for('cart_view'))

        for p in afectados.values():
            query = f"UPDATE productos SET stock_talles = {ph} WHERE id = {ph}"
            cursor.execute(query, (dict_to_stock_str(p['stock_talles']), p['id']))

        detalle_str = "\n".join(items_texto)
        query_ins = f'''
            INSERT INTO compras (usuario_nombre, usuario_celular, detalle_items, total, estado)
            VALUES ({ph}, {ph}, {ph}, {ph}, 'Pendiente')
        '''
        cursor.execute(query_ins, (user['nombre'], user['celular'], detalle_str, total))

        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        app.logger.exception("Error al procesar el checkout")
        flash_error("No se pudo procesar la compra. Tus productos siguen en el carrito, intentá nuevamente.")
        return redirect(url_for('cart_view'))
    finally:
        conn.close()

    session['cart'] = {}

    mensaje = f"¡Hola Louisiana Clothes! Mi nombre es {user['nombre']}.\nQuiero confirmar el siguiente pedido:\n\n{detalle_str}\n\nTotal: ${total:,.2f}"
    url_whatsapp = f"https://wa.me/{NUMERO_WHATSAPP_TIENDA}?text={urllib.parse.quote(mensaje)}"

    return redirect(url_whatsapp)

# --- AUTENTICACIÓN DE USUARIOS ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        celular = request.form.get('celular', '').strip()
        password = request.form.get('password', '').strip()

        conn, db_type = get_db()
        cursor = conn.cursor()
        ph = get_placeholder(db_type)
        query = f"SELECT * FROM usuarios WHERE celular = {ph}"
        cursor.execute(query, (celular,))
        usuario = cursor.fetchone()
        conn.close()

        if usuario and check_password_hash(usuario['password_hash'], password):
            session['user'] = {'id': usuario['id'], 'nombre': usuario['nombre'], 'celular': usuario['celular']}
            return redirect(url_for('index'))

        return render_page('login.html', error="Celular o contraseña incorrectos.")

    return render_page('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        celular = request.form.get('celular', '').strip()
        password = request.form.get('password', '').strip()

        if not nombre or not celular or not password:
            return render_page('register.html', error="Todos los campos son obligatorios.")

        password_hash = generate_password_hash(password)

        conn, db_type = get_db()
        cursor = conn.cursor()
        ph = get_placeholder(db_type)
        try:
            query = f"INSERT INTO usuarios (nombre, celular, password_hash) VALUES ({ph}, {ph}, {ph})"
            cursor.execute(query, (nombre, celular, password_hash))
            conn.commit()
            conn.close()

            return redirect(url_for('login'))
        except Exception:
            conn.close()
            return render_page('register.html', error="El número de celular ya está registrado.")

    return render_page('register.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('index'))

# --- PANEL DE ADMINISTRACIÓN ---

@app.route('/admin')
def admin_dashboard():
    if not session.get('is_admin'):
        return render_page('admin_login.html')

    tab = request.args.get('tab', 'inventario')
    conn, db_type = get_db()
    cursor = conn.cursor()

    productos = get_all_products()
    portadas = get_portadas()

    cursor.execute("SELECT * FROM compras ORDER BY fecha DESC")
    compras = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT id, nombre, celular, fecha_registro FROM usuarios ORDER BY fecha_registro DESC")
    usuarios = [dict(r) for r in cursor.fetchall()]

    conn.close()

    return render_page(
        'admin_dashboard.html',
        tab=tab,
        productos=productos,
        portadas=portadas,
        compras=compras,
        usuarios=usuarios,
        producto_editar=None
    )

@app.route('/admin/login', methods=['POST'])
def admin_login():
    key = request.form.get('admin_key', '')
    if secrets.compare_digest(key, ADMIN_PASSWORD):
        session['is_admin'] = True
        return redirect(url_for('admin_dashboard'))
    return render_page('admin_login.html', error="Clave de administrador incorrecta.")

@app.route('/admin/logout')
def admin_logout():
    session.pop('is_admin', None)
    return redirect(url_for('index'))

@app.route('/admin/update_portada', methods=['POST'])
def admin_update_portada():
    if not session.get('is_admin'):
        return redirect(url_for('admin_dashboard'))

    categoria = request.form.get('categoria')
    url_imagen = safe_http_url(request.form.get('imagen_url'))
    file = request.files.get('imagen_file')

    if file and file.filename != '':
        uploaded_url = upload_to_cloudinary(file)
        if uploaded_url:
            url_imagen = uploaded_url

    if url_imagen and categoria in ['mujer', 'hero']:
        clave_db = f"portada_{categoria}"
        conn, db_type = get_db()
        cursor = conn.cursor()
        ph = get_placeholder(db_type)
        if db_type == 'postgres':
            query = f"INSERT INTO configuracion (clave, valor) VALUES ({ph}, {ph}) ON CONFLICT (clave) DO UPDATE SET valor = EXCLUDED.valor"
        else:
            query = "INSERT OR REPLACE INTO configuracion (clave, valor) VALUES (?, ?)"
        cursor.execute(query, (clave_db, url_imagen))
        conn.commit()
        conn.close()

    return redirect(url_for('admin_dashboard', tab='portadas'))

@app.route('/admin/add', methods=['POST'])
def admin_add_product():
    if not session.get('is_admin'):
        return redirect(url_for('admin_dashboard'))

    nombre = request.form.get('nombre')
    categoria = request.form.get('categoria')
    try:
        precio = float(request.form.get('precio', 0))
    except ValueError:
        precio = 0.0
    stock_talles = request.form.get('stock_talles')
    descripcion = request.form.get('descripcion')

    imagenes_guardadas = []

    files = request.files.getlist('imagen_file')
    for file in files:
        if file and file.filename != '':
            uploaded_url = upload_to_cloudinary(file)
            if uploaded_url:
                imagenes_guardadas.append(uploaded_url)

    imagen_url_input = request.form.get('imagen_url', '').strip()
    if imagen_url_input:
        urls = [u.strip() for u in imagen_url_input.replace('\n', ',').split(',') if u.strip()]
        imagenes_guardadas.extend([u for u in urls if safe_http_url(u)])

    if not imagenes_guardadas:
        imagenes_guardadas.append("https://via.placeholder.com/800")

    imagen_db_str = ",".join(imagenes_guardadas)

    conn, db_type = get_db()
    cursor = conn.cursor()
    ph = get_placeholder(db_type)
    query = f'''
        INSERT INTO productos (nombre, categoria, precio, stock_talles, descripcion, imagen)
        VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph})
    '''
    cursor.execute(query, (nombre, categoria, precio, stock_talles, descripcion, imagen_db_str))
    conn.commit()
    conn.close()

    return redirect(url_for('admin_dashboard'))

@app.route('/admin/edit/<int:product_id>')
def admin_edit_product(product_id):
    if not session.get('is_admin'):
        return redirect(url_for('admin_dashboard'))

    productos = get_all_products()
    portadas = get_portadas()
    producto_editar = next((p for p in productos if p['id'] == product_id), None)

    if not producto_editar:
        flash_error("El producto que intentás editar ya no existe.")
        return redirect(url_for('admin_dashboard'))

    conn, db_type = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM compras ORDER BY fecha DESC")
    compras = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT id, nombre, celular, fecha_registro FROM usuarios ORDER BY fecha_registro DESC")
    usuarios = [dict(r) for r in cursor.fetchall()]
    conn.close()

    return render_page(
        'admin_dashboard.html',
        tab='inventario',
        productos=productos,
        portadas=portadas,
        compras=compras,
        usuarios=usuarios,
        producto_editar=producto_editar
    )

@app.route('/admin/update_product/<int:product_id>', methods=['POST'])
def admin_update_product(product_id):
    if not session.get('is_admin'):
        return redirect(url_for('admin_dashboard'))

    nombre = request.form.get('nombre')
    categoria = request.form.get('categoria')
    try:
        precio = float(request.form.get('precio', 0))
    except ValueError:
        precio = 0.0
    descripcion = request.form.get('descripcion')

    productos = get_all_products()
    producto_actual = next((p for p in productos if p['id'] == product_id), None)

    if not producto_actual:
        flash_error("El producto que intentás editar ya no existe.")
        return redirect(url_for('admin_dashboard'))

    nuevo_stock = {}
    for talle in producto_actual['stock_talles'].keys():
        if request.form.get(f"eliminar_talle_{talle}") == "1":
            continue
        cant_str = request.form.get(f"talle_cant_{talle}")
        if cant_str is not None:
            try:
                nuevo_stock[talle] = max(0, int(cant_str))
            except ValueError:
                pass

    nuevo_talle_nombre = request.form.get('nuevo_talle_nombre', '').strip().upper()
    nuevo_talle_cant = request.form.get('nuevo_talle_cant', '').strip()
    if nuevo_talle_nombre and nuevo_talle_cant != '':
        try:
            nuevo_stock[nuevo_talle_nombre] = max(0, int(nuevo_talle_cant))
        except ValueError:
            pass

    stock_str = dict_to_stock_str(nuevo_stock)

    imagenes_existentes = [i.strip() for i in request.form.get('imagenes_existentes', '').split(',') if i.strip()]

    files = request.files.getlist('imagen_file')
    for file in files:
        if file and file.filename != '':
            uploaded_url = upload_to_cloudinary(file)
            if uploaded_url:
                imagenes_existentes.append(uploaded_url)

    imagen_url_input = request.form.get('imagen_url', '').strip()
    if imagen_url_input:
        urls = [u.strip() for u in imagen_url_input.replace('\n', ',').split(',') if u.strip()]
        imagenes_existentes.extend([u for u in urls if safe_http_url(u)])

    if not imagenes_existentes:
        imagenes_existentes.append("https://via.placeholder.com/800")

    imagen_db_str = ",".join(imagenes_existentes)

    conn, db_type = get_db()
    cursor = conn.cursor()
    ph = get_placeholder(db_type)
    query = f'''
        UPDATE productos
        SET nombre = {ph}, categoria = {ph}, precio = {ph}, stock_talles = {ph}, descripcion = {ph}, imagen = {ph}
        WHERE id = {ph}
    '''
    cursor.execute(query, (nombre, categoria, precio, stock_str, descripcion, imagen_db_str, product_id))
    conn.commit()
    conn.close()

    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete/<int:product_id>', methods=['POST'])
def admin_delete_product(product_id):
    if not session.get('is_admin'):
        return redirect(url_for('admin_dashboard'))

    conn, db_type = get_db()
    cursor = conn.cursor()
    ph = get_placeholder(db_type)
    query = f"DELETE FROM productos WHERE id = {ph}"
    cursor.execute(query, (product_id,))
    conn.commit()
    conn.close()

    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
def admin_delete_user(user_id):
    if not session.get('is_admin'):
        return redirect(url_for('admin_dashboard'))

    conn, db_type = get_db()
    cursor = conn.cursor()
    ph = get_placeholder(db_type)
    query = f"DELETE FROM usuarios WHERE id = {ph}"
    cursor.execute(query, (user_id,))
    conn.commit()
    conn.close()

    return redirect(url_for('admin_dashboard', tab='usuarios'))

@app.route('/admin/update_order_status/<int:order_id>', methods=['POST'])
def admin_update_order_status(order_id):
    if not session.get('is_admin'):
        return redirect(url_for('admin_dashboard'))

    nuevo_estado = request.form.get('nuevo_estado')
    if nuevo_estado:
        conn, db_type = get_db()
        cursor = conn.cursor()
        ph = get_placeholder(db_type)
        query = f"UPDATE compras SET estado = {ph} WHERE id = {ph}"
        cursor.execute(query, (nuevo_estado, order_id))
        conn.commit()
        conn.close()

    return redirect(url_for('admin_dashboard', tab='compras'))

if __name__ == '__main__':
    app.run(debug=os.environ.get('FLASK_DEBUG', '0') == '1')
