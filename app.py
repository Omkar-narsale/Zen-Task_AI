from flask import Flask, render_template, request, redirect, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from sqlalchemy import case, or_
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from werkzeug.utils import secure_filename
from flask import send_from_directory
# ================= APP =================
app = Flask(__name__)
app.secret_key = "todo-final-secret"
UPLOAD_FOLDER = "uploads/assignments"
ALLOWED_EXTENSIONS = {"pdf"}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
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
    # ROLE SYSTEM (ADD-ON)
    role = db.Column(db.String(20), default="student")  
# student / admin
    admin_type = db.Column(db.String(20), nullable=True)  
# teacher / hod / principal (only if role == admin)

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
# ================= ADMIN ASSIGNED TASKS =================
class AssignedTask(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    title = db.Column(db.String(200))
    description = db.Column(db.Text)
    deadline = db.Column(db.DateTime)

    status = db.Column(db.String(20), default="Pending")
    is_late = db.Column(db.Boolean, default=False)

    assigned_by = db.Column(db.Integer, db.ForeignKey("user.id"))
    assigned_to = db.Column(db.Integer, db.ForeignKey("user.id"))

    submission_file = db.Column(db.String(300), nullable=True)
    submitted_at = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.now)

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

        if not user:
            return render_template("login.html", error="Invalid credentials")

        session["user_id"] = user.id

        if user.role == "admin":
            return redirect("/admin/dashboard")

        return redirect("/")

    return render_template("login.html")


@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        role = request.form.get("role", "student")
        admin_type = request.form.get("admin_type") if role == "admin" else None

        user = User(
            name=request.form["name"],
            email=request.form["email"],
            password=request.form["password"],
            role=role,
            admin_type=admin_type
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

# ================= ADMIN ASSIGN TASK =================

@app.route("/admin/assign-task", methods=["GET", "POST"])
def admin_assign_task():
    if not is_admin():
        return redirect("/")

    if request.method == "POST":
        title = request.form["title"]
        description = request.form["description"]
        deadline = datetime.strptime(
            request.form["deadline"], "%Y-%m-%dT%H:%M"
        )
        student_id = request.form["student_id"]

        task = AssignedTask(
            title=title,
            description=description,
            deadline=deadline,
            assigned_by=session["user_id"],
            assigned_to=student_id
        )
        db.session.add(task)
        db.session.commit()

        student = User.query.get(student_id)
        send_email(
            student.email,
            "📘 New Assigned Task",
            f"You have a new task: {title}"
        )

        return redirect("/admin/assign-task")

    students = User.query.filter_by(role="student").all()
    tasks = AssignedTask.query.order_by(
        AssignedTask.created_at.desc()
    ).all()

    return render_template(
        "admin_assign_task.html",
        students=students,
        tasks=tasks
    )


@app.route("/admin/update-task/<int:task_id>", methods=["GET","POST"])
def admin_update_task(task_id):
    if not is_admin():
        return redirect("/")

    task = AssignedTask.query.get_or_404(task_id)

    if request.method == "POST":
        task.title = request.form["title"]
        task.description = request.form["description"]
        task.deadline = datetime.strptime(
            request.form["deadline"], "%Y-%m-%dT%H:%M"
        )
        db.session.commit()
        return redirect("/admin/assign-task")

    return render_template(
        "admin_update_task.html",
        task=task
    )
@app.route("/admin/download/<filename>")
def download_submission(filename):
    if not is_admin():
        return redirect("/")
    return send_from_directory(
        app.config["UPLOAD_FOLDER"], filename, as_attachment=True
    )


# ================= STUDENT ASSIGNED TASKS =================

@app.route("/student/assigned-tasks")
def student_assigned_tasks():
    if not is_student():
        return redirect("/")

    tasks = AssignedTask.query.filter_by(
        assigned_to=session["user_id"]
    ).all()

    return render_template(
        "student_assigned_tasks.html",
        tasks=tasks
    )

@app.route("/student/submit-task/<int:task_id>", methods=["POST"])
def submit_assigned_task(task_id):
    if not is_student():
        return redirect("/")

    task = AssignedTask.query.get_or_404(task_id)

    if task.assigned_to != session["user_id"]:
        return redirect("/")

    file = request.files.get("submission")

    # PDF is OPTIONAL
    if file and file.filename != "":
        filename = secure_filename(file.filename)
        save_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(save_path)

        task.submission_file = filename

    # Late check
    now = datetime.now()
    if task.deadline and now > task.deadline:
        task.is_late = True

    task.submitted_at = now
    task.status = "Submitted"

    db.session.commit()
    return redirect("/student/assigned-tasks")
# ================= ADMIN DASHBOARD =================
@app.route("/admin/dashboard")
def admin_dashboard():
    if not is_admin():
        return redirect("/")

    tasks = AssignedTask.query.order_by(
        AssignedTask.created_at.desc()
    ).all()

    total = len(tasks)
    pending = AssignedTask.query.filter_by(status="Pending").count()
    submitted = AssignedTask.query.filter_by(status="Submitted").count()
    completed = AssignedTask.query.filter_by(status="Reviewed").count()

    return render_template(
        "admin_dashboard.html",
        tasks=tasks,
        total=total,
        pending=pending,
        submitted=submitted,
        completed=completed
    )
# ================= ADMIN ACCEPT TASK =================
@app.route("/admin/accept-task/<int:task_id>")
def admin_accept_task(task_id):
    if not is_admin():
        return redirect("/")

    task = AssignedTask.query.get_or_404(task_id)
    task.status = "Reviewed"
    db.session.commit()

    return redirect("/admin/dashboard")

# ================= ADMIN RESUBMIT TASK =================
@app.route("/admin/resubmit-task/<int:task_id>")
def admin_resubmit_task(task_id):
    if not is_admin():
        return redirect("/")

    task = AssignedTask.query.get_or_404(task_id)

    task.status = "Pending"
    task.submission_file = None
    task.submitted_at = None
    task.is_late = False

    db.session.commit()
    return redirect("/admin/dashboard")

@app.route("/admin/review-task/<int:task_id>")
def admin_review_task(task_id):
    if not is_admin():
        return redirect("/")

    task = AssignedTask.query.get_or_404(task_id)
    task.status = "Reviewed"
    db.session.commit()

    return redirect("/admin/dashboard")
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
        return jsonify({"reply":"🔒 Please login first."})

    msg = request.get_json().get("message","").lower().strip()
    uid = session["user_id"]

    if msg == "help":
        return jsonify({"reply":
            "🤖 Commands:\n"
            "• add task Buy milk\n"
            "• show tasks\n"
            "• complete task Buy milk\n"
            "• delete task Buy milk\n"
            "• show overdue\n"
            "• today tasks\n"
            "• task stats\n"
            "• add note Meeting ideas\n"
            "• show notes\n"
            "• pin note Meeting ideas\n"
            "• show pinned notes"
        })

    if msg.startswith("add task"):
        title = msg.replace("add task","").strip() or "New Task"
        todo = Todo(
            title=title,
            desc="🤖 Created by Chatbot",
            category="General",
            priority="Medium",
            end_time=datetime.now()+timedelta(hours=2),
            user_id=uid
        )
        db.session.add(todo)
        db.session.commit()
        return jsonify({"reply":f"✅ Task **{title}** added!"})

    if msg.startswith("complete task"):
        title = msg.replace("complete task","").strip()
        task = Todo.query.filter(
            Todo.user_id==uid,
            Todo.title.ilike(f"%{title}%"),
            Todo.is_deleted==False
        ).first()
        if not task:
            return jsonify({"reply":"❌ Task not found"})
        task.status = "Completed"
        db.session.commit()
        return jsonify({"reply":f"🎉 Task **{task.title}** completed!"})

    if msg.startswith("delete task"):
        title = msg.replace("delete task","").strip()
        task = Todo.query.filter(
            Todo.user_id==uid,
            Todo.title.ilike(f"%{title}%")
        ).first()
        if not task:
            return jsonify({"reply":"❌ Task not found"})
        task.is_deleted = True
        db.session.commit()
        return jsonify({"reply":f"🗑 Task **{task.title}** deleted!"})

    if msg == "show tasks":
        tasks = Todo.query.filter_by(user_id=uid,is_deleted=False).limit(5).all()
        if not tasks:
            return jsonify({"reply":"📭 No tasks"})
        reply = "📝 Tasks:\n"
        for t in tasks:
            reply += f"• {t.title} ({t.status})\n"
        return jsonify({"reply":reply})

    if msg == "show overdue":
        tasks = Todo.query.filter_by(user_id=uid,status="Overdue").all()
        if not tasks:
            return jsonify({"reply":"🎉 No overdue tasks"})
        reply = "⚠️ Overdue:\n"
        for t in tasks:
            reply += f"• {t.title}\n"
        return jsonify({"reply":reply})

    if msg == "today tasks":
        today = datetime.now().date()
        tasks = Todo.query.filter(
            Todo.user_id==uid,
            Todo.end_time>=datetime.combine(today,datetime.min.time()),
            Todo.end_time<=datetime.combine(today,datetime.max.time())
        ).all()
        if not tasks:
            return jsonify({"reply":"🎉 No tasks today"})
        reply = "📅 Today:\n"
        for t in tasks:
            reply += f"• {t.title}\n"
        return jsonify({"reply":reply})

    if msg == "task stats":
        total = Todo.query.filter_by(user_id=uid).count()
        completed = Todo.query.filter_by(user_id=uid,status="Completed").count()
        return jsonify({"reply":f"📊 Total: {total}, Completed: {completed}"})

    if msg.startswith("add note"):
        content = msg.replace("add note","").strip()
        if not content:
            return jsonify({"reply":"❌ Empty note"})
        note = Note(
            title="🤖 Chatbot Note",
            content=content,
            tag="chatbot",
            user_id=uid
        )
        db.session.add(note)
        db.session.commit()
        return jsonify({"reply":"📝 Note added!"})

    if msg == "show notes":
        notes = Note.query.filter_by(user_id=uid,is_deleted=False).limit(5).all()
        if not notes:
            return jsonify({"reply":"📭 No notes"})
        reply = "🗒 Notes:\n"
        for n in notes:
            reply += f"• {n.content[:40]}...\n"
        return jsonify({"reply":reply})

    if msg.startswith("pin note"):
        text = msg.replace("pin note","").strip()
        note = Note.query.filter(
            Note.user_id==uid,
            Note.content.ilike(f"%{text}%"),
            Note.is_deleted==False
        ).first()
        if not note:
            return jsonify({"reply":"❌ Note not found"})
        note.pinned = True
        db.session.commit()
        return jsonify({"reply":"📌 Note pinned!"})

    if msg == "show pinned notes":
        notes = Note.query.filter_by(user_id=uid,pinned=True,is_deleted=False).all()
        if not notes:
            return jsonify({"reply":"📭 No pinned notes"})
        reply = "📌 Pinned:\n"
        for n in notes:
            reply += f"• {n.content[:40]}...\n"
        return jsonify({"reply":reply})

    return jsonify({"reply":"🤔 I didn’t understand. Type help."})

# ================= HELPERS =================
def is_admin():
    return (
        "user_id" in session and
        User.query.get(session["user_id"]).role == "admin"
    )

def is_student():
    return (
        "user_id" in session and
        User.query.get(session["user_id"]).role == "student"
    )
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
@app.context_processor
def inject_current_user():
    user = None
    if "user_id" in session:
        user = User.query.get(session["user_id"])
    return dict(current_user=user)

# ================= RUN =================
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)
