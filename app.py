import os
import sqlite3
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

from ai import analyze_image
from recommender import get_recommendations_dynamic
from PIL import Image

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-key")

app.config["UPLOAD_FOLDER"] = "uploads"
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}

def allowed_file(fname):
    return "." in fname and fname.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def get_db():
    return sqlite3.connect("fashion.db", check_same_thread=False)

# ----------------- Auth & pages -----------------
@app.route("/")
def home():
    if "user" in session:
        return redirect(url_for("upload_page"))
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username","").strip()
        password = request.form.get("password","")
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT id, password_hash FROM users WHERE username=?", (username,))
        row = c.fetchone()
        conn.close()
        if row and check_password_hash(row[1], password):
            session["user"] = username
            flash("Welcome back!", "success")
            return redirect(url_for("upload_page"))
        flash("Invalid credentials", "error")
    return render_template("login.html")

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form.get("username","").strip()
        password = request.form.get("password","")
        if not username or not password:
            flash("Username and password required", "error")
            return render_template("signup.html")
        conn = get_db()
        c = conn.cursor()
        try:
            c.execute(
                "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                (username, generate_password_hash(password), datetime.utcnow().isoformat())
            )
            conn.commit()
            flash("Account created. Please log in.", "success")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("Username already exists", "error")
        finally:
            conn.close()
    return render_template("signup.html")

@app.route("/logout")
def logout():
    session.pop("user", None)
    flash("Logged out", "info")
    return redirect(url_for("login"))

# ----------------- Upload & Results -----------------
@app.route("/upload", methods=["GET"])
def upload_page():
    if "user" not in session:
        return redirect(url_for("login"))
    return render_template("upload.html")

@app.route("/upload", methods=["POST"])
def handle_upload():
    if "user" not in session:
        return redirect(url_for("login"))

    file = request.files.get("file")
    if not file or file.filename == "":
        flash("Please upload an image.", "error")
        return redirect(url_for("upload_page"))
    if not allowed_file(file.filename):
        flash("Allowed formats: png, jpg, jpeg, webp.", "error")
        return redirect(url_for("upload_page"))

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    filename = secure_filename(file.filename)
    save_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(save_path)

    # --- AI analysis (dynamic) ---
    info = analyze_image(save_path)  # {'pred_type', 'vibe', 'color_name', 'color_hex', 'raw_label'}

    # --- Build dynamic recommendations ---
    recs = get_recommendations_dynamic(
        pred_type=info["pred_type"],
        color_name=info["color_name"],
        vibe=info["vibe"]
    )

    return render_template(
        "results.html",
        uploaded_filename=filename,
        recs=recs,
        detection_info=info
    )

# Serve uploaded files
@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

if __name__ == "__main__":
    app.run(debug=True)
