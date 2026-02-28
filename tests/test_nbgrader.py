"""Tests for LatePenalty.nbgrader — nbgrader_grade class."""

import json
import pytest
import pandas as pd
import numpy as np
from unittest.mock import MagicMock, patch, call
from datetime import datetime
from LatePenalty.nbgrader import nbgrader_grade


# ===========================================================================
# Auth and Setup Tests
# ===========================================================================


class TestAuthCanvas:
    """Tests for Canvas API authentication."""

    def test_auth_loads_token(self, credentials, mock_canvas_api_nbgrader):
        """auth_canvas reads the JSON and initialises Canvas with correct URL and token."""
        MockCanvas, canvas_instance, _, _ = mock_canvas_api_nbgrader
        ng = nbgrader_grade(verbosity=0)
        ng.auth_canvas(credentials)
        MockCanvas.assert_called_once_with("https://canvas.ucsd.edu", "fake-canvas-token")
        assert ng.API_KEY == "fake-canvas-token"
        assert ng.GITHUB_TOKEN == "fake-github-token"

    def test_auth_calls_activity_stream(self, credentials, mock_canvas_api_nbgrader):
        """auth_canvas verifies the connection by fetching the activity stream."""
        _, canvas_instance, _, _ = mock_canvas_api_nbgrader
        ng = nbgrader_grade(verbosity=0)
        ng.auth_canvas(credentials)
        canvas_instance.get_activity_stream_summary.assert_called_once()

    def test_missing_file_raises(self, mock_canvas_api_nbgrader):
        """auth_canvas raises FileNotFoundError for a non-existent file."""
        ng = nbgrader_grade(verbosity=0)
        with pytest.raises(FileNotFoundError):
            ng.auth_canvas("/no/such/credentials.json")

    def test_bad_keys_raises(self, bad_credentials, mock_canvas_api_nbgrader):
        """auth_canvas raises KeyError when required keys are absent."""
        ng = nbgrader_grade(verbosity=0)
        with pytest.raises(KeyError):
            ng.auth_canvas(bad_credentials)


class TestSetCourse:
    """Tests for course setup and student roster loading."""

    def test_fetches_students(self, credentials, mock_canvas_api_nbgrader, mock_course):
        """set_course fetches students with enrollment_type=['student']."""
        ng = nbgrader_grade(verbosity=0)
        ng.auth_canvas(credentials)
        ng.set_course(99999)
        mock_course.get_users.assert_called_once_with(enrollment_type=["student"])

    def test_builds_email_to_canvas_id(self, credentials, mock_canvas_api_nbgrader):
        """set_course builds the email_to_canvas_id mapping correctly."""
        ng = nbgrader_grade(verbosity=0)
        ng.auth_canvas(credentials)
        ng.set_course(99999)
        assert ng.email_to_canvas_id == {"alice": 101, "bob": 102, "carol": 103}

    def test_builds_canvas_id_to_email(self, credentials, mock_canvas_api_nbgrader):
        """set_course builds the canvas_id_to_email mapping correctly."""
        ng = nbgrader_grade(verbosity=0)
        ng.auth_canvas(credentials)
        ng.set_course(99999)
        assert ng.canvas_id_to_email == {101: "alice", 102: "bob", 103: "carol"}

    def test_user_count(self, credentials, mock_canvas_api_nbgrader):
        """set_course stores all fetched user objects."""
        ng = nbgrader_grade(verbosity=0)
        ng.auth_canvas(credentials)
        ng.set_course(99999)
        assert len(ng.users) == 3


class TestLoadGradesCsv:
    """Tests for loading nbgrader CSV data."""

    def test_loads_csv(self, nbgrader_csv, mock_canvas_api_nbgrader):
        """load_grades_csv creates a DataFrame with the expected shape."""
        ng = nbgrader_grade(verbosity=0)
        ng.load_grades_csv(nbgrader_csv)
        assert ng.grades is not None
        assert len(ng.grades) == 6  # 3 students x 2 assignments

    def test_parses_assignments(self, nbgrader_csv, mock_canvas_api_nbgrader):
        """load_grades_csv triggers _parse_assignments and populates grades_by_assignment."""
        ng = nbgrader_grade(verbosity=0)
        ng.load_grades_csv(nbgrader_csv)
        assert "A1" in ng.grades_by_assignment
        assert "A2" in ng.grades_by_assignment

    def test_assignment_students(self, nbgrader_csv, mock_canvas_api_nbgrader):
        """Each parsed assignment DataFrame is indexed by student_id."""
        ng = nbgrader_grade(verbosity=0)
        ng.load_grades_csv(nbgrader_csv)
        a1 = ng.grades_by_assignment["A1"]
        assert list(sorted(a1.index)) == ["alice", "bob", "carol"]

    def test_raises_on_empty(self, tmp_path, mock_canvas_api_nbgrader):
        """_parse_assignments raises ValueError when the DataFrame is empty."""
        # Create an empty CSV with only headers
        fp = tmp_path / "empty.csv"
        pd.DataFrame(columns=["student_id", "assignment", "duedate", "timestamp", "raw_score", "max_score"]).to_csv(
            fp, index=False
        )
        ng = nbgrader_grade(verbosity=0)
        with pytest.raises(ValueError, match="grades has not been loaded"):
            ng.load_grades_csv(str(fp))


class TestLoadLateException:
    """Tests for loading late exception YAML."""

    def test_loads_yaml(self, late_exception_yaml, mock_canvas_api_nbgrader):
        """load_late_exception populates the late_exception dict from YAML."""
        ng = nbgrader_grade(verbosity=0)
        ng.load_late_exception(late_exception_yaml)
        assert "bob" in ng.late_exception
        assert ng.late_exception["bob"]["allowed_late_days"] == 10
        assert "carol" in ng.late_exception
        assert ng.late_exception["carol"]["allowed_late_days"] == 3

    def test_default_is_empty_dict(self, mock_canvas_api_nbgrader):
        """Without loading any YAML, late_exception is an empty dict."""
        ng = nbgrader_grade(verbosity=0)
        assert ng.late_exception == {}


# ===========================================================================
# Late Day Calculation Tests
# ===========================================================================


class TestCalculateLateDays:
    """Tests for _calculate_late_days and get_late_days."""

    def test_on_time_returns_zero(self, nbgrader_csv):
        """An on-time submission returns 0 late days."""
        ng = nbgrader_grade(verbosity=0)
        ng.load_grades_csv(nbgrader_csv)
        # alice submitted A1 at 20:00, due 23:59:59 => on-time
        assert ng.get_late_days("A1", "alice") == 0

    def test_late_submission_with_tolerance(self, nbgrader_csv):
        """Bob's A1 submission is ~34h past due; after 3h tolerance => 2 late days."""
        ng = nbgrader_grade(verbosity=0)
        ng.load_grades_csv(nbgrader_csv)
        # bob: 2024-01-17 10:00:00 - 2024-01-15 23:59:59 = 34h0m1s
        # adjusted: 34h0m1s - 3h = 31h0m1s => ceil(31.0003/24) = ceil(1.29) = 2
        assert ng.get_late_days("A1", "bob") == 2

    def test_carol_a2_late(self, nbgrader_csv):
        """Carol's A2 submission is ~58h past due; after 3h tolerance => 3 late days."""
        ng = nbgrader_grade(verbosity=0)
        ng.load_grades_csv(nbgrader_csv)
        # carol: 2024-01-25 10:00:00 - 2024-01-22 23:59:59 = 58h0m1s
        # adjusted: 58h0m1s - 3h = 55h0m1s => ceil(55.0003/24) = ceil(2.29) = 3
        assert ng.get_late_days("A2", "carol") == 3

    def test_missing_student_returns_zero(self, nbgrader_csv):
        """A student not in the assignment data returns 0 late days."""
        ng = nbgrader_grade(verbosity=0)
        ng.load_grades_csv(nbgrader_csv)
        assert ng.get_late_days("A1", "nonexistent_student") == 0

    def test_before_deadline_within_tolerance(self, nbgrader_csv):
        """Carol's A1 submission is 59m59s early => 0 late days."""
        ng = nbgrader_grade(verbosity=0)
        ng.load_grades_csv(nbgrader_csv)
        assert ng.get_late_days("A1", "carol") == 0

    def test_late_days_stored_in_dict(self, nbgrader_csv):
        """late_days_by_assignment contains Series indexed by student_id."""
        ng = nbgrader_grade(verbosity=0)
        ng.load_grades_csv(nbgrader_csv)
        assert "A1" in ng.late_days_by_assignment
        assert isinstance(ng.late_days_by_assignment["A1"], pd.Series)


class TestCalculateCreditBalance:
    """Tests for calculate_credit_balance."""

    def test_default_credit_on_time(self, nbgrader_csv):
        """An on-time student retains the full default credit."""
        ng = nbgrader_grade(verbosity=0)
        ng.load_grades_csv(nbgrader_csv)
        # alice was on-time for A1, default_credit=5
        balance = ng.calculate_credit_balance(["A1"], "alice", default_credit=5)
        assert balance == 5

    def test_credit_deducted_for_late(self, nbgrader_csv):
        """Bob used 2 late days on A1; balance should be 5 - 2 = 3."""
        ng = nbgrader_grade(verbosity=0)
        ng.load_grades_csv(nbgrader_csv)
        balance = ng.calculate_credit_balance(["A1"], "bob", default_credit=5)
        assert balance == 3

    def test_late_exception_overrides_default(self, nbgrader_csv, late_exception_yaml):
        """Bob's exception gives 10 late days; after 2 used on A1 => 8."""
        ng = nbgrader_grade(verbosity=0)
        ng.load_grades_csv(nbgrader_csv)
        ng.load_late_exception(late_exception_yaml)
        balance = ng.calculate_credit_balance(["A1"], "bob", default_credit=5)
        assert balance == 8

    def test_multiple_assignments_deduct(self, nbgrader_csv):
        """Carol used 0 on A1 and 3 on A2; balance should be 5 - 0 - 3 = 2."""
        ng = nbgrader_grade(verbosity=0)
        ng.load_grades_csv(nbgrader_csv)
        balance = ng.calculate_credit_balance(["A1", "A2"], "carol", default_credit=5)
        assert balance == 2

    def test_insufficient_credit_no_deduction(self, nbgrader_csv):
        """When late days exceed remaining credit, days are NOT deducted (penalty applies instead)."""
        ng = nbgrader_grade(verbosity=0)
        ng.load_grades_csv(nbgrader_csv)
        # carol A2 uses 3 late days; with only default_credit=2, 3 > 2 so no deduction
        balance = ng.calculate_credit_balance(["A2"], "carol", default_credit=2)
        # late_days=3 > default_credit=2, so the deduction is skipped => balance stays 2
        assert balance == 2


# ===========================================================================
# Grade Posting Tests
# ===========================================================================


class TestPostGrade:
    """Tests for _post_grade."""

    def test_edits_submission(self, credentials, mock_canvas_api_nbgrader, mock_assignment):
        """_post_grade calls submission.edit with grade and comment."""
        _, _, mock_course, _ = mock_canvas_api_nbgrader
        ng = nbgrader_grade(verbosity=0)
        ng.auth_canvas(credentials)
        ng.set_course(99999)
        ng.link_assignment(42)

        mock_submission = MagicMock()
        mock_submission.score = 0  # different from grade we're posting
        mock_assignment.get_submission.return_value = mock_submission

        ng._post_grade(student_id=101, grade=90.0, text_comment="Great job!")
        mock_submission.edit.assert_called_once_with(
            submission={"posted_grade": 90.0},
            comment={"text_comment": "Great job!"},
        )

    def test_skips_same_score(self, credentials, mock_canvas_api_nbgrader, mock_assignment):
        """_post_grade skips posting when existing score matches and force=False."""
        ng = nbgrader_grade(verbosity=0)
        ng.auth_canvas(credentials)
        ng.set_course(99999)
        ng.link_assignment(42)

        mock_submission = MagicMock()
        mock_submission.score = 90.0
        mock_assignment.get_submission.return_value = mock_submission

        result = ng._post_grade(student_id=101, grade=90.0, text_comment="same")
        assert result is None
        mock_submission.edit.assert_not_called()

    def test_force_overrides_same_score(self, credentials, mock_canvas_api_nbgrader, mock_assignment):
        """_post_grade posts even when score matches when force=True."""
        ng = nbgrader_grade(verbosity=0)
        ng.auth_canvas(credentials)
        ng.set_course(99999)
        ng.link_assignment(42)

        mock_submission = MagicMock()
        mock_submission.score = 90.0
        mock_assignment.get_submission.return_value = mock_submission

        ng._post_grade(student_id=101, grade=90.0, text_comment="forced", force=True)
        mock_submission.edit.assert_called_once()

    def test_none_grade_posts_comment_only(self, credentials, mock_canvas_api_nbgrader, mock_assignment):
        """_post_grade with grade=None posts only a comment, no posted_grade."""
        ng = nbgrader_grade(verbosity=0)
        ng.auth_canvas(credentials)
        ng.set_course(99999)
        ng.link_assignment(42)

        mock_submission = MagicMock()
        mock_submission.score = 50.0  # different from None, so won't skip
        mock_assignment.get_submission.return_value = mock_submission

        ng._post_grade(student_id=101, grade=None, text_comment="comment only")
        mock_submission.edit.assert_called_once_with(
            comment={"text_comment": "comment only"},
        )


class TestPostToCanvas:
    """Tests for post_to_canvas."""

    def test_raises_without_grades(self, credentials, mock_canvas_api_nbgrader):
        """post_to_canvas raises ValueError when no CSV has been loaded."""
        ng = nbgrader_grade(verbosity=0)
        ng.auth_canvas(credentials)
        ng.set_course(99999)
        ng.link_assignment(42)
        with pytest.raises(ValueError, match="Nbgrader CSV has not been loaded"):
            ng.post_to_canvas("A1", [])

    def test_post_false_prints_preview(
        self, credentials, mock_canvas_api_nbgrader, nbgrader_csv, capsys
    ):
        """post_to_canvas with post=False prints preview but does not call _post_grade."""
        ng = nbgrader_grade(verbosity=0)
        ng.auth_canvas(credentials)
        ng.set_course(99999)
        ng.link_assignment(42)
        ng.load_grades_csv(nbgrader_csv)

        with patch.object(ng, "_post_grade") as mock_post:
            ng.post_to_canvas("A1", [], post=False)
            mock_post.assert_not_called()

        captured = capsys.readouterr()
        assert "Post Disabled" in captured.out

    def test_post_true_calls_post_grade(
        self, credentials, mock_canvas_api_nbgrader, nbgrader_csv, mock_assignment
    ):
        """post_to_canvas with post=True calls _post_grade for each student."""
        ng = nbgrader_grade(verbosity=0)
        ng.auth_canvas(credentials)
        ng.set_course(99999)
        ng.link_assignment(42)
        ng.load_grades_csv(nbgrader_csv)

        mock_submission = MagicMock()
        mock_submission.score = -1  # different from any real grade
        mock_assignment.get_submission.return_value = mock_submission

        ng.post_to_canvas("A1", [], post=True)
        # Should have called get_submission for each of the 3 students
        assert mock_assignment.get_submission.call_count == 3


# ===========================================================================
# GitHub Validation Tests
# ===========================================================================


class TestGitHubValidation:
    """Tests for static GitHub checking methods."""

    @patch("LatePenalty.nbgrader.requests.get")
    def test_check_git_user_exists(self, mock_get):
        """check_git_user returns True for HTTP 200."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        result = nbgrader_grade.check_git_user("testuser")
        assert result is True
        mock_get.assert_called_once_with("https://github.com/testuser", timeout=5)

    @patch("LatePenalty.nbgrader.requests.get")
    def test_check_git_user_not_exists(self, mock_get):
        """check_git_user returns False for HTTP 404."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        result = nbgrader_grade.check_git_user("nonexistent")
        assert result is False

    @patch("LatePenalty.nbgrader.requests.get")
    def test_check_git_repo_exists(self, mock_get):
        """check_git_repo returns True when repo page returns 200."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        result = nbgrader_grade.check_git_repo("testuser", "testrepo")
        assert result is True
        mock_get.assert_called_once_with(
            "https://github.com/testuser/testrepo", timeout=5
        )

    @patch("LatePenalty.nbgrader.requests.get")
    def test_check_git_repo_not_exists(self, mock_get):
        """check_git_repo returns False for HTTP 404."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        result = nbgrader_grade.check_git_repo("testuser", "norepo")
        assert result is False

    @patch("LatePenalty.nbgrader.requests.get")
    def test_check_git_file_exists(self, mock_get):
        """check_git_file returns True when the file URL returns 200."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        result = nbgrader_grade.check_git_file("testuser", "testrepo", "README.md")
        assert result is True
        mock_get.assert_called_once_with(
            "https://github.com/testuser/testrepo/blob/master/README.md",
            timeout=5,
        )

    @patch("LatePenalty.nbgrader.requests.get")
    def test_check_git_file_not_exists(self, mock_get):
        """check_git_file returns False for HTTP 404."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        result = nbgrader_grade.check_git_file("testuser", "testrepo", "nope.txt")
        assert result is False

    def test_check_page_success(self):
        """_check_page returns True for status codes below 400."""
        page = MagicMock()
        page.status_code = 200
        assert nbgrader_grade._check_page(page) is True

        page.status_code = 301
        assert nbgrader_grade._check_page(page) is True

        page.status_code = 399
        assert nbgrader_grade._check_page(page) is True

    def test_check_page_failure(self):
        """_check_page returns False for status codes 400 and above."""
        page = MagicMock()
        page.status_code = 400
        assert nbgrader_grade._check_page(page) is False

        page.status_code = 404
        assert nbgrader_grade._check_page(page) is False

        page.status_code = 500
        assert nbgrader_grade._check_page(page) is False
