"""
Shared utilities for loan pricers.

Provides parameter resolution logic so that loans can be defined either by:
  - maturity_date (preferred, explicit)
  - number_of_payments + periodicity (legacy, derived)

Also resolves amortization_type defaults per loan type.
"""
import QuantLib as ql
from datetime import datetime
from utilities.date_functions import datetime_to_ql, ql_to_datetime

# Periodicity → months per period
PERIODICITY_MONTHS = {
    "Anual": 12,
    "Semestral": 6,
    "Trimestral": 3,
    "Bimensual": 2,
    "Mensual": 1,
}

# Default amortization per loan type
DEFAULT_AMORTIZATION = {
    "fija": "french",
    "ibr": "linear",
    "uvr": "french",
}


def resolve_maturity(
    start_date,
    maturity_date=None,
    number_of_payments: int = None,
    periodicity: str = None,
) -> datetime:
    """
    Resolve the maturity date from either explicit maturity_date or
    number_of_payments + periodicity.

    Args:
        start_date: str (YYYY-MM-DD) or datetime
        maturity_date: str (YYYY-MM-DD), datetime, or None
        number_of_payments: int or None
        periodicity: str (Anual, Semestral, etc.) or None

    Returns:
        datetime — the resolved maturity date

    Raises:
        ValueError if neither maturity_date nor (number_of_payments + periodicity) is provided
    """
    # Parse start_date
    if isinstance(start_date, str):
        start_date = datetime.strptime(start_date, '%Y-%m-%d')

    # Priority 1: explicit maturity_date
    if maturity_date is not None:
        if isinstance(maturity_date, str):
            return datetime.strptime(maturity_date, '%Y-%m-%d')
        return maturity_date

    # Priority 2: derive from number_of_payments + periodicity
    if number_of_payments is not None and periodicity is not None:
        if periodicity not in PERIODICITY_MONTHS:
            raise ValueError(f"Invalid periodicity '{periodicity}'. Valid: {list(PERIODICITY_MONTHS.keys())}")

        months_total = int(number_of_payments) * PERIODICITY_MONTHS[periodicity]
        start_ql = datetime_to_ql(start_date)
        maturity_ql = start_ql + ql.Period(months_total, ql.Months)
        return ql_to_datetime(maturity_ql)

    raise ValueError(
        "Must provide either 'maturity_date' or both 'number_of_payments' and 'periodicity'"
    )


def resolve_amortization_type(amortization_type=None, loan_type: str = "fija") -> str:
    """
    Resolve the amortization type, using defaults per loan type when not specified.

    Args:
        amortization_type: 'french', 'linear', 'bullet', or None
        loan_type: 'fija', 'ibr', or 'uvr'

    Returns:
        str — resolved amortization type
    """
    if amortization_type is not None:
        return amortization_type
    return DEFAULT_AMORTIZATION.get(loan_type, "french")


def resolve_loan_params(loan: dict) -> dict:
    """
    Resolve a loan dict into standardized parameters for the pricers.

    Handles both new format (with maturity_date, amortization_type) and
    legacy format (with number_of_payments only).

    Args:
        loan: dict with loan parameters from database

    Returns:
        dict with resolved: start_date (datetime), maturity_date (datetime),
        amortization_type (str), plus all original fields
    """
    start_date = loan['start_date']
    if isinstance(start_date, str):
        start_date = datetime.strptime(start_date, '%Y-%m-%d')

    maturity_date = resolve_maturity(
        start_date=start_date,
        maturity_date=loan.get('maturity_date'),
        number_of_payments=int(loan['number_of_payments']) if loan.get('number_of_payments') else None,
        periodicity=loan.get('periodicity'),
    )

    loan_type = loan.get('type', 'fija')
    amortization_type = resolve_amortization_type(
        amortization_type=loan.get('amortization_type'),
        loan_type=loan_type,
    )

    return {
        **loan,
        'start_date_dt': start_date,
        'maturity_date_dt': maturity_date,
        'amortization_type_resolved': amortization_type,
    }
