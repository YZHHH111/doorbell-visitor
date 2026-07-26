import os
import sqlite3
import base64
import hashlib
from datetime import datetime, timezone, timedelta
from flask import Flask, render_template, request, jsonify, redirect, session, send_file
from io import BytesIO
import qrcode

app = Flask(__name__)
app.secret_key = os.urandom(24).hex()
DB_PATH = os.environ.get('DB_PATH', os.path.join(os.path.dirname(__file__), 'visitors.db'))
ADMIN_PASSWORD = "wq123456"
MAX_PHOTO_SIZE = 2 * 1024 * 1024
BJ_TZ = timezone(timedelta(hours=8))


def bj_now():
    return datetime.now(BJ_TZ).strftime('%Y-%m-%d %H:%M:%S')


def bj_today():
    return datetime.now(BJ_TZ).strftime('%Y-%m-%d')


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute('''CREATE TABLE IF NOT EXISTS visitors
                    (id INTEGER PRIMARY KEY AUTOINCREMENT,
                     name TEXT NOT NULL,
                     reason TEXT DEFAULT '',
                     phone TEXT DEFAULT '',
                     photo TEXT DEFAULT '',
                     created_at TEXT NOT NULL)''')
    try:
        conn.execute("ALTER TABLE visitors ADD COLUMN photo TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE visitors ADD COLUMN temperature REAL DEFAULT NULL")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE visitors ADD COLUMN humidity REAL DEFAULT NULL")
    except sqlite3.OperationalError:
        pass
    conn.execute('''CREATE TABLE IF NOT EXISTS sensor_log
                    (id INTEGER PRIMARY KEY AUTOINCREMENT,
                     temperature REAL,
                     humidity REAL,
                     created_at TEXT NOT NULL)''')
    conn.commit()
    conn.close()


init_db()


@app.route('/')
def index():
    return redirect('/visit')


@app.route('/visit')
def visitor_form():
    return render_template('visitor_form.html')


@app.route('/api/visitor/submit', methods=['POST'])
def visitor_submit():
    name = request.form.get('name', '').strip()
    reason = request.form.get('reason', '').strip()
    phone = request.form.get('phone', '').strip()
    if not name:
        return jsonify({'error': '请填写姓名'}), 400
    photo = ''
    if 'photo' in request.files:
        f = request.files['photo']
        if f and f.filename:
            data = f.read()
            if len(data) <= MAX_PHOTO_SIZE:
                photo = 'data:' + (f.content_type or 'image/jpeg') + ';base64,' + base64.b64encode(data).decode()
    conn = get_db()
    cur = conn.execute("INSERT INTO visitors (name, reason, phone, photo, created_at) VALUES (?, ?, ?, ?, ?)",
                       (name, reason, phone, photo, bj_now()))
    new_id = cur.lastrowid
    conn.commit()
    conn.close()
    return jsonify({'status': 'ok', 'message': f'{name}，登记成功！', 'id': new_id})


@app.route('/api/visitor/camera', methods=['POST'])
def visitor_camera():
    auth = request.headers.get('Authorization', '')
    token = hashlib.sha256(b'wq123456').hexdigest()
    if auth != f'Bearer {token}':
        return jsonify({'error': 'unauthorized'}), 401
    data = request.get_json()
    if not data or not data.get('name'):
        return jsonify({'error': 'name required'}), 400
    temperature = data.get('temperature')
    humidity = data.get('humidity')
    if temperature is not None:
        try: temperature = float(temperature)
        except: temperature = None
    if humidity is not None:
        try: humidity = float(humidity)
        except: humidity = None
    conn = get_db()
    conn.execute("INSERT INTO visitors (name, reason, photo, created_at, temperature, humidity) VALUES (?, ?, ?, ?, ?, ?)",
                 (data['name'], '摄像头识别', '', bj_now(), temperature, humidity))
    conn.commit()
    conn.close()
    return jsonify({'status': 'ok'})


@app.route('/api/visitor/latest')
def visitor_latest():
    after_id = request.args.get('after_id', '0')
    conn = get_db()
    rows = conn.execute("SELECT * FROM visitors WHERE id > ? ORDER BY id ASC", (after_id,)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/visitor/list')
def visitor_list():
    conn = get_db()
    rows = conn.execute("SELECT * FROM visitors ORDER BY created_at DESC LIMIT 200").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route('/admin', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        password = request.form.get('password', '')
        if password == ADMIN_PASSWORD:
            session['admin'] = True
            return redirect('/admin/dashboard')
        return render_template('admin_login.html', error='密码错误')
    return render_template('admin_login.html')


@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('admin'):
        return redirect('/admin')
    conn = get_db()
    rows = conn.execute("SELECT * FROM visitors ORDER BY created_at DESC LIMIT 200").fetchall()
    total = conn.execute("SELECT COUNT(*) as c FROM visitors").fetchone()['c']
    today = conn.execute("SELECT COUNT(*) as c FROM visitors WHERE created_at >= ?", (bj_today(),)).fetchone()['c']
    conn.close()
    return render_template('admin_dashboard.html', visitors=[dict(r) for r in rows], total=total, today=today)


@app.route('/admin/logout')
def admin_logout():
    session.pop('admin', None)
    return redirect('/admin')

@app.route('/admin/camera')
def admin_camera():
    if not session.get('admin'):
        return redirect('/admin')
    return render_template('admin_camera.html')


@app.route('/qrcode')
def qrcode_page():
    return render_template('qrcode.html', base_url=request.host_url.rstrip('/'))


@app.route('/api/qrcode.png')
def qrcode_png():
    url = request.host_url.rstrip('/') + '/visit'
    img = qrcode.make(url)
    buf = BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return send_file(buf, mimetype='image/png')


@app.route('/api/sensor/upload', methods=['POST'])
def sensor_upload():
    auth = request.headers.get('Authorization', '')
    token = hashlib.sha256(b'wq123456').hexdigest()
    if auth != f'Bearer {token}':
        return jsonify({'error': 'unauthorized'}), 401
    data = request.get_json()
    if not data:
        return jsonify({'error': 'no data'}), 400
    temperature = data.get('temperature')
    humidity = data.get('humidity')
    if temperature is not None:
        try: temperature = float(temperature)
        except: temperature = None
    if humidity is not None:
        try: humidity = float(humidity)
        except: humidity = None
    conn = get_db()
    conn.execute("INSERT INTO sensor_log (temperature, humidity, created_at) VALUES (?, ?, ?)",
                 (temperature, humidity, bj_now()))
    conn.commit()
    conn.close()
    return jsonify({'status': 'ok'})


@app.route('/api/sensor/history')
def sensor_history():
    if not session.get('admin'):
        return jsonify({'error': 'unauthorized'}), 403
    conn = get_db()
    rows = conn.execute("""
        SELECT created_at, temperature, humidity FROM sensor_log
        ORDER BY created_at ASC LIMIT 500
    """).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/stats')
def stats():
    if not session.get('admin'):
        return jsonify({'error': 'unauthorized'}), 403
    conn = get_db()
    daily = conn.execute("""
        SELECT date(created_at) as day, COUNT(*) as count
        FROM visitors
        GROUP BY date(created_at)
        ORDER BY day DESC LIMIT 14
    """).fetchall()
    top = conn.execute("""
        SELECT name, COUNT(*) as count
        FROM visitors
        GROUP BY name
        ORDER BY count DESC LIMIT 10
    """).fetchall()
    conn.close()
    return jsonify({
        'daily': [dict(r) for r in daily],
        'top': [dict(r) for r in top]
    })


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
