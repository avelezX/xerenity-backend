"""
All Loans Server — portfolio-level loan analysis endpoint.

Supports two modes:
  1. With CurveManager (new): NPV, mark-to-market P&L, DV01, market-consistent metrics
  2. Without CurveManager (legacy): IRR-based metrics using legacy cashflow calculator

The mode is determined by whether 'use_market_pricing' is True in the request body.
"""
import pandas as pd
from server.main_server import XerenityFunctionServer, XerenityError, responseHttpOk
from loans_calculator.portfolio_summary_function import LoanPortfolioAnalyzer


class AllLoanServer(XerenityFunctionServer):
    def __init__(self, body):
        expected = {
            'filter_date': [str]
        }

        body_fields = set(expected).difference(body.keys())

        if len(body_fields) > 0:
            raise XerenityError(message="Missing fields {}".format(str(body_fields)), code=400)

        self.all_loan_data = body
        self.filter_date = body['filter_date']
        self.use_market_pricing = body.get('use_market_pricing', False)

    def _build_curve_manager(self):
        """Build CurveManager with latest market data for NPV calculations."""
        try:
            from pricing.curves.curve_manager import CurveManager
            from pricing.data.market_data import MarketDataLoader

            cm = CurveManager()
            loader = MarketDataLoader()
            cm.build_all(loader)
            return cm
        except Exception as e:
            print(f"Warning: Could not build CurveManager: {e}")
            return None

    def calculate(self):
        cm = None
        if self.use_market_pricing:
            cm = self._build_curve_manager()

        analyzer = LoanPortfolioAnalyzer(
            all_loan_data=self.all_loan_data,
            filter_date=self.filter_date,
            curve_manager=cm,
        )
        analyzer.retrieve_data()
        analyzer.process_loans()
        analyzer.aggregate_data()
        analyzer.calculate_weighted_averages()
        final_df = analyzer.get_final_dataframe()

        result = {
            'portfolio': final_df.to_dict(orient="records"),
            'summary': analyzer.get_portfolio_summary(),
            'failed_loans': analyzer.get_failed_loans(),
        }

        return responseHttpOk(body=result)
