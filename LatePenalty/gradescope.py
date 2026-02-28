"""Process Gradescope CSV grades and post to Canvas with late penalty."""

import canvasapi
from canvasapi import Canvas
import numpy as np
import pandas as pd
import json
from datetime import datetime
import yaml
from typing import List
from collections import defaultdict


class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


class gradescope_grade:
    def __init__(self,
                 credentials_fp = "", # credential file path. [Template of the credentials.json](https://github.com/FleischerResearchLab/CanvasGroupy/blob/main/nbs/credentials.json)
                 API_URL="https://canvas.ucsd.edu", # the domain name of canvas
                 course_id="", # Course ID can be found in the course url
                 assignment_id=-1, # assignment id, can be found in the canvas assignment url
                 gradescope_fp="", # gradescope csv file path 
                 verbosity=1 # Controls the verbosity: 0 = Silent, 1 = print all messages
                ):
        "Initialize Canvas Group within a Group Set and its appropriate memberships"
        self.API_URL = API_URL
        self.canvas = None
        self.course = None
        self.users = None
        self.course_staffs = None
        self.course_staffs_emails = None
        self.email_to_canvas_id = None
        self.canvas_id_to_email = None
        self.email_to_name = None
        self.API_KEY = None
        self.verbosity = verbosity
        self.assignment = None
        self.gradescope = None

        # initialize by the input parameter
        if credentials_fp != "":
            self.auth_canvas(credentials_fp)
        if course_id != "":
            self.set_course(course_id)
        if assignment_id != -1:
            self.link_assignment(assignment_id)
        if gradescope_fp != "":
            self.load_gradescope_csv(gradescope_fp)

    def auth_canvas(self,
                    credentials_fp: str # the Authenticator key generated from canvas
                   ):
        "Authorize the canvas module with API_KEY"
        with open(credentials_fp, "r") as f:
            credentials = json.load(f)
        self.API_KEY = credentials["Canvas Token"]
        self.GITHUB_TOKEN = credentials["GitHub Token"]
        self.canvas = Canvas(self.API_URL, self.API_KEY)
        # test authorization
        _ = self.canvas.get_activity_stream_summary()
        if self.verbosity != 0:
            print(f"{bcolors.OKGREEN}Authorization Successful!{bcolors.ENDC}")

    def set_course(self, 
                   course_id: int # the course id of the target course
                  ):
        "Set the target course by the course ID"
        self.course = self.canvas.get_course(course_id)
        if self.verbosity != 0:
            print(f"Course Set: {bcolors.OKGREEN} {self.course.name} {bcolors.ENDC}")
            print(f"Getting List of Users... This might take a while...")
        type_list = ['teacher', 'ta', 'designer']
        self.course_staffs = list(self.course.get_users(enrollment_type=type_list))
        self.users = list(self.course.get_users(enrollment_type=['student']))
        if self.verbosity != 0:
            print(f"Users Fetch Complete!\n"
                  f"The course has {bcolors.OKBLUE}{len(self.users)}{bcolors.ENDC} users.\n"
                  f"The course has {bcolors.OKBLUE}{len(self.course_staffs)}{bcolors.ENDC} course staffs")
        self.email_to_canvas_id = {}
        self.canvas_id_to_email = {}
        self.email_to_name = {}
        self.course_staffs_emails = [u.email.split("@")[0] for u in self.course_staffs]
        for u in self.users:
            try:
                self.email_to_canvas_id[u.email.split("@")[0]] = u.id
                self.canvas_id_to_email[u.id] = u.email.split("@")[0]
                self.email_to_name[u.email.split("@")[0]] = u.short_name
            except Exception:
                if self.verbosity != 0:
                    print(f"{bcolors.WARNING}Failed to Parse email and id"
                          f" for {bcolors.UNDERLINE}{u.short_name}{bcolors.ENDC}{bcolors.ENDC}")

    def link_assignment(self,
                        assignment_id: int # assignment id, found at the url of assignment tab
                       ) -> canvasapi.assignment.Assignment: # target assignment
        "Link the target assignment on canvas"
        assignment = self.course.get_assignment(assignment_id)
        if self.verbosity != 0:
            print(f"Assignment {bcolors.OKGREEN+assignment.name+bcolors.ENDC} Link!")
        self.assignment = assignment
        return assignment

    def load_gradescope_csv(self,
                            csv_pf:str # csv file path 
                           ):
        "Load gradescope exported csv file"
        self.gradescope = pd.read_csv(csv_pf)
        self.gradescope['Email'] = self.gradescope["Email"].str.split("@").str[0]
        self.gradescope = self.gradescope.set_index("Email")
        self.gradescope = self.gradescope.fillna(0)

    def calculate_late_hour(self,
                            target_assignment:str, # target assignment name. Must in the column of gradescope csv 
                           ) -> pd.Series: # late hours of the target assignment
        "Calculate the late hours of each submission of the target assignment"
        late_col_name = f"{target_assignment} - Lateness (H:M:S)"
        late_col = self.gradescope[late_col_name]
        # calculate how many slip days (hours) used for this assignment.
        late_hours = (
            late_col.str.split(":").str[0].astype(int) + 
            np.ceil(late_col.str.split(":").str[1].astype(int)/60)
        )
        return late_hours

    def calculate_credit_balance(self,
                                 passed_assignments:List[str], # list of passed assignment. Must in the column of gradescope csv
                                 total_credit = 120 # total number of allowed late hours
                                ) -> dict: # {email: credit balance} late credit balance of each student
        "Calculate the balance of late hours from the gradescope file"
        self.gradescope["late balance"] = total_credit
        for passed_assignment in passed_assignments:
            late_hours = self.calculate_late_hour(passed_assignment)
            late_balance = self.gradescope["late balance"] - late_hours
            # do not deduct balanced if late penalty is applied.
            # mask only the late hours within the range of the allowance
            valid_balance_mask = late_balance >= 0
            self.gradescope.loc[valid_balance_mask, "late balance"] = late_balance
        return self.gradescope["late balance"]

    def calculate_late_reports(self,
                               passed_assignments: List[str], # list of passed assignment. Must in the column of gradescope csv
                               total_credit = 120 # total number of allowed late hours
                            ) -> List[dict]: # {email: (str: late_assignments, int: late_hours, bool: penalty_applied )}, {email: int total_late_hours}
        late_assignments = defaultdict(list)
        total_late_hours = defaultdict(int)
        self.gradescope["_late_balance"] = total_credit
        for passed_assignment in passed_assignments:
            late_hours = self.calculate_late_hour(passed_assignment)
            late_balance = self.gradescope["_late_balance"] - late_hours
            # do not deduct balanced if late penalty is applied.
            # mask only the late hours within the range of the allowance
            valid_balance_mask = late_balance >= 0
            self.gradescope.loc[valid_balance_mask, "_late_balance"] = late_balance
            penalty_applied = self.gradescope.index[~valid_balance_mask]
            for email, late_hour in late_hours.items(): 
                late_assignments[email].append(
                    (passed_assignment, late_hour, email in penalty_applied)
                )
                total_late_hours[email] += late_hour
        return late_assignments, total_late_hours

    def calculate_total_score(self,
                              components:List[str], # components of a single assignment. Must in the column of gradescope csv
                             ) -> pd.Series:
        "Calculate the total score of an assignment"
        self.gradescope["target_total"] = 0
        for component in components:
            self.gradescope["target_total"] += self.gradescope[component]
        return self.gradescope["target_total"]

    def _post_grade(self,
                    student_id: int, # canvas student id of a student. found in self.email_to_canvas_id
                    grade: float, # grade of that assignment
                    text_comment="", # Text comment of the submission. Can feed
                    force=False, # Whether force to post grade for all students. If False (default), it will skip post for the same score.
                  ) -> canvasapi.submission.Submission: # created submission
        "Post grade and comment to canvas to the target assignment"
        submission = self.assignment.get_submission(student_id)
        if not force and submission.score == grade:
            if self.verbosity != 0:
                print(f"Grade for {bcolors.OKGREEN+self.canvas_id_to_email[student_id]+bcolors.ENDC} did not change.\n"
                      f"{bcolors.OKCYAN}Skipped{bcolors.ENDC}.\n"
                     )
            return
        edited = submission.edit(
            submission={
                'posted_grade': grade
            }, comment={
                'text_comment': text_comment
            }
        )
        if self.verbosity != 0:
            print(f"Grade for {bcolors.OKGREEN+self.canvas_id_to_email[student_id]+bcolors.ENDC} Posted! \n Grade: {bcolors.OKGREEN+str(grade)+bcolors.ENDC} \n Comment: {bcolors.OKGREEN+text_comment+bcolors.ENDC} \n")
        return edited

    def post_to_canvas(self,
                       target_assignment:str, # target assignment name to grab the late time. Must in the column of gradescope csv 
                       passed_assignments:List[str], # list of passed assignment. Must in the column of gradescope csv
                       components=[], # components of a single assignment. Must in the column of gradescope csv
                       total_credit=120, # total number of allowed late hours
                       post=False, # For testing purposes. Can halt the post-operation
                       force=False, # whether force to post grade for all students. If False (default), it will skip post for the same score.
                       student=[], # list of student email to post grade. If empty, it will post all students
                      ):
        "Post grade to canvas with late penalty."
        if self.gradescope is None:
            raise ValueError("Gradescope CSV has not been loaded. Please set it via process_grade.load_gradescope_csv")
        if self.assignment is None:
            raise ValueError("Assignment has not been link. Please link the assignment.")
        credit_balance = self.calculate_credit_balance(passed_assignments, total_credit=total_credit)
        late_hours = self.calculate_late_hour(target_assignment)
        if len(components) > 1:
            total_score = self.calculate_total_score(components)
        else:
            total_score = self.gradescope[target_assignment]
        # Post Grade
        if not force and self.verbosity != 0:
            print("Force Posting Disabled. If you need to completely overwrite student scores, please set force=True")
        for email, _ in self.gradescope.iterrows():
            if email in self.course_staffs_emails:
                # the course staffs did not have a canvas profile and thus don't need to post grade
                continue
            if len(student) > 0 and email not in student:
                # if student list is provided, only post the grade for the student in the lit
                continue
            remaining = credit_balance[email]
            score, slip_hour = round(total_score[email], 4), late_hours[email]
            message = f"{target_assignment}: \n"
            if slip_hour > 0:
                # means late submission. Check remaining slip day
                message += f"Late Submission: {int(slip_hour)} Hours Late\n"
                if remaining - slip_hour < 0:
                    message += "Insufficient Slip Credit. 25% late penalty applied\n"
                    score = round(score * 0.75, 4)
                else:
                    message += "Slip Credit Used. No late penalty applied\n"
                    remaining = remaining - slip_hour
            else:
                if score == 0:
                    message += "No/Invalid Submission\n"
                else:
                    message += "Submitted in-time\n"
            message += f"Remaining Slip Credit: {int(remaining)} Hours"
            if post:
                try:
                    student_id = self.email_to_canvas_id[email.split("@")[0]]
                    self._post_grade(grade=score,
                                     student_id=student_id,
                                     text_comment=message,
                                     force=force
                                    )
                except Exception as e:
                    print(f"Student: {bcolors.WARNING+email+bcolors.ENDC} Not found on canvas.\n"
                          f"Maybe Testing Account or Dropped Student\n")
                    print(e)
            else:
                print(
                    f"{bcolors.WARNING}Post Disabled{bcolors.ENDC}\n"
                    f"The message for {email.split('@')[0]} is: \n{bcolors.OKGREEN+message+bcolors.ENDC}\n Grade: {bcolors.OKGREEN+str(score)+bcolors.ENDC} \n"
                )
