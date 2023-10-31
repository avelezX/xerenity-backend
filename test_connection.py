from src.xerenity.xty import Xerenity
from src.data_source.tes.tes import Tes

xty = Xerenity(
    username='',
    password=''
)

tes = Tes(xty=xty)

all_src = tes.get_sources()

for src in all_src:
    print('-----------------------------------')
    print(xty.read_table(table_name='tes_24'))

xty.log_out()
