import sqlite3


class SQLiteClient:

    def __init__(self, filepath: str):
        self.filepath = filepath
        self.conn = None

    def create_connection(self):
        if not self.conn:
            self.conn = sqlite3.connect(self.filepath, check_same_thread=False)

    def close_connection(self):
        if self.conn:
            self.conn = self.conn.close()

    def execute_command(self, command: str, params: tuple):
        if self.conn:
            self.conn.execute(command, params)
            self.conn.commit()
        else:
            raise ConnectionError('You must connect to db before!')

    def execute_select_command(self, command: str, params: tuple):
        if self.conn:
            cur = self.conn.cursor()
            cur.execute(command, params)
            return cur.fetchall()
        else:
            raise ConnectionError('You must connect to db before!')
