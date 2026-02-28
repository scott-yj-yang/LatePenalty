"""Tests for LatePenalty.gradescope — gradescope_grade class."""

import json
import pytest
import pandas as pd
from unittest.mock import MagicMock, patch
from LatePenalty.gradescope import gradescope_grade


# ===================================================================
# Auth and Setup Tests
# ===================================================================


class TestAuthCanvas:
    """Tests for auth_canvas method."""

    def test_auth_loads_token_and_creates_canvas(self, credentials, mock_canvas_api):
        MockCanvas, canvas_instance, _, _ = mock_canvas_api
        gg = gradescope_grade(verbosity=0)
        gg.auth_canvas(credentials)
        MockCanvas.assert_called_once_with("https://canvas.ucsd.edu", "fake-canvas-token")
        canvas_instance.get_activity_stream_summary.assert_called_once()
        assert gg.API_KEY == "fake-canvas-token"

    def test_auth_stores_github_token(self, credentials, mock_canvas_api):
        _, _, _, _ = mock_canvas_api
        gg = gradescope_grade(verbosity=0)
        gg.auth_canvas(credentials)
        assert gg.GITHUB_TOKEN == "fake-github-token"

    def test_auth_missing_file_raises_file_not_found(self, mock_canvas_api):
        _, _, _, _ = mock_canvas_api
        gg = gradescope_grade(verbosity=0)
        with pytest.raises(FileNotFoundError):
            gg.auth_canvas("/nonexistent/path/credentials.json")

    def test_auth_bad_keys_raises_key_error(self, bad_credentials, mock_canvas_api):
        _, _, _, _ = mock_canvas_api
        gg = gradescope_grade(verbosity=0)
        with pytest.raises(KeyError):
            gg.auth_canvas(bad_credentials)

    def test_auth_custom_api_url(self, credentials, mock_canvas_api):
        MockCanvas, _, _, _ = mock_canvas_api
        gg = gradescope_grade(API_URL="https://custom.canvas.edu", verbosity=0)
        gg.auth_canvas(credentials)
        MockCanvas.assert_called_once_with("https://custom.canvas.edu", "fake-canvas-token")


class TestSetCourse:
    """Tests for set_course method."""

    def test_set_course_fetches_students_and_staff(self, credentials, mock_canvas_api, mock_students, mock_staff):
        _, canvas_instance, mock_course, _ = mock_canvas_api
        gg = gradescope_grade(verbosity=0)
        gg.auth_canvas(credentials)
        gg.set_course(99999)

        canvas_instance.get_course.assert_called_once_with(99999)
        assert gg.course is mock_course
        assert len(gg.users) == 3
        assert len(gg.course_staffs) == 2

    def test_set_course_builds_email_mappings(self, credentials, mock_canvas_api):
        _, _, _, _ = mock_canvas_api
        gg = gradescope_grade(verbosity=0)
        gg.auth_canvas(credentials)
        gg.set_course(99999)

        assert gg.email_to_canvas_id["alice"] == 101
        assert gg.email_to_canvas_id["bob"] == 102
        assert gg.email_to_canvas_id["carol"] == 103

        assert gg.canvas_id_to_email[101] == "alice"
        assert gg.canvas_id_to_email[102] == "bob"
        assert gg.canvas_id_to_email[103] == "carol"

        assert gg.email_to_name["alice"] == "Alice Smith"
        assert gg.email_to_name["bob"] == "Bob Jones"

    def test_set_course_staff_emails_populated(self, credentials, mock_canvas_api):
        _, _, _, _ = mock_canvas_api
        gg = gradescope_grade(verbosity=0)
        gg.auth_canvas(credentials)
        gg.set_course(99999)

        assert "instructor" in gg.course_staffs_emails
        assert "ta_person" in gg.course_staffs_emails
        assert len(gg.course_staffs_emails) == 2


class TestLinkAssignment:
    """Tests for link_assignment method."""

    def test_link_assignment_returns_assignment(self, credentials, mock_canvas_api):
        _, _, mock_course, mock_assignment = mock_canvas_api
        gg = gradescope_grade(verbosity=0)
        gg.auth_canvas(credentials)
        gg.set_course(99999)

        result = gg.link_assignment(42)
        mock_course.get_assignment.assert_called_with(42)
        assert result is mock_assignment

    def test_link_assignment_stores_assignment(self, credentials, mock_canvas_api):
        _, _, _, mock_assignment = mock_canvas_api
        gg = gradescope_grade(verbosity=0)
        gg.auth_canvas(credentials)
        gg.set_course(99999)
        gg.link_assignment(42)

        assert gg.assignment is mock_assignment


class TestLoadGradescopeCsv:
    """Tests for load_gradescope_csv method."""

    def test_loads_csv_and_indexes_by_email_prefix(self, gradescope_csv):
        gg = gradescope_grade(verbosity=0)
        gg.load_gradescope_csv(gradescope_csv)

        assert isinstance(gg.gradescope, pd.DataFrame)
        assert gg.gradescope.index.name == "Email"
        assert "alice" in gg.gradescope.index
        assert "bob" in gg.gradescope.index
        assert "carol" in gg.gradescope.index

    def test_fills_nan_with_zero(self, tmp_path):
        data = {
            "Email": ["alice@ucsd.edu", "bob@ucsd.edu"],
            "HW1": [90.0, None],
            "HW1 - Lateness (H:M:S)": ["00:00:00", "00:00:00"],
        }
        df = pd.DataFrame(data)
        fp = tmp_path / "sparse.csv"
        df.to_csv(fp, index=False)

        gg = gradescope_grade(verbosity=0)
        gg.load_gradescope_csv(str(fp))

        assert gg.gradescope.loc["bob", "HW1"] == 0


# ===================================================================
# Late Calculation Tests
# ===================================================================


class TestCalculateLateness:
    """Tests for late hour calculation and credit balance methods."""

    @pytest.fixture
    def gg_with_csv(self, gradescope_csv):
        """A gradescope_grade instance with CSV already loaded."""
        gg = gradescope_grade(verbosity=0)
        gg.load_gradescope_csv(gradescope_csv)
        return gg

    def test_calculate_late_hour_on_time(self, gg_with_csv):
        late_hours = gg_with_csv.calculate_late_hour("HW1")
        # alice: "00:00:00" -> 0 hours
        assert late_hours["alice"] == 0

    def test_calculate_late_hour_late_submission(self, gg_with_csv):
        late_hours = gg_with_csv.calculate_late_hour("HW1")
        # bob: "25:30:00" -> 25 + ceil(30/60) = 25 + 1 = 26
        assert late_hours["bob"] == 26

    def test_calculate_credit_balance_deducts_correctly(self, gg_with_csv):
        balance = gg_with_csv.calculate_credit_balance(["HW1"], total_credit=120)
        # alice: on time, balance stays 120
        assert balance["alice"] == 120
        # bob: 26 hours late, balance = 120 - 26 = 94
        assert balance["bob"] == 94
        # carol: on time, balance stays 120
        assert balance["carol"] == 120

    def test_credit_does_not_go_negative_when_exceeded(self, gg_with_csv):
        # With only 20 total credit, bob's 26-hour lateness exceeds credit
        balance = gg_with_csv.calculate_credit_balance(["HW1"], total_credit=20)
        # bob: 26 hours late > 20 total credit, balance NOT deducted (stays 20)
        assert balance["bob"] == 20

    def test_credit_balance_multiple_assignments(self, gg_with_csv):
        balance = gg_with_csv.calculate_credit_balance(["HW1", "HW2"], total_credit=120)
        # alice: on time both, stays 120
        assert balance["alice"] == 120
        # bob: 26 hours late on HW1, on time HW2 -> 120 - 26 = 94
        assert balance["bob"] == 94
        # carol: on time HW1, 50 hours late HW2 -> 120 - 50 = 70
        assert balance["carol"] == 70

    def test_calculate_total_score_sums_components(self, gg_with_csv):
        total = gg_with_csv.calculate_total_score(["Component1", "Component2"])
        # alice: 40 + 50 = 90
        assert total["alice"] == 90
        # bob: 35 + 50 = 85
        assert total["bob"] == 85
        # carol: 0 + 0 = 0
        assert total["carol"] == 0

    def test_calculate_late_reports_structure(self, gg_with_csv):
        late_assignments, total_late_hours = gg_with_csv.calculate_late_reports(
            ["HW1", "HW2"], total_credit=120
        )
        # bob was 26 hours late on HW1
        assert ("HW1", 26, False) in late_assignments["bob"]
        # carol was 50 hours late on HW2
        assert ("HW2", 50, False) in late_assignments["carol"]
        # alice on time for both
        assert all(entry[1] == 0 for entry in late_assignments["alice"])

    def test_calculate_late_reports_total_hours(self, gg_with_csv):
        _, total_late_hours = gg_with_csv.calculate_late_reports(
            ["HW1", "HW2"], total_credit=120
        )
        assert total_late_hours["bob"] == 26
        assert total_late_hours["carol"] == 50
        assert total_late_hours["alice"] == 0

    def test_calculate_late_reports_penalty_applied_when_exceeded(self, gg_with_csv):
        late_assignments, _ = gg_with_csv.calculate_late_reports(
            ["HW1"], total_credit=20
        )
        # bob: 26 hours late > 20 credit -> penalty applied
        bob_hw1 = [e for e in late_assignments["bob"] if e[0] == "HW1"][0]
        assert bob_hw1[2] is True  # penalty_applied = True


# ===================================================================
# Grade Posting Tests
# ===================================================================


class TestPostGrade:
    """Tests for _post_grade method."""

    @pytest.fixture
    def gg_ready(self, credentials, mock_canvas_api):
        """A gradescope_grade instance with auth, course, and assignment configured."""
        _, _, _, mock_assignment = mock_canvas_api
        gg = gradescope_grade(verbosity=0)
        gg.auth_canvas(credentials)
        gg.set_course(99999)
        gg.link_assignment(42)
        return gg

    def test_post_grade_edits_submission(self, gg_ready, mock_canvas_api):
        _, _, _, mock_assignment = mock_canvas_api
        mock_submission = MagicMock()
        mock_submission.score = None  # different from grade, so it proceeds
        mock_assignment.get_submission.return_value = mock_submission

        gg_ready._post_grade(student_id=101, grade=85.0, text_comment="Good job")
        mock_assignment.get_submission.assert_called_once_with(101)
        mock_submission.edit.assert_called_once_with(
            submission={'posted_grade': 85.0},
            comment={'text_comment': "Good job"}
        )

    def test_post_grade_skips_same_score(self, gg_ready, mock_canvas_api):
        _, _, _, mock_assignment = mock_canvas_api
        mock_submission = MagicMock()
        mock_submission.score = 85.0  # same as grade
        mock_assignment.get_submission.return_value = mock_submission

        result = gg_ready._post_grade(student_id=101, grade=85.0)
        mock_submission.edit.assert_not_called()
        assert result is None

    def test_post_grade_force_overrides_skip(self, gg_ready, mock_canvas_api):
        _, _, _, mock_assignment = mock_canvas_api
        mock_submission = MagicMock()
        mock_submission.score = 85.0  # same as grade, but force=True
        mock_assignment.get_submission.return_value = mock_submission

        gg_ready._post_grade(student_id=101, grade=85.0, force=True)
        mock_submission.edit.assert_called_once()


class TestPostToCanvas:
    """Tests for post_to_canvas method."""

    @pytest.fixture
    def gg_full(self, credentials, mock_canvas_api, gradescope_csv):
        """Fully configured gradescope_grade with CSV loaded."""
        _, _, _, mock_assignment = mock_canvas_api
        gg = gradescope_grade(verbosity=0)
        gg.auth_canvas(credentials)
        gg.set_course(99999)
        gg.link_assignment(42)
        gg.load_gradescope_csv(gradescope_csv)
        return gg

    def test_raises_without_csv_loaded(self, credentials, mock_canvas_api):
        _, _, _, _ = mock_canvas_api
        gg = gradescope_grade(verbosity=0)
        gg.auth_canvas(credentials)
        gg.set_course(99999)
        gg.link_assignment(42)
        # gradescope CSV not loaded
        with pytest.raises(ValueError, match="Gradescope CSV has not been loaded"):
            gg.post_to_canvas("HW1", [])

    def test_raises_without_assignment_linked(self, credentials, mock_canvas_api, gradescope_csv):
        _, _, _, _ = mock_canvas_api
        gg = gradescope_grade(verbosity=0)
        gg.auth_canvas(credentials)
        gg.set_course(99999)
        gg.load_gradescope_csv(gradescope_csv)
        # assignment not linked
        with pytest.raises(ValueError, match="Assignment has not been link"):
            gg.post_to_canvas("HW1", [])

    def test_post_false_prints_preview(self, gg_full, capsys):
        gg_full.verbosity = 1  # enable output for print checks
        gg_full.post_to_canvas("HW1", [], post=False)
        captured = capsys.readouterr()
        # should contain "Post Disabled" messages for students
        assert "Post Disabled" in captured.out

    def test_late_penalty_applied_when_credit_exhausted(self, gg_full, mock_canvas_api):
        _, _, _, mock_assignment = mock_canvas_api
        mock_submission = MagicMock()
        mock_submission.score = None
        mock_assignment.get_submission.return_value = mock_submission

        # bob is 26 hours late on HW1; with only 20 credit, penalty applies
        gg_full.post_to_canvas(
            "HW1", [], total_credit=20, post=True, force=True
        )

        # Find the call for bob (student_id=102)
        # _post_grade is called via self, so we check mock_assignment.get_submission calls
        calls = mock_assignment.get_submission.call_args_list
        # Collect all posted grades by student_id
        posted = {}
        for call in calls:
            student_id = call[0][0]
            posted[student_id] = True

        # Verify edit was called with 25% penalty for bob
        edit_calls = mock_submission.edit.call_args_list
        # bob's score is 85.0 * 0.75 = 63.75
        bob_grade_found = False
        for call in edit_calls:
            grade = call[1].get('submission', call[0][0] if call[0] else {}).get('posted_grade', None)
            if grade is None and len(call[0]) == 0:
                grade = call[1].get('submission', {}).get('posted_grade')
            if grade == 63.75:
                bob_grade_found = True
        assert bob_grade_found, "Bob's grade should be 85.0 * 0.75 = 63.75 after late penalty"

    def test_skips_staff_members(self, gg_full, mock_canvas_api, tmp_path):
        """Staff members listed in course_staffs_emails should be skipped."""
        _, _, _, mock_assignment = mock_canvas_api
        mock_submission = MagicMock()
        mock_submission.score = None
        mock_assignment.get_submission.return_value = mock_submission

        # Add "instructor" and "ta_person" as rows in the CSV so they appear in iteration
        data = {
            "Email": ["alice@ucsd.edu", "instructor@ucsd.edu", "ta_person@ucsd.edu"],
            "HW1": [90.0, 100.0, 100.0],
            "HW1 - Lateness (H:M:S)": ["00:00:00", "00:00:00", "00:00:00"],
        }
        df = pd.DataFrame(data)
        fp = tmp_path / "staff_test.csv"
        df.to_csv(fp, index=False)
        gg_full.load_gradescope_csv(str(fp))

        gg_full.post_to_canvas("HW1", [], post=True, force=True)

        # Only alice (101) should have a submission fetched, not instructor or ta_person
        get_sub_calls = mock_assignment.get_submission.call_args_list
        submitted_ids = [c[0][0] for c in get_sub_calls]
        assert 101 in submitted_ids
        assert 901 not in submitted_ids
        assert 902 not in submitted_ids
