# ⚡ SmartPrep AI

> An intelligent study planner that generates adaptive schedules based on topic difficulty and tracks your progress as you go.

![Python](https://img.shields.io/badge/Python-3.10+-blue?style=flat-square)
![Flask](https://img.shields.io/badge/Flask-3.0-lightgrey?style=flat-square)
![SQLite](https://img.shields.io/badge/SQLite-3-green?style=flat-square)
![License](https://img.shields.io/badge/License-MIT-yellow?style=flat-square)

---

## Overview

SmartPrep AI takes the guesswork out of exam preparation. You tell it what subjects and topics you need to cover, how hard each topic is, and when your exam is — and it builds a realistic, evenly-distributed study schedule with more time allocated to harder material.

As you study, mark sessions complete. If you miss one, the planner adapts and pushes that session forward to the next available slot without overloading your day.

---

## Features

- **Difficulty-weighted scheduling** — Hard topics get 2× time, Medium 1.5×, Easy 1×
- **Adaptive rescheduling** — Incomplete sessions are redistributed automatically
- **Priority rebalancing** — Subjects with lower completion get bumped up in future cycles
- **Progress dashboard** — Overall % complete, per-subject breakdown, daily streak counter
- **Daily load cap** — No single day gets more than 6 hours of study scheduled
- **Demo data** — One-click seed route to populate a realistic multi-subject plan

---

## Tech Stack

| Layer     | Technology                        |
|-----------|-----------------------------------|
| Backend   | Python 3.10+, Flask 3.0           |
| Database  | SQLite 3 (via standard library)   |
| Frontend  | Vanilla HTML, CSS, JavaScript     |
| Fonts     | DM Serif Display + DM Sans        |

No ORM, no frontend framework — intentionally lightweight and transparent.

---

## Project Structure

```
ai-study-planner/
│
├── app.py              # Flask routes (thin controllers)
├── models.py           # DB schema, helpers, stats queries
├── scheduler.py        # Scheduling & rescheduling logic
├── requirements.txt
├── README.md
│
├── templates/
│   ├── base.html       # Shared nav + layout
│   ├── index.html      # Home / plan list
│   ├── new_plan.html   # Plan creation form
│   ├── dashboard.html  # Schedule + progress view
│   └── 404.html
│
├── static/
│   ├── style.css       # Full stylesheet (CSS variables, responsive)
│   └── script.js       # Form builder, mark-complete, live stat updates
│
└── database.db         # Auto-created on first run
```

---

## How to Run Locally

### 1. Clone the repo

```bash
git clone https://github.com/yourusername/smartprep-ai.git
cd smartprep-ai
```

### 2. Create a virtual environment

```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Run the app

```bash
python app.py
```

Visit [http://localhost:5000](http://localhost:5000) in your browser.

### 5. Load demo data (optional)

Go to [http://localhost:5000/seed](http://localhost:5000/seed) to create a pre-populated sample plan with Mathematics, Physics, Computer Science, and Chemistry.

---

## Scheduling Algorithm

1. **Compute topic weights** — Easy=1.0, Medium=1.5, Hard=2.0
2. **Sort topics by priority** — Higher weight first; subjects with lower completion get an additional boost when rescheduling
3. **Allocate hours proportionally** — Each topic receives `(weight / total_weight) × total_available_hours`
4. **Spread across days** — Sessions are chunked by preferred session size (1h Easy, 1.5h Medium, 2h Hard) and placed into days that still have capacity under the 6h/day cap
5. **Reschedule incomplete** — When a session is flagged incomplete, remaining hours are pushed into the nearest future days that have headroom

---

## Future Improvements

- [ ] **User accounts** — Multi-user support with login/session
- [ ] **Spaced repetition** — Schedule review sessions based on the forgetting curve
- [ ] **Calendar export** — Export schedule to `.ics` for Google Calendar / Apple Calendar
- [ ] **Mobile app** — PWA or React Native version for on-the-go access
- [ ] **Study timer** — Built-in Pomodoro timer that auto-marks sessions complete
- [ ] **AI topic suggestions** — Use an LLM to suggest subtopics based on syllabus input
- [ ] **Email reminders** — Daily digest of what to study

---

## License

MIT — use it, fork it, learn from it.

---

*Built as a portfolio project demonstrating full-stack Python/Flask development, scheduling algorithms, and clean UI design.*
