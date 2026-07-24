import os
import sqlite3
import hashlib
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, session, send_file
from io import BytesIO
import qrcode

app = Flask(__name__)
app.secret_key = os.urandom(24).hex()
DB_PATH = os.path.join(os.path.dirname(__file__), 'visitors.db')
ADMIN_PASSWORD = "wq123456"


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
    conn = get_db()
    conn.execute("INSERT INTO visitors (name, reason, phone, created_at) VALUES (?, ?, ?, ?)",
                 (name, reason, phone, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    conn.commit()
    conn.close()
    return jsonify({'status': 'ok', 'message': f'{name}，登记成功！'})


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
    today = conn.execute("SELECT COUNT(*) as c FROM visitors WHERE date(created_at) = date('now')").fetchone()['c']
    conn.close()
    return render_template('admin_dashboard.html', visitors=[dict(r) for r in rows], total=total, today=today)


@app.route('/admin/logout')
def admin_logout():
    session.pop('admin', None)
    return redirect('/admin')


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
