# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/api/00_gradescope_process_grade.ipynb.

# %% auto 0
__all__ = ['bcolors', 'gradescope_grade']

# %% ../nbs/api/00_gradescope_process_grade.ipynb 3
import canvasapi
from canvasapi import Canvas
import numpy as np
import pandas as pd
import json
from datetime import datetime

# %% ../nbs/api/00_gradescope_process_grade.ipynb 4
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

# %% ../nbs/api/00_gradescope_process_grade.ipynb 5
class gradescope_grade:
    def __init__(self,
                 credentials_fp = "", # credential file path. [Template of the credentials.json](https://github.com/FleischerResearchLab/CanvasGroupy/blob/main/nbs/credentials.json)
                 API_URL="https://canvas.ucsd.edu", # the domain name of canvas
                 course_id="", # Course ID, can be found in the course url
                 assignment_id=-1, # assignment id, can be found in the canvas assignment url
                 gradescope_fp="", # gradescope csv file path 
                 verbosity=0 # Controls the verbosity: 0 = Silent, 1 = print all messages
                ):
        "Initialize Canvas Group within a Group Set and its appropriate memberships"
        self.API_URL = API_URL
        self.canvas = None
        self.course = None
        self.users = None
        self.email_to_canvas_id = None
        self.canvas_id_to_email = None
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
        self.users = list(self.course.get_users())
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
                    print(f"{bcolors.WARNING}Failed to Parse email and id"
                          f" for {bcolors.UNDERLINE}{u.short_name}{bcolors.ENDC}{bcolors.ENDC}")

    def link_assignment(self,
                        assignment_id: int # assignment id, found at the url of assignmnet tab
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
        # calculate how many slip day (hours) used for this assignment.
        late_hours = (
            late_col.str.split(":").str[0].astype(int) + 
            np.ceil(late_col.str.split(":").str[1].astype(int)/60)
        )
        return late_hours
        
    def calculate_credit_balance(self,
                                 passed_assignments:[str], # list of passed assignment. Must in the column of gradescope csv
                                 total_credit = 120 # total number of allowed late hours
                                ) -> dict: # {email: credit balance} late credit balance of each students
        "Calculate the balance of late hours from the gradescope file"
        self.gradescope["late balance"] = total_credit
        for passed in passed_assignments:
            late_hours = self.calculate_late_hour(passed)
            self.gradescope["late balance"] = self.gradescope["late balance"] - late_hours
        return self.gradescope["late balance"]
    
    def calculate_total_score(self,
                              components:[str], # components of a single assignment. Must in the column of gradescope csv
                             ) -> pd.Series:
        "Calculate the total score of an assignment"
        self.gradescope["target_total"] = 0
        for component in components:
            self.gradescope["target_total"] += self.gradescope[component]
        return self.gradescope["target_total"]
    
    def _post_grade(self,
                   student_id: int, # canvas student id of student. found in self.email_to_canvas_id
                   grade: float, # grade of that assignment
                   text_comment="", # text comment of the submission. Can feed
                  ) -> canvasapi.submission.Submission: # created submission
        "Post grade and comment to canvas to the target assignment"
        submission = self.assignment.get_submission(student_id)
        edited = submission.edit(
            submission={
                'posted_grade': grade
            }, comment={
                'text_comment': text_comment
            }
        )
        if self.verbosity != 0:
            print(f"Grade for {bcolors.OKGREEN+email+bcolors.ENDC} Posted!")
        return edited
    
    def post_to_canvas(self,
                       target_assignment:str, # target assignment name to grab the late time. Must in the column of gradescope csv 
                       passed_assignments:[str], # list of passed assignment. Must in the column of gradescope csv
                       components:[str], # components of a single assignment. Must in the column of gradescope csv
                       post=True, # for testing purposes. Can hault the post operation
                      ):
        "Post grade to canvas with late penalty."
        if self.gradescope is None:
            raise ValueError("Gradescope CSV has not been loaded. Please set it via process_grade.load_gradescope_csv")
        credit_balance = self.calculate_credit_balance(passed_assignments)
        late_hours = self.calculate_late_hour(target_assignment)
        if len(components) > 1:
            total_score = self.calculate_total_score(components)
        else:
            total_score = self.gradescope[target_assignment]
        # Post Grade
        for email, _ in self.gradescope.iterrows():
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
            else:
                message += "Submitted intime\n"
            balance_after = remaining - slip_hour
            message += f"Remaining Slip Credit: {int(balance_after)} Hours"
            try:
                if post:
                    student_id = grade.email_to_canvas_id[email.split("@")[0]]
                    grade._post_grade(grade=score, student_id=student_id, text_comment=message)
                else:
                    print(f"{bcolors.WARNING}Post Disabled{bcolors.ENDC}\n"
                          f"The message is: \n{bcolors.OKGREEN+message+bcolors.ENDC}"
                         )
            except Exception as e:
                print(f"Studnet: {bcolors.WARNING+email+bcolors.ENDC} Not found on canvas. \n"
                      f"Maybe Testing Account or Dropped Student")
                print(e)
                pass
        
