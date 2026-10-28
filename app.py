
from flask import Flask, render_template, request, redirect, flash
import sqlite3
from pathlib import Path

app = Flask(__name__)
app.secret_key = "scholarship-demo"
DB = Path(__file__).with_name("scholarship.db")


def connect():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def setup():
    with connect() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS students (
            student_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            course TEXT NOT NULL,
            income REAL NOT NULL CHECK(income >= 0)
        );

        CREATE TABLE IF NOT EXISTS scholarships (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            min_marks REAL NOT NULL,
            income_limit REAL NOT NULL,
            award REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL REFERENCES students(student_id),
            scholarship_id INTEGER NOT NULL REFERENCES scholarships(id),
            marks REAL NOT NULL CHECK(marks BETWEEN 0 AND 100),
            status TEXT NOT NULL DEFAULT 'PENDING'
                CHECK(status IN ('PENDING','APPROVED','REJECTED'))
        );
        """)

        if con.execute("SELECT COUNT(*) FROM scholarships").fetchone()[0] == 0:
            con.executemany(
                "INSERT INTO scholarships VALUES (?,?,?,?,?)",
                [
                    (1, "Merit Scholarship", 60, 300000, 10000),
                    (2, "Excellence Scholarship", 85, 200000, 20000)
                ]
            )

        if con.execute("SELECT COUNT(*) FROM students").fetchone()[0] == 0:
            con.executemany(
                "INSERT INTO students VALUES (?,?,?,?)",
                [
                    (101, "Sahil Khan", "BCA", 200000),
                    (102, "Aman Verma", "BCA", 180000)
                ]
            )

        if con.execute("SELECT COUNT(*) FROM applications").fetchone()[0] == 0:
            con.executemany(
                """INSERT INTO applications
                   (student_id, scholarship_id, marks, status)
                   VALUES (?,?,?,?)""",
                [(101, 1, 85, "PENDING"), (102, 2, 90, "PENDING")]
            )


@app.route("/")
def home():
    with connect() as con:
        students = con.execute(
            "SELECT * FROM students ORDER BY student_id"
        ).fetchall()

        scholarships = con.execute(
            "SELECT * FROM scholarships ORDER BY id"
        ).fetchall()

        applications = con.execute("""
            SELECT a.id, a.student_id, s.name AS student_name,
                   s.course, s.income, sh.name AS scholarship_name,
                   sh.award, a.marks, a.status
            FROM applications a
            JOIN students s ON s.student_id = a.student_id
            JOIN scholarships sh ON sh.id = a.scholarship_id
            ORDER BY a.id DESC
        """).fetchall()

    return render_template(
        "index.html",
        students=students,
        scholarships=scholarships,
        applications=applications
    )


@app.post("/students/add")
def add_student():
    try:
        sid = int(request.form["student_id"])
        name = request.form["name"].strip()
        course = request.form["course"].strip()
        income = float(request.form["income"])

        if sid <= 0 or not name or not course or income < 0:
            raise ValueError

        with connect() as con:
            con.execute(
                "INSERT INTO students VALUES (?,?,?,?)",
                (sid, name, course, income)
            )
        flash("Student added successfully!", "success")

    except ValueError:
        flash("Please enter valid student details.", "error")
    except sqlite3.IntegrityError:
        flash("Student ID already exists.", "error")

    return redirect("/")


@app.post("/students/delete/<int:sid>")
def delete_student(sid):
    with connect() as con:
        linked = con.execute(
            "SELECT COUNT(*) FROM applications WHERE student_id=?",
            (sid,)
        ).fetchone()[0]

        if linked:
            flash("Remove this student's applications first.", "error")
        else:
            con.execute("DELETE FROM students WHERE student_id=?", (sid,))
            flash("Student deleted.", "success")

    return redirect("/")


@app.post("/applications/add")
def add_application():
    try:
        sid = int(request.form["student_id"])
        shid = int(request.form["scholarship_id"])
        marks = float(request.form["marks"])

        if not 0 <= marks <= 100:
            raise ValueError

        with connect() as con:
            student = con.execute(
                "SELECT income FROM students WHERE student_id=?", (sid,)
            ).fetchone()
            scholarship = con.execute(
                "SELECT * FROM scholarships WHERE id=?", (shid,)
            ).fetchone()

            if student is None or scholarship is None:
                flash("Select a valid student and scholarship.", "error")
            else:
                eligible = (
                    marks >= scholarship["min_marks"]
                    and student["income"] <= scholarship["income_limit"]
                )
                status = "PENDING" if eligible else "REJECTED"

                con.execute("""
                    INSERT INTO applications
                    (student_id, scholarship_id, marks, status)
                    VALUES (?,?,?,?)
                """, (sid, shid, marks, status))

                flash(
                    "Application added: " + status,
                    "success" if eligible else "error"
                )

    except (ValueError, TypeError):
        flash("Marks must be between 0 and 100.", "error")

    return redirect("/")


@app.post("/applications/approve/<int:aid>")
def approve(aid):
    with connect() as con:
        row = con.execute("""
            SELECT a.status, a.marks, s.income,
                   sh.min_marks, sh.income_limit
            FROM applications a
            JOIN students s ON s.student_id = a.student_id
            JOIN scholarships sh ON sh.id = a.scholarship_id
            WHERE a.id=?
        """, (aid,)).fetchone()

        if row is None:
            flash("Application not found.", "error")
        elif row["status"] != "PENDING":
            flash("Only pending applications can be approved.", "error")
        elif (row["marks"] < row["min_marks"]
              or row["income"] > row["income_limit"]):
            con.execute(
                "UPDATE applications SET status='REJECTED' WHERE id=?", (aid,)
            )
            flash("Eligibility criteria not met.", "error")
        else:
            con.execute(
                "UPDATE applications SET status='APPROVED' WHERE id=?", (aid,)
            )
            flash("Application approved!", "success")

    return redirect("/")


@app.post("/applications/reject/<int:aid>")
def reject(aid):
    with connect() as con:
        cur = con.execute("""
            UPDATE applications SET status='REJECTED'
            WHERE id=? AND status='PENDING'
        """, (aid,))

        flash(
            "Application rejected." if cur.rowcount else
            "Only pending applications can be rejected.",
            "success" if cur.rowcount else "error"
        )

    return redirect("/")


@app.post("/applications/delete/<int:aid>")
def delete_application(aid):
    with connect() as con:
        con.execute("DELETE FROM applications WHERE id=?", (aid,))
    flash("Application removed.", "success")
    return redirect("/")


if __name__ == "__main__":
    setup()
    app.run(host="127.0.0.1", port=5000, debug=False)
