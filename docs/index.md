# LatePenalty

> Apply late penalties to Gradescope and nbgrader submissions when posting grades to Canvas LMS.

LatePenalty automates the process of applying late submission penalties when publishing grades from **Gradescope** or **nbgrader** to **Canvas LMS**. It supports configurable slip day/hour systems with personalized feedback messages.

## Features

- **Gradescope Integration** — Load Gradescope CSV exports, calculate slip hours, apply 25% late penalty
- **nbgrader Integration** — Parse nbgrader timestamps with 3-hour grace period, manage slip days
- **Slip Credit System** — Configurable total credit (hours or days) with per-student exceptions
- **Canvas Posting** — Post grades with personalized feedback messages via Canvas API
- **Multi-Component Scoring** — Combine autograder + manual grading into single assignments
- **COGS108 A1 Grading** — GitHub validation (user, repo, files, PR) for COGS108

## Quick Start

```bash
pip install LatePenalty
```

```python
from LatePenalty import gradescope_grade

gg = gradescope_grade(
    credentials_fp="credentials.json",
    course_id=12345,
    assignment_id=67890,
    gradescope_fp="grades.csv"
)

gg.post_to_canvas(
    target_assignment="HW1",
    passed_assignments=["HW1"],
    post=True
)
```

See the [Getting Started](getting-started/installation.md) guide for full setup instructions.
