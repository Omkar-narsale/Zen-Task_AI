from flask import Flask, render_template, request, redirect, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from sqlalchemy import case
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
# ================= APP =================
app = Flask(__name__)
app.secret_key = "todo-final-secret"

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///todo.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

# ================= EMAIL CONFIG =================
SENDER_EMAIL = "narsaleomkar2006@gmail.com"          # 🔴 CHANGE
EMAIL_PASSWORD = "vvxzogqsudvergtx"  # 🔴 CHANGE

# ================= MODELS =================
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    email = db.Column(db.String(120), unique=True)
    password = db.Column(db.String(100))

class Todo(db.Model):
    sno = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200))
    desc = db.Column(db.String(500))
    category = db.Column(db.String(50))
    priority = db.Column(db.String(20))   # High / Medium / Low
    end_time = db.Column(db.DateTime)

    status = db.Column(db.String(20), default="Pending")
    is_deleted = db.Column(db.Boolean, default=False)
    alerted = db.Column(db.Boolean, default=False)

    date_created = db.Column(db.DateTime, default=datetime.now)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))

# ================= EMAIL =================
def send_email(to_email, subject, message):
    try:
        msg = MIMEMultipart()
        msg["From"] = SENDER_EMAIL
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(message, "plain"))

        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(SENDER_EMAIL, EMAIL_PASSWORD)
        server.send_message(msg)
        server.quit()

        print("📧 Email sent to", to_email)
    except Exception as e:
        print("❌ Email error:", e)

# ================= AUTH =================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = User.query.filter_by(
            email=request.form["email"],
            password=request.form["password"]
        ).first()
        if user:
            session["user_id"] = user.id
            return redirect("/")
    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        user = User(
            name=request.form["name"],
            email=request.form["email"],
            password=request.form["password"]
        )
        db.session.add(user)
        db.session.commit()
        return redirect("/login")
    return render_template("register.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# ================= HOME =================
@app.route("/", methods=["GET", "POST"])
def home():
    if "user_id" not in session:
        return redirect("/login")

    now = datetime.now()
    user = User.query.get(session["user_id"])

    # -------- AUTO OVERDUE --------
    overdue_tasks = Todo.query.filter(
        Todo.user_id == user.id,
        Todo.status == "Pending",
        Todo.end_time < now,
        Todo.is_deleted == False
    ).all()

    for t in overdue_tasks:
        t.status = "Overdue"

    # -------- EMAIL REMINDERS --------
    tasks = Todo.query.filter(
        Todo.user_id == user.id,
        Todo.status == "Pending",
        Todo.alerted == False,
        Todo.is_deleted == False
    ).all()

    for t in tasks:
        minutes_left = (t.end_time - now).total_seconds() / 60

        send = False
        if t.priority == "High" and minutes_left <= 30:
            send = True
        elif t.priority == "Medium" and minutes_left <= 15:
            send = True
        elif t.priority == "Low" and minutes_left <= 5:
            send = True

        if send and minutes_left > 0:
            send_email(
                user.email,
                f"⏰ Todo Reminder: {t.title}",
                f"""
Hello {user.name},

Your task "{t.title}" is due soon.

Priority: {t.priority}
Due at: {t.end_time.strftime('%d %b %Y %H:%M')}

— Todo App
"""
            )
            t.alerted = True

    db.session.commit()

    # -------- ADD TASK --------
    if request.method == "POST":
        todo = Todo(
            title=request.form["title"],
            desc=request.form["desc"],
            category=request.form["category"],
            priority=request.form["priority"],
            end_time=datetime.strptime(request.form["end_time"], "%Y-%m-%dT%H:%M"),
            user_id=user.id
        )
        db.session.add(todo)
        db.session.commit()

    todos = Todo.query.filter_by(
        user_id=user.id,
        is_deleted=False
    ).order_by(
        case(
            (Todo.priority == "High", 1),
            (Todo.priority == "Medium", 2),
            (Todo.priority == "Low", 3),
        ),
        Todo.end_time.asc()
    ).all()

    return render_template("index.html", todos=todos)

# ================= TASK ACTIONS =================
@app.route("/complete/<int:sno>")
def complete(sno):
    todo = Todo.query.get_or_404(sno)
    if todo.user_id == session["user_id"]:
        todo.status = "Completed"
        db.session.commit()
    return redirect("/")

@app.route("/delete/<int:sno>")
def delete(sno):
    todo = Todo.query.get_or_404(sno)
    if todo.user_id == session["user_id"]:
        todo.is_deleted = True
        db.session.commit()
    return redirect("/")

@app.route("/update/<int:sno>", methods=["GET", "POST"])
def update(sno):
    todo = Todo.query.get_or_404(sno)
    if request.method == "POST":
        todo.title = request.form["title"]
        todo.desc = request.form["desc"]
        todo.category = request.form["category"]
        todo.priority = request.form["priority"]
        todo.end_time = datetime.strptime(request.form["end_time"], "%Y-%m-%dT%H:%M")
        db.session.commit()
        return redirect("/")
    return render_template("update.html", todo=todo)

# ================= DASHBOARD =================
from datetime import datetime, timedelta
from sqlalchemy import case

@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect("/login")

    uid = session["user_id"]
    now = datetime.utcnow()

    total = Todo.query.filter_by(user_id=uid).count()
    completed = Todo.query.filter_by(user_id=uid, status="Completed").count()
    pending = Todo.query.filter_by(user_id=uid, status="Pending").count()
    overdue = Todo.query.filter_by(user_id=uid, status="Overdue").count()

    # PRIORITY COUNTS
    high = Todo.query.filter_by(user_id=uid, priority="High").count()
    medium = Todo.query.filter_by(user_id=uid, priority="Medium").count()
    low = Todo.query.filter_by(user_id=uid, priority="Low").count()

    completion_percent = int((completed / total) * 100) if total else 0

    # PRODUCTIVITY STATUS
    if completion_percent >= 75:
        productivity = "Excellent"
    elif completion_percent >= 40:
        productivity = "Average"
    else:
        productivity = "Low"

    # TODAY TASKS
    today_start = datetime(now.year, now.month, now.day)
    today_end = today_start + timedelta(days=1)

    today_tasks = Todo.query.filter(
        Todo.user_id == uid,
        Todo.end_time >= today_start,
        Todo.end_time < today_end
    ).count()

    # WEEKLY DATA (Mon → Sun)
    week_tasks = [0] * 7
    tasks = Todo.query.filter_by(user_id=uid).all()
    for t in tasks:
        week_tasks[t.date_created.weekday()] += 1

    return render_template(
        "dashboard.html",
        total=total,
        completed=completed,
        pending=pending,
        overdue=overdue,
        high=high,
        medium=medium,
        low=low,
        completion_percent=completion_percent,
        productivity=productivity,
        today_tasks=today_tasks,
        week_tasks=week_tasks
    )
# ================= PROFILE =================
@app.route("/profile")
def profile():
    if "user_id" not in session:
        return redirect("/login")

    uid = session["user_id"]

    total = Todo.query.filter_by(
        user_id=uid,
        is_deleted=False
    ).count()

    completed = Todo.query.filter_by(
        user_id=uid,
        status="Completed",
        is_deleted=False
    ).count()

    pending = Todo.query.filter_by(
        user_id=uid,
        status="Pending",
        is_deleted=False
    ).count()

    percent = int((completed / total) * 100) if total > 0 else 0

    # ✅ Achievement progress bars
    achievement_bars = [
    {
        "label": "10 Tasks",
        "progress": min(int((completed / 10) * 100), 100)
    },
    {
        "label": "25 Tasks",
        "progress": min(int((completed / 25) * 100), 100)
    },
    {
        "label": "50 Tasks",
        "progress": min(int((completed / 50) * 100), 100)
    }
]

    return render_template(
        "profile.html",
        total=total,
        completed=completed,
        pending=pending,
        percent=percent,
        achievement_bars=achievement_bars
    )

# ================= ACHIEVEMENTS =================
@app.route("/achievements")
def achievements():
    completed = Todo.query.filter_by(
        user_id=session["user_id"], status="Completed"
    ).count()

    achievements = [
        ("Starter",1),("Focused",5),("Consistent",10),
        ("Task Master",25),("Legend",50)
    ]

    return render_template(
        "achievements.html",
        achievements=[
            {"title":a,"unlocked":completed>=n}
            for a,n in achievements
        ]
    )

# ================= CALENDAR =================
@app.route("/calendar")
def calendar():
    return render_template("calendar.html")

@app.route("/date-todos")
def date_todos():
    d = request.args.get("date")
    start = datetime.strptime(d,"%Y-%m-%d")
    end = start.replace(hour=23,minute=59,second=59)

    todos = Todo.query.filter(
        Todo.user_id == session["user_id"],
        Todo.date_created >= start,
        Todo.date_created <= end
    ).all()

    return render_template("date_todos.html", todos=todos, selected_date=d)

# ================= TEST EMAIL =================
@app.route("/test-email")
def test_email():
    user = User.query.get(session["user_id"])
    send_email(
        user.email,
        "✅ Test Email",
        "If you received this, email notifications work."
    )
    return "Test email sent"
# ================= CHATBOT (RULE-BASED) =================

import random
from flask import jsonify

def chatbot_response(message):
    msg = message.lower()

    greetings = [
        "hi", "hello", "hey", "good morning", "good evening"
    ]

    if any(word in msg for word in greetings):
        return random.choice([
            "Hello 👋 How can I help you?",
            "Hey there! 😊 Ask me anything about your tasks.",
            "Hi! I'm your Todo assistant 🤖"
        ])

    if "help" in msg:
        return (
            "Here’s what I can help you with:\n\n"
            "• add task\n"
            "• delete task\n"
            "• update task\n"
            "• priorities\n"
            "• email notifications\n"
            "• overdue tasks\n"
            "• dashboard\n"
            "• profile\n"
            "• achievements\n"
            "• productivity"
        )

    if "add task" in msg or "create task" in msg:
        return (
            "To add a task:\n"
            "1️⃣ Go to Home\n"
            "2️⃣ Fill title, priority & due time\n"
            "3️⃣ Click Add Task"
        )

    if "delete" in msg:
        return "Click the ❌ Delete button next to the task."

    if "update" in msg or "edit" in msg:
        return "Click ✏️ Update to modify a pending task."

    if "priority" in msg:
        return (
            "Task priorities work like this:\n\n"
            "🔴 High → Email before 30 mins\n"
            "🟡 Medium → Email before 15 mins\n"
            "🟢 Low → Email before 5 mins"
        )

    if "email" in msg or "mail" in msg:
        return (
            "Email alerts are automatic.\n"
            "You’ll receive a mail when a task is close to its due time.\n"
            "No page refresh required."
        )

    if "overdue" in msg:
        return (
            "If a task crosses its due time:\n"
            "• Status becomes Overdue\n"
            "• It turns red\n"
            "• Appears in dashboard stats"
        )

    if "dashboard" in msg:
        return (
            "Dashboard shows:\n"
            "📊 Total tasks\n"
            "✅ Completed\n"
            "⏳ Pending\n"
            "🔥 Priority split\n"
            "📈 Weekly productivity"
        )

    if "profile" in msg:
        return (
            "Profile shows:\n"
            "• Completion percentage\n"
            "• Pending vs Completed\n"
            "• Achievement progress bars (10 / 25 / 50)"
        )

    if "achievement" in msg:
        return (
            "Achievements unlock when you complete tasks:\n"
            "🏅 1 task\n"
            "🏅 5 tasks\n"
            "🏅 10 tasks\n"
            "🏅 25 tasks\n"
            "🏅 50 tasks"
        )

    if "productivity" in msg:
        return (
            "Productivity is calculated using completion rate:\n"
            "💚 Excellent → 75%+\n"
            "💛 Average → 40–74%\n"
            "❤️ Low → below 40%"
        )

    if "thank" in msg:
        return random.choice([
            "You're welcome 😊",
            "Happy to help!",
            "Anytime 👍"
        ])

    return (
        "🤔 I didn’t understand that.\n"
        "Type **help** to see what I can do."
    )


@app.route("/chatbot", methods=["POST"])
def chatbot():
    data = request.get_json()
    user_message = data.get("message", "")
    reply = chatbot_response(user_message)
    return jsonify({"reply": reply})
# ================= RUN =================
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)
