# Quick Start

## Gradescope Workflow

```python
from LatePenalty import gradescope_grade

# Initialize with credentials and course
gg = gradescope_grade(
    credentials_fp="credentials.json",
    course_id=12345,
    assignment_id=67890,
    gradescope_fp="grades.csv"
)

# Post grades with late penalty
# First run with post=False to preview
gg.post_to_canvas(
    target_assignment="HW1",
    passed_assignments=["HW1"],
    total_credit=120,  # 120 slip hours
    post=False         # preview mode
)

# Then set post=True to actually post
gg.post_to_canvas(
    target_assignment="HW1",
    passed_assignments=["HW1"],
    total_credit=120,
    post=True
)
```

## nbgrader Workflow

```python
from LatePenalty import nbgrader_grade

# Initialize
ng = nbgrader_grade(
    credentials_fp="credentials.json",
    course_id=12345,
    assignment_id=67890,
    grades_fp="grades.csv",
    late_exception_fp="late_exceptions.yaml"
)

# Post grades with slip day tracking
ng.post_to_canvas(
    target_assignment="A2",
    passed_assignments=["A1", "A2"],
    default_credit=7,              # 7 slip days
    late_submission_deadline=5,     # reject after 5 days
    post=True
)
```

## Late Exception YAML Format

Per-student late day exceptions are specified in YAML:

```yaml
student_1:
    allowed_late_days: 7
    reasons: sickness

student_3:
    allowed_late_days: 10
    reasons: family issue
```
