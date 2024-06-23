from loan.Loan import Loan
import QuantLib as ql
import pandas as pd
from utilities.date_functions import ql_to_datetime


class UvrLoan(Loan):
    def generate_cash_flow(self, value_date=None, uvr=None):
        """
        Generates a cash flow table for the loan.

        Returns:
        - pd.DataFrame: A DataFrame containing the cash flow details.
        """
        monthly_payment = self.calculate_custom_period_payment()
        periods = list(range(1, self.number_of_payments + 1))

        interest_payment = []
        principal_payment = []
        ending_balance = []
        date_list = []
        current_balance = self.original_balance

        for i in range(len(periods)):
            date_list.append(
                self.start_date_ql + ql.Period(int((i + 1) * (12 * self.number_to_user[self.periodicity])), ql.Months))
            interest_payment.append(
                current_balance * (self.interest_rate / 100 * self.number_to_user[self.periodicity]))
            principal_payment.append(monthly_payment - interest_payment[-1])
            ending_balance.append(current_balance - principal_payment[-1])

            current_balance = ending_balance[-1]

        # date_list = [self.start_date_ql + ql.Period(i, ql.Months) for i in range(len(periods))]
        date_list = [ql_to_datetime(ql_date) for ql_date in date_list]
        cf_data = {
            'date': date_list,
            'interest': interest_payment,
            'rate': self.interest_rate,
            'principal': principal_payment,
            'payment': [monthly_payment] * len(periods),
            'ending_balance': ending_balance,
            'beginning_balance': [self.original_balance] + ending_balance[:-1]
        }

        cf_table = pd.DataFrame(data=cf_data, index=periods)
        cf_table = cf_table[['date', 'beginning_balance', 'rate', 'payment', 'interest', 'principal', 'ending_balance']]

        return cf_table
