import QuantLib as ql
import datetime

# Quant Lib realted
def ql_to_string(query_date=ql.Date):
    return '{:02d}/{:02d}/{}'.format(query_date.month(), query_date.dayOfMonth(), query_date.year())

def datetime_to_ql(dt):
    return ql.Date(dt.day, dt.month, dt.year)

def ql_to_datetime(d):
    return datetime.datetime(d.year(), d.month(), d.dayOfMonth())

def add_months(date,months):
    sig= ql.Date(date.day, date.month, date.year) + ql.Period(months,ql.Months)
    sig= ql.Date(sig.dayOfMonth(),sig.month(),sig.year())
    return ql_to_datetime(sig)

def columns_with_date(df):

    def check_column_name(name):
        return 'Date' in name or 'date' in name or 'time' in name or 'Time' in name

    # Identify columns meeting the condition
    return [col for col in df if check_column_name(col)]

def fit_nelson_siegel(x, y):
    def nelson_siegel_curve(t, beta0, beta1, beta2, tau):
        return beta0 + beta1 * ((1 - np.exp(-t / tau)) / (t / tau)) + beta2 * (((1 - np.exp(-t / tau)) / (t / tau)) - np.exp(-t / tau))



# Function to calculate days using ql.Thirty360 (BondBasis)
def days_30_360(start_date, end_date):
    day_count = ql.Thirty360(ql.Thirty360.BondBasis)
    return day_count.dayCount(ql.Date(start_date.day, start_date.month, start_date.year),
                              ql.Date(end_date.day, end_date.month, end_date.year))

# Function to calculate days using ql.ActualActual (ISDA)
def days_actual_actual(start_date, end_date):
    day_count = ql.ActualActual(ql.ActualActual.ISDA)
    return day_count.dayCount(ql.Date(start_date.day, start_date.month, start_date.year),
                              ql.Date(end_date.day, end_date.month, end_date.year))

# Function to calculate days using ql.Actual365Fixed
def days_actual_365_fixed(start_date, end_date):
    day_count = ql.Actual365Fixed()
    return day_count.dayCount(ql.Date(start_date.day, start_date.month, start_date.year),
                              ql.Date(end_date.day, end_date.month, end_date.year))