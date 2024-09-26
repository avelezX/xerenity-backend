import os
import json
from src.xerenity.xty import Xerenity
from server.loan_calculator.loan_calculator import LoanCalculatorServer

xty = Xerenity(
    username=os.getenv('XTY_USER'),
    password=os.getenv('XTY_PWD'),
)

all_loans_data = xty.get_loans_data(
    filter_date="2024-09-25",
    loans=["74b1af78-0430-40d1-a643-ddfff9c213e1", "eb29e2f0-265d-42b9-ad87-e846a1cd1f52",
           "1437dbcc-a96b-42a4-ab62-2d8c42ac255c", "edcfc203-e2ca-4c79-ad10-820376476587"]
)

open("all_loan.json", "w+").write(json.dumps(all_loans_data))
