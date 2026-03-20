from flask import Flask, request, redirect, session, render_template_string, send_file
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
import pandas as pd
from datetime import datetime
import os

app = Flask(__name__)
app.secret_key = "secret123"

# ===== DB =====
def get_db():
    return sqlite3.connect("hotel.db")

def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        username TEXT,
        password TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS rooms (
        id INTEGER PRIMARY KEY,
        room_number TEXT,
        status TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS bookings (
        id INTEGER PRIMARY KEY,
        room_number TEXT,
        checkin TEXT,
        checkout TEXT,
        status TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY,
        room_number TEXT,
        amount REAL,
        paid_time TEXT
    )""")

    # tạo admin
    c.execute("SELECT * FROM users WHERE username='admin'")
    if not c.fetchone():
        c.execute("INSERT INTO users VALUES (NULL, ?, ?)",
                  ("admin", generate_password_hash("123456")))

    conn.commit()
    conn.close()

init_db()

# ===== AUTH =====
def login_required(f):
    def wrap(*args, **kwargs):
        if "user" not in session:
            return redirect("/login")
        return f(*args, **kwargs)
    return wrap

# ===== LOGIN =====
@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        u = request.form["username"]
        p = request.form["password"]

        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username=?", (u,))
        user = c.fetchone()
        conn.close()

        if user and check_password_hash(user[2], p):
            session["user"] = u
            return redirect("/")
        return "Sai tài khoản!"

    return """
    <h2>Login</h2>
    <form method="post">
    <input name="username"><br>
    <input type="password" name="password"><br>
    <button>Login</button>
    </form>
    """

# ===== DASHBOARD =====
@app.route("/")
@login_required
def dashboard():
    conn = get_db()
    df = pd.read_sql_query("""
    SELECT DATE(paid_time) as d, SUM(amount) as total
    FROM payments GROUP BY d
    """, conn)
    conn.close()

    labels = df["d"].tolist() if not df.empty else []
    values = df["total"].tolist() if not df.empty else []

    return render_template_string("""
    <h2>🏨 Dashboard</h2>
    <a href="/rooms">Phòng</a> |
    <a href="/checkin">Check-in</a> |
    <a href="/checkout">Check-out</a> |
    <a href="/export">Excel</a> |
    <a href="/logout">Logout</a>

    <canvas id="c"></canvas>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script>
    new Chart(document.getElementById('c'), {
        type:'line',
        data:{labels:{{l|safe}}, datasets:[{data:{{v|safe}}}]}
    })
    </script>
    """, l=labels, v=values)

# ===== ROOMS =====
@app.route("/rooms", methods=["GET","POST"])
@login_required
def rooms():
    conn = get_db()
    c = conn.cursor()

    if request.method == "POST":
        c.execute("INSERT INTO rooms VALUES (NULL, ?, 'empty')",
                  (request.form["room"],))
        conn.commit()

    rooms = c.execute("SELECT * FROM rooms").fetchall()
    conn.close()

    html = "<h2>Phòng</h2><form method='post'><input name='room'><button>Thêm</button></form><ul>"
    for r in rooms:
        color = {"empty":"green","occupied":"red","cleaning":"orange"}[r[2]]
        html += f"<li style='color:{color}'>Phòng {r[1]} - {r[2]}</li>"
    html += "</ul><a href='/'>Back</a>"

    return html

# ===== CHECKIN =====
@app.route("/checkin", methods=["GET","POST"])
@login_required
def checkin():
    if request.method == "POST":
        room = request.form["room"]
        checkout = request.form["checkout"]

        conn = get_db()
        c = conn.cursor()

        c.execute("INSERT INTO bookings VALUES(NULL,?,?,?,?)",
                  (room, str(datetime.now()), checkout, "staying"))

        c.execute("UPDATE rooms SET status='occupied' WHERE room_number=?", (room,))

        conn.commit()
        conn.close()

        return redirect("/")

    return """
    <h2>Check-in</h2>
    <form method="post">
    Phòng:<input name="room"><br>
    Ngày checkout:<input name="checkout"><br>
    <button>OK</button>
    </form>
    """

# ===== CHECKOUT =====
@app.route("/checkout", methods=["GET","POST"])
@login_required
def checkout():
    conn = get_db()
    c = conn.cursor()

    if request.method == "POST":
        room = request.form["room"]

        booking = c.execute("""
        SELECT * FROM bookings WHERE room_number=? AND status='staying'
        """,(room,)).fetchone()

        if booking:
            checkin = datetime.fromisoformat(booking[2])
            now = datetime.now()

            days = max(1, (now.date()-checkin.date()).days)
            amount = days * 200000

            c.execute("INSERT INTO payments VALUES(NULL,?,?,?)",
                      (room, amount, str(now)))

            c.execute("UPDATE bookings SET status='done' WHERE id=?", (booking[0],))
            c.execute("UPDATE rooms SET status='cleaning' WHERE room_number=?", (room,))

            conn.commit()

        conn.close()
        return redirect("/")

    rooms = c.execute("SELECT room_number FROM rooms WHERE status='occupied'").fetchall()
    conn.close()

    html = "<h2>Check-out</h2><form method='post'>"
    for r in rooms:
        html += f"<button name='room' value='{r[0]}'>Phòng {r[0]}</button><br>"
    html += "</form>"

    return html

# ===== EXPORT =====
@app.route("/export")
@login_required
def export():
    conn = get_db()
    df = pd.read_sql_query("SELECT * FROM payments", conn)
    conn.close()

    file = "report.xlsx"
    df.to_excel(file, index=False)
    return send_file(file, as_attachment=True)

# ===== LOGOUT =====
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# ===== RUN =====
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
