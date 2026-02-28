# LatePenalty

> Apply late penalties to Gradescope and nbgrader submissions when posting grades to Canvas LMS.

[![CI](https://github.com/scott-yj-yang/LatePenalty/actions/workflows/test.yaml/badge.svg)](https://github.com/scott-yj-yang/LatePenalty/actions/workflows/test.yaml)

## Installation

```bash
pip install LatePenalty
```

Or install from source:

```bash
git clone https://github.com/scott-yj-yang/LatePenalty.git
cd LatePenalty
pip install -e .
```

## Quick Start

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

## Documentation

Full documentation: [https://scott-yj-yang.github.io/LatePenalty](https://scott-yj-yang.github.io/LatePenalty)

## Features

- **Gradescope Integration** — Load CSV exports, calculate slip hours, apply 25% late penalty
- **nbgrader Integration** — Parse timestamps with 3-hour grace period, manage slip days
- **Slip Credit System** — Configurable total credit with per-student exceptions via YAML
- **Canvas Posting** — Post grades with personalized feedback messages
- **Multi-Component Scoring** — Combine autograder + manual grading scores

## Credentials

Create a `credentials.json` file:

```json
{
    "Canvas Token": "your-canvas-token",
    "GitHub Token": "your-github-token"
}
```

See the [Authentication guide](https://scott-yj-yang.github.io/LatePenalty/getting-started/authentication/) for details.

## License

Apache 2.0
