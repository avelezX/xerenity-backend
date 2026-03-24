"""
Loan Portfolio Analyzer.

Aggregates a portfolio of loans (fija, IBR, UVR) and computes:
  - Per-loan: NPV (market), principal outstanding, accrued interest, IRR, duration, tenor
  - Per-bank: weighted averages of all metrics, broken down by loan type
  - Portfolio: total NPV, DV01, weighted cost of debt, mark-to-market P&L

Uses the new pricing infrastructure (IbrLoanPricer, FixedLoanPricer, UvrLoanPricer)
with CurveManager for market-consistent discounting.

Fallback: when CurveManager is not available (no curves built), falls back to
the legacy LoanCalculatorServer + funciones_analisis_credito pipeline.
"""
import pandas as pd
import numpy as np
from datetime import datetime
from utilities.date_functions import datetime_to_ql, ql_to_datetime

# Day count convention mapping (internal → IRR calculation convention)
DAY_COUNT_MAP = {
    'por_dias_360': '30/360',
    'por_dias_365': 'actual/365',
    'por_periodo': '30/360',  # default fallback for IRR calc
}


class LoanPortfolioAnalyzer:
    """
    Analyzes a portfolio of loans with market-consistent pricing.

    Args:
        all_loan_data: dict with keys:
            - loans: list of loan dicts (id, owner, type, interest_rate, periodicity,
              number_of_payments, start_date, original_balance, days_count,
              grace_type, grace_period, min_period_rate, bank, loan_identifier)
            - db_info: historical IBR/rate data for curve building
            - db_info_uvr: historical UVR values
            - filter_date: valuation date string 'YYYY-MM-DD'
        filter_date: valuation date as string 'YYYY-MM-DD'
        curve_manager: optional CurveManager instance (for NPV/DV01)
    """

    def __init__(self, all_loan_data, filter_date, curve_manager=None):
        self.all_loans_data = all_loan_data
        self.filter_date = filter_date
        self.cm = curve_manager

        # Parsed dates
        self.value_date = None
        self.value_date_dt = None

        # Raw data
        self.db_info = None
        self.db_info_uvr = None

        # Results per loan
        self.loan_results = []
        self.failed_loans = []

        # Aggregated results
        self.bank_data = {}
        self.portfolio_totals = {}

    def retrieve_data(self):
        """Parse dates and extract db_info from input."""
        self.value_date = datetime_to_ql(datetime.strptime(self.filter_date, '%Y-%m-%d'))
        self.value_date_dt = datetime.strptime(self.filter_date, '%Y-%m-%d')
        self.db_info = self.all_loans_data.get('db_info')
        self.db_info_uvr = self.all_loans_data.get('db_info_uvr')

    def process_loans(self):
        """
        Process each loan: generate cashflows and compute analytics.

        Uses new pricers (IbrLoanPricer, FixedLoanPricer, UvrLoanPricer) when
        CurveManager is available. Falls back to legacy pipeline otherwise.
        """
        if self.cm is not None:
            self._process_with_pricers()
        else:
            self._process_legacy()

    def _process_with_pricers(self):
        """Process loans using the new pricing infrastructure."""
        from pricing.instruments.ibr_loan import IbrLoanPricer
        from pricing.instruments.fixed_loan import FixedLoanPricer
        from pricing.instruments.uvr_loan import UvrLoanPricer
        from pricing.instruments.loan_utils import resolve_loan_params

        ibr_pricer = IbrLoanPricer(self.cm)
        fixed_pricer = FixedLoanPricer(self.cm)
        uvr_pricer = UvrLoanPricer(self.cm)

        for i, loan in enumerate(self.all_loans_data['loans']):
            try:
                # Resolve maturity_date and amortization_type (supports both new and legacy format)
                resolved = resolve_loan_params(loan)
                loan_type = loan.get('type', 'fija')
                start_date = resolved['start_date_dt']
                maturity_date = resolved['maturity_date_dt']
                amort_type = resolved['amortization_type_resolved']
                periodicity = loan['periodicity']

                # Skip expired loans
                if maturity_date <= self.value_date_dt:
                    continue

                # Skip loans that haven't started yet
                if start_date > self.value_date_dt:
                    continue

                common_args = dict(
                    notional=float(loan['original_balance']),
                    start_date=start_date,
                    maturity_date=maturity_date,
                    periodicity=periodicity,
                    days_count=loan.get('days_count', 'por_dias_360'),
                    grace_type=loan.get('grace_type'),
                    grace_period=int(loan.get('grace_period', 0) or 0),
                )

                if loan_type == 'ibr':
                    result = ibr_pricer.price(
                        spread_pct=float(loan['interest_rate']),
                        amortization_type=amort_type,
                        min_period_rate=float(loan['min_period_rate']) if loan.get('min_period_rate') else None,
                        db_info=self.db_info,
                        **common_args,
                    )
                    npv = result['npv']

                elif loan_type == 'fija':
                    result = fixed_pricer.price(
                        rate_pct=float(loan['interest_rate']),
                        amortization_type=amort_type,
                        **common_args,
                    )
                    npv = result['npv']

                elif loan_type == 'uvr':
                    result = uvr_pricer.price(
                        notional_uvr=float(loan['original_balance']),
                        start_date=start_date,
                        maturity_date=maturity_date,
                        rate_pct=float(loan['interest_rate']),
                        periodicity=periodicity,
                        days_count=loan.get('days_count', 'por_dias_360'),
                        amortization_type=amort_type,
                        grace_type=loan.get('grace_type'),
                        grace_period=int(loan.get('grace_period', 0) or 0),
                        db_info=self.db_info_uvr,
                    )
                    npv = result['npv_cop']
                else:
                    self.failed_loans.append({
                        'loan_id': loan.get('id'), 'reason': f"Unknown type: {loan_type}"
                    })
                    continue

                self.loan_results.append({
                    'loan_id': loan.get('id'),
                    'loan_identifier': loan.get('loan_identifier'),
                    'bank': loan.get('bank', 'Unknown'),
                    'type': loan_type,
                    'notional': float(loan['original_balance']),
                    'npv': npv,
                    'principal_outstanding': result.get('principal_outstanding',
                                                         result.get('principal_outstanding_cop', 0)),
                    'accrued_interest': result.get('accrued_interest',
                                                    result.get('accrued_interest_cop', 0)),
                    'total_value': result.get('total_value',
                                              result.get('total_value_cop', 0)),
                    'duration': result.get('duration', 0),
                    'tenor_years': result.get('tenor_years', 0),
                    'avg_rate_pct': result.get('avg_rate_pct', result.get('rate_pct', 0)),
                    'periods_total': result.get('periods_total', 0),
                    'periods_remaining': result.get('periods_remaining', 0),
                })

            except Exception as e:
                self.failed_loans.append({
                    'loan_id': loan.get('id'),
                    'loan_identifier': loan.get('loan_identifier'),
                    'reason': f"{type(e).__name__}: {e}",
                })

    def _process_legacy(self):
        """Fallback: process loans using legacy LoanCalculatorServer."""
        from server.loan_calculator.loan_calculator import LoanCalculatorServer
        from loans_calculator.funciones_analisis_credito import create_cashflows_and_total_value

        for i, loan in enumerate(self.all_loans_data['loans']):
            try:
                loan_temp = loan.copy()
                loan_type = loan_temp.get('type', 'fija')

                if loan_type == 'uvr':
                    loan_temp['db_info'] = self.db_info_uvr
                    calc = LoanCalculatorServer(loan_temp, local_dev=True)
                    loan_payments = calc.cash_flow_uvr()
                elif loan_type == 'fija':
                    loan_temp['db_info'] = self.db_info
                    calc = LoanCalculatorServer(loan_temp, local_dev=True)
                    loan_payments = calc.cash_flow()
                elif loan_type == 'ibr':
                    loan_temp['db_info'] = self.db_info
                    calc = LoanCalculatorServer(loan_temp, local_dev=True)
                    loan_payments = calc.cash_flow_ibr()
                else:
                    self.failed_loans.append({
                        'loan_id': loan.get('id'), 'reason': f"Unknown type: {loan_type}"
                    })
                    continue

                start_date = datetime.strptime(loan['start_date'], '%Y-%m-%d')
                convention = DAY_COUNT_MAP.get(loan.get('days_count', 'por_dias_360'), '30/360')

                variables = create_cashflows_and_total_value(
                    pd.DataFrame(loan_payments),
                    self.value_date,
                    start_date,
                    convention,
                )

                total_value = variables.get('total_value', 0) or 0
                accrued = variables.get('accrued_interest', 0) or 0
                irr = variables.get('irr', 0) or 0
                duration = variables.get('duration', 0) or 0
                tenor = variables.get('tenor', 0) or 0
                last_payment = variables.get('last_payment')

                # Skip expired or not-yet-started loans
                if last_payment is not None:
                    last_dt = last_payment if isinstance(last_payment, datetime) else pd.Timestamp(last_payment).to_pydatetime()
                    if last_dt <= self.value_date_dt:
                        continue
                if start_date > self.value_date_dt:
                    continue

                self.loan_results.append({
                    'loan_id': loan.get('id'),
                    'loan_identifier': loan.get('loan_identifier'),
                    'bank': loan.get('bank', 'Unknown'),
                    'type': loan_type,
                    'notional': float(loan['original_balance']),
                    'npv': None,  # Not available in legacy mode
                    'principal_outstanding': total_value - accrued,
                    'accrued_interest': accrued,
                    'total_value': total_value,
                    'duration': duration,
                    'tenor_years': tenor,
                    'avg_rate_pct': irr * 100 if irr else 0,
                    'periods_total': 0,
                    'periods_remaining': 0,
                })

            except Exception as e:
                self.failed_loans.append({
                    'loan_id': loan.get('id'),
                    'loan_identifier': loan.get('loan_identifier'),
                    'reason': f"{type(e).__name__}: {e}",
                })

    def aggregate_data(self):
        """
        Aggregate loan results by bank and compute weighted averages.

        Metrics computed per bank:
          - total_value: sum of (principal_outstanding + accrued_interest)
          - npv: sum of market NPV (None if legacy mode)
          - weighted average: IRR, duration, tenor (weighted by total_value)
          - breakdown by type: fija, ibr, uvr
        """
        for loan in self.loan_results:
            bank = loan['bank'] or 'Unknown'
            total_value = loan['total_value']

            if total_value is None or np.isnan(total_value) or total_value <= 0:
                self.failed_loans.append({
                    'loan_id': loan['loan_id'],
                    'reason': f"Invalid total_value: {total_value}",
                })
                continue

            if bank not in self.bank_data:
                self.bank_data[bank] = {
                    'total_value': 0, 'npv': 0,
                    'accrued_interest': 0,
                    'weighted_rate_sum': 0, 'weighted_duration_sum': 0,
                    'weighted_tenor_sum': 0,
                    'loan_count': 0, 'loan_ids': [],
                    # By type
                    'total_value_fija': 0, 'weighted_rate_fija_sum': 0,
                    'total_value_ibr': 0, 'weighted_rate_ibr_sum': 0,
                    'total_value_uvr': 0, 'weighted_rate_uvr_sum': 0,
                }

            bd = self.bank_data[bank]
            bd['total_value'] += total_value
            bd['accrued_interest'] += loan['accrued_interest'] or 0
            bd['weighted_rate_sum'] += (loan['avg_rate_pct'] or 0) * total_value
            bd['weighted_duration_sum'] += (loan['duration'] or 0) * total_value
            bd['weighted_tenor_sum'] += (loan['tenor_years'] or 0) * total_value
            bd['loan_count'] += 1
            bd['loan_ids'].append(loan['loan_id'])

            if loan['npv'] is not None:
                bd['npv'] += loan['npv']

            loan_type = loan['type']
            if loan_type == 'fija':
                bd['total_value_fija'] += total_value
                bd['weighted_rate_fija_sum'] += (loan['avg_rate_pct'] or 0) * total_value
            elif loan_type == 'ibr':
                bd['total_value_ibr'] += total_value
                bd['weighted_rate_ibr_sum'] += (loan['avg_rate_pct'] or 0) * total_value
            elif loan_type == 'uvr':
                bd['total_value_uvr'] += total_value
                bd['weighted_rate_uvr_sum'] += (loan['avg_rate_pct'] or 0) * total_value

        # Compute weighted averages per bank
        for bank, bd in self.bank_data.items():
            tv = bd['total_value']
            bd['avg_rate'] = bd['weighted_rate_sum'] / tv if tv > 0 else None
            bd['avg_duration'] = bd['weighted_duration_sum'] / tv if tv > 0 else None
            bd['avg_tenor'] = bd['weighted_tenor_sum'] / tv if tv > 0 else None
            bd['avg_rate_fija'] = (bd['weighted_rate_fija_sum'] / bd['total_value_fija']
                                   if bd['total_value_fija'] > 0 else None)
            bd['avg_rate_ibr'] = (bd['weighted_rate_ibr_sum'] / bd['total_value_ibr']
                                  if bd['total_value_ibr'] > 0 else None)
            bd['avg_rate_uvr'] = (bd['weighted_rate_uvr_sum'] / bd['total_value_uvr']
                                  if bd['total_value_uvr'] > 0 else None)
            bd['mtm_pnl'] = bd['npv'] - bd['total_value'] if bd['npv'] else None

    def calculate_weighted_averages(self):
        """Compute portfolio-level weighted averages across all banks."""
        total_value = sum(bd['total_value'] for bd in self.bank_data.values())
        total_npv = sum(bd['npv'] for bd in self.bank_data.values())
        total_accrued = sum(bd['accrued_interest'] for bd in self.bank_data.values())
        total_loans = sum(bd['loan_count'] for bd in self.bank_data.values())

        total_value_fija = sum(bd['total_value_fija'] for bd in self.bank_data.values())
        total_value_ibr = sum(bd['total_value_ibr'] for bd in self.bank_data.values())
        total_value_uvr = sum(bd['total_value_uvr'] for bd in self.bank_data.values())

        weighted_rate = sum(bd['weighted_rate_sum'] for bd in self.bank_data.values())
        weighted_duration = sum(bd['weighted_duration_sum'] for bd in self.bank_data.values())
        weighted_tenor = sum(bd['weighted_tenor_sum'] for bd in self.bank_data.values())
        weighted_rate_fija = sum(bd['weighted_rate_fija_sum'] for bd in self.bank_data.values())
        weighted_rate_ibr = sum(bd['weighted_rate_ibr_sum'] for bd in self.bank_data.values())
        weighted_rate_uvr = sum(bd['weighted_rate_uvr_sum'] for bd in self.bank_data.values())

        self.portfolio_totals = {
            'total_value': total_value,
            'npv': total_npv,
            'mtm_pnl': total_npv - total_value if total_npv else None,
            'accrued_interest': total_accrued,
            'loan_count': total_loans,
            'failed_count': len(self.failed_loans),
            'avg_rate': weighted_rate / total_value if total_value > 0 else None,
            'avg_duration': weighted_duration / total_value if total_value > 0 else None,
            'avg_tenor': weighted_tenor / total_value if total_value > 0 else None,
            # By type
            'total_value_fija': total_value_fija,
            'total_value_ibr': total_value_ibr,
            'total_value_uvr': total_value_uvr,
            'avg_rate_fija': weighted_rate_fija / total_value_fija if total_value_fija > 0 else None,
            'avg_rate_ibr': weighted_rate_ibr / total_value_ibr if total_value_ibr > 0 else None,
            'avg_rate_uvr': weighted_rate_uvr / total_value_uvr if total_value_uvr > 0 else None,
        }

    def get_final_dataframe(self):
        """
        Build summary DataFrame with one row per bank + totals row.

        Returns:
            pd.DataFrame sorted by total_value descending
        """
        rows = []
        for bank, bd in self.bank_data.items():
            rows.append({
                'bank': bank,
                'total_value': bd['total_value'],
                'npv': bd['npv'] or None,
                'mtm_pnl': bd['mtm_pnl'],
                'accrued_interest': bd['accrued_interest'],
                'avg_rate': bd['avg_rate'],
                'avg_duration': bd['avg_duration'],
                'avg_tenor': bd['avg_tenor'],
                'loan_count': bd['loan_count'],
                'total_value_fija': bd['total_value_fija'],
                'avg_rate_fija': bd['avg_rate_fija'],
                'total_value_ibr': bd['total_value_ibr'],
                'avg_rate_ibr': bd['avg_rate_ibr'],
                'total_value_uvr': bd['total_value_uvr'],
                'avg_rate_uvr': bd['avg_rate_uvr'],
                'loan_ids': bd['loan_ids'],
            })

        # Totals row
        t = self.portfolio_totals
        rows.append({
            'bank': 'TOTAL',
            'total_value': t.get('total_value', 0),
            'npv': t.get('npv'),
            'mtm_pnl': t.get('mtm_pnl'),
            'accrued_interest': t.get('accrued_interest', 0),
            'avg_rate': t.get('avg_rate'),
            'avg_duration': t.get('avg_duration'),
            'avg_tenor': t.get('avg_tenor'),
            'loan_count': t.get('loan_count', 0),
            'total_value_fija': t.get('total_value_fija', 0),
            'avg_rate_fija': t.get('avg_rate_fija'),
            'total_value_ibr': t.get('total_value_ibr', 0),
            'avg_rate_ibr': t.get('avg_rate_ibr'),
            'total_value_uvr': t.get('total_value_uvr', 0),
            'avg_rate_uvr': t.get('avg_rate_uvr'),
            'loan_ids': [],
        })

        df = pd.DataFrame(rows)

        # Output columns
        cols = [
            'bank', 'total_value', 'npv', 'mtm_pnl', 'accrued_interest',
            'avg_rate', 'avg_duration', 'avg_tenor', 'loan_count',
            'total_value_fija', 'avg_rate_fija',
            'total_value_ibr', 'avg_rate_ibr',
            'total_value_uvr', 'avg_rate_uvr',
            'loan_ids',
        ]
        df = df[[c for c in cols if c in df.columns]]
        df = df.fillna(0)

        # Sort banks by total_value, keep TOTAL at the bottom
        bank_rows = df[df['bank'] != 'TOTAL'].sort_values('total_value', ascending=False)
        total_row = df[df['bank'] == 'TOTAL']
        return pd.concat([bank_rows, total_row], ignore_index=True)

    def get_loan_details(self):
        """Return per-loan results as a list of dicts."""
        return self.loan_results

    def get_failed_loans(self):
        """Return list of loans that failed processing with reasons."""
        return self.failed_loans

    def get_portfolio_summary(self):
        """Return portfolio-level summary dict."""
        return self.portfolio_totals
