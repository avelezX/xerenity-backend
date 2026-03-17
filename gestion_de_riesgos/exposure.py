"""
Cálculo de exposición en USD por commodity.
Basado en el instructivo de Exposición del Blotter VB.

Commodities:
  - AZUCAR (Sugar #11) - ICE SB - Centavos USD/Libra
  - MAIZ/GLUCOSA (Corn) - CME ZC - Centavos USD/Bushel → Precio implícito glucosa
  - COCOA EN POLVO - ICE CC - USD/Ton con factor 1.22
  - MANTECA DE CACAO - ICE CC - USD/Ton con factor 1.95
  - LICOR DE CACAO - ICE CC - USD/Ton con factor 1.53
  - BOLSA ROLLO + ENVOLTURA - Precio fijo / TRM
"""


class CommodityExposure:
    """Clase base para cálculo de exposición."""

    def __init__(self, nombre, proyeccion_mensual):
        self.nombre = nombre
        self.proyeccion_mensual = proyeccion_mensual  # list 12 meses
        self.ton_total = sum(proyeccion_mensual)

    def calcular_exposicion(self):
        raise NotImplementedError

    def precio_por_ton(self):
        if self.ton_total == 0:
            return 0
        return self.calcular_exposicion() / self.ton_total

    def to_dict(self):
        exposicion = self.calcular_exposicion()
        return {
            'nombre': self.nombre,
            'proyeccion_mensual': self.proyeccion_mensual,
            'ton_total': round(self.ton_total, 2),
            'exposicion_usd': round(exposicion, 2),
            'precio_por_ton': round(self.precio_por_ton(), 2),
        }


class AzucarExposure(CommodityExposure):
    """
    Sección 3: AZUCAR - Cálculo Contratos Futuros (ICE Sugar #11)
    Unidad: Centavos USD / Libra
    """
    LIBRAS_CONTRATO = 112_000
    LBS_PER_TON = 2204.62

    def __init__(self, proyeccion_mensual, precio_cent_lb, factor_crudo_refinado=1.05):
        super().__init__('AZUCAR', proyeccion_mensual)
        self.precio_cent_lb = precio_cent_lb
        self.factor_crudo_refinado = factor_crudo_refinado

    def calcular_exposicion(self):
        ton_contrato = self.LIBRAS_CONTRATO / self.LBS_PER_TON
        ton_reales = self.ton_total * self.factor_crudo_refinado
        num_contratos = ton_reales / ton_contrato
        precio_x_libra = self.precio_cent_lb / 100
        precio_x_contrato = precio_x_libra * self.LIBRAS_CONTRATO
        return precio_x_contrato * num_contratos

    def to_dict(self):
        base = super().to_dict()
        ton_contrato = self.LIBRAS_CONTRATO / self.LBS_PER_TON
        ton_reales = self.ton_total * self.factor_crudo_refinado
        num_contratos = ton_reales / ton_contrato
        precio_x_libra = self.precio_cent_lb / 100
        precio_x_contrato = precio_x_libra * self.LIBRAS_CONTRATO

        base.update({
            'exchange': 'ICE - SB',
            'unidad_cotizacion': 'Centavos USD / Libra',
            'precio_futuro': self.precio_cent_lb,
            'ton_contrato': round(ton_contrato, 2),
            'factor_crudo_refinado': self.factor_crudo_refinado,
            'ton_reales': round(ton_reales, 2),
            'num_contratos': round(num_contratos, 2),
            'libras_x_contrato': self.LIBRAS_CONTRATO,
            'precio_x_libra': round(precio_x_libra, 4),
            'precio_x_contrato': round(precio_x_contrato, 2),
        })
        return base


class MaizGlucosaExposure(CommodityExposure):
    """
    Sección 4: MAIZ / GLUCOSA - Precio Implícito (CME Corn)
    Unidad: Centavos USD / Bushel
    """
    CONV_BU_TON = 0.3936825
    CREDITO_PCT = 0.26

    def __init__(self, proyeccion_mensual, precio_cent_bu, base_cent_bu,
                 flete_usd_ton, processing_fee_usd, proc_fee_cop_kg,
                 trm, factor_maiz_glucosa=1.495):
        super().__init__('MAIZ', proyeccion_mensual)
        self.precio_cent_bu = precio_cent_bu
        self.base_cent_bu = base_cent_bu
        self.flete_usd_ton = flete_usd_ton
        self.processing_fee_usd = processing_fee_usd
        self.proc_fee_cop_kg = proc_fee_cop_kg
        self.trm = trm
        self.factor_maiz_glucosa = factor_maiz_glucosa

    def calcular_exposicion(self):
        precio_cent_ton = (self.precio_cent_bu + self.base_cent_bu) * self.CONV_BU_TON
        precio_usd_ton = precio_cent_ton / 100
        precio_net = self.flete_usd_ton + precio_usd_ton
        credito_subproductos = precio_net * self.CREDITO_PCT
        precio_neto = precio_usd_ton + credito_subproductos
        glucosa_materia = self.factor_maiz_glucosa * precio_neto
        proc_fee_usd_ton = (self.proc_fee_cop_kg / self.trm) * 1000
        precio_glucosa = proc_fee_usd_ton + self.processing_fee_usd + glucosa_materia
        return self.ton_total * precio_glucosa

    def to_dict(self):
        base = super().to_dict()
        precio_cent_ton = (self.precio_cent_bu + self.base_cent_bu) * self.CONV_BU_TON
        precio_usd_ton = precio_cent_ton / 100
        precio_net = self.flete_usd_ton + precio_usd_ton
        credito_subproductos = precio_net * self.CREDITO_PCT
        precio_neto = precio_usd_ton + credito_subproductos
        glucosa_materia = self.factor_maiz_glucosa * precio_neto
        proc_fee_usd_ton = (self.proc_fee_cop_kg / self.trm) * 1000
        precio_glucosa = proc_fee_usd_ton + self.processing_fee_usd + glucosa_materia

        base.update({
            'exchange': 'CME - ZC',
            'unidad_cotizacion': 'Centavos USD / Bushel',
            'precio_futuro': self.precio_cent_bu,
            'base_cent_bu': self.base_cent_bu,
            'conv_bu_ton': self.CONV_BU_TON,
            'precio_cent_ton': round(precio_cent_ton, 2),
            'precio_usd_ton': round(precio_usd_ton, 4),
            'flete_usd_ton': self.flete_usd_ton,
            'precio_net': round(precio_net, 2),
            'credito_subproductos': round(credito_subproductos, 2),
            'precio_neto': round(precio_neto, 2),
            'factor_maiz_glucosa': self.factor_maiz_glucosa,
            'glucosa_materia': round(glucosa_materia, 2),
            'processing_fee_usd': self.processing_fee_usd,
            'proc_fee_cop_kg': self.proc_fee_cop_kg,
            'trm': self.trm,
            'proc_fee_usd_ton': round(proc_fee_usd_ton, 2),
            'precio_glucosa': round(precio_glucosa, 2),
        })
        return base


class CocoaDerivadoExposure(CommodityExposure):
    """
    Sección 5: COCOA - Polvo, Manteca y Licor (ICE CC)
    Unidad: USD / Tonelada Métrica
    Cada derivado tiene un factor de conversión diferente.
    """
    TON_CONTRATO = 10

    def __init__(self, nombre, proyeccion_mensual, factor_conversion, precio_futuro_usd_ton):
        super().__init__(nombre, proyeccion_mensual)
        self.factor_conversion = factor_conversion
        self.precio_futuro = precio_futuro_usd_ton

    def calcular_exposicion(self):
        kg_reales = self.ton_total * 1000 * self.factor_conversion
        ton_reales = kg_reales / 1000
        num_contratos = ton_reales / self.TON_CONTRATO
        precio_x_contrato = self.TON_CONTRATO * self.precio_futuro
        return num_contratos * precio_x_contrato

    def to_dict(self):
        base = super().to_dict()
        kg_reales = self.ton_total * 1000 * self.factor_conversion
        ton_reales = kg_reales / 1000
        num_contratos = ton_reales / self.TON_CONTRATO
        precio_x_contrato = self.TON_CONTRATO * self.precio_futuro

        base.update({
            'exchange': 'ICE - CC',
            'unidad_cotizacion': 'USD / Tonelada Métrica',
            'precio_futuro': self.precio_futuro,
            'ton_contrato': self.TON_CONTRATO,
            'factor_conversion': self.factor_conversion,
            'kg_reales': round(kg_reales, 2),
            'ton_reales': round(ton_reales, 2),
            'num_contratos': round(num_contratos, 2),
            'precio_x_contrato': round(precio_x_contrato, 2),
        })
        return base


class EmpaqueExposure:
    """
    Sección 6: BOLSA ROLLO + ENVOLTURA EXTERNA (sin futuro)
    Precio fijo × ton / TRM
    """

    def __init__(self, proyeccion_bolsa, proyeccion_envoltura, precio_total_fijo, trm=3800):
        self.nombre = 'EMPAQUE'
        self.proyeccion_bolsa = proyeccion_bolsa
        self.proyeccion_envoltura = proyeccion_envoltura
        self.ton_bolsa = sum(proyeccion_bolsa)
        self.ton_envoltura = sum(proyeccion_envoltura)
        self.precio_total_fijo = precio_total_fijo
        self.trm = trm

    def calcular_exposicion(self):
        return self.precio_total_fijo * (self.ton_envoltura + self.ton_bolsa) / self.trm

    def to_dict(self):
        exposicion = self.calcular_exposicion()
        return {
            'nombre': self.nombre,
            'exchange': 'N/A',
            'unidad_cotizacion': 'Precio fijo / TRM',
            'proyeccion_bolsa': self.proyeccion_bolsa,
            'proyeccion_envoltura': self.proyeccion_envoltura,
            'ton_bolsa': round(self.ton_bolsa, 2),
            'ton_envoltura': round(self.ton_envoltura, 2),
            'precio_total_fijo': self.precio_total_fijo,
            'trm': self.trm,
            'exposicion_usd': round(exposicion, 2),
        }


def calcular_exposicion_total(params):
    """
    Calcula la exposición total de la compañía.

    params: dict con todos los inputs necesarios:
      - proyeccion_azucar: list[12]
      - precio_azucar_cent_lb: float
      - factor_crudo_refinado: float (default 1.05)
      - proyeccion_glucosa: list[12]
      - precio_maiz_cent_bu: float
      - base_maiz_cent_bu: float
      - flete_usd_ton: float
      - processing_fee_usd: float
      - proc_fee_cop_kg: float
      - trm: float
      - factor_maiz_glucosa: float (default 1.495)
      - proyeccion_cocoa_polvo: list[12]
      - factor_cocoa_polvo: float (default 1.22)
      - proyeccion_manteca: list[12]
      - factor_manteca: float (default 1.95)
      - proyeccion_licor: list[12]
      - factor_licor: float (default 1.53)
      - precio_cocoa_usd_ton: float
      - proyeccion_bolsa: list[12]
      - proyeccion_envoltura: list[12]
      - precio_empaque_fijo: float
      - ventas_intl_usd: float (optional)
      - ventas_co_usd: float (optional)
      - ventas_pe_usd: float (optional)
    """
    azucar = AzucarExposure(
        params['proyeccion_azucar'],
        params['precio_azucar_cent_lb'],
        params.get('factor_crudo_refinado', 1.05),
    )

    maiz = MaizGlucosaExposure(
        params['proyeccion_glucosa'],
        params['precio_maiz_cent_bu'],
        params['base_maiz_cent_bu'],
        params['flete_usd_ton'],
        params['processing_fee_usd'],
        params['proc_fee_cop_kg'],
        params['trm'],
        params.get('factor_maiz_glucosa', 1.495),
    )

    polvo = CocoaDerivadoExposure(
        'COCOA_POLVO',
        params['proyeccion_cocoa_polvo'],
        params.get('factor_cocoa_polvo', 1.22),
        params['precio_cocoa_usd_ton'],
    )

    manteca = CocoaDerivadoExposure(
        'MANTECA_CACAO',
        params['proyeccion_manteca'],
        params.get('factor_manteca', 1.95),
        params['precio_cocoa_usd_ton'],
    )

    licor = CocoaDerivadoExposure(
        'LICOR_CACAO',
        params['proyeccion_licor'],
        params.get('factor_licor', 1.53),
        params['precio_cocoa_usd_ton'],
    )

    empaque = EmpaqueExposure(
        params['proyeccion_bolsa'],
        params['proyeccion_envoltura'],
        params['precio_empaque_fijo'],
        params.get('trm', 3800),
    )

    commodities = [azucar, maiz, polvo, manteca, licor, empaque]
    total_commodities = sum(c.calcular_exposicion() for c in commodities)

    # Exposición USD: Ventas Internacionales - Exposición del mes (sum commodities)
    ventas_intl = params.get('ventas_intl_usd', 0)
    ventas_co = params.get('ventas_co_usd', 0)
    ventas_pe = params.get('ventas_pe_usd', 0)
    exposicion_ventas = ventas_intl
    exposicion_real_usd = ventas_intl - total_commodities

    return {
        'commodities': [c.to_dict() for c in commodities],
        'total_commodities_usd': round(total_commodities, 2),
        'exposicion_ventas_intl': round(exposicion_ventas, 2),
        'exposicion_real_usd': round(exposicion_real_usd, 2),
        'exposicion_pen': round(ventas_pe, 2),
    }
