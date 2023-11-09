import sys
sys.path.append("/Users/avelezxerenity/Documents/GitHub/pysdk")
import os
from inflation_query.Inflation_query import implied_inflation_calc
from src.xerenity.xty import Xerenity
from utilities.date_functions import add_months,ql_to_datetime
from swap_functions.ibr_quantlib_details import ibr_quantlib_det,ibr_overnight_index,ibr_swap_cupon_helper,depo_helpers_ibr
from    dates_convention_to_ql
import pandas as pd
import QuantLib as ql
import plotly.graph_objects as go
from datetime import datetime,date
xty = Xerenity(
    username=os.getenv('XTY_USER'),
    password=os.getenv('XTY_PWD'),
)





####################################
####---Creating the IBR swaps helpers
####################################
###

# Create the helpers ( qutes) in the quantlib library.
#Input a 




def ibr_swaps_helpers(ibr_quotes):

    OIS_helpers = []
    for key, value in ibr_quotes.items():

        if ql.Period(ibr_quotes['tenor'],dates_convention_to_ql(ibr_quotes['tenor_period']))<=ql.Period(18,ql.Months):
            OIS_helpers.append(depo_helpers_ibr(ibr_quotes['rate'],ibr_quotes['tenor'],ibr_quotes['tenor_unit']))

        else:
            OIS_helpers.append( ibr_swap_cupon_helper(ibr_quotes['rate'],ibr_quotes['tenor'],ibr_quotes['tenor_unit']))

  