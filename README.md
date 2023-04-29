# Gradescope / Nbgrader Late Penalty

<!-- WARNING: THIS FILE WAS AUTOGENERATED! DO NOT EDIT! -->

``` python
import numpy as np
import pandas as pd
```

This module support both gradescope and nbgrader.

## Install

``` sh
pip install git+https://github.com/scott-yj-yang/LatePenalty.git
```

## How to use

``` python
from LatePenalty.gradescope import gradescope_grade
```

``` python
grade = gradescope_grade("../../credentials.json",
                         course_id=45059,
                         assignment_id=641795,
                         gradescope_fp="data/gradescope_example.csv",
                         verbosity=1,
                        )
```

    Authorization Successful!
    Course Set:  COGS 118A - Supvr/Mach Learning Algorithms - Fleischer [SP23] 
    Getting List of Users... This might take a while...
    Users Fetch Complete! The course has 173 users.
    Assignment A1 Link!

``` python
# take a look at the csv file
grade.gradescope
```

<div>
<style scoped>
    .dataframe tbody tr th:only-of-type {
        vertical-align: middle;
    }
&#10;    .dataframe tbody tr th {
        vertical-align: top;
    }
&#10;    .dataframe thead th {
        text-align: right;
    }
</style>

|                 | First Name  | Last Name | SID       | Assignment 1 | Assignment 1 - Manual Grading | Assignment 1 - Lateness (H:M:S) |
|-----------------|-------------|-----------|-----------|--------------|-------------------------------|---------------------------------|
| Email           |             |           |           |              |                               |                                 |
| kkdwdx          | FVPqOMpv    | jhjx      | zPBPCJwDL | 0.650        | 1.8                           | 24:01:41                        |
| JhThhnUaOPDUIEb | BVTLaj      | JL        | bJhgVCFRz | 0.900        | 2.1                           | 00:00:00                        |
| dbAbqg          | uaNTaJHacrK | PNrEkH    | DqEMLsESM | 0.475        | 1.9                           | 00:00:00                        |

</div>

Use `process_grade.post_to_canvas` to directly post to canvas

``` python
grade.post_to_canvas(
    target_assignment="Assignment 1",
    passed_assignments=[],
    components=["Assignment 1", "Assignment 1 - Manual Grading"],
    post=False
)
```

    Post Disabled
    The message is: 
    Assignment 1: 
    Late Submission: 25 Hours Late
    Slip Credit Used. No late penalty applied
    Remaining Slip Credit: 95 Hours
    Post Disabled
    The message is: 
    Assignment 1: 
    Submitted intime
    Remaining Slip Credit: 120 Hours
    Post Disabled
    The message is: 
    Assignment 1: 
    Submitted intime
    Remaining Slip Credit: 120 Hours
