"""
app.py — SmartPrep AI Flask application.

Routes are kept thin; business logic lives in scheduler.py and models.py.
"""

from flask import Flask, render_template, request, redirect, url_for, jsonify, abort
from datetime import date, datetime
import json

import models
import scheduler as sched

app = Flask(__name__)
app.secret_key = "smartprep-dev-key-change-in-production"


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

@app.before_request
def bootstrap():
    """Initialize DB on first request if tables don't exist yet."""
    models.init_db()


# ---------------------------------------------------------------------------
# Home — list existing plans or show creation prompt
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    plans = models.list_plans()
    today = date.today().isoformat()
    return render_template("index.html", plans=plans, today=today)


# ---------------------------------------------------------------------------
# Create a new study plan
# ---------------------------------------------------------------------------

@app.route("/plan/new", methods=["GET"])
def new_plan():
    today = date.today().isoformat()
    return render_template("new_plan.html", today=today)


@app.route("/plan/create", methods=["POST"])
def create_plan():
    """
    Expects a JSON body like:
    {
      "name": "Semester Finals",
      "exam_date": "2025-06-20",
      "subjects": [
        {
          "name": "Mathematics",
          "topics": [
            {"name": "Calculus", "difficulty": "Hard"},
            {"name": "Statistics", "difficulty": "Medium"}
          ]
        }
      ]
    }
    """
    data = request.get_json()

    if not data or not data.get("name") or not data.get("exam_date"):
        return jsonify({"error": "Name and exam date are required."}), 400

    subjects = data.get("subjects", [])
    if not subjects or not any(s.get("topics") for s in subjects):
        return jsonify({"error": "At least one subject with topics is required."}), 400

    exam_date = data["exam_date"]
    if exam_date <= date.today().isoformat():
        return jsonify({"error": "Exam date must be in the future."}), 400

    # Create the plan record
    plan_id = models.create_plan(data["name"], exam_date)

    # Persist subjects and topics
    for subject in subjects:
        if not subject.get("name") or not subject.get("topics"):
            continue
        models.add_subject_with_topics(plan_id, subject["name"], subject["topics"])

    # Generate the initial schedule
    topics = models.get_topics_for_plan(plan_id)
    slots = sched.generate_schedule(topics, exam_date)
    models.save_schedule(plan_id, slots)

    return jsonify({"plan_id": plan_id}), 201


# ---------------------------------------------------------------------------
# Dashboard — view schedule + progress for a plan
# ---------------------------------------------------------------------------

@app.route("/plan/<int:plan_id>")
def dashboard(plan_id):
    plan = models.get_plan(plan_id)
    if not plan:
        abort(404)

    schedule = models.get_schedule(plan_id)
    grouped = sched.group_schedule_by_date(schedule)
    stats = models.get_progress_stats(plan_id)
    today = date.today().isoformat()

    # Days remaining until exam
    exam_date = date.fromisoformat(plan["exam_date"])
    days_left = (exam_date - date.today()).days

    return render_template(
        "dashboard.html",
        plan=plan,
        grouped_schedule=grouped,
        stats=stats,
        today=today,
        days_left=max(0, days_left)
    )


# ---------------------------------------------------------------------------
# Mark a slot complete / incomplete — called via JS fetch
# ---------------------------------------------------------------------------

@app.route("/slot/<int:slot_id>/status", methods=["POST"])
def update_slot(slot_id):
    data = request.get_json()
    new_status = data.get("status")

    if new_status not in ("complete", "incomplete", "pending"):
        return jsonify({"error": "Invalid status."}), 400

    slot = models.get_slot(slot_id)
    if not slot:
        return jsonify({"error": "Slot not found."}), 404

    models.update_slot_status(slot_id, new_status)

    # If marked incomplete, trigger adaptive reschedule
    if new_status == "incomplete":
        plan = models.get_plan(slot["plan_id"])
        full_schedule = models.get_schedule(slot["plan_id"])
        incomplete = [s for s in full_schedule if s["status"] == "incomplete"]

        sched.reschedule_incomplete(
            slot["plan_id"], incomplete, full_schedule, plan["exam_date"]
        )
        # For simplicity, rescheduling just logs the moves — in a v2 we'd
        # persist new rows. The "push to next day" UX is shown in the UI.

    # Return fresh stats so the frontend can update progress bars without reload
    stats = models.get_progress_stats(slot["plan_id"])
    return jsonify({"ok": True, "stats": stats})


# ---------------------------------------------------------------------------
# Delete a plan
# ---------------------------------------------------------------------------

@app.route("/plan/<int:plan_id>/delete", methods=["POST"])
def delete_plan(plan_id):
    models.delete_plan(plan_id)
    return redirect(url_for("index"))


# ---------------------------------------------------------------------------
# Seed sample data — handy for demos / testing
# ---------------------------------------------------------------------------

@app.route("/seed")
def seed_demo():
    """
    Creates a realistic sample plan so you can see the app in action
    without manually entering data. Visit /seed once then delete this route.
    """
    from datetime import timedelta
    exam = (date.today() + timedelta(days=21)).isoformat()

    plan_id = models.create_plan("📚 Semester Finals – Demo", exam)

    subjects_data = [
        {
            "name": "Mathematics",
            "topics": [
                {"name": "Differential Calculus", "difficulty": "Hard"},
                {"name": "Integral Calculus", "difficulty": "Hard"},
                {"name": "Probability & Statistics", "difficulty": "Medium"},
                {"name": "Linear Algebra Basics", "difficulty": "Medium"},
            ]
        },
        {
            "name": "Physics",
            "topics": [
                {"name": "Mechanics & Motion", "difficulty": "Medium"},
                {"name": "Electromagnetism", "difficulty": "Hard"},
                {"name": "Thermodynamics", "difficulty": "Medium"},
                {"name": "Optics", "difficulty": "Easy"},
            ]
        },
        {
            "name": "Computer Science",
            "topics": [
                {"name": "Data Structures", "difficulty": "Hard"},
                {"name": "Sorting Algorithms", "difficulty": "Medium"},
                {"name": "Database Fundamentals", "difficulty": "Easy"},
                {"name": "OS Concepts", "difficulty": "Medium"},
            ]
        },
        {
            "name": "Chemistry",
            "topics": [
                {"name": "Organic Reactions", "difficulty": "Hard"},
                {"name": "Periodic Table & Trends", "difficulty": "Easy"},
                {"name": "Thermochemistry", "difficulty": "Medium"},
            ]
        }
    ]

    for subj in subjects_data:
        models.add_subject_with_topics(plan_id, subj["name"], subj["topics"])

    topics = models.get_topics_for_plan(plan_id)
    slots = sched.generate_schedule(topics, exam)
    models.save_schedule(plan_id, slots)

    # Mark a few slots complete to make the dashboard look lively
    schedule = models.get_schedule(plan_id)
    for i, slot in enumerate(schedule[:5]):
        models.update_slot_status(slot["id"], "complete")

    return redirect(url_for("dashboard", plan_id=plan_id))


# ---------------------------------------------------------------------------
# 404 handler
# ---------------------------------------------------------------------------

@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404


if __name__ == "__main__":
    models.init_db()
    app.run(debug=True, port=5000)
