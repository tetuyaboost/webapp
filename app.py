from flask import Flask, render_template, request, redirect, url_for
from flask_login import LoginManager, login_user, login_required, logout_user, current_user, UserMixin
import sqlite3
import os
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash


app = Flask(__name__)
app.secret_key = 'your_secret_key'  # セッション保護に必要

DB_NAME = "school.db"

# --- Flask-Login 初期化 ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# --- Userクラス（Flask-Login用） ---
class User(UserMixin):
    def __init__(self, id):
        self.id = id

@login_manager.user_loader
def load_user(user_id):
    return User(user_id)

# --- DB初期化 ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS classes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            day TEXT NOT NULL,
            period TEXT NOT NULL,
            room TEXT NOT NULL,
            user_id INTEGER NOT NULL
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            class_id INTEGER,
            date TEXT,
            status TEXT,
            FOREIGN KEY(class_id) REFERENCES classes(id)
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS evaluation (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            class_id INTEGER,
            method TEXT,
            percentage INTEGER,
            FOREIGN KEY(class_id) REFERENCES classes(id)
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            class_id INTEGER,
            title TEXT,
            deadline TEXT,
            submitted INTEGER DEFAULT 0,
            note TEXT,
            FOREIGN KEY(class_id) REFERENCES classes(id)
        )
    ''')

    conn.commit()
    conn.close()

init_db()

# --- ルート（時間割） ---
@app.route('/')
@login_required
def index():
    days = ['月曜日', '火曜日', '水曜日', '木曜日', '金曜日']
    periods = ['1', '2', '3', '4', '5', '6']
    timetable = {day: {p: None for p in periods} for day in days}

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT id, name, day, period, room FROM classes WHERE user_id=?", (current_user.id,))
    classes = c.fetchall()

    for class_id, name, day, period, room in classes:
        c.execute("SELECT COUNT(*) FROM assignments WHERE class_id=? AND submitted=0", (class_id,))
        unsubmitted_count = c.fetchone()[0]

        c.execute("SELECT deadline FROM assignments WHERE class_id=? AND submitted=0", (class_id,))
        overdue = any(datetime.strptime(d, "%Y-%m-%d").date() < datetime.today().date()
                      for (d,) in c.fetchall() if d)

        timetable[day][period] = {
            'id': class_id,
            'name': name,
            'room': room,
            'unsubmitted': unsubmitted_count,
            'overdue': overdue
        }

    conn.close()
    return render_template('index.html', timetable=timetable, days=days, periods=periods)

# --- ログイン・ログアウト・登録 ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("SELECT id, password FROM users WHERE username=?", (username,))
        user = c.fetchone()
        conn.close()

        if not user or not check_password_hash(user[1], password):
            error = "ユーザー名またはパスワードが正しくありません"
        else:
            login_user(User(user[0]))
            return redirect(url_for('index'))
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        hashed_pw = generate_password_hash(password)

        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        try:
            c.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hashed_pw))
            conn.commit()
            conn.close()
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            error = "そのユーザー名は既に使われています"
            conn.close()
    return render_template('register.html', error=error)

# --- 授業追加・編集・削除 ---
@app.route('/add_class', methods=['GET', 'POST'])
@login_required
def add_class():
    if request.method == 'POST':
        name = request.form['name']
        day = request.form['day']
        period = request.form['period']
        room = request.form['room']
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("INSERT INTO classes (name, day, period, room, user_id) VALUES (?, ?, ?, ?, ?)",
                  (name, day, period, room, current_user.id))
        conn.commit()
        conn.close()
        return redirect('/')
    return render_template('add_class.html')

@app.route('/edit_class/<int:class_id>', methods=['GET', 'POST'])
@login_required
def edit_class(class_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    if request.method == 'POST':
        name = request.form['name']
        day = request.form['day']
        period = request.form['period']
        room = request.form['room']
        c.execute("UPDATE classes SET name=?, day=?, period=?, room=? WHERE id=? AND user_id=?",
                  (name, day, period, room, class_id, current_user.id))
        conn.commit()
        conn.close()
        return redirect('/')
    c.execute("SELECT name, day, period, room FROM classes WHERE id=? AND user_id=?", (class_id, current_user.id))
    class_data = c.fetchone()
    conn.close()
    if class_data:
        return render_template('edit_class.html', class_id=class_id, name=class_data[0],
                               day=class_data[1], period=class_data[2], room=class_data[3])
    return "見つかりません", 404

@app.route('/delete_class/<int:class_id>', methods=['POST'])
@login_required
def delete_class(class_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("DELETE FROM attendance WHERE class_id=?", (class_id,))
    c.execute("DELETE FROM evaluation WHERE class_id=?", (class_id,))
    c.execute("DELETE FROM assignments WHERE class_id=?", (class_id,))
    c.execute("DELETE FROM classes WHERE id=? AND user_id=?", (class_id, current_user.id))
    conn.commit()
    conn.close()
    return redirect('/')

# --- 出席機能 ---
@app.route('/class/<int:class_id>/attendance', methods=['GET', 'POST'])
@login_required
def view_attendance(class_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    if request.method == 'POST':
        date = request.form['date']
        status = request.form['status']
        c.execute("INSERT INTO attendance (class_id, date, status) VALUES (?, ?, ?)", (class_id, date, status))
        conn.commit()

    c.execute("SELECT name FROM classes WHERE id=? AND user_id=?", (class_id, current_user.id))
    class_data = c.fetchone()
    if not class_data:
        return "授業が見つかりません", 404

    c.execute("SELECT date, status FROM attendance WHERE class_id=? ORDER BY date DESC", (class_id,))
    attendance = c.fetchall()

    status_counts = {"出席": 0, "欠席": 0, "遅刻": 0}
    for _, status in attendance:
        if status in status_counts:
            status_counts[status] += 1

    conn.close()
    return render_template('attendance.html', class_name=class_data[0],
                           attendance=attendance, class_id=class_id, status_counts=status_counts)

# --- 評価機能 ---
@app.route('/class/<int:class_id>/evaluation', methods=['GET', 'POST'])
@login_required
def evaluation(class_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    if request.method == 'POST':
        method = request.form.get('method')
        percentage = request.form.get('percentage')
        c.execute("INSERT INTO evaluation (class_id, method, percentage) VALUES (?, ?, ?)",
                  (class_id, method, int(percentage)))
        conn.commit()

    c.execute("SELECT name FROM classes WHERE id=? AND user_id=?", (class_id, current_user.id))
    class_name = c.fetchone()[0]

    c.execute("SELECT method, percentage, id FROM evaluation WHERE class_id=?", (class_id,))
    evaluations = c.fetchall()
    conn.close()
    return render_template('evaluation.html', class_name=class_name,
                           evaluations=evaluations, class_id=class_id)

@app.route('/class/<int:class_id>/evaluation/delete/<int:eval_id>', methods=['POST'])
@login_required
def delete_evaluation(class_id, eval_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("DELETE FROM evaluation WHERE id=?", (eval_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('evaluation', class_id=class_id))

# --- 課題管理 ---
@app.route('/class/<int:class_id>/assignments', methods=['GET', 'POST'])
@login_required
def assignments(class_id):
    mode = request.args.get('mode', 'unsubmitted')
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    if request.method == 'POST':
        title = request.form['title']
        deadline = request.form['deadline']
        note = request.form.get('note', '')
        c.execute("INSERT INTO assignments (class_id, title, deadline, note) VALUES (?, ?, ?, ?)",
                  (class_id, title, deadline, note))
        conn.commit()

    c.execute("SELECT name FROM classes WHERE id=? AND user_id=?", (class_id, current_user.id))
    class_name = c.fetchone()[0]

    if mode == 'unsubmitted':
        c.execute("SELECT id, title, deadline, submitted, note FROM assignments WHERE class_id=? AND submitted=0 ORDER BY deadline ASC", (class_id,))
    else:
        c.execute("SELECT id, title, deadline, submitted, note FROM assignments WHERE class_id=? ORDER BY id ASC", (class_id,))
    assignments = c.fetchall()
    conn.close()
    return render_template('assignments.html', class_name=class_name, assignments=assignments,
                           class_id=class_id, mode=mode)

@app.route('/class/<int:class_id>/assignments/toggle/<int:assignment_id>', methods=['POST'])
@login_required
def toggle_submission(class_id, assignment_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT submitted FROM assignments WHERE id=?", (assignment_id,))
    current = c.fetchone()[0]
    new_status = 0 if current else 1
    c.execute("UPDATE assignments SET submitted=? WHERE id=?", (new_status, assignment_id))
    conn.commit()
    conn.close()
    return redirect(url_for('assignments', class_id=class_id))

@app.route('/class/<int:class_id>/assignments/delete/<int:assignment_id>', methods=['POST'])
@login_required
def delete_assignment(class_id, assignment_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("DELETE FROM assignments WHERE id=?", (assignment_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('assignments', class_id=class_id))

# --- アプリ起動 ---
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
