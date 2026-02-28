"""Shared test fixtures for LatePenalty test suite."""

import json
import pytest
import pandas as pd
import numpy as np
from unittest.mock import MagicMock, patch
from datetime import datetime


# ---------------------------------------------------------------------------
# Credential fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def credentials(tmp_path):
    """Create a temporary credentials.json and return its path."""
    creds = {"Canvas Token": "fake-canvas-token", "GitHub Token": "fake-github-token"}
    fp = tmp_path / "credentials.json"
    fp.write_text(json.dumps(creds))
    return str(fp)


@pytest.fixture
def bad_credentials(tmp_path):
    """Create a credentials.json missing required keys."""
    fp = tmp_path / "credentials.json"
    fp.write_text(json.dumps({"wrong_key": "value"}))
    return str(fp)


# ---------------------------------------------------------------------------
# Canvas mock fixtures
# ---------------------------------------------------------------------------

def _make_mock_user(email_prefix, canvas_id, short_name=None):
    """Helper to create a mock Canvas user object."""
    user = MagicMock()
    user.email = f"{email_prefix}@ucsd.edu"
    user.id = canvas_id
    user.short_name = short_name or email_prefix.title()
    return user


@pytest.fixture
def mock_students():
    """Three mock student users."""
    return [
        _make_mock_user("alice", 101, "Alice Smith"),
        _make_mock_user("bob", 102, "Bob Jones"),
        _make_mock_user("carol", 103, "Carol Lee"),
    ]


@pytest.fixture
def mock_staff():
    """Two mock staff users (TA and instructor)."""
    return [
        _make_mock_user("instructor", 901, "Prof Instructor"),
        _make_mock_user("ta_person", 902, "TA Person"),
    ]


@pytest.fixture
def mock_course(mock_students, mock_staff):
    """Mock Canvas course with students and staff pre-loaded."""
    course = MagicMock()
    course.name = "Test Course"
    course.id = 99999

    def get_users_side_effect(enrollment_type=None):
        if enrollment_type == ['student']:
            return mock_students
        elif enrollment_type == ['teacher', 'ta', 'designer']:
            return mock_staff
        return mock_students + mock_staff

    course.get_users.side_effect = get_users_side_effect
    return course


@pytest.fixture
def mock_assignment():
    """Mock Canvas assignment."""
    assignment = MagicMock()
    assignment.name = "Homework 1"
    assignment.id = 42
    return assignment


@pytest.fixture
def mock_canvas_api(mock_course, mock_assignment):
    """Patch canvasapi.Canvas for gradescope module and return (MockCanvas, canvas_instance, mock_course, mock_assignment)."""
    with patch("LatePenalty.gradescope.Canvas") as MockCanvas:
        canvas_instance = MagicMock()
        MockCanvas.return_value = canvas_instance
        canvas_instance.get_activity_stream_summary.return_value = {}
        canvas_instance.get_course.return_value = mock_course
        mock_course.get_assignment.return_value = mock_assignment
        yield MockCanvas, canvas_instance, mock_course, mock_assignment


@pytest.fixture
def mock_canvas_api_nbgrader(mock_course, mock_assignment):
    """Patch canvasapi.Canvas for nbgrader module."""
    with patch("LatePenalty.nbgrader.Canvas") as MockCanvas:
        canvas_instance = MagicMock()
        MockCanvas.return_value = canvas_instance
        canvas_instance.get_activity_stream_summary.return_value = {}
        canvas_instance.get_course.return_value = mock_course
        mock_course.get_assignment.return_value = mock_assignment
        yield MockCanvas, canvas_instance, mock_course, mock_assignment


# ---------------------------------------------------------------------------
# Gradescope data fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def gradescope_csv(tmp_path):
    """Create a minimal Gradescope CSV and return its path."""
    data = {
        "Email": ["alice@ucsd.edu", "bob@ucsd.edu", "carol@ucsd.edu"],
        "HW1": [90.0, 85.0, 0.0],
        "HW1 - Lateness (H:M:S)": ["00:00:00", "25:30:00", "00:00:00"],
        "HW2": [80.0, 75.0, 95.0],
        "HW2 - Lateness (H:M:S)": ["00:00:00", "00:00:00", "50:00:00"],
        "Component1": [40.0, 35.0, 0.0],
        "Component2": [50.0, 50.0, 0.0],
    }
    df = pd.DataFrame(data)
    fp = tmp_path / "gradescope.csv"
    df.to_csv(fp, index=False)
    return str(fp)


# ---------------------------------------------------------------------------
# nbgrader data fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def nbgrader_csv(tmp_path):
    """Create a minimal nbgrader CSV and return its path."""
    data = {
        "student_id": ["alice", "bob", "carol", "alice", "bob", "carol"],
        "assignment": ["A1", "A1", "A1", "A2", "A2", "A2"],
        "duedate": [
            "2024-01-15 23:59:59", "2024-01-15 23:59:59", "2024-01-15 23:59:59",
            "2024-01-22 23:59:59", "2024-01-22 23:59:59", "2024-01-22 23:59:59",
        ],
        "timestamp": [
            "2024-01-15 20:00:00.000000",  # on-time
            "2024-01-17 10:00:00.000000",  # ~1.4 days late (after 3h tolerance)
            "2024-01-15 23:00:00.000000",  # on-time (before deadline)
            "2024-01-22 20:00:00.000000",  # on-time
            "2024-01-22 20:00:00.000000",  # on-time
            "2024-01-25 10:00:00.000000",  # ~2.4 days late (after 3h tolerance)
        ],
        "raw_score": [90.0, 85.0, 95.0, 80.0, 75.0, 70.0],
        "max_score": [100.0, 100.0, 100.0, 100.0, 100.0, 100.0],
    }
    df = pd.DataFrame(data)
    fp = tmp_path / "grades.csv"
    df.to_csv(fp, index=False)
    return str(fp)


@pytest.fixture
def late_exception_yaml(tmp_path):
    """Create a late exception YAML file and return its path."""
    import yaml
    exceptions = {
        "bob": {"allowed_late_days": 10, "reasons": "accommodation"},
        "carol": {"allowed_late_days": 3, "reasons": "sickness"},
    }
    fp = tmp_path / "late_exception.yaml"
    fp.write_text(yaml.dump(exceptions))
    return str(fp)
