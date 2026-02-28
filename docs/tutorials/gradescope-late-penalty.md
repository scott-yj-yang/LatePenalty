# Gradescope Late Penalty Tutorial

This tutorial walks through applying late penalties to Gradescope submissions.

## Prerequisites

- A `credentials.json` file (see [Authentication](../getting-started/authentication.md))
- A Gradescope CSV export file
- Your Canvas course ID and assignment ID

## Step 1: Initialize

```python
from LatePenalty import gradescope_grade

gg = gradescope_grade(
    credentials_fp="credentials.json",
    API_URL="https://canvas.ucsd.edu",
    course_id=12345,
    assignment_id=67890,
    gradescope_fp="grades.csv",
    verbosity=1
)
```

## Step 2: Preview Grades

Run with `post=False` to preview what will be posted:

```python
gg.post_to_canvas(
    target_assignment="HW1",
    passed_assignments=["HW1"],
    total_credit=120,
    post=False
)
```

## Step 3: Post Grades

When satisfied with the preview, set `post=True`:

```python
gg.post_to_canvas(
    target_assignment="HW1",
    passed_assignments=["HW1"],
    total_credit=120,
    post=True
)
```

## Multi-Component Assignments

If an assignment has multiple Gradescope components (e.g., autograder + manual):

```python
gg.post_to_canvas(
    target_assignment="HW1",
    passed_assignments=["HW1"],
    components=["HW1 - Autograder", "HW1 - Manual"],
    total_credit=120,
    post=True
)
```

## Slip Hours

The `total_credit` parameter sets the total slip hours available. If a student exceeds their credit, a 25% late penalty is applied.

```python
# Check credit balances
balance = gg.calculate_credit_balance(
    passed_assignments=["HW1", "HW2"],
    total_credit=120
)
print(balance)
```
