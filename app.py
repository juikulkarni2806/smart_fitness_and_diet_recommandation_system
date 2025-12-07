from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import sqlite3
import os
import bcrypt
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = "replace_this_with_a_random_secret"

DB_PATH = "users.db"

# ---------- DB helpers ----------
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            height_cm REAL,
            weight_kg REAL,
            bmi REAL,
            goal TEXT
        );
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            date TEXT NOT NULL,
            steps INTEGER DEFAULT 0,
            water INTEGER DEFAULT 0,
            workout INTEGER DEFAULT 0,
            UNIQUE(user_id, date),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );
    """)
    conn.commit()
    conn.close()

init_db()

# ---------- helpers ----------
def calculate_bmi(height_cm, weight_kg):
    try:
        if not height_cm or not weight_kg:
            return None
        h_m = float(height_cm) / 100.0
        bmi = float(weight_kg) / (h_m * h_m)
        return round(bmi, 2)
    except Exception:
        return None

def recommend_goal_by_bmi(bmi):
    if bmi is None:
        return "general"
    if bmi < 18.5:
        return "muscle_gain"
    if 18.5 <= bmi <= 24.9:
        return "general"
    return "weight_loss"

# ---------- routes ----------
@app.route("/")
def home():
    # page_class used by base.html for theme classes
    return render_template("home.html", page_class="home-bg")

@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name","").strip()
        email = request.form.get("email","").strip().lower()
        password = request.form.get("password","")
        try:
            height = float(request.form.get("height_cm") or 0)
        except:
            height = 0
        try:
            weight = float(request.form.get("weight_kg") or 0)
        except:
            weight = 0

        bmi = calculate_bmi(height, weight)
        goal = recommend_goal_by_bmi(bmi)

        hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

        conn = get_db()
        c = conn.cursor()
        try:
            c.execute("""
                INSERT INTO users (name, email, password, height_cm, weight_kg, bmi, goal)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (name, email, hashed, height or None, weight or None, bmi, goal))
            conn.commit()
            user_id = c.lastrowid
            # auto-login
            session["user_id"] = user_id
            session["user_name"] = name
            session["logged_in"] = True
            flash("Registration successful", "success")
            return redirect(url_for("dashboard"))
        except sqlite3.IntegrityError:
            flash("Email already registered", "danger")
        finally:
            conn.close()

    return render_template("register.html", page_class="home-bg")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email","").strip().lower()
        password = request.form.get("password","")
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE email=?", (email,))
        row = c.fetchone()
        conn.close()
        if row:
            stored = row["password"]
            if bcrypt.checkpw(password.encode("utf-8"), stored.encode("utf-8")):
                session["user_id"] = row["id"]
                session["user_name"] = row["name"]
                session["logged_in"] = True
                flash("Login successful", "success")
                return redirect(url_for("dashboard"))
        flash("Invalid credentials", "danger")
    return render_template("login.html", page_class="home-bg")

@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out", "info")
    return redirect(url_for("home"))

@app.route("/dashboard")
def dashboard():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE id=?", (session["user_id"],))
    user = c.fetchone()

    # today's summary
    today = datetime.today().strftime("%Y-%m-%d")
    c.execute("SELECT steps, water, workout FROM progress WHERE user_id=? AND date=?", (session["user_id"], today))
    row = c.fetchone()
    summary = {"steps": 0, "water": 0, "workout": 0}
    if row:
        summary["steps"] = row["steps"] or 0
        summary["water"] = row["water"] or 0
        summary["workout"] = row["workout"] or 0

    # last 7 days (labels + arrays)
    seven_days = (datetime.today() - timedelta(days=6)).strftime("%Y-%m-%d")
    c.execute("""
        SELECT date, steps, water, workout FROM progress
        WHERE user_id=? AND date>=?
        ORDER BY date ASC
    """, (session["user_id"], seven_days))
    rows = c.fetchall()
    conn.close()

    labels = []
    steps_arr = []
    water_arr = []
    workout_arr = []
    for r in rows:
        labels.append(r["date"])
        steps_arr.append(r["steps"] or 0)
        water_arr.append(r["water"] or 0)
        workout_arr.append(r["workout"] or 0)

    # small inspirational quote
    quotes = ["Small steps every day lead to big results.", "Consistency is the key to progress.", "Progress > Perfection."]
    quote = quotes[datetime.today().day % len(quotes)]

    return render_template("dashboard.html",
                           page_class="dashboard-bg",
                           user=user,
                           summary=summary,
                           chart_labels=labels,
                           chart_steps=steps_arr,
                           chart_water=water_arr,
                           chart_workout=workout_arr,
                           quote=quote)

@app.route("/diet", methods=["GET","POST"])
def diet():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT goal FROM users WHERE id=?", (session["user_id"],))
    row = c.fetchone()
    goal = row["goal"] if row else "general"

    if request.method == "POST":
        new_goal = request.form.get("goal")
        if new_goal:
            conn = get_db()
            c = conn.cursor()
            c.execute("UPDATE users SET goal=? WHERE id=?", (new_goal, session["user_id"]))
            conn.commit()
            conn.close()
            goal = new_goal
            flash("Goal updated", "success")

    if goal == "weight_loss":
        plan = {"type": "Weight Loss Diet", "meals": [
            "Breakfast: Oatmeal with fruits",
            "Lunch: Brown rice + grilled veggies + lean protein",
            "Snack: Fruit / nuts",
            "Dinner: Soup + salad"
        ]}
    elif goal == "muscle_gain":
        plan = {"type": "Muscle Gain Diet", "meals": [
            "Breakfast: Eggs + wholegrain toast",
            "Lunch: Rice + chicken/beans + veggies",
            "Snack: Protein shake",
            "Dinner: Paneer / tofu with roti"
        ]}
    else:
        plan = {"type": "General Fitness Diet", "meals": [
            "Breakfast: Fruit + oats",
            "Lunch: Balanced plate with carbs+protein+veg",
            "Snack: Yogurt / nuts",
            "Dinner: Light meal"
        ]}

    return render_template("diet.html", page_class="diet-bg", plan=plan, current_goal=goal)

@app.route("/workout", methods=["GET","POST"])
def workout():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT goal FROM users WHERE id=?", (session["user_id"],))
    row = c.fetchone()
    goal = row["goal"] if row else "general"

    if request.method == "POST":
        new_goal = request.form.get("goal")
        if new_goal:
            conn = get_db()
            c = conn.cursor()
            c.execute("UPDATE users SET goal=? WHERE id=?", (new_goal, session["user_id"]))
            conn.commit()
            conn.close()
            goal = new_goal
            flash("Goal updated", "success")

    if goal == "weight_loss":
        plan = {"type": "Weight Loss Workout", "exercises": [
            "Jumping Jacks — 30s", "Burpees — 10 reps", "Mountain Climbers — 20 reps", "Squats — 3 x 15", "Plank — 3 x 30s"
        ]}
    elif goal == "muscle_gain":
        plan = {"type": "Muscle Gain Workout", "exercises": [
            "Push-ups — 4 x 12", "Squats — 4 x 12", "Lunges — 3 x 12 each leg", "Dumbbell curls — 3 x 12"
        ]}
    else:
        plan = {"type": "General Fitness", "exercises": [
            "Brisk walk — 20 min", "Bodyweight squats — 3 x 15", "Light stretching"
        ]}

    return render_template("workout.html", page_class="workout-bg", plan=plan, current_goal=goal)

@app.route("/add_progress", methods=["GET","POST"])
def add_progress():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    if request.method == "POST":
        date = request.form.get("date") or datetime.today().strftime("%Y-%m-%d")
        try:
            steps = int(request.form.get("steps") or 0)
        except:
            steps = 0
        try:
            water = int(request.form.get("water") or 0)
        except:
            water = 0
        try:
            workout_min = int(request.form.get("workout") or 0)
        except:
            workout_min = 0

        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT id FROM progress WHERE user_id=? AND date=?", (session["user_id"], date))
        exists = c.fetchone()
        if exists:
            c.execute("UPDATE progress SET steps=?, water=?, workout=? WHERE user_id=? AND date=?",
                      (steps, water, workout_min, session["user_id"], date))
        else:
            c.execute("INSERT INTO progress (user_id, date, steps, water, workout) VALUES (?, ?, ?, ?, ?)",
                      (session["user_id"], date, steps, water, workout_min))
        conn.commit()
        conn.close()
        flash("Progress saved", "success")
        return redirect(url_for("progress"))

    today_date = datetime.today().strftime("%Y-%m-%d")
    return render_template("add_progress.html", page_class="dashboard-bg", today=today_date)

@app.route("/progress")
def progress():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT date, steps, water, workout FROM progress WHERE user_id=? ORDER BY date DESC", (session["user_id"],))
    rows = c.fetchall()
    conn.close()
    return render_template("progress.html", page_class="progress-bg", rows=rows)

@app.route("/progress_data")
def progress_data():
    if not session.get("logged_in"):
        return jsonify({"error": "not logged in"}), 401
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT date, steps, water, workout FROM progress WHERE user_id=? ORDER BY date DESC LIMIT 14", (session["user_id"],))
    rows = c.fetchall()
    conn.close()
    # convert to dict grouped by date (sorted asc)
    data_by_date = {}
    for r in rows:
        d = r["date"]
        if d not in data_by_date:
            data_by_date[d] = {"steps": r["steps"] or 0, "water": r["water"] or 0, "workout": r["workout"] or 0}
    labels = sorted(list(data_by_date.keys()))[-7:]
    steps = [data_by_date[d]["steps"] for d in labels]
    water = [data_by_date[d]["water"] for d in labels]
    workout = [data_by_date[d]["workout"] for d in labels]
    return jsonify({"labels": labels, "steps": steps, "water": water, "workout": workout})

@app.route("/profile", methods=["GET","POST"])
def profile():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    conn = get_db()
    c = conn.cursor()
    if request.method == "POST":
        name = request.form.get("name","").strip()
        try:
            height = float(request.form.get("height_cm") or 0)
        except:
            height = None
        try:
            weight = float(request.form.get("weight_kg") or 0)
        except:
            weight = None

        bmi = calculate_bmi(height, weight)
        goal = recommend_goal_by_bmi(bmi)
        c.execute("UPDATE users SET name=?, height_cm=?, weight_kg=?, bmi=?, goal=? WHERE id=?",
                  (name, height, weight, bmi, goal, session["user_id"]))
        conn.commit()
        session["user_name"] = name
        flash("Profile updated", "success")

    c.execute("SELECT id, name, email, height_cm, weight_kg, bmi, goal FROM users WHERE id=?", (session["user_id"],))
    user = c.fetchone()
    conn.close()
    return render_template("profile.html", page_class="profile-bg", user=user)


if __name__ == "__main__":
    app.run(debug=True)
