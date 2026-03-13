"""
URL configuration for xerenity_functions project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

import json
from django.urls import path
from django.views.decorators.csrf import csrf_exempt
from server.main_server import XerenityError, responseHttpError


def period_payment(request):
    try:
        from server.loan_calculator.loan_calculator import LoanCalculatorServer
        calc = LoanCalculatorServer(json.loads(request.body))
        return calc.period_payment()
    except XerenityError as xerror:
        return responseHttpError(message=xerror.message, code=xerror.code)
    except Exception as e:
        return responseHttpError(message=str(e), code=400)


def cash_flow(request):
    """

    Entry point for cash flow calculation
    :param request:
    :return:
    """

    try:

        if len(request.body) == 0:
            raise Exception('No se encontraron datos para este credito')

        from server.loan_calculator.loan_calculator import LoanCalculatorServer
        calc = LoanCalculatorServer(json.loads(request.body))
        return calc.cash_flow()
    except XerenityError as xerror:
        return responseHttpError(message=xerror.message, code=xerror.code)
    except Exception as e:
        return responseHttpError(message=str(e), code=400)


def ibr_rates(request):
    """

    Entry point for ibr rates calculation
    :param request:
    :return:
    """

    try:
        from server.loan_calculator.loan_calculator import LoanCalculatorServer
        calc = LoanCalculatorServer(json.loads(request.body))
        return calc.cash_flow_ibr()
    except XerenityError as xerror:
        return responseHttpError(message=xerror.message, code=xerror.code)
    except Exception as e:
        return responseHttpError(message=str(e), code=400)


def fwd_rates(request):
    try:
        from server.ibr_quotes_servefr.ibr_quotes_calculator import IbQuotesServer
        calc = IbQuotesServer(json.loads(request.body))
        return calc.calculate()
    except XerenityError as xerror:
        return responseHttpError(message=xerror.message, code=xerror.code)
    except Exception as e:
        return responseHttpError(message=str(e), code=400)


def uvr_prints(request):
    try:
        from server.uvr_prints_server.uvr_prints_calculator import UVRPrintsServer
        calc = UVRPrintsServer(json.loads(request.body))
        return calc.calculate()
    except XerenityError as xerror:
        return responseHttpError(message=xerror.message, code=xerror.code)
    except Exception as e:
        return responseHttpError(message=str(e), code=400)


def cpi_implicit(request):
    try:
        from server.uvr_prints_server.uvr_prints_calculator import UVRPrintsServer
        calc = UVRPrintsServer(json.loads(request.body))
        return calc.calculate_cpi_implicit()
    except XerenityError as xerror:
        return responseHttpError(message=xerror.message, code=xerror.code)
    except Exception as e:
        return responseHttpError(message=str(e), code=400)


def all_loans(request):
    try:
        from server.all_loans_server.all_loans_server import AllLoanServer
        calc = AllLoanServer(json.loads(request.body))
        return calc.calculate()
    except XerenityError as xerror:
        return responseHttpError(message=xerror.message, code=xerror.code)
    except Exception as e:
        return responseHttpError(message=str(e), code=400)


def risk_management(request):
    try:
        from server.risk_management_server.risk_management_server import RiskManagementServer
        calc = RiskManagementServer(json.loads(request.body))
        return calc.calculate()
    except XerenityError as xerror:
        return responseHttpError(message=xerror.message, code=xerror.code)
    except Exception as e:
        return responseHttpError(message=str(e), code=400)


def risk_rolling_var(request):
    try:
        from server.risk_management_server.risk_management_server import RiskManagementServer
        calc = RiskManagementServer(json.loads(request.body))
        return calc.rolling_var()
    except XerenityError as xerror:
        return responseHttpError(message=xerror.message, code=xerror.code)
    except Exception as e:
        return responseHttpError(message=str(e), code=400)


def risk_benchmark_factors(request):
    try:
        from server.risk_management_server.risk_management_server import RiskManagementServer
        calc = RiskManagementServer(json.loads(request.body))
        return calc.benchmark_factors()
    except XerenityError as xerror:
        return responseHttpError(message=xerror.message, code=xerror.code)
    except Exception as e:
        return responseHttpError(message=str(e), code=400)


urlpatterns = [
    path("period_payment", csrf_exempt(period_payment), name="period_payment"),
    path("cash_flow", csrf_exempt(cash_flow), name="cash_flow"),
    path("ibr_rates", csrf_exempt(ibr_rates), name="ibr_rates"),
    path("fwd_rates", csrf_exempt(fwd_rates), name="fwd_rates"),
    path("uvr_prints", csrf_exempt(uvr_prints), name="uvr_prints"),
    path("cpi_implicit", csrf_exempt(cpi_implicit), name="cpi_implicit"),
    path("all_loans", csrf_exempt(all_loans), name="all_loans"),
    path("risk_management", csrf_exempt(risk_management), name="risk_management"),
    path("risk_rolling_var", csrf_exempt(risk_rolling_var), name="risk_rolling_var"),
    path("risk_benchmark_factors", csrf_exempt(risk_benchmark_factors), name="risk_benchmark_factors"),
]
