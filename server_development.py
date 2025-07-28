import requests
import json
from src.xerenity.xty import Xerenity
from server.loan_calculator.loan_calculator import LoanCalculatorServer

xty = Xerenity(
    username='',
    password='',
)

all_loans_data = xty.session.rpc('uvr_cash_flow_data',
                                 {"credito_id": "b78f3f59-360b-467b-b3b9-b3462cf1ea78", "filter_date": "2025-07-28"}
                                 ).execute().data

open("all_loan.json", "w+").write(json.dumps(all_loans_data))


response = requests.get('http://127.0.0.1:8000/uvr_rates',json=all_loans_data)

print(response.json())
