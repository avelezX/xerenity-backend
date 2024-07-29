# %%
import sys
#sys.path.append("/Users/avelezxerenity/Documents/GitHub/pysdk")
sys.path.append("/Users/andre/Documents/xerenity/pysdk")
from db_call.db_call import get_last_cpi, get_tes_table, get_last_cpi_lag,get_last_banrep
from bond_functions.tes_quant_lib_details import depo_helpers, tes_quantlib_det
import matplotlib.pyplot as plt
#import seaborn as sns
#import plotly.graph_objects as go
import pandas as pd
import QuantLib as ql
import datetime as dt
from utilities.date_functions import ql_to_datetime
from bond_functions.bond_curve_structures import BondCurve
from bond_functions.bond_structure import tes_bond_structure
from dotenv import load_dotenv
from src.data_source.tes.tes import Tes
from src.xerenity.xty import Xerenity
import os

load_dotenv()
print(os.getenv('XTY_USER'))
xty = Xerenity(
    username=os.getenv('XTY_USER'),
    password=os.getenv('XTY_PWD'),
)

######################################
#  Calculo de curvas implicitas en los TES
######################################
class inflacion_implicita:


    def __init__(self, calc_date=ql.Date.todaysDate(), central_bank_rate=None, 
            tes_table=None,
            inflation_lag_0=None,
            last_cpi=None,
            fixed_rate_excluded_bonds=None,
            uvr_excluded_bonds=None):

        self.calc_date=calc_date
        self.central_bank_rate=central_bank_rate/100
        self.inflation_print = last_cpi/100 
        self.tes_table=tes_table 
        self.fixed_rate_excluded_bonds=fixed_rate_excluded_bonds
        self.uvr_excluded_bonds=uvr_excluded_bonds
        self.inflation_lag_0=inflation_lag_0
        self.day_count=ql.Actual365Fixed()
        # Depo helpers for each curve.
        # COP  
        depo_maturities = [ql.Period(2, ql.Months)]
        depo_rates = [self.central_bank_rate]
        self.depo_help = depo_helpers(depo_maturities, depo_rates, details=tes_quantlib_det)

        # UVR
        depo_maturities_uvr = [ql.Period(5, ql.Days), ql.Period(2, ql.Months)]
        uvr_ov_deposit_rate = ((1+self.central_bank_rate)/(1+self.inflation_print))-1
        depo_rates_uvr = [uvr_ov_deposit_rate, uvr_ov_deposit_rate]
        self.depo_help_uvr = depo_helpers(depo_maturities_uvr, depo_rates_uvr, details=tes_quantlib_det)

        # Excluded bonds
        self.excluded_bonds=fixed_rate_excluded_bonds


    def create_date_ranges(self):
    
        end_date = self.calc_date + ql.Period(10, ql.Years)  # Limit to the next 10 years
        #day_count = ql.Actual365Fixed()
        if self.calc_date.dayOfMonth() < 15:
            init_date = ql.Date(15, self.calc_date.month(), self.calc_date.year())

        else:
            init_date = ql.Date(15, self.calc_date.month(), self.calc_date.year())+ql.Period(1, ql.Months)

        dates = [init_date]
        for m in range(1, 121):
            current_date = init_date + ql.Period(m, ql.Months)
            current_date = ql.Date(15, current_date.month(), current_date.year())
            dates.append(current_date)
        return dates



    def bond_curve_implied_inflation_mat(self):
   
        # Crear la clase bonos para los bonos en COP ( nominales tasa fija)
        cop = BondCurve(currency='COP', country='col',bond_info_df=self.tes_table, supabase=xty)
        cop_df = cop.create_df(self.excluded_bonds)
        helpers = cop.create_bond_helpers(cop_df, excluded_bonds=self.excluded_bonds)
        cop_yield_curve = cop.yield_curve_ql(self.calc_date, helpers, self.depo_help)


        # Crear la clase bonos para los bonos en COP ( nominales tasa fija)
        uvr = BondCurve('UVR', 'col', bond_info_df=self.tes_table, supabase=xty)
        uvr_df = uvr.create_df()
        helpers_uvr = uvr.create_bond_helpers(uvr_df, excluded_bonds=[])
        uvr_yield_curve = uvr.yield_curve_ql(self.calc_date, helpers_uvr, self.depo_help_uvr)

        # Poniendo las curvas en la misma matrix
        dates=self.create_date_ranges()
        date_df = pd.DataFrame(data={'Date': dates})
        date_df['Discount Factors'] = date_df['Date'].apply(lambda d: cop_yield_curve.discount(d) if cop_yield_curve.timeFromReference(d) <= cop_yield_curve.maxTime() else None)
        date_df['Zero Rates'] = date_df['Date'].apply(lambda d: cop_yield_curve.zeroRate(d, self.day_count, ql.Continuous).rate() if cop_yield_curve.timeFromReference(d) <= cop_yield_curve.maxTime() else None)
        date_df['Discount Factors_UVR'] = date_df['Date'].apply(lambda d: uvr_yield_curve.discount(d) if uvr_yield_curve.timeFromReference(d) <= uvr_yield_curve.maxTime() else None)
        date_df['Zero Rates_UVR'] = date_df['Date'].apply(lambda d: uvr_yield_curve.zeroRate(d, self.day_count, ql.Continuous).rate() if uvr_yield_curve.timeFromReference(d) <= uvr_yield_curve.maxTime() else None)
        date_df['Inflacion Implicita'] = ((1+date_df['Zero Rates'])/(1+date_df['Zero Rates_UVR'])-1)
        date_df['Date'] = date_df['Date'] - ql.Period('1m')

        return date_df


    def create_cpi_index(self):

        df = self.inflation_lag_0
        date_df=self.bond_curve_implied_inflation_mat()    
        df['Total'] = df['cpi_index']
        df.index.name = 'fecha'
        df['fecha'] = pd.to_datetime(df.index)
        df.set_index('fecha', inplace=True)
        df_cpi = pd.DataFrame(df['Total'].dropna())
        df_cpi.rename(columns={'Total': 'indice'}, inplace=True)
        df_cpi.set_index(pd.to_datetime(df_cpi.index.year*10000 +
                        df_cpi.index.month*100 + 15, format='%Y%m%d'), inplace=True)

        total_cpi = df_cpi['indice']

        for d in date_df['Date']:
            d_1 = d-ql.Period('1y')
            f_1 = total_cpi[ql_to_datetime(d_1)]
            f_2 = (1+date_df['Inflacion Implicita'][date_df['Date'] == d].values)
            total_cpi.loc[ql_to_datetime(d)] = f_1*f_2[0]
            print(d)

        total_cpi = pd.DataFrame(total_cpi)
        total_cpi_monthly = total_cpi.pct_change(periods=1)
        total_cpi_yoy = total_cpi.pct_change(periods=12)


        return {'total_cpi': total_cpi, 'total_cpi_yoy': total_cpi_yoy, 'total_cpi_monthly': total_cpi_monthly}

# %%
