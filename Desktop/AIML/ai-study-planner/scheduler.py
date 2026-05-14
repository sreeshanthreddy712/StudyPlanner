"""
scheduler.py — Core scheduling engine for SmartPrep AI.

This module handles:
  1. Initial schedule generation (weight-based allocation)
  2. Adaptive rescheduling when a task is marked incomplete

Design philosophy:
  - Hard topics get 2x slots, Medium gets 1.5x, Easy gets 1x
  - Topics from subjects with lower completion get bumped up in priority
  - No single day is overloaded beyond MAX_HOURS_PER_DAY
  - Weekends and weekdays are treated equally (students prep differently)
"""

from datetime import date, timedelta
from collections import defaultdict
import math


# Maximum study hours we'll schedule in a single day.
# Anything beyond this is unrealistic for sustained retention.
MAX_HOURS_PER_DAY = 6.0

# Base hours allocated per "weight unit" — gets scaled to fit available time
BASE_HOURS_PER_WEIGHT = 1.0


def _business_days(start: date, end: date) -> list:
    """
    Returns list of dates from start to end (exclusive).
    We include all days — weekends are valid study days.
    """
    days = []
    cursor = start
    while cursor < end:
        days.append(cursor)
        cursor += timedelta(days=1)
    return days


def _hours_for_topic(weight: float, total_weight: float, available_days: int) -> float:
    """
    Proportionally allocate hours based on topic weight.
    Clamps to a minimum of 0.5h and maximum of MAX_HOURS_PER_DAY.
    """
    total_available_hours = available_days * MAX_HOURS_PER_DAY
    raw = (weight / total_weight) * total_available_hours
    return max(0.5, min(raw, MAX_HOURS_PER_DAY))


def generate_schedule(topics: list, exam_date_str: str, completion_map: dict = None) -> list:
    """
    Build a day-by-day study schedule.

    Args:
        topics: List of topic dicts from models.get_topics_for_plan()
        exam_date_str: 'YYYY-MM-DD' string for the exam date
        completion_map: {subject_name: completion_pct} — used for priority boost
                        when rescheduling. None for first-time generation.

    Returns:
        List of slot dicts: [{topic_id, slot_date, duration_hr}, ...]
    """
    if not topics:
        return []

    exam_date = date.fromisoformat(exam_date_str)
    today = date.today()

    # If the exam is today or in the past, still show something useful
    start_date = today if today < exam_date else exam_date - timedelta(days=1)
    available_days = _business_days(start_date, exam_date)

    if not available_days:
        return []

    # Sort topics: harder difficulty first, then boost subjects with low completion
    sorted_topics = _prioritize_topics(topics, completion_map)

    total_weight = sum(t["weight"] for t in sorted_topics)
    slots = []

    # Track hours already assigned per day so we don't overload
    day_load: dict[date, float] = defaultdict(float)

    for topic in sorted_topics:
        hours_needed = _hours_for_topic(topic["weight"], total_weight, len(available_days))
        slots.extend(_spread_topic(topic, hours_needed, available_days, day_load))

    return slots


def _prioritize_topics(topics: list, completion_map: dict) -> list:
    """
    Sort topics by effective priority:
      - Hard > Medium > Easy base priority
      - Subjects with lower completion get a bump
    """
    def priority_key(t):
        # Invert completion so 0% completion = highest priority boost
        subject_completion = 0.0
        if completion_map:
            subject_completion = completion_map.get(t["subject_name"], 0.0)

        # Lower completion → higher sort value (we sort descending)
        completion_boost = (100 - subject_completion) / 100.0

        return t["weight"] + completion_boost

    return sorted(topics, key=priority_key, reverse=True)


def _spread_topic(topic: dict, hours_needed: float, available_days: list, day_load: dict) -> list:
    """
    Distribute a topic's hours across multiple days to avoid overloading.
    We try to fit sessions in 1–2 hour chunks.

    Returns a list of slot dicts for this topic.
    """
    slots = []
    remaining = hours_needed

    # Preferred session length depends on difficulty
    session_size = {
        "Easy": 1.0,
        "Medium": 1.5,
        "Hard": 2.0
    }.get(topic["difficulty"], 1.0)

    for day in available_days:
        if remaining <= 0:
            break

        space_left = MAX_HOURS_PER_DAY - day_load[day]
        if space_left <= 0:
            continue

        # Don't put more than session_size in one day for this topic
        session = min(session_size, remaining, space_left)
        if session < 0.25:
            continue  # Too small a fragment, skip this day

        slots.append({
            "topic_id": topic["id"],
            "slot_date": day.isoformat(),
            "duration_hr": round(session, 2)
        })

        day_load[day] += session
        remaining -= session

    # If we ran out of days but still have time, append to the last available day
    # (better than losing the session)
    if remaining > 0.25 and available_days:
        last_day = available_days[-1]
        slots.append({
            "topic_id": topic["id"],
            "slot_date": last_day.isoformat(),
            "duration_hr": round(remaining, 2)
        })

    return slots


def reschedule_incomplete(plan_id: int, incomplete_slots: list, existing_schedule: list,
                          exam_date_str: str) -> list:
    """
    Adaptive rescheduler — called when a user marks a task as 'incomplete'.

    Strategy:
      1. Collect all incomplete slots
      2. Find future available days (today onward, before exam)
      3. Redistribute incomplete sessions into those days without blowing the daily cap
      4. Return the updated full schedule

    Args:
        plan_id: Used for filtering
        incomplete_slots: Slot dicts with status='incomplete'
        existing_schedule: Full schedule list from get_schedule()
        exam_date_str: Exam date

    Returns:
        List of updated slot dicts (id + new slot_date)
    """
    exam_date = date.fromisoformat(exam_date_str)
    today = date.today()
    future_days = _business_days(today, exam_date)

    if not future_days:
        return []  # No room to reschedule

    # Build current load map from non-incomplete future slots
    day_load: dict[str, float] = defaultdict(float)
    for slot in existing_schedule:
        if slot["status"] != "incomplete" and slot["slot_date"] >= today.isoformat():
            day_load[slot["slot_date"]] += slot["duration_hr"]

    updates = []

    for slot in incomplete_slots:
        hours_needed = slot["duration_hr"]
        remaining = hours_needed

        for day in future_days:
            if remaining <= 0:
                break

            space = MAX_HOURS_PER_DAY - day_load[day.isoformat()]
            if space <= 0:
                continue

            chunk = min(remaining, space)
            if chunk < 0.25:
                continue

            day_load[day.isoformat()] += chunk
            remaining -= chunk

            updates.append({
                "slot_id": slot["id"],
                "new_date": day.isoformat(),
                "duration_hr": round(chunk, 2)
            })

    return updates


def group_schedule_by_date(schedule: list) -> dict:
    """
    Group a flat schedule list into {date_str: [slots]} for template rendering.
    Sorts dates ascending.
    """
    grouped = defaultdict(list)
    for slot in schedule:
        grouped[slot["slot_date"]].append(slot)

    return dict(sorted(grouped.items()))


def compute_completion_map(schedule: list) -> dict:
    """
    Build {subject_name: completion_pct} from a schedule list.
    Used when regenerating/rescheduling to reprioritize topics.
    """
    totals = defaultdict(lambda: {"total": 0, "done": 0})

    for slot in schedule:
        subject = slot["subject_name"]
        totals[subject]["total"] += 1
        if slot["status"] == "complete":
            totals[subject]["done"] += 1

    result = {}
    for subject, counts in totals.items():
        pct = (counts["done"] / counts["total"] * 100) if counts["total"] else 0
        result[subject] = round(pct, 1)

    return result
