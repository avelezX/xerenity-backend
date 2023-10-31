from supabase import Client
from supabase import create_client
from supabase.lib.client_options import ClientOptions


class Xerenity:

    def __init__(self, username, password, auto_refresh: bool = False):
        url: str = "https://tvpehjbqxpiswkqszwwv.supabase.co"
        key: str = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InR2cGVoamJxeHBpc3drcXN6d3d2Iiwicm9sZSI6ImFub24iLCJpYXQiOjE2OTY0NTEzODksImV4cCI6MjAxMjAyNzM4OX0.LZW0i9HU81lCdyjAdqjwwF4hkuSVtsJsSDQh7blzozw"

        opts = ClientOptions(auto_refresh_token=auto_refresh).replace(schema="xerenity")

        self.session: Client = create_client(url, key, options=opts)

        self.session.auth.sign_in_with_password(
            {
                "email": username,
                "password": password
            }
        )

    def log_out(self) -> None:
        """

        Logs out user from current session
        https://supabase.com/docs/reference/python/auth-signout
        :return: None
        """

        self.session.auth.sign_out()

    def read_table(self, table_name):
        """

        Retrieves all data from a given source
        :param table_name: table source to be read from
        :return:
        """
        return self.session.table(table_name=table_name).select('*').execute()

    def read_last_entry(self, table_name, colum_name):
        """

        :param table_name:
        :return:
        """

        return self.session.table(table_name=table_name).select('*').order(colum_name).limit(1)
