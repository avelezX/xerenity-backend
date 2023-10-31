"""
tes
dtcc
series

"""

from src.xerenity.xty import Xerenity


class Source:

    def __init__(self, xty: Xerenity):
        self.xty = xty
        self.name = ''

    def get_sources(self):
        return self.xty.read_table(table_name=self.name).data

    def read_source(self, source_name):
        return self.xty.read_table(table_name=source_name).data
