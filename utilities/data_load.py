from src.utilities import SnowflakeConnector


class DataLoad:
    truncate_sql = """DELETE FROM {db}.{schema}.{table}"""

    def __init__(self, config):
        """
        :param config: must contain connection info related to snowflake
        """

        self.user = config.get('snowflake_user')
        self.password = config.get('snowflake_password')
        self.account = config.get('snowflake_account')
        self.warehouse = config.get('snowflake_warehouse')
        self.database = config.get('snowflake_database')
        self.schema = config.get('snowflake_schema')
        # connects to snowflake
        self.cnx = SnowflakeConnector(self.user, self.password, self.account,
                                      self.warehouse, self.database, self.schema)

    def incremental_load(self, df, src_table, target_table, on_keys=None):
        """
        - performs insert/update operation on src and target table
        - truncates src table
        :param df:
        :param src_table:
        :param target_table:
        :param on_keys:
        :return:
        """
        truncate_sql = self.truncate_sql.format(db=self.database,
                                                schema=self.schema,
                                                table=src_table)
        self.cnx.execute(truncate_sql)
        # print(f'copying data to intermediate table : {src_table}')
        num_chunks, num_rows = self.cnx.cursor_writer(df, src_table)
        # print(f'num_chunks:{num_chunks} records inserted: {num_rows} : {src_table}')

        records_inserted, records_updated = self.cnx.upsert_writer(src_table, target_table, on_keys)
        print(f'rows inserted : {records_inserted}, rows updated: {records_updated} : {target_table} ')
        # self.cnx.execute(truncate_sql)
        # print(f'truncated intermediate table : {src_table}')
        return

    def historical_load(self, df, table_name, is_truncate='False'):
        """
        truncate and loads historical data to the table
        :param df: df which should be loaded into the table
        :param table_name:
        :param is_truncate: if true then - truncate the table and load the data, else just load the data
        :return:
        """
        if is_truncate == 'True':
            truncate_sql = self.truncate_sql.format(db=self.database,
                                                    schema=self.schema,
                                                    table=table_name)
            self.cnx.execute(truncate_sql)

        num_chunks, num_rows = self.cnx.cursor_writer(df, table_name)
        print(f'num_chunks:{num_chunks} records inserted: {num_rows} :{table_name}')
        return

