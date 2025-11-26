import sqlite3
from flask import Flask, render_template, request, redirect, url_for, jsonify, send_file
import csv
import io
from datetime import datetime

app = Flask(__name__, template_folder="templates")

DB_FILE = "expenses.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS expenses(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT,
        category TEXT,
        amount REAL,
        payment_method TEXT,
        note TEXT
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS budgets(
        month TEXT PRIMARY KEY,
        income REAL
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS category_budgets(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        month TEXT,
        category TEXT,
        amount REAL,
        UNIQUE(month, category)
    )""")
    conn.commit()
    conn.close()

def get_month():
    return request.args.get("month") or datetime.now().strftime("%Y-%m")

@app.route("/")
def index():
    return redirect(url_for("dashboard"))

@app.route("/dashboard")
def dashboard():
    month = get_month()
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    cur.execute("SELECT SUM(amount) FROM expenses WHERE substr(date,1,7)=?", (month,))
    total_expenses = cur.fetchone()[0] or 0

    cur.execute("SELECT income FROM budgets WHERE month=?", (month,))
    row = cur.fetchone()
    income = row[0] if row else 0

    savings = income - total_expenses

    cur.execute("""SELECT c.category, IFNULL(SUM(e.amount),0), IFNULL(c.amount,0)
                   FROM (SELECT DISTINCT category FROM expenses) x
                   LEFT JOIN category_budgets c ON c.category=x.category AND c.month=?
                   LEFT JOIN expenses e ON e.category=x.category AND substr(e.date,1,7)=?
                   GROUP BY x.category""", (month, month))
    budget_rows = cur.fetchall()

    conn.close()

    return render_template("dashboard.html", month=month,
                           income=income, expenses=total_expenses, savings=savings,
                           budget_rows=budget_rows)

@app.route("/expenses", methods=["GET", "POST"])
def expenses():
    month = get_month()
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    if request.method == "POST":
        date = request.form["date"]
        category = request.form["category"]
        amount = float(request.form["amount"])
        method = request.form["payment_method"]
        note = request.form["note"]
        cur.execute("INSERT INTO expenses(date,category,amount,payment_method,note) VALUES(?,?,?,?,?)",
                    (date, category, amount, method, note))
        conn.commit()
        return redirect(url_for("expenses", month=month))

    cur.execute("SELECT * FROM expenses WHERE substr(date,1,7)=?", (month,))
    expenses = cur.fetchall()
    conn.close()
    return render_template("expenses.html", expenses=expenses, month=month)

@app.route("/expenses/delete/<int:exp_id>", methods=["POST"])
def delete_expense(exp_id):
    month = get_month()
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("DELETE FROM expenses WHERE id=?", (exp_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("expenses", month=month))

@app.route("/budgets", methods=["GET", "POST"])
def budgets():
    month = get_month()
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    if request.method == "POST":
        income = float(request.form.get("income", 0))
        cur.execute("INSERT OR REPLACE INTO budgets(month,income) VALUES(?,?)", (month, income))

        categories = request.form.getlist("category[]")
        amounts = request.form.getlist("amount[]")
        for c, a in zip(categories, amounts):
            if c.strip():
                cur.execute("INSERT OR REPLACE INTO category_budgets(month,category,amount) VALUES(?,?,?)",
                            (month, c, float(a or 0)))

        conn.commit()
        return redirect(url_for("budgets", month=month))

    cur.execute("SELECT income FROM budgets WHERE month=?", (month,))
    row = cur.fetchone()
    income = row[0] if row else 0

    cur.execute("SELECT category,amount FROM category_budgets WHERE month=?", (month,))
    category_budgets = cur.fetchall()
    conn.close()
    return render_template("budgets.html", month=month, income=income, category_budgets=category_budgets)

@app.route("/api/category_spend")
def category_spend():
    month = get_month()
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT category, SUM(amount) FROM expenses WHERE substr(date,1,7)=? GROUP BY category", (month,))
    data = cur.fetchall()
    conn.close()
    return jsonify(data)

@app.route("/api/daily_trend")
def daily_trend():
    month = get_month()
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT date, SUM(amount) FROM expenses WHERE substr(date,1,7)=? GROUP BY date ORDER BY date", (month,))
    data = cur.fetchall()
    conn.close()
    return jsonify(data)

# ✅ New chart 1: Payment method breakdown
@app.route("/api/payment_methods")
def payment_methods():
    month = get_month()
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT payment_method, SUM(amount) FROM expenses WHERE substr(date,1,7)=? GROUP BY payment_method", (month,))
    data = cur.fetchall()
    conn.close()
    return jsonify(data)

# ✅ New chart 2: Monthly trend (all months)
@app.route("/api/monthly_trend")
def monthly_trend():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT substr(date,1,7) as month, SUM(amount) FROM expenses GROUP BY month ORDER BY month")
    data = cur.fetchall()
    conn.close()
    return jsonify(data)

@app.route("/export")
def export():
    month = get_month()
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT * FROM expenses WHERE substr(date,1,7)=?", (month,))
    rows = cur.fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID","Date","Category","Amount","Payment Method","Note"])
    writer.writerows(rows)
    output.seek(0)

    return send_file(io.BytesIO(output.read().encode()), as_attachment=True,
                     download_name=f"expenses_{month}.csv", mimetype="text/csv")

if __name__ == "__main__":
    init_db()
    app.run(debug=True)
