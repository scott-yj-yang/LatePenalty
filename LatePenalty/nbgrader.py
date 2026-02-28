"""Process nbgrader CSV grades and post to Canvas with late penalty."""

import canvasapi
from canvasapi import Canvas
import numpy as np
import pandas as pd
import json
from datetime import datetime
import yaml
import os
import requests
import nbformat
from typing import List


class bcolors:
    HEADER = "\033[95m"
    OKBLUE = "\033[94m"
    OKCYAN = "\033[96m"
    OKGREEN = "\033[92m"
    WARNING = "\033[93m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"


class nbgrader_grade:
    """Process nbgrader CSV grades and post to Canvas with late penalty.

    Handles loading nbgrader-exported CSVs, computing late days and slip
    credit balances, loading late-day exceptions, applying late penalties,
    and posting final grades with comments to Canvas LMS.

    Args:
        credentials_fp: Path to credentials JSON file containing
            'Canvas Token' and 'GitHub Token' keys.
        late_exception_fp: Path to YAML file with per-student late-day
            exceptions (overrides the default credit).
        API_URL: Canvas instance base URL.
        course_id: Canvas course ID, found in the course URL.
        assignment_id: Canvas assignment ID, found in the assignment URL.
        grades_fp: Path to the nbgrader-exported CSV grades file.
        verbosity: Output verbosity level (0 = silent, 1 = print all messages).
    """

    def __init__(
        self,
        credentials_fp="",
        late_exception_fp="",
        API_URL="https://canvas.ucsd.edu",
        course_id="",
        assignment_id=-1,
        grades_fp="",
        verbosity=0,
    ):
        self.API_URL = API_URL
        self.canvas = None
        self.course = None
        self.users = None
        self.email_to_canvas_id = None
        self.canvas_id_to_email = None
        self.API_KEY = None
        self.verbosity = verbosity
        self.assignment = None
        self.grades = None
        self.late_exception = dict()
        self.grades_by_assignment = dict()
        self.late_days_by_assignment = dict()
        self.pr_details = None

        # initialize by the input parameter
        if credentials_fp != "":
            self.auth_canvas(credentials_fp)
        if course_id != "":
            self.set_course(course_id)
        if assignment_id != -1:
            self.link_assignment(assignment_id)
        if late_exception_fp != "":
            self.load_late_exception(late_exception_fp)
        if grades_fp != "":
            self.load_grades_csv(grades_fp)

    def auth_canvas(self, credentials_fp: str):
        """Authorize the Canvas API connection.

        Reads the credentials JSON file and initializes the Canvas API client.
        Tests the connection by fetching the activity stream summary.

        Args:
            credentials_fp: Path to JSON file containing 'Canvas Token' and
                'GitHub Token' keys.

        Raises:
            FileNotFoundError: If the credentials file does not exist.
            KeyError: If required token keys are missing from the JSON.
        """
        with open(credentials_fp, "r") as f:
            credentials = json.load(f)
        self.API_KEY = credentials["Canvas Token"]
        self.GITHUB_TOKEN = credentials["GitHub Token"]
        self.canvas = Canvas(self.API_URL, self.API_KEY)
        # test authorization
        _ = self.canvas.get_activity_stream_summary()
        if self.verbosity != 0:
            print(f"{bcolors.OKGREEN}Authorization Successful!{bcolors.ENDC}")

    def set_course(self, course_id: int):
        """Set the target course and load the student roster.

        Fetches all students enrolled in the course and builds
        email-to-Canvas-ID and Canvas-ID-to-email lookup dictionaries
        for grade posting.

        Args:
            course_id: The Canvas course ID, found in the course URL.
        """
        self.course = self.canvas.get_course(course_id)
        if self.verbosity != 0:
            print(f"Course Set: {bcolors.OKGREEN} {self.course.name} {bcolors.ENDC}")
            print(f"Getting List of Users... This might take a while...")
        self.users = list(self.course.get_users(enrollment_type=["student"]))
        if self.verbosity != 0:
            print(f"Users Fetch Complete! The course has {bcolors.OKBLUE}{len(self.users)}{bcolors.ENDC} users.")
        self.email_to_canvas_id = {}
        self.canvas_id_to_email = {}
        for u in self.users:
            try:
                self.email_to_canvas_id[u.email.split("@")[0]] = u.id
                self.canvas_id_to_email[u.id] = u.email.split("@")[0]
            except Exception:
                if self.verbosity != 0:
                    print(
                        f"{bcolors.WARNING}Failed to Parse email and id"
                        f" for {bcolors.UNDERLINE}{u.short_name}{bcolors.ENDC}{bcolors.ENDC}"
                    )

    def link_assignment(
        self, assignment_id: int
    ) -> canvasapi.assignment.Assignment:
        """Link a Canvas assignment for grade posting.

        Fetches the assignment object from Canvas and stores it for
        subsequent grade submissions.

        Args:
            assignment_id: Canvas assignment ID, found in the assignment URL.

        Returns:
            The linked Canvas Assignment object.
        """
        assignment = self.course.get_assignment(assignment_id)
        if self.verbosity != 0:
            print(f"Assignment {bcolors.OKGREEN+assignment.name+bcolors.ENDC} Link!")
        self.assignment = assignment
        return assignment

    def load_grades_csv(self, csv_pf: str):
        """Load an nbgrader-exported CSV file and parse assignments.

        Reads the CSV and triggers assignment parsing, which groups
        grades by assignment name and calculates late days for each.

        Args:
            csv_pf: Path to the nbgrader-exported CSV grades file.
        """
        self.grades = pd.read_csv(csv_pf)
        self._parse_assignments()

    def load_late_exception(self, yaml_fp: str):
        """Load a YAML file containing per-student late-day exceptions.

        Students listed in the exception file receive a custom number of
        allowed late days instead of the default credit.

        Args:
            yaml_fp: Path to the YAML file mapping student IDs to their
                allowed late-day overrides.
        """
        with open(yaml_fp, "r") as f:
            self.late_exception = yaml.safe_load(f)

    def _parse_assignments(self):
        "Parse all assignments by assignment name. And calculate late days used."
        if len(self.grades) == 0:
            raise ValueError("grades has not been loaded. Please loaded via self.load_grades_csv")
        assignments = self.grades["assignment"].unique()
        # I am just lazy :-)
        df = self.grades
        for assignment in assignments:
            A = df[df["assignment"] == assignment]
            # filter those who submitted
            A = A[~A["timestamp"].isna()].copy()
            # remove the redundant user with /
            A = A[~A["student_id"].str.contains("/")].copy()
            A = A.set_index("student_id")
            slip_day_used = self._calculate_late_days(A)
            A["slip_day_used"] = slip_day_used
            # store the parsed result
            self.grades_by_assignment[assignment] = A
            self.late_days_by_assignment[assignment] = A["slip_day_used"]

    def check_git_user(user_name: str):
        """Check that a GitHub user exists.

        Args:
            user_name: The GitHub username to check.

        Returns:
            True if the user's GitHub profile page returns a successful
            status code, False otherwise.
        """

        page = requests.get("https://github.com/" + user_name, timeout=5)
        return nbgrader_grade._check_page(page)

    def check_git_repo(
        user_name: str,
        repo_name: str,
    ):
        """Check that a GitHub repository exists and is public.

        Args:
            user_name: The GitHub username who owns the repository.
            repo_name: The repository name to check.

        Returns:
            True if the repository page returns a successful status code,
            False otherwise.
        """

        page = requests.get("https://github.com/" + user_name + "/" + repo_name, timeout=5)
        return nbgrader_grade._check_page(page)

    def check_git_file(
        user_name: str,
        repo_name: str,
        f_name: str,
    ):
        """Check that a file exists in a public GitHub repository.

        Assumes the file is on the master branch.

        Args:
            user_name: The GitHub username who owns the repository.
            repo_name: The repository name.
            f_name: File path within the repository to check.

        Returns:
            True if the file's URL returns a successful status code,
            False otherwise.
        """

        page = requests.get("https://github.com/" + user_name + "/" + repo_name + "/blob/master/" + f_name, timeout=5)
        return nbgrader_grade._check_page(page)

    def _check_page(page):
        """Check whether a web page request was successful.

        Args:
            page: A ``requests.models.Response`` object returned from
                ``requests.get()``.

        Returns:
            True if the HTTP status code is below 400, False otherwise.
        """

        if page.status_code < 400:
            return True
        else:
            return False

    def grade_prs(
        student_details: dict,
        pr_details: dict,
    ):
        """Check if pull requests exist and grade students accordingly.

        Looks up each student's GitHub username in the pull request
        details and awards points if a matching PR is found.

        Args:
            student_details: Dict mapping student IDs to dicts with keys
                ``'pid'``, ``'github'``, and ``'score'``.
            pr_details: Dict mapping GitHub usernames (lowercase) to
                concatenated PR title and body text.

        Returns:
            1 if a matching pull request was found, 0 otherwise.

        Raises:
            ValueError: If iteration completes without returning (should
                not happen in normal usage).
        """
        # Change points distribution of each rubric items
        PR_SCORE = 1
        print(f"DEBUG: in grade_prs, student details: {student_details}")
        # print(f"DEBUG: in grade_prs, pr_details: {pr_details}")
        for student in student_details:
            if (
                len(student_details[student]["github"]) == 0
                or student_details[student]["github"].lower() not in pr_details
            ):
                print(
                    f"student_details[student][github] not in pr_details: {student_details[student]['github'] not in pr_details}"
                )
                return 0
            last_2 = student_details[student]["pid"][-2:]
            print(last_2)
            if last_2 in pr_details[student_details[student]["github"].lower()]:
                student_details[student]["score"] += PR_SCORE
                return 1
            else:
                print(
                    student,
                    "PR not found",
                    last_2,
                    student_details[student],
                    pr_details[student_details[student]["github"].lower()],
                )  # why do you index when you did not find it???????
                return 0
        raise ValueError("Issue with this students")

    def _calculate_late_days(self, df: pd.DataFrame) -> pd.Series:  # dataframe of a specific assignment  # late days
        # parse the timestamp
        duedate_format = "%Y-%m-%d %H:%M:%S"
        timestamp_format = "%Y-%m-%d %H:%M:%S.%f"
        df["duedate"] = df["duedate"].apply(lambda x: datetime.strptime(x, duedate_format))
        df["timestamp"] = df["timestamp"].apply(lambda x: datetime.strptime(x, timestamp_format))

        # Calculate the time difference between submission and due date
        late_time_delta = df["timestamp"] - df["duedate"]

        # Add 3-hour tolerance: Convert 3 hours to timedelta for comparison
        tolerance = pd.to_timedelta(3, unit="h")

        # Apply tolerance: Subtract 3 hours from the late time delta
        adjusted_late_time = late_time_delta - tolerance

        # calculate late days, use ReLU
        slip_day_used = adjusted_late_time.apply(
            lambda x: np.max([np.ceil(x.total_seconds() / 60 / 60 / 24), 0])
        ).apply(
            lambda x: x if x <= 5 else 0
        )  # cap the maximum at 5

        return slip_day_used

    def get_late_days(
        self,
        target_assignment: str,
        student_id: str,
    ) -> int:
        """Get the number of late days for a student's assignment submission.

        Looks up pre-computed late days from the parsed assignment data.
        Returns 0 if the student did not submit the assignment.

        Args:
            target_assignment: Assignment name as it appears in the
                nbgrader CSV ``assignment`` column.
            student_id: The student identifier (nbgrader student ID).

        Returns:
            Number of late days for the submission, or 0 if not found.
        """
        try:
            late_day = self.late_days_by_assignment[target_assignment][student_id]
        except KeyError:
            if self.verbosity != 1:
                print(
                    f"Student {bcolors.WARNING+student_id+bcolors.ENDC} did "
                    f"not submit {bcolors.WARNING+target_assignment+bcolors.ENDC}"
                )
            late_day = 0
        return late_day

    def calculate_credit_balance(
        self,
        passed_assignments: List[str],
        student_id: str,
        default_credit=5,
    ) -> int:
        """Calculate remaining slip-day credit for a specific student.

        Iterates over previously graded assignments and deducts late days
        from the student's credit balance. If the student appears in the
        late-exception list, their custom allowance is used instead of
        the default. Days are only deducted when the student still has
        sufficient credit (i.e., no penalty was applied).

        Args:
            passed_assignments: List of assignment names that have already
                been graded, as they appear in the nbgrader CSV.
            student_id: The student identifier (nbgrader student ID).
            default_credit: Default number of allowed late days per
                student, unless overridden by the exception file.

        Returns:
            The remaining slip-day credit for the student.
        """
        # if student is in the late exception, use the new number
        if student_id in self.late_exception:
            default_credit = self.late_exception[student_id]["allowed_late_days"]
        for passed in passed_assignments:
            late_days = self.get_late_days(passed, student_id)
            if late_days <= default_credit:
                # means this passed assignment did not get penalty
                default_credit -= self.get_late_days(passed, student_id)
        return default_credit

    def _post_grade(
        self,
        student_id: int,
        grade: float,
        text_comment="",
        force=False,
    ) -> canvasapi.submission.Submission:
        """Post a grade and comment to Canvas for a single student submission.

        Fetches the existing submission and, unless ``force`` is True,
        skips posting when the score has not changed. If ``grade`` is None,
        only the comment is posted without changing the score.

        Args:
            student_id: Canvas user ID of the student, found in
                ``self.email_to_canvas_id``.
            grade: Numeric grade to post for the assignment, or None to
                post only a comment.
            text_comment: Text comment attached to the submission that the
                student will see as grade feedback.
            force: If False (default), skip posting when the existing
                score matches ``grade``. If True, always post.

        Returns:
            The edited Canvas Submission object, or None if skipped.
        """
        submission = self.assignment.get_submission(student_id)
        if not force and submission.score == grade:
            if self.verbosity != 0:
                print(
                    f"Grade for {bcolors.OKGREEN+self.canvas_id_to_email[student_id]+bcolors.ENDC} did not change.\n"
                    f"{bcolors.OKCYAN}Skipped{bcolors.ENDC}.\n"
                )
            return
        if grade is not None:
            edited = submission.edit(submission={"posted_grade": grade}, comment={"text_comment": text_comment})
        else:
            edited = submission.edit(comment={"text_comment": text_comment})
        if self.verbosity != 0:
            print(f"Grade for {bcolors.OKCYAN}{self.canvas_id_to_email[student_id]}{bcolors.ENDC} Posted!")
        return edited

    def pull_request_details(self):
        """Fetch pull request details from GitHub and cache to a JSON file.

        Retrieves all pull requests from the COGS108 MyFirstPullRequest
        repository via the GitHub API (paginated up to 9 pages). Results
        are cached in ``Pull_Requests.json`` to avoid repeated API calls.
        Populates ``self.pr_details`` with a mapping from GitHub username
        to concatenated PR title and body text.
        """
        try:
            f = open("Pull_Requests.json")
            print("Pull Requests opened.")
        except FileNotFoundError:
            pr_link = "https://api.github.com/repos/COGS108/MyFirstPullRequest/pulls?state=all&per_page=100&page="
            pull_requests = []
            for n_iter in range(1, 10):
                r = requests.get(pr_link + str(n_iter))
                print(len(r.text))
                pulls = json.loads(r.text)
                pull_requests.append(pulls)

            with open("Pull_Requests.json", "w") as json_file:
                json.dump(pull_requests, json_file)

            print("Pull Requests fetched and saved.")

        f = open("Pull_Requests.json")
        pr = json.load(f)
        pr_details = {}
        for n_iter in range(1, 10):
            for pulls in pr:
                for pull in pulls:
                    try:
                        text = (pull["title"] + str(pull["body"])).lower()
                    except TypeError:
                        print(pull)
                        print(pull["title"])
                        print(pull["body"])
                    pr_details[pull["user"]["login"].lower()] = pr_details.get(pull["user"]["login"], "") + text
        self.pr_details = pr_details

    def grade_A1_git(
        self,
        student_id: str,
        quarter: str,
        message: str,
        score: float,
    ):
        """Grade the Git/GitHub portion of Assignment 1 for COGS108.

        Reads the student's submitted notebook to extract their GitHub
        username and PID, then checks for the existence of the GitHub
        user, repository, required files (.gitignore and README), and
        a pull request. Awards points for each criterion met.

        Args:
            student_id: The nbgrader student identifier.
            quarter: Course quarter code (e.g., ``'Fa23'``, ``'Wi24'``),
                used to locate the assignment directory.
            message: Existing feedback message to append Git grading
                details to.
            score: The student's current score, to which Git points
                are added.

        Returns:
            A tuple of ``(message, score)`` where ``message`` is the
            updated feedback string and ``score`` is the updated
            numeric grade including Git points.
        """

        if self.pr_details is None:
            self.pull_request_details()

        # Initialize scores
        user_score = 0
        repo_score = 0
        file_score = 0
        pr_score = 0

        # read students' submissions and fetch Github ID:
        home_dir = os.path.expanduser("~")
        graded_dir = os.path.join(home_dir, "autograded")
        A1_dir = os.path.join(graded_dir, student_id, f"A1_COGS108_{quarter}")
        try:
            for file in os.listdir(A1_dir):
                if file.endswith(".ipynb") and "A1" in file:
                    file_path = os.path.join(A1_dir, file)
        except FileNotFoundError:
            print(f"{student_id} does not have a submission for A1, skipped to the next student")

        student_details = {}

        nb = nbformat.read(file_path, as_version=4)
        subs = ["PID", "github_username"]
        for cells in nb.cells:
            try:
                if cells["metadata"]["nbgrader"]["grade_id"] == "cell-784114344a572182":
                    cell = cells
                    break
            except KeyError:
                continue

        test_list = cell["source"].split("\n")
        res = [i for i in test_list if any(substring in i for substring in subs)]
        print(res)
        if len(res) != 0:
            PID_string = [i for i in res if all(substring in i for substring in ["PID", "="])]
            github_string = [i for i in res if all(substring in i for substring in ["github_username", "="])]
            if len(PID_string) != 0 and len(github_string) != 0:
                PID = (PID_string[-1].split("="))[-1].strip().strip("'").strip('"').strip(";").replace("'", "")
                github_username = (github_string[-1].split("="))[-1].strip().strip("'").strip('"')
                print(student_id, PID, github_username)
                student_details[student_id] = {"pid": PID, "github": github_username, "score": 0}

        print(student_details)

        try:
            if len(student_details[student_id]["github"]) == 0:
                print("GitHub ID does not exist")
                pass

            # User exists:
            if nbgrader_grade.check_git_user(student_details[student_id]["github"]):
                student_details[student_id]["score"] += 0.5
                print(student_details)
                user_score = 0.5

            # Repo exists:
            if nbgrader_grade.check_git_repo(student_details[student_id]["github"], "COGS108_repo"):
                student_details[student_id]["score"] += 0.5
                print(student_details)
                repo_score = 0.5

            # Files exist:
            is_gitignore = nbgrader_grade.check_git_file(
                student_details[student_id]["github"], "COGS108_repo", ".gitignore"
            )
            is_readme = nbgrader_grade.check_git_file(student_details[student_id]["github"], "COGS108_repo", "README")
            is_readme = is_readme or nbgrader_grade.check_git_file(
                student_details[student_id]["github"], "COGS108_repo", "README.txt"
            )
            is_readme = is_readme or nbgrader_grade.check_git_file(
                student_details[student_id]["github"], "COGS108_repo", "README.md"
            )
            if is_gitignore and is_readme:
                student_details[student_id]["score"] += 0.5
                print(student_details)
                file_score = 0.5

            # Pull requests:
            pr_score = nbgrader_grade.grade_prs(student_details, self.pr_details)
            print(f"PR_score: {pr_score}")
            score += student_details[student_id]["score"]

            message += f"user_exists_score: {user_score},\n"
            message += f"repo_exists_score: {repo_score},\n"
            message += f"files_exist_score: {file_score},\n"
            message += f"pull_request_score: {pr_score}.\n"

        # build message for each student
        except KeyError as e:
            print("User does not exist, skipped grading git.")
            print(e)
            message += f"No information provided in assignment, 0 automatically assigned for git part.\n"
            pass

        return message, score

    def post_to_canvas(
        self,
        target_assignment: str,
        passed_assignments: List[str],
        student=None,
        A1_git=False,
        quarter="",
        default_credit: int = 7,
        late_submission_deadline: int = 5,
        post=True,
        force=False,
    ):
        """Apply late penalties and post grades with comments to Canvas.

        Main grading workflow: iterates over students who submitted the
        target assignment, calculates slip-day credit balances, determines
        late days, applies a 25 percent penalty when credit is exhausted
        (or zeros the score if submission exceeds the late deadline), and
        posts grades with detailed feedback comments to Canvas.

        Args:
            target_assignment: Assignment name whose late-day data will
                be read from the parsed nbgrader grades.
            passed_assignments: List of previously graded assignment names
                used to compute remaining slip-day credit.
            student: List of student IDs to grade. If None, all students
                who submitted the target assignment are graded.
            A1_git: If True, additionally grade the Git/GitHub portion
                of COGS108 Assignment 1.
            quarter: Course quarter code (e.g., ``'Fa23'``, ``'Wi24'``),
                required when ``A1_git`` is True.
            default_credit: Default number of allowed late days per
                student, unless overridden by the exception file.
            late_submission_deadline: Maximum number of late days accepted.
                Submissions beyond this threshold receive a score of zero.
            post: If True (default), actually post grades to Canvas. If
                False, only print what would be posted (dry run).
            force: If True, post grades even when the score has not
                changed. Defaults to False.

        Raises:
            ValueError: If the nbgrader CSV has not been loaded.
        """
        if self.grades is None:
            raise ValueError("Nbgrader CSV has not been loaded. Please set it via self.load_grades_csv")

        for student_id, row in self.grades_by_assignment[target_assignment].iterrows():
            if student is not None and student_id not in student:
                continue
            penalty = False
            # fetch useful information
            balance = self.calculate_credit_balance(passed_assignments, student_id, default_credit=default_credit)
            late_days = self.get_late_days(target_assignment, student_id)
            score = row["raw_score"]

            message = f"{target_assignment}: \n"

            if A1_git:
                message, score = self.grade_A1_git(student_id, quarter, message, score)

            if late_days > 0:
                # means late submission. Check remaining slip day
                message += f"Late Submission: {int(late_days)} Days Late\n"
                if late_days > late_submission_deadline:
                    message += f"Submit after the late deadline, invalid submission\n"
                    penalty = False
                    score = 0
                elif balance - late_days < 0:
                    message += "Insufficient Slip Credit. 25% late penalty applied\n"
                    score = round(score * 0.75, 4)
                    penalty = True
                else:
                    message += "Slip Credit Used. No late penalty applied\n"
            else:
                message += "Submitted before deadline\n"
            if not penalty:
                # if student did not get penalized and use the slip day
                balance_after = balance - late_days
            else:
                # if the student did get penalized and did not use the slip day
                balance_after = balance
            message += f"Remaining Slip Day Credit: {int(balance_after)} Days"
            if post:
                try:
                    canvas_student_id = self.email_to_canvas_id[student_id]
                    self._post_grade(grade=score, student_id=canvas_student_id, text_comment=message, force=force)
                    if self.verbosity != 0:
                        print(
                            f"The message for {bcolors.OKCYAN+student_id+bcolors.ENDC} "
                            f"is: \n{bcolors.OKGREEN+message+bcolors.ENDC}\n"
                            f"The score is {bcolors.OKGREEN}{score}{bcolors.ENDC}\n\n"
                        )
                except Exception as e:
                    print(
                        f"Student: {bcolors.WARNING+student_id+bcolors.ENDC} Not found on canvas. \n"
                        f"Maybe Testing Account or Dropped Student"
                    )
                    print(e)
                    pass
            else:
                print(
                    f"{bcolors.WARNING}Post Disabled{bcolors.ENDC}\n"
                    f"The message for {bcolors.OKCYAN+student_id+bcolors.ENDC} "
                    f"is: \n{bcolors.OKGREEN+message+bcolors.ENDC}\n"
                    f"The score is {bcolors.OKGREEN}{score}{bcolors.ENDC}\n\n"
                )
