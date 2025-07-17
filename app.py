from flask import Flask, render_template, request, redirect, url_for
import sqlite3
import os

app = Flask(__name__)
DB_NAME = "school.db"

# --- DB初期化関数（classesとattendance） ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS classes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            day TEXT NOT NULL,
            period TEXT NOT NULL,
            room TEXT NOT NULL
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
        submitted INTEGER,
        note TEXT,
        FOREIGN KEY(class_id) REFERENCES classes(id)
        )
    ''')
    
    try:
        c.execute("ALTER TABLE assignments ADD COLUMN note TEXT")
    except sqlite3.OperationalError:
        # すでに note カラムがある場合は無視
        pass
    
    
    conn.commit()
    conn.close()

init_db()

from datetime import datetime

@app.route('/')
def index():
    days = ['月曜日', '火曜日', '水曜日', '木曜日', '金曜日']
    periods = ['1', '2', '3', '4', '5', '6']
    timetable = {day: {p: None for p in periods} for day in days}

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    c.execute("SELECT * FROM classes")
    classes = c.fetchall()

    for cls in classes:
        class_id, name, day, period, room = cls

        # 未提出課題数
        c.execute("SELECT COUNT(*) FROM assignments WHERE class_id=? AND submitted=0", (class_id,))
        unsubmitted_count = c.fetchone()[0]

        # 締切超過の未提出課題があるか
        c.execute("SELECT deadline FROM assignments WHERE class_id=? AND submitted=0", (class_id,))
        overdue = False
        today = datetime.today().date()
        for (deadline,) in c.fetchall():
            try:
                if datetime.strptime(deadline, "%Y-%m-%d").date() < today:
                    overdue = True
                    break
            except ValueError:
                continue  # 万一不正な日付が入っていた場合は無視

        timetable[day][period] = {
            'id': class_id,
            'name': name,
            'room': room,
            'unsubmitted': unsubmitted_count,
            'overdue': overdue
        }

    conn.close()
    return render_template('index.html', timetable=timetable, days=days, periods=periods)

@app.route('/add_class', methods=['GET', 'POST'])
def add_class():
    if request.method == 'POST':
        name = request.form['name']
        day = request.form['day']
        period = request.form['period']
        room = request.form['room']
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("INSERT INTO classes (name, day, period, room) VALUES (?, ?, ?, ?)", (name, day, period, room))
        conn.commit()
        conn.close()
        return redirect('/')
    return render_template('add_class.html')

@app.route('/edit_class/<int:class_id>', methods=['GET', 'POST'])
def edit_class(class_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    if request.method == 'POST':
        name = request.form['name']
        day = request.form['day']
        period = request.form['period']
        room = request.form['room']

        c.execute('UPDATE classes SET name=?, day=?, period=?, room=? WHERE id=?',
                  (name, day, period, room, class_id))
        conn.commit()
        conn.close()
        return redirect(url_for('index'))

    # GETのとき：授業データを取得してフォーム表示
    c.execute("SELECT name, day, period, room FROM classes WHERE id=?", (class_id,))
    class_data = c.fetchone()
    conn.close()

    if class_data:
        name, day, period, room = class_data
        return render_template('edit_class.html', class_id=class_id, name=name, day=day, period=period, room=room)
    else:
        return "授業が見つかりません", 404

@app.route('/delete_class/<int:class_id>', methods=['POST'])
def delete_class(class_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    # 関連データも削除
    c.execute("DELETE FROM attendance WHERE class_id=?", (class_id,))
    c.execute("DELETE FROM evaluation WHERE class_id=?", (class_id,))
    c.execute("DELETE FROM assignments WHERE class_id=?", (class_id,))
    c.execute("DELETE FROM classes WHERE id=?", (class_id,))
    
    conn.commit()
    conn.close()

    return redirect(url_for('index'))


@app.route('/class/<int:class_id>/attendance', methods=['GET', 'POST'])
def view_attendance(class_id):
    order = request.args.get('order', 'desc')  # デフォルトは降順

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    if request.method == 'POST':
        date = request.form['date']
        status = request.form['status']
        c.execute("INSERT INTO attendance (class_id, date, status) VALUES (?, ?, ?)",
                  (class_id, date, status))
        conn.commit()

    # 授業名を取得
    c.execute("SELECT name FROM classes WHERE id=?", (class_id,))
    class_name = c.fetchone()[0]

    # 出席記録を取得（orderによって切替）
    if order == 'asc':
        c.execute("SELECT date, status FROM attendance WHERE class_id=? ORDER BY date ASC", (class_id,))
    else:
        c.execute("SELECT date, status FROM attendance WHERE class_id=? ORDER BY date DESC", (class_id,))
    attendance = c.fetchall()

    # 出席ステータスの集計
    status_counts = {"出席": 0, "欠席": 0, "遅刻": 0}
    for _, status in attendance:
        if status in status_counts:
            status_counts[status] += 1

    conn.close()

    return render_template(
        'attendance.html',
        class_name=class_name,
        attendance=attendance,
        class_id=class_id,
        order=order,
        status_counts=status_counts  # ← 忘れずに渡す
    )



@app.route('/class/<int:class_id>/evaluation', methods=['GET', 'POST'])
def evaluation(class_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    if request.method == 'POST':
        method = request.form.get('method')
        percentage = request.form.get('percentage')

        if not method or not percentage:
            return "すべての項目を入力してください", 400

        try:
            percentage = int(percentage)
        except ValueError:
            return "割合は数値で入力してください", 400

        c.execute("INSERT INTO evaluation (class_id, method, percentage) VALUES (?, ?, ?)",
                  (class_id, method, percentage))
        conn.commit()

    # 授業名取得
    c.execute("SELECT name FROM classes WHERE id=?", (class_id,))
    class_name = c.fetchone()[0]

    # 評価方式一覧取得
    c.execute("SELECT method, percentage, id FROM evaluation WHERE class_id=?", (class_id,))
    evaluations = c.fetchall()
    conn.close()

    return render_template('evaluation.html', class_name=class_name, evaluations=evaluations, class_id=class_id)




@app.route('/class/<int:class_id>/evaluation/delete/<int:eval_id>', methods=['POST'])
def delete_evaluation(class_id, eval_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("DELETE FROM evaluation WHERE id=?", (eval_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('evaluation', class_id=class_id))

@app.route('/class/<int:class_id>/assignments', methods=['GET', 'POST'])
def assignments(class_id):
    mode = request.args.get('mode', 'unsubmitted')  # デフォルトは未提出のみ

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    if request.method == 'POST':
        title = request.form.get('title')
        deadline = request.form.get('deadline')
        note = request.form.get('note', '')
        c.execute("INSERT INTO assignments (class_id, title, deadline, note) VALUES (?, ?, ?, ?)",
                  (class_id, title, deadline, note))
        conn.commit()

    # 授業名取得
    c.execute("SELECT name FROM classes WHERE id=?", (class_id,))
    class_name = c.fetchone()[0]

    if mode == 'unsubmitted':
        c.execute("""
            SELECT id, title, deadline, submitted, note 
            FROM assignments 
            WHERE class_id=? AND submitted=0
            ORDER BY deadline ASC
        """, (class_id,))
    else:  # all
        c.execute("""
            SELECT id, title, deadline, submitted, note 
            FROM assignments 
            WHERE class_id=?
            ORDER BY id ASC
        """, (class_id,))

    assignments = c.fetchall()
    conn.close()

    return render_template('assignments.html', class_name=class_name, assignments=assignments, class_id=class_id, mode=mode)



@app.route('/class/<int:class_id>/assignments/toggle/<int:assignment_id>', methods=['POST'])
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
def delete_assignment(class_id, assignment_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("DELETE FROM assignments WHERE id=?", (assignment_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('assignments', class_id=class_id))


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))  # Renderの環境変数PORTを取得
    app.run(host='0.0.0.0', port=port, debug=True)
