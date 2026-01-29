from flask import Flask, render_template, request, redirect, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from sqlalchemy import case, or_
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
SENDER_EMAIL = "narsaleomkar2006@gmail.com"
EMAIL_PASSWORD = "vvxzogqsudvergtx"

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
    priority = db.Column(db.String(20))
    end_time = db.Column(db.DateTime)

    status = db.Column(db.String(20), default="Pending")
    is_deleted = db.Column(db.Boolean, default=False)
    alerted = db.Column(db.Boolean, default=False)

    date_created = db.Column(db.DateTime, default=datetime.now)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))


class Note(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200))
    content = db.Column(db.Text)
    tag = db.Column(db.String(50))

    pinned = db.Column(db.Boolean, default=False)
    completed = db.Column(db.Boolean, default=False)
    is_deleted = db.Column(db.Boolean, default=False)

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
    except Exception as e:
        print("Email error:", e)

# ================= AUTH =================
@app.route("/login", methods=["GET","POST"])
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


@app.route("/register", methods=["GET","POST"])
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

# ================= HOME / TODO =================
@app.route("/", methods=["GET","POST"])
def home():
    if "user_id" not in session:
        return redirect("/login")

    now = datetime.now()
    user = User.query.get(session["user_id"])

    overdue = Todo.query.filter(
        Todo.user_id == user.id,
        Todo.status == "Pending",
        Todo.end_time < now,
        Todo.is_deleted == False
    ).all()

    for t in overdue:
        t.status = "Overdue"

    tasks = Todo.query.filter(
        Todo.user_id == user.id,
        Todo.status == "Pending",
        Todo.alerted == False,
        Todo.is_deleted == False
    ).all()

    for t in tasks:
        mins = (t.end_time - now).total_seconds() / 60
        send = (
            (t.priority == "High" and mins <= 30) or
            (t.priority == "Medium" and mins <= 15) or
            (t.priority == "Low" and mins <= 5)
        )
        if send and mins > 0:
            send_email(
                user.email,
                f"⏰ Todo Reminder: {t.title}",
                f"Task '{t.title}' is due soon."
            )
            t.alerted = True

    db.session.commit()

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
            (Todo.priority=="High",1),
            (Todo.priority=="Medium",2),
            (Todo.priority=="Low",3)
        ),
        Todo.end_time.asc()
    ).all()

    return render_template("index.html", todos=todos)

@app.route("/complete/<int:sno>")
def complete(sno):
    t = Todo.query.get_or_404(sno)
    t.status = "Completed"
    db.session.commit()
    return redirect("/")

@app.route("/delete/<int:sno>")
def delete(sno):
    t = Todo.query.get_or_404(sno)
    t.is_deleted = True
    db.session.commit()
    return redirect("/")

@app.route("/update/<int:sno>", methods=["GET","POST"])
def update(sno):
    t = Todo.query.get_or_404(sno)
    if request.method == "POST":
        t.title = request.form["title"]
        t.desc = request.form["desc"]
        t.category = request.form["category"]
        t.priority = request.form["priority"]
        t.end_time = datetime.strptime(request.form["end_time"], "%Y-%m-%dT%H:%M")
        db.session.commit()
        return redirect("/")
    return render_template("update.html", todo=t)

# ================= DASHBOARD =================
@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect("/login")

    uid = session["user_id"]

    total = Todo.query.filter_by(user_id=uid).count()
    completed = Todo.query.filter_by(user_id=uid, status="Completed").count()
    pending = Todo.query.filter_by(user_id=uid, status="Pending").count()
    overdue = Todo.query.filter_by(user_id=uid, status="Overdue").count()

    high = Todo.query.filter_by(user_id=uid, priority="High").count()
    medium = Todo.query.filter_by(user_id=uid, priority="Medium").count()
    low = Todo.query.filter_by(user_id=uid, priority="Low").count()

    completion_percent = int((completed/total)*100) if total else 0

    productivity = (
        "Excellent" if completion_percent >= 75
        else "Average" if completion_percent >= 40
        else "Low"
    )

    today = datetime.now().date()
    today_tasks = Todo.query.filter(
        Todo.user_id == uid,
        Todo.end_time >= datetime.combine(today, datetime.min.time()),
        Todo.end_time <= datetime.combine(today, datetime.max.time())
    ).count()

    week_tasks = [0]*7
    for t in Todo.query.filter_by(user_id=uid).all():
        week_tasks[t.date_created.weekday()] += 1

    return render_template(
        "dashboard.html",
        total=total, completed=completed, pending=pending, overdue=overdue,
        high=high, medium=medium, low=low,
        completion_percent=completion_percent,
        productivity=productivity,
        today_tasks=today_tasks,
        week_tasks=week_tasks
    )

# ================= PROFILE =================
@app.route("/profile")
def profile():
    uid = session["user_id"]
    total = Todo.query.filter_by(user_id=uid).count()
    completed = Todo.query.filter_by(user_id=uid, status="Completed").count()
    pending = total - completed
    percent = int((completed/total)*100) if total else 0

    achievement_bars = [
        {"label":"10 Tasks","progress":min(int((completed/10)*100),100)},
        {"label":"25 Tasks","progress":min(int((completed/25)*100),100)},
        {"label":"50 Tasks","progress":min(int((completed/50)*100),100)},
    ]

    return render_template(
        "profile.html",
        total=total, completed=completed,
        pending=pending, percent=percent,
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

# ================= NOTES =================
@app.route("/notes")
def notes():
    if "user_id" not in session:
        return redirect("/login")

    q = request.args.get("q","").strip()
    tag = request.args.get("tag","").strip()

    query = Note.query.filter(
        Note.user_id == session["user_id"],
        Note.is_deleted == False
    )

    if q:
        query = query.filter(
            or_(
                Note.title.ilike(f"%{q}%"),
                Note.content.ilike(f"%{q}%"),
                Note.tag.ilike(f"%{q}%")
            )
        )

    if tag:
        query = query.filter(Note.tag == tag)

    notes = query.order_by(
        Note.pinned.desc(),
        Note.date_created.desc()
    ).all()

    tags = db.session.query(Note.tag).filter(
        Note.user_id == session["user_id"],
        Note.is_deleted == False,
        Note.tag != None
    ).distinct().all()

    return render_template("notes.html", notes=notes, tags=tags)

@app.route("/notes/add", methods=["POST"])
def add_note():
    note = Note(
        title=request.form["title"],
        content=request.form["content"],
        tag=request.form["tag"],
        user_id=session["user_id"]
    )
    db.session.add(note)
    db.session.commit()
    return redirect("/notes")

@app.route("/notes/pin/<int:id>")
def pin_note(id):
    note = Note.query.get_or_404(id)
    note.pinned = not note.pinned
    db.session.commit()
    return redirect("/notes")

@app.route("/notes/complete/<int:id>")
def complete_note(id):
    note = Note.query.get_or_404(id)
    note.completed = True
    db.session.commit()
    return redirect("/notes")

@app.route("/notes/delete/<int:id>")
def delete_note(id):
    note = Note.query.get_or_404(id)
    note.is_deleted = True
    db.session.commit()
    return redirect("/notes")

@app.route("/notes/trash")
def notes_trash():
    notes = Note.query.filter_by(
        user_id=session["user_id"],
        is_deleted=True
    ).all()
    return render_template("notes_trash.html", notes=notes)

@app.route("/notes/restore/<int:id>")
def restore_note(id):
    note = Note.query.get_or_404(id)
    note.is_deleted = False
    db.session.commit()
    return redirect("/notes/trash")
# ================= CHATBOT =================
@app.route("/chatbot", methods=["POST"])
def chatbot():
    if "user_id" not in session:
        return jsonify({"reply": "Please login first."})

    msg = request.get_json().get("message", "").lower().strip()
    uid = session["user_id"]

    # ================= HELP =================
    if msg == "help":
        return jsonify({"reply":
            "🤖 I can help you with:\n\n"
            "• add task Buy milk\n"
            "• show tasks\n"
            "• complete task Buy milk\n"
            "• delete task Buy milk\n"
            "• show overdue\n"
            "• today tasks\n"
            "• task stats\n\n"
            "📝 Notes:\n"
            "• add note Meeting ideas\n"
            "• show notes\n"
            "• pin note Meeting ideas\n"
            "• show pinned notes"
        })

    # ================= ADD TASK =================
    if msg.startswith("add task"):
        title = msg.replace("add task", "").strip() or "New Task"
        todo = Todo(
            title=title,
            desc="Added via chatbot",
            category="General",
            priority="Medium",
            end_time=datetime.now() + timedelta(hours=2),
            user_id=uid
        )
        db.session.add(todo)
        db.session.commit()
        return jsonify({"reply": f"✅ Task '{title}' added successfully!"})

    # ================= SHOW TASKS =================
    if msg == "show tasks":
        tasks = Todo.query.filter_by(
            user_id=uid,
            is_deleted=False
        ).order_by(Todo.end_time.asc()).limit(5).all()

        if not tasks:
            return jsonify({"reply": "📭 You have no tasks."})

        reply = "📝 Your tasks:\n"
        for t in tasks:
            reply += f"• {t.title} ({t.status})\n"

        return jsonify({"reply": reply})

    # ================= COMPLETE TASK =================
    if msg.startswith("complete task"):
        title = msg.replace("complete task", "").strip()
        task = Todo.query.filter(
            Todo.user_id == uid,
            Todo.title.ilike(f"%{title}%"),
            Todo.is_deleted == False
        ).first()

        if not task:
            return jsonify({"reply": "❌ Task not found."})

        task.status = "Completed"
        db.session.commit()
        return jsonify({"reply": f"✅ Task '{task.title}' completed!"})

    # ================= DELETE TASK =================
    if msg.startswith("delete task"):
        title = msg.replace("delete task", "").strip()
        task = Todo.query.filter(
            Todo.user_id == uid,
            Todo.title.ilike(f"%{title}%")
        ).first()

        if not task:
            return jsonify({"reply": "❌ Task not found."})

        task.is_deleted = True
        db.session.commit()
        return jsonify({"reply": f"🗑 Task '{task.title}' deleted."})

    # ================= OVERDUE =================
    if msg == "show overdue":
        overdue = Todo.query.filter_by(
            user_id=uid,
            status="Overdue"
        ).all()

        if not overdue:
            return jsonify({"reply": "🎉 No overdue tasks!"})

        reply = "⚠️ Overdue tasks:\n"
        for t in overdue:
            reply += f"• {t.title}\n"

        return jsonify({"reply": reply})

    # ================= TODAY TASKS =================
    if msg == "today tasks":
        today = datetime.now().date()
        tasks = Todo.query.filter(
            Todo.user_id == uid,
            Todo.end_time >= datetime.combine(today, datetime.min.time()),
            Todo.end_time <= datetime.combine(today, datetime.max.time())
        ).all()

        if not tasks:
            return jsonify({"reply": "🎉 No tasks due today."})

        reply = "📅 Today's tasks:\n"
        for t in tasks:
            reply += f"• {t.title}\n"

        return jsonify({"reply": reply})

    # ================= TASK STATS =================
    if msg == "task stats":
        total = Todo.query.filter_by(user_id=uid).count()
        completed = Todo.query.filter_by(
            user_id=uid,
            status="Completed"
        ).count()

        return jsonify({"reply": f"📊 Total tasks: {total}\n✅ Completed: {completed}"})

    # ================= ADD NOTE =================
    if msg.startswith("add note"):
        content = msg.replace("add note", "").strip()
        if not content:
            return jsonify({"reply": "❌ Please provide note content."})

        note = Note(
            title="Chatbot Note",
            content=content,
            tag="chatbot",
            user_id=uid
        )
        db.session.add(note)
        db.session.commit()
        return jsonify({"reply": "📝 Note added successfully!"})

    # ================= SHOW NOTES =================
    if msg == "show notes":
        notes = Note.query.filter_by(
            user_id=uid,
            is_deleted=False
        ).order_by(Note.date_created.desc()).limit(5).all()

        if not notes:
            return jsonify({"reply": "📭 No notes found."})

        reply = "🗒 Your notes:\n"
        for n in notes:
            reply += f"• {n.content[:40]}...\n"

        return jsonify({"reply": reply})

    # ================= PIN NOTE =================
    if msg.startswith("pin note"):
        text = msg.replace("pin note", "").strip()
        note = Note.query.filter(
            Note.user_id == uid,
            Note.content.ilike(f"%{text}%"),
            Note.is_deleted == False
        ).first()

        if not note:
            return jsonify({"reply": "❌ Note not found."})

        note.pinned = True
        db.session.commit()
        return jsonify({"reply": "📌 Note pinned!"})

    # ================= SHOW PINNED NOTES =================
    if msg == "show pinned notes":
        notes = Note.query.filter_by(
            user_id=uid,
            pinned=True,
            is_deleted=False
        ).all()

        if not notes:
            return jsonify({"reply": "📭 No pinned notes."})

        reply = "📌 Pinned notes:\n"
        for n in notes:
            reply += f"• {n.content[:40]}...\n"

        return jsonify({"reply": reply})

    return jsonify({"reply": "🤔 I didn’t understand. Type **help**."})
# ================= RUN =================
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)