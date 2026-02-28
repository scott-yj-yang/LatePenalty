# nbgrader Late Penalty Tutorial

This tutorial walks through applying late penalties to nbgrader submissions.

## Prerequisites

- A `credentials.json` file (see [Authentication](../getting-started/authentication.md))
- An nbgrader CSV grades export
- Your Canvas course ID and assignment ID
- (Optional) A late exception YAML file

## Step 1: Initialize

```python
from LatePenalty import nbgrader_grade

ng = nbgrader_grade(
    credentials_fp="credentials.json",
    API_URL="https://canvas.ucsd.edu",
    course_id=12345,
    assignment_id=67890,
    grades_fp="grades.csv",
    late_exception_fp="late_exceptions.yaml",
    verbosity=1
)
```

## Step 2: Preview Grades

```python
ng.post_to_canvas(
    target_assignment="A2",
    passed_assignments=["A1", "A2"],
    default_credit=7,
    late_submission_deadline=5,
    post=False
)
```

## Step 3: Post Grades

```python
ng.post_to_canvas(
    target_assignment="A2",
    passed_assignments=["A1", "A2"],
    default_credit=7,
    late_submission_deadline=5,
    post=True
)
```

## Late Exceptions

Create a YAML file for per-student late day exceptions:

```yaml
student_1:
    allowed_late_days: 7
    reasons: sickness

student_3:
    allowed_late_days: 10
    reasons: family issue
```

Students listed in the exception file get extra slip days beyond the default.

## Late Day Calculation

- **3-hour grace period** on all submissions
- Late days are calculated as ceiling of (submission time - due date - 3 hours) / 24 hours
- Maximum 5 late days per submission
- If slip credit is exhausted, a **25% late penalty** is applied
- Submissions after the `late_submission_deadline` (default: 5 days) receive a score of 0
