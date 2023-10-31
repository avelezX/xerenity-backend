from src.data_source.source import Source
from src.xerenity.xty import Xerenity


class Tes(Source):

    def __init__(self, xty: Xerenity):
        super().__init__(xty)
        self.name = 'tes'
