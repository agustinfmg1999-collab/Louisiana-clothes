import os
import sqlite3
import re
import urllib.parse
from flask import Flask, render_template_string, request, redirect, url_for, session, send_from_directory

app = Flask(__name__)
app.secret_key = 'louisiana_clothes_secret_key_super_segura'

ADMIN_PASSWORD = "14230618aF"  # Contraseña para acceder al panel de administración
NUMERO_WHATSAPP_TIENDA = "5493704020319"

UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

DATABASE = 'louisiana.db'

# --- CONFIGURACIÓN DE BASE DE DATOS (SQLITE) ---

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        cursor = conn.cursor()
        
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

        # Migración automática de columna 'estado' si no existía
        try:
            cursor.execute("ALTER TABLE compras ADD COLUMN estado TEXT DEFAULT 'Pendiente'")
        except sqlite3.OperationalError:
            pass

        cursor.execute('SELECT COUNT(*) FROM productos')
        if cursor.fetchone()[0] == 0:
            productos_iniciales = [
                ('Camisa Oxford Rústica', 'hombre', 45000.00, 'S:5, M:10, L:3, XL:0', 'Camisa de algodón pesado, ideal para un look casual estructurado.', 'https://images.unsplash.com/photo-1596755094514-f87e34085b2c?auto=format&fit=crop&q=80&w=800'),
                ('Vestido Lino Tierra', 'mujer', 68000.00, 'XS:2, S:8, M:4, L:0', 'Vestido midi fluido de lino natural, fresco y elegante.', 'https://images.unsplash.com/photo-1572804013309-59a88b7e92f1?auto=format&fit=crop&q=80&w=800'),
                ('Chaqueta de Cuero Vintage', 'hombre', 120000.00, 'M:3, L:5, XL:2', 'Chaqueta estilo aviador en tono café oscuro.', 'https://images.unsplash.com/photo-1551028719-00167b16eac5?auto=format&fit=crop&q=80&w=800'),
                ('Suéter Tejido Artesanal', 'mujer', 55000.00, 'S:6, M:0, L:4', 'Suéter en tono terracota con textura acanalada.', 'https://images.unsplash.com/photo-1576995853123-5a10305d93c0?auto=format&fit=crop&q=80&w=800')
            ]
            cursor.executemany('''
                INSERT INTO productos (nombre, categoria, precio, stock_talles, descripcion, imagen)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', productos_iniciales)

        conn.commit()

init_db()

# --- FUNCIONES AUXILIARES DE STOCK ---

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
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM productos")
    rows = cursor.fetchall()
    conn.close()
    
    productos = []
    for r in rows:
        productos.append({
            'id': r['id'],
            'nombre': r['nombre'],
            'categoria': r['categoria'],
            'precio': r['precio'],
            'stock_talles': parse_stock_string(r['stock_talles']),
            'descripcion': r['descripcion'],
            'imagen': r['imagen']
        })
    return productos

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- PLANTILLAS HTML ---

HTML_LAYOUT = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Louisiana Clothes</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400..900;1,400..900&family=Montserrat:wght@300;400;600;700&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Montserrat', sans-serif; }
        .font-serif { font-family: 'Playfair Display', serif; }
    </style>
</head>
<body class="bg-[#F8F5F2] text-[#2D1B12] min-h-screen flex flex-col justify-between">

    <header class="bg-[#2D1B12] text-[#F3EBE1] shadow-md sticky top-0 z-50">
        <div class="max-w-7xl mx-auto px-6 py-3 flex justify-between items-center">
            
            <a href="/" class="flex items-center hover:opacity-90 transition py-1">
                <img src="{{ url_for('static', filename='uploads/Logo.svg') }}" 
                     alt="Louisiana Clothes Logo" 
                     class="h-16 w-auto object-contain"
                     onerror="this.style.display='none'; this.nextElementSibling.style.display='block';">
                <span class="hidden font-serif text-xl font-bold tracking-wider text-[#D9A372]">LOUISIANA</span>
            </a>
            
            <nav class="flex items-center gap-8 text-sm font-semibold uppercase">
                <a href="/" class="hover:text-[#D9A372] transition">Inicio</a>
                <a href="/?categoria=hombre" class="hover:text-[#D9A372] transition">Hombre</a>
                <a href="/?categoria=mujer" class="hover:text-[#D9A372] transition">Mujer</a>
            </nav>

            <div class="flex items-center gap-4">
                {% if user_logged %}
                    <div class="flex items-center gap-3 bg-[#3D281C] px-3 py-1.5 rounded-full text-xs font-semibold">
                        <span class="text-[#D9A372]"><i class="fa-solid fa-user"></i> {{ user_logged.nombre }}</span>
                        <a href="/logout" class="text-gray-400 hover:text-white transition" title="Cerrar sesión">
                            <i class="fa-solid fa-right-from-bracket"></i>
                        </a>
                    </div>
                {% else %}
                    <a href="/login" class="text-xs font-bold uppercase tracking-wider hover:text-[#D9A372] transition flex items-center gap-1">
                        <i class="fa-solid fa-user"></i> Iniciar Sesión / Registro
                    </a>
                {% endif %}

                <a href="/cart" class="bg-[#8C5E3C] hover:bg-[#6F472B] text-white px-4 py-2 rounded-full font-bold text-sm transition flex items-center gap-2">
                    <i class="fa-solid fa-bag-shopping"></i>
                    <span>Carrito</span>
                    {% if cart_count > 0 %}
                    <span class="bg-[#D9A372] text-[#2D1B12] text-xs font-extrabold w-5 h-5 flex items-center justify-center rounded-full">
                        {{ cart_count }}
                    </span>
                    {% endif %}
                </a>

                <a href="/admin" class="text-[#4A3225] hover:text-[#D9A372] transition opacity-30 hover:opacity-100 p-1 text-xs" title="Panel Admin">
                    <i class="fa-solid fa-lock"></i>
                </a>
            </div>
        </div>
    </header>

    {% if error %}
    <div class="max-w-7xl mx-auto px-6 pt-6 w-full">
        <div class="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded-lg text-sm relative">
            <span>{{ error }}</span>
        </div>
    </div>
    {% endif %}

    <main class="flex-grow max-w-7xl w-full mx-auto px-6 py-10">
        __CONTENT__
    </main>

    <footer class="bg-[#1A100B] text-[#A89F91] py-8 border-t border-[#3D281C]">
        <div class="max-w-7xl mx-auto px-6 text-center">
            <h3 class="font-serif text-xl font-bold text-[#D9A372] mb-2">LOUISIANA CLOTHES</h3>
            <p class="text-xs tracking-widest uppercase mb-4">Elegancia Clásica & Estilo Natural</p>
            <p class="text-xs text-gray-500">&copy; 2026 Louisiana Clothes. Todos los derechos reservados.</p>
        </div>
    </footer>

</body>
</html>
"""

CATALOG_CONTENT = """
    {% if not cat_actual and not talle_actual %}
    <section class="mb-14">
        <div class="text-center mb-8">
            <h2 class="text-xs font-bold uppercase tracking-widest text-[#8C5E3C]">Colecciones Principales</h2>
            <p class="text-3xl font-serif font-bold text-[#2D1B12] mt-1">Elige tu categoría</p>
        </div>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-8">
            <a href="/?categoria=hombre" class="group relative h-96 rounded-2xl overflow-hidden shadow-md flex items-end p-8 border border-[#EAE3DC]">
                <img src="https://images.unsplash.com/photo-1617137984095-74e4e5e3613f?auto=format&fit=crop&q=80&w=1000" class="absolute inset-0 w-full h-full object-cover group-hover:scale-105 transition duration-700">
                <div class="absolute inset-0 bg-gradient-to-t from-black/80 via-black/30 to-transparent"></div>
                <div class="relative z-10">
                    <span class="text-xs uppercase tracking-widest text-[#D9A372] font-semibold">Colección Masculina</span>
                    <h3 class="text-3xl font-serif font-bold text-white mt-1">HOMBRE</h3>
                </div>
            </a>
            <a href="/?categoria=mujer" class="group relative h-96 rounded-2xl overflow-hidden shadow-md flex items-end p-8 border border-[#EAE3DC]">
                <img src="https://images.unsplash.com/photo-1515886657613-9f3515b0c78f?auto=format&fit=crop&q=80&w=1000" class="absolute inset-0 w-full h-full object-cover group-hover:scale-105 transition duration-700">
                <div class="absolute inset-0 bg-gradient-to-t from-black/80 via-black/30 to-transparent"></div>
                <div class="relative z-10">
                    <span class="text-xs uppercase tracking-widest text-[#D9A372] font-semibold">Colección Femenina</span>
                    <h3 class="text-3xl font-serif font-bold text-white mt-1">MUJER</h3>
                </div>
            </a>
        </div>
    </section>
    {% endif %}

    <div class="flex flex-col md:flex-row md:justify-between md:items-end gap-4 mb-8">
        <div>
            <h1 class="text-4xl font-serif font-bold text-[#2D1B12]">
                {% if cat_actual == 'hombre' %}Colección Hombre{% elif cat_actual == 'mujer' %}Colección Mujer{% else %}Todos los Productos{% endif %}
            </h1>
        </div>
        <div class="flex flex-wrap items-center gap-3">
            <div class="flex gap-1 bg-white p-1 rounded-lg border border-gray-200 shadow-sm">
                <a href="/{% if talle_actual %}?talle={{ talle_actual }}{% endif %}" class="px-3 py-1.5 rounded-md text-xs font-semibold transition {% if not cat_actual %}bg-[#2D1B12] text-white{% else %}text-[#2D1B12] hover:bg-gray-100{% endif %}">Todos</a>
                <a href="/?categoria=hombre{% if talle_actual %}&talle={{ talle_actual }}{% endif %}" class="px-3 py-1.5 rounded-md text-xs font-semibold transition {% if cat_actual == 'hombre' %}bg-[#2D1B12] text-white{% else %}text-[#2D1B12] hover:bg-gray-100{% endif %}">Hombre</a>
                <a href="/?categoria=mujer{% if talle_actual %}&talle={{ talle_actual }}{% endif %}" class="px-3 py-1.5 rounded-md text-xs font-semibold transition {% if cat_actual == 'mujer' %}bg-[#2D1B12] text-white{% else %}text-[#2D1B12] hover:bg-gray-100{% endif %}">Mujer</a>
            </div>
            {% if todos_talles %}
            <div class="flex items-center gap-1 bg-white p-1 rounded-lg border border-gray-200 shadow-sm">
                <span class="text-xs font-bold text-gray-400 px-2 uppercase">Talle:</span>
                <a href="/{% if cat_actual %}?categoria={{ cat_actual }}{% endif %}" class="px-2 py-1 rounded text-xs font-bold transition {% if not talle_actual %}bg-[#8C5E3C] text-white{% else %}text-gray-600 hover:bg-gray-100{% endif %}">Todos</a>
                {% for t in todos_talles %}
                <a href="/?{% if cat_actual %}categoria={{ cat_actual }}&{% endif %}talle={{ t }}" class="px-2 py-1 rounded text-xs font-bold transition {% if talle_actual == t %}bg-[#8C5E3C] text-white{% else %}text-gray-600 hover:bg-gray-100{% endif %}">{{ t }}</a>
                {% endfor %}
            </div>
            {% endif %}
        </div>
    </div>

    {% if productos %}
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-8">
        {% for p in productos %}
        <div class="bg-white rounded-xl shadow-sm hover:shadow-md transition overflow-hidden border border-[#EAE3DC] flex flex-col justify-between">
            <div>
                <div class="h-64 overflow-hidden bg-gray-100 relative">
                    <img src="{{ p.imagen }}" alt="{{ p.nombre }}" class="w-full h-full object-cover hover:scale-105 transition duration-500">
                </div>
                <div class="p-5">
                    <span class="text-xs uppercase tracking-wider font-bold text-[#8C5E3C]">{{ p.categoria }}</span>
                    <h2 class="text-lg font-serif font-bold text-[#2D1B12] mt-1">{{ p.nombre }}</h2>
                    <p class="text-gray-500 text-sm mt-2 line-clamp-2">{{ p.descripcion }}</p>
                    <p class="text-xl font-bold text-[#2D1B12] mt-3">${{ "{:,.2f}".format(p.precio).replace(',', 'X').replace('.', ',').replace('X', '.') }}</p>
                </div>
            </div>

            <div class="p-5 pt-0">
                <form action="/add_to_cart/{{ p.id }}" method="POST" class="space-y-3">
                    <div>
                        <label class="block text-[11px] font-bold uppercase text-gray-400 mb-1">Seleccionar Talle:</label>
                        <select name="talle" required class="w-full border border-gray-300 rounded-lg p-2 text-xs font-semibold text-[#2D1B12] focus:outline-none focus:border-[#8C5E3C]">
                            {% for talle, stock in p.stock_talles.items() %}
                                {% if stock > 0 %}
                                    <option value="{{ talle }}">Talle {{ talle }} ({{ stock }} disp.)</option>
                                {% else %}
                                    <option value="{{ talle }}" disabled class="text-gray-400 bg-gray-100">Talle {{ talle }} (Agotado)</option>
                                {% endif %}
                            {% endfor %}
                        </select>
                    </div>

                    <button type="submit" class="w-full bg-[#2D1B12] hover:bg-[#8C5E3C] text-white py-2 rounded-lg text-xs font-bold uppercase tracking-wider transition flex items-center justify-center gap-2">
                        <i class="fa-solid fa-cart-plus"></i> Añadir al Carrito
                    </button>
                </form>
            </div>
        </div>
        {% endfor %}
    </div>
    {% else %}
    <div class="text-center py-12 bg-white rounded-xl border border-[#EAE3DC]">
        <p class="text-gray-500">No se encontraron productos disponibles con los filtros seleccionados.</p>
    </div>
    {% endif %}
"""

CART_CONTENT = """
    <h1 class="text-4xl font-serif font-bold text-[#2D1B12] mb-8">Tu Carrito de Compras</h1>

    {% if items %}
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
        <div class="lg:col-span-2 space-y-4">
            {% for item in items %}
            <div class="bg-white p-4 rounded-xl border border-[#EAE3DC] flex items-center gap-4 shadow-sm">
                <img src="{{ item.producto.imagen }}" class="w-20 h-20 object-cover rounded-lg">
                <div class="flex-grow">
                    <h3 class="font-serif font-bold text-lg text-[#2D1B12]">{{ item.producto.nombre }}</h3>
                    <p class="text-xs font-semibold text-[#8C5E3C] uppercase mt-0.5">Talle: <span class="bg-[#F8F5F2] px-2 py-0.5 rounded border border-[#EAE3DC] text-[#2D1B12] font-bold">{{ item.talle }}</span></p>
                    <p class="text-sm text-gray-500 mt-1">${{ "{:,.2f}".format(item.producto.precio).replace(',', 'X').replace('.', ',').replace('X', '.') }} c/u</p>
                </div>
                <div class="flex items-center gap-3">
                    <span class="font-bold text-sm bg-gray-100 px-3 py-1 rounded">Cant: {{ item.cantidad }}</span>
                    <span class="font-bold text-lg text-[#2D1B12]">${{ "{:,.2f}".format(item.subtotal).replace(',', 'X').replace('.', ',').replace('X', '.') }}</span>
                    <a href="/remove_from_cart/{{ item.item_key }}" class="text-red-500 hover:text-red-700 p-2"><i class="fa-solid fa-trash"></i></a>
                </div>
            </div>
            {% endfor %}
        </div>

        <div class="bg-white p-6 rounded-xl border border-[#EAE3DC] shadow-sm h-fit">
            <h2 class="font-serif font-bold text-xl mb-4 border-b pb-2">Resumen de Compra</h2>
            <div class="flex justify-between items-center mb-4 text-lg">
                <span>Total</span>
                <span class="font-bold text-2xl text-[#8C5E3C]">${{ "{:,.2f}".format(total).replace(',', 'X').replace('.', ',').replace('X', '.') }}</span>
            </div>
            
            {% if user_logged %}
            <a href="/checkout" class="block w-full text-center bg-[#25D366] hover:bg-[#128C7E] text-white py-3 rounded-lg font-bold transition flex items-center justify-center gap-2">
                <i class="fa-brands fa-whatsapp text-lg"></i> Finalizar Pedido por WhatsApp
            </a>
            {% else %}
            <div class="bg-[#F8F5F2] p-3 rounded-lg border border-[#EAE3DC] text-center mb-3">
                <p class="text-xs text-gray-600 mb-2">Debes iniciar sesión para completar la compra.</p>
                <a href="/login" class="block w-full bg-[#8C5E3C] text-white py-2 rounded-md font-bold text-xs uppercase tracking-wider hover:bg-[#6F472B] transition">Iniciar Sesión</a>
            </div>
            {% endif %}
        </div>
    </div>
    {% else %}
    <div class="text-center py-16 bg-white rounded-xl border border-[#EAE3DC]">
        <i class="fa-solid fa-bag-shopping text-6xl text-gray-300 mb-4"></i>
        <h2 class="text-2xl font-serif text-gray-600 mb-4">Tu carrito está vacío</h2>
        <a href="/" class="bg-[#2D1B12] text-white px-6 py-3 rounded-lg font-bold hover:bg-[#8C5E3C] transition">Ir a la tienda</a>
    </div>
    {% endif %}
"""

LOGIN_CONTENT = """
    <div class="max-w-md mx-auto bg-white p-8 rounded-2xl border border-[#EAE3DC] shadow-sm">
        <h1 class="text-3xl font-serif font-bold text-center text-[#2D1B12] mb-6">Iniciar Sesión</h1>
        <form action="/login" method="POST" class="space-y-4">
            <div>
                <label class="block text-xs font-bold uppercase text-gray-600 mb-1">Celular</label>
                <input type="tel" name="celular" required class="w-full border border-gray-300 rounded-lg p-2.5 text-sm focus:outline-none focus:border-[#8C5E3C]">
            </div>
            <div>
                <label class="block text-xs font-bold uppercase text-gray-600 mb-1">Contraseña</label>
                <input type="password" name="password" required class="w-full border border-gray-300 rounded-lg p-2.5 text-sm focus:outline-none focus:border-[#8C5E3C]">
            </div>
            <button type="submit" class="w-full bg-[#2D1B12] text-white py-3 rounded-lg font-bold hover:bg-[#8C5E3C] transition uppercase text-xs tracking-wider">Ingresar</button>
        </form>
        
        <div class="mt-4 pt-4 border-t text-center text-xs">
            <a href="/register" class="font-bold text-[#8C5E3C] hover:underline">¿No tienes cuenta? Regístrate aquí</a>
        </div>
    </div>
"""

REGISTER_CONTENT = """
    <div class="max-w-md mx-auto bg-white p-8 rounded-2xl border border-[#EAE3DC] shadow-sm">
        <h1 class="text-3xl font-serif font-bold text-center text-[#2D1B12] mb-6">Registro</h1>
        <form action="/register" method="POST" class="space-y-4">
            <div>
                <label class="block text-xs font-bold uppercase text-gray-600 mb-1">Nombre Completo</label>
                <input type="text" name="nombre" required class="w-full border border-gray-300 rounded-lg p-2.5 text-sm focus:outline-none focus:border-[#8C5E3C]">
            </div>
            <div>
                <label class="block text-xs font-bold uppercase text-gray-600 mb-1">Celular</label>
                <input type="tel" name="celular" required class="w-full border border-gray-300 rounded-lg p-2.5 text-sm focus:outline-none focus:border-[#8C5E3C]">
            </div>
            <div>
                <label class="block text-xs font-bold uppercase text-gray-600 mb-1">Contraseña</label>
                <input type="password" name="password" required class="w-full border border-gray-300 rounded-lg p-2.5 text-sm focus:outline-none focus:border-[#8C5E3C]">
            </div>
            <button type="submit" class="w-full bg-[#8C5E3C] text-white py-3 rounded-lg font-bold hover:bg-[#6F472B] transition uppercase text-xs tracking-wider">Completar Registro</button>
        </form>
    </div>
"""

ADMIN_LOGIN_CONTENT = """
    <div class="max-w-md mx-auto bg-white p-8 rounded-2xl border border-[#EAE3DC] shadow-sm">
        <div class="text-center mb-6">
            <i class="fa-solid fa-user-shield text-4xl text-[#8C5E3C] mb-2"></i>
            <h1 class="text-2xl font-serif font-bold text-[#2D1B12]">Acceso Administrador</h1>
        </div>
        <form action="/admin/login" method="POST" class="space-y-4">
            <div>
                <label class="block text-xs font-bold uppercase text-gray-600 mb-1">Clave Administrador</label>
                <input type="password" name="admin_key" required placeholder="••••••••" class="w-full border border-gray-300 rounded-lg p-2.5 text-sm focus:outline-none focus:border-[#8C5E3C]">
            </div>
            <button type="submit" class="w-full bg-[#2D1B12] text-white py-3 rounded-lg font-bold hover:bg-[#8C5E3C] transition text-xs uppercase tracking-wider">Ingresar</button>
        </form>
    </div>
"""

ADMIN_DASHBOARD_CONTENT = """
    <div class="flex justify-between items-center mb-8">
        <h1 class="text-4xl font-serif font-bold text-[#2D1B12]">Panel de Administración</h1>
        <a href="/admin/logout" class="text-xs font-bold text-red-600 hover:underline"><i class="fa-solid fa-right-from-bracket"></i> Cerrar Admin</a>
    </div>

    <div class="flex border-b border-gray-200 mb-8 gap-4">
        <a href="/admin?tab=inventario" class="pb-3 px-1 border-b-2 font-bold text-sm {% if tab == 'inventario' %}border-[#8C5E3C] text-[#8C5E3C]{% else %}border-transparent text-gray-500 hover:text-black{% endif %}">
            <i class="fa-solid fa-boxes-stacked mr-1"></i> Inventario
        </a>
        <a href="/admin?tab=compras" class="pb-3 px-1 border-b-2 font-bold text-sm {% if tab == 'compras' %}border-[#8C5E3C] text-[#8C5E3C]{% else %}border-transparent text-gray-500 hover:text-black{% endif %}">
            <i class="fa-solid fa-receipt mr-1"></i> Compras
        </a>
        <a href="/admin?tab=usuarios" class="pb-3 px-1 border-b-2 font-bold text-sm {% if tab == 'usuarios' %}border-[#8C5E3C] text-[#8C5E3C]{% else %}border-transparent text-gray-500 hover:text-black{% endif %}">
            <i class="fa-solid fa-users mr-1"></i> Usuarios Registrados
        </a>
    </div>

    {% if tab == 'inventario' %}
        {% if producto_editar %}
        <div class="mb-10 bg-[#F3EBE1] p-6 rounded-xl border-2 border-[#8C5E3C] shadow-md">
            <div class="flex justify-between items-center mb-4">
                <h2 class="font-serif font-bold text-2xl text-[#2D1B12]">
                    Modificar Stock: {{ producto_editar.nombre }}
                </h2>
                <a href="/admin" class="text-xs font-bold text-gray-500 hover:text-black uppercase">Cancelar</a>
            </div>
            
            <form action="/admin/update_stock/{{ producto_editar.id }}" method="POST" class="space-y-4">
                <div class="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-6 gap-3 mb-4">
                    {% for talle, cant in producto_editar.stock_talles.items() %}
                    <div class="bg-white p-3 rounded-lg border border-gray-300 text-center">
                        <span class="block text-xs font-extrabold uppercase text-[#8C5E3C] mb-1">Talle {{ talle }}</span>
                        <input type="number" min="0" name="stock_directo_{{ talle }}" value="{{ cant }}" class="w-full border border-gray-300 rounded p-1 text-center font-bold text-sm focus:outline-none focus:border-[#8C5E3C]">
                    </div>
                    {% endfor %}
                </div>

                <button type="submit" class="bg-[#2D1B12] hover:bg-[#8C5E3C] text-white px-6 py-2.5 rounded-lg text-sm font-bold transition">
                    Guardar Cambios
                </button>
            </form>
        </div>
        {% endif %}

        <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
            <div class="bg-white p-6 rounded-xl border border-[#EAE3DC] shadow-sm h-fit">
                <h2 class="font-serif font-bold text-xl mb-4 text-[#2D1B12]">Agregar Producto</h2>
                <form action="/admin/add" method="POST" enctype="multipart/form-data" class="space-y-4">
                    <div>
                        <label class="block text-xs font-bold uppercase text-gray-600 mb-1">Nombre</label>
                        <input type="text" name="nombre" required class="w-full border border-gray-300 rounded-lg p-2.5 text-sm focus:outline-none focus:border-[#8C5E3C]">
                    </div>
                    <div>
                        <label class="block text-xs font-bold uppercase text-gray-600 mb-1">Categoría</label>
                        <select name="categoria" class="w-full border border-gray-300 rounded-lg p-2.5 text-sm focus:outline-none focus:border-[#8C5E3C]">
                            <option value="hombre">Hombre</option>
                            <option value="mujer">Mujer</option>
                        </select>
                    </div>
                    <div>
                        <label class="block text-xs font-bold uppercase text-gray-600 mb-1">Precio ($ ARS)</label>
                        <input type="number" step="0.01" name="precio" required placeholder="Ej: 45000" class="w-full border border-gray-300 rounded-lg p-2.5 text-sm focus:outline-none focus:border-[#8C5E3C]">
                    </div>
                    <div>
                        <label class="block text-xs font-bold uppercase text-gray-600 mb-1">Stock Inicial por Talle</label>
                        <input type="text" name="stock_talles" placeholder="Ej: S:10, M:5, L:8" required class="w-full border border-gray-300 rounded-lg p-2.5 text-sm focus:outline-none focus:border-[#8C5E3C]">
                    </div>
                    <div>
                        <label class="block text-xs font-bold uppercase text-gray-600 mb-1">Descripción</label>
                        <textarea name="descripcion" rows="3" required class="w-full border border-gray-300 rounded-lg p-2.5 text-sm focus:outline-none focus:border-[#8C5E3C]"></textarea>
                    </div>
                    <div>
                        <label class="block text-xs font-bold uppercase text-gray-600 mb-1">Imagen</label>
                        <input type="file" name="imagen_file" accept="image/*" class="w-full text-xs text-gray-500 mb-2">
                        <input type="url" name="imagen_url" placeholder="O pega una URL..." class="w-full border border-gray-300 rounded-lg p-2.5 text-sm focus:outline-none focus:border-[#8C5E3C]">
                    </div>
                    <button type="submit" class="w-full bg-[#2D1B12] text-white py-3 rounded-lg font-bold hover:bg-[#8C5E3C] transition">
                        Guardar Producto
                    </button>
                </form>
            </div>

            <div class="lg:col-span-2 bg-white p-6 rounded-xl border border-[#EAE3DC] shadow-sm">
                <h2 class="font-serif font-bold text-xl mb-4 text-[#2D1B12]">Inventario Actual</h2>
                <div class="overflow-x-auto">
                    <table class="w-full text-left border-collapse">
                        <thead>
                            <tr class="border-b border-gray-200 text-xs uppercase text-gray-400">
                                <th class="pb-3">Imagen</th>
                                <th class="pb-3">Nombre</th>
                                <th class="pb-3">Stock Dispo.</th>
                                <th class="pb-3">Precio</th>
                                <th class="pb-3 text-right">Acciones</th>
                            </tr>
                        </thead>
                        <tbody class="divide-y divide-gray-100">
                            {% for p in productos %}
                            <tr>
                                <td class="py-3"><img src="{{ p.imagen }}" class="w-12 h-12 object-cover rounded-md"></td>
                                <td class="py-3 font-semibold text-sm">{{ p.nombre }}</td>
                                <td class="py-3 text-xs">
                                    <div class="flex flex-wrap gap-1">
                                    {% for talle, cant in p.stock_talles.items() %}
                                        <span class="px-2 py-0.5 rounded bg-gray-100 text-gray-800 border font-semibold">
                                            {{ talle }}: {{ cant }}
                                        </span>
                                    {% endfor %}
                                    </div>
                                </td>
                                <td class="py-3 text-sm font-bold">${{ "{:,.2f}".format(p.precio).replace(',', 'X').replace('.', ',').replace('X', '.') }}</td>
                                <td class="py-3 text-right">
                                    <a href="/admin/edit_stock/{{ p.id }}" class="text-[#8C5E3C] hover:underline text-xs font-bold mr-2">Stock</a>
                                    <a href="/admin/delete/{{ p.id }}" onclick="return confirm('¿Eliminar producto?');" class="text-red-500 hover:text-red-700 text-xs"><i class="fa-solid fa-trash"></i></a>
                                </td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>

    {% elif tab == 'compras' %}
        <div class="bg-white p-6 rounded-xl border border-[#EAE3DC] shadow-sm">
            <h2 class="font-serif font-bold text-2xl mb-6 text-[#2D1B12]">Registro de Compras</h2>
            {% if compras %}
            <div class="overflow-x-auto">
                <table class="w-full text-left border-collapse">
                    <thead>
                        <tr class="border-b border-gray-200 text-xs uppercase text-gray-400">
                            <th class="pb-3">ID</th>
                            <th class="pb-3">Cliente</th>
                            <th class="pb-3">Celular</th>
                            <th class="pb-3">Detalle</th>
                            <th class="pb-3">Total</th>
                            <th class="pb-3">Estado</th>
                            <th class="pb-3">Fecha</th>
                            <th class="pb-3 text-right">Cambiar Estado</th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-gray-100 text-sm">
                        {% for c in compras %}
                        <tr>
                            <td class="py-3 font-bold">#{{ c.id }}</td>
                            <td class="py-3">{{ c.usuario_nombre }}</td>
                            <td class="py-3">{{ c.usuario_celular }}</td>
                            <td class="py-3 text-xs text-gray-600 max-w-xs">{{ c.detalle_items }}</td>
                            <td class="py-3 font-bold text-[#8C5E3C]">${{ "{:,.2f}".format(c.total).replace(',', 'X').replace('.', ',').replace('X', '.') }}</td>
                            <td class="py-3">
                                <span class="px-2 py-1 rounded text-xs font-bold 
                                    {% if c.estado == 'Completado' %}bg-green-100 text-green-800
                                    {% elif c.estado == 'Cancelado' %}bg-red-100 text-red-800
                                    {% else %}bg-yellow-100 text-yellow-800{% endif %}">
                                    {{ c.estado }}
                                </span>
                            </td>
                            <td class="py-3 text-xs text-gray-400">{{ c.fecha }}</td>
                            <td class="py-3 text-right">
                                <form action="/admin/update_order_status/{{ c.id }}" method="POST" class="inline-flex gap-1">
                                    <select name="nuevo_estado" onchange="this.form.submit()" class="text-xs border rounded p-1">
                                        <option value="Pendiente" {% if c.estado == 'Pendiente' %}selected{% endif %}>Pendiente</option>
                                        <option value="Completado" {% if c.estado == 'Completado' %}selected{% endif %}>Completado</option>
                                        <option value="Cancelado" {% if c.estado == 'Cancelado' %}selected{% endif %}>Cancelado</option>
                                    </select>
                                </form>
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
            {% else %}
            <p class="text-gray-500 text-sm text-center py-8">No hay compras registradas aún.</p>
            {% endif %}
        </div>

    {% elif tab == 'usuarios' %}
        <div class="bg-[#ffffff] p-6 rounded-xl border border-[#EAE3DC] shadow-sm">
            <h2 class="font-serif font-bold text-2xl mb-6 text-[#2D1B12]">Usuarios Registrados</h2>
            {% if usuarios %}
            <div class="overflow-x-auto">
                <table class="w-full text-left border-collapse">
                    <thead>
                        <tr class="border-b border-gray-200 text-xs uppercase text-gray-400">
                            <th class="pb-3">ID</th>
                            <th class="pb-3">Nombre</th>
                            <th class="pb-3">Celular</th>
                            <th class="pb-3">Fecha Registro</th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-gray-100 text-sm">
                        {% for u in usuarios %}
                        <tr>
                            <td class="py-3 font-bold">#{{ u.id }}</td>
                            <td class="py-3 font-semibold">{{ u.nombre }}</td>
                            <td class="py-3">{{ u.celular }}</td>
                            <td class="py-3 text-xs text-gray-400">{{ u.fecha_registro }}</td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
            {% else %}
            <p class="text-gray-500 text-sm text-center py-8">No hay usuarios registrados.</p>
            {% endif %}
        </div>
    {% endif %}
"""

# --- RENDERIZADO DE PLANTILLAS ---

def render_page(content, **context):
    cart = session.get('cart', {})
    cart_count = sum(cart.values())
    user_logged = session.get('user', None)
    
    full_html = HTML_LAYOUT.replace('__CONTENT__', content)
    return render_template_string(full_html, cart_count=cart_count, user_logged=user_logged, **context)

# --- RUTAS PRINCIPALES ---

@app.route('/')
def index():
    cat = request.args.get('categoria', '')
    talle_filtro = request.args.get('talle', '')
    
    productos = get_all_products()
    
    # Extraer todos los talles únicos disponibles en el catálogo
    todos_talles = sorted(list(set(
        talle for p in productos for talle in p['stock_talles'].keys()
    )))

    if cat:
        productos = [p for p in productos if p['categoria'] == cat]
        
    if talle_filtro:
        productos = [p for p in productos if p['stock_talles'].get(talle_filtro, 0) > 0]

    return render_page(CATALOG_CONTENT, productos=productos, cat_actual=cat, talle_actual=talle_filtro, todos_talles=todos_talles)

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# --- RUTAS DE CARRITO ---

@app.route('/add_to_cart/<int:product_id>', methods=['POST'])
def add_to_cart(product_id):
    talle = request.form.get('talle')
    if not talle:
        return redirect(url_for('index'))

    cart = session.get('cart', {})
    item_key = f"{product_id}_{talle}"
    cart[item_key] = cart.get(item_key, 0) + 1
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
            p_id, talle = item_key.split('_')
            p_id = int(p_id)
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

    return render_page(CART_CONTENT, items=items, total=total)

@app.route('/remove_from_cart/<item_key>')
def remove_from_cart(item_key):
    cart = session.get('cart', {})
    if item_key in cart:
        del cart[item_key]
        session['cart'] = cart
    return redirect(url_for('cart_view'))

# --- FINALIZACIÓN DE COMPRA (CHECKOUT) ---

@app.route('/checkout')
def checkout():
    user = session.get('user')
    cart = session.get('cart', {})
    if not user or not cart:
        return redirect(url_for('cart_view'))

    productos_dict = {p['id']: p for p in get_all_products()}
    conn = get_db()
    cursor = conn.cursor()

    items_texto = []
    total = 0.0

    for item_key, cantidad in cart.items():
        p_id, talle = item_key.split('_')
        p_id = int(p_id)
        if p_id in productos_dict:
            p = productos_dict[p_id]
            subtotal = p['precio'] * cantidad
            total += subtotal
            items_texto.append(f"- {p['nombre']} (Talle: {talle}) x{cantidad} = ${subtotal:,.2f}")

            # Descontar stock
            stock_dict = p['stock_talles']
            if talle in stock_dict:
                stock_dict[talle] = max(0, stock_dict[talle] - cantidad)
                nuevo_stock_str = dict_to_stock_str(stock_dict)
                cursor.execute("UPDATE productos SET stock_talles = ? WHERE id = ?", (nuevo_stock_str, p_id))

    detalle_str = "\n".join(items_texto)
    cursor.execute('''
        INSERT INTO compras (usuario_nombre, usuario_celular, detalle_items, total, estado)
        VALUES (?, ?, ?, ?, 'Pendiente')
    ''', (user['nombre'], user['celular'], detalle_str, total))

    conn.commit()
    conn.close()

    # Vaciar carrito
    session['cart'] = {}

    # Generar mensaje de WhatsApp
    mensaje = f"¡Hola Louisiana Clothes! Mi nombre es {user['nombre']}.\nQuiero confirmar el siguiente pedido:\n\n{detalle_str}\n\nTotal: ${total:,.2f}"
    url_whatsapp = f"https://wa.me/{NUMERO_WHATSAPP_TIENDA}?text={urllib.parse.quote(mensaje)}"

    return redirect(url_whatsapp)

# --- AUTENTICACIÓN DE USUARIOS ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        celular = request.form.get('celular', '').strip()
        password = request.form.get('password', '').strip()

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM usuarios WHERE celular = ? AND password_hash = ?", (celular, password))
        usuario = cursor.fetchone()
        conn.close()

        if usuario:
            session['user'] = {'id': usuario['id'], 'nombre': usuario['nombre'], 'celular': usuario['celular']}
            return redirect(url_for('index'))
        
        return render_page(LOGIN_CONTENT, error="Celular o contraseña incorrectos.")

    return render_page(LOGIN_CONTENT)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        celular = request.form.get('celular', '').strip()
        password = request.form.get('password', '').strip()

        conn = get_db()
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT INTO usuarios (nombre, celular, password_hash) VALUES (?, ?, ?)",
                           (nombre, celular, password))
            conn.commit()
            conn.close()

            # Iniciar sesión automáticamente tras el registro
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            conn.close()
            return render_page(REGISTER_CONTENT, error="El número de celular ya está registrado.")

    return render_page(REGISTER_CONTENT)

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('index'))

# --- PANEL DE ADMINISTRACIÓN ---

@app.route('/admin')
def admin_dashboard():
    if not session.get('is_admin'):
        return render_page(ADMIN_LOGIN_CONTENT)

    tab = request.args.get('tab', 'inventario')
    conn = get_db()
    cursor = conn.cursor()

    productos = get_all_products()
    
    cursor.execute("SELECT * FROM compras ORDER BY fecha DESC")
    compras = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT id, nombre, celular, fecha_registro FROM usuarios ORDER BY fecha_registro DESC")
    usuarios = [dict(r) for r in cursor.fetchall()]

    conn.close()

    return render_page(
        ADMIN_DASHBOARD_CONTENT,
        tab=tab,
        productos=productos,
        compras=compras,
        usuarios=usuarios,
        producto_editar=None
    )

@app.route('/admin/login', methods=['POST'])
def admin_login():
    key = request.form.get('admin_key', '')
    if key == ADMIN_PASSWORD:
        session['is_admin'] = True
        return redirect(url_for('admin_dashboard'))
    return render_page(ADMIN_LOGIN_CONTENT, error="Clave de administrador incorrecta.")

@app.route('/admin/logout')
def admin_logout():
    session.pop('is_admin', None)
    return redirect(url_for('index'))

@app.route('/admin/add', methods=['POST'])
def admin_add_product():
    if not session.get('is_admin'):
        return redirect(url_for('admin_dashboard'))

    nombre = request.form.get('nombre')
    categoria = request.form.get('categoria')
    precio = float(request.form.get('precio', 0))
    stock_talles = request.form.get('stock_talles')
    descripcion = request.form.get('descripcion')
    imagen_url = request.form.get('imagen_url')

    file = request.files.get('imagen_file')
    if file and file.filename != '' and allowed_file(file.filename):
        filename = file.filename
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        imagen = f"/uploads/{filename}"
    else:
        imagen = imagen_url if imagen_url else "https://via.placeholder.com/800"

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO productos (nombre, categoria, precio, stock_talles, descripcion, imagen)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (nombre, categoria, precio, stock_talles, descripcion, imagen))
    conn.commit()
    conn.close()

    return redirect(url_for('admin_dashboard'))

@app.route('/admin/edit_stock/<int:product_id>')
def admin_edit_stock(product_id):
    if not session.get('is_admin'):
        return redirect(url_for('admin_dashboard'))

    productos = get_all_products()
    producto_editar = next((p for p in productos if p['id'] == product_id), None)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM compras ORDER BY fecha DESC")
    compras = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT id, nombre, celular, fecha_registro FROM usuarios ORDER BY fecha_registro DESC")
    usuarios = [dict(r) for r in cursor.fetchall()]
    conn.close()

    return render_page(
        ADMIN_DASHBOARD_CONTENT,
        tab='inventario',
        productos=productos,
        compras=compras,
        usuarios=usuarios,
        producto_editar=producto_editar
    )

@app.route('/admin/update_stock/<int:product_id>', methods=['POST'])
def admin_update_stock(product_id):
    if not session.get('is_admin'):
        return redirect(url_for('admin_dashboard'))

    productos = get_all_products()
    producto = next((p for p in productos if p['id'] == product_id), None)

    if producto:
        nuevo_stock = {}
        for talle in producto['stock_talles'].keys():
            campo = f"stock_directo_{talle}"
            if campo in request.form:
                try:
                    nuevo_stock[talle] = max(0, int(request.form[campo]))
                except ValueError:
                    nuevo_stock[talle] = producto['stock_talles'][talle]

        stock_str = dict_to_stock_str(nuevo_stock)

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("UPDATE productos SET stock_talles = ? WHERE id = ?", (stock_str, product_id))
        conn.commit()
        conn.close()

    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete/<int:product_id>')
def admin_delete_product(product_id):
    if not session.get('is_admin'):
        return redirect(url_for('admin_dashboard'))

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM productos WHERE id = ?", (product_id,))
    conn.commit()
    conn.close()

    return redirect(url_for('admin_dashboard'))

@app.route('/admin/update_order_status/<int:order_id>', methods=['POST'])
def admin_update_order_status(order_id):
    if not session.get('is_admin'):
        return redirect(url_for('admin_dashboard'))

    nuevo_estado = request.form.get('nuevo_estado')
    if nuevo_estado:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("UPDATE compras SET estado = ? WHERE id = ?", (nuevo_estado, order_id))
        conn.commit()
        conn.close()

    return redirect(url_for('admin_dashboard', tab='compras'))

if __name__ == '__main__':
    app.run(debug=True)
