import math
import concurrent.futures
import numpy as np
import pandas as pd
import snowflake.connector
from snowflake.connector.pandas_tools import write_pandas


class SnowflakeConnector:
    chunk_size = 16000

    def __init__(self, user, password, account,
                 warehouse, database, schema):
        """
        :param user:
        :param password:
        :param account:
        :param warehouse:
        :param database:
        :param schema:
        """

        self.user = user
        self.password = password
        self.account = account
        self.warehouse = warehouse
        self.database = database
        self.schema = schema
        self._connection()

    def _connection(self):
        self.connection = snowflake.connector.connect(
            user=self.user,
            password=self.password,
            account=self.account,
            warehouse=self.warehouse,
            database=self.database,
            schema=self.schema)
        return self.connection

    def execute(self, sql):
        """
        :param sql:
        :return:
        """
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(sql)
                res = cursor.fetchall()
            return res
        except Exception as e:
            raise e

    def pandas_writer(self, df, table_name):
        """
        :param df: data-frame to insert into table
        :param table_name:
        :return: success, nchunks, nrows inserted
        """
        if len(df) > 0:
            status, num_chunks, num_rows, _ = write_pandas(self.connection, df, table_name, chunk_size=self.chunk_size)
            return status, num_chunks, num_rows
        else:
            return 'success', 0, 0

    def split_df(self, df, chunk_size):
        """
        :param df:
        :param chunk_size:
        :return: num_chunks, list_of_df
        """
        list_of_df = list()
        df = df.drop_duplicates()
        num_chunks = math.ceil(len(df) / self.chunk_size)
        for i in range(num_chunks):
            list_of_df.append(df[i * chunk_size:(i + 1) * chunk_size])
        return num_chunks, list_of_df

    def get_columns(self, table_name):
        """
        :param table_name:
        :return: list of columns
        """
        query_col = """SELECT COLUMN_NAME 
                    FROM INFORMATION_SCHEMA.COLUMNS 
                    WHERE TABLE_NAME = '""" + table_name + """'
                    AND TABLE_SCHEMA = '""" + self.schema + """'
                    ORDER BY ORDINAL_POSITION"""

        # print(f'finding columns : {table_name} ')
        res = self.execute(query_col)
        columns = [i[0] for i in res]
        columns = columns[:-1]
        return columns

    @staticmethod
    def add_missing_columns(df, columns):
        """Formats the DF and adds missing columns"""
        print(f'total records in df :{len(df)}')
        # adding missing columns
        df_columns = list(df.columns.values)
        table_columns = columns

        col_not_in_df = set(table_columns) - set(df_columns)
        print(f'missing columns from df : {col_not_in_df}')
        for col in col_not_in_df:
            df[col] = ''
        df = df[table_columns]
        print(f'added missing columns to df')
        print(f'final df col length : {len(df.columns)}')
        return df

    def concurrent_insert(self, frame, table_name, columns):
        # remove nan, null, quotes from df
        frame.fillna(value=np.nan, inplace=True)
        frame.fillna('', inplace=True)
        frame.replace({"'": '`'}, regex=True, inplace=True)
        frame_list = frame.values.tolist()

        template_query = 'INSERT INTO ' + self.schema + '.' + table_name + \
                         ' (' + ','.join(columns) + ') VALUES '

        for row in frame_list:
            # format list of lines from frame_list
            sub_query = str(tuple(row)).replace("\'\'", 'NULL') + ','
            template_query += sub_query

        query = template_query[:-1]
        # print(query)
        result = self.execute(query)
        num_rows = result[0][0]
        return num_rows

    def cursor_writer(self, data, table_name, columns=[]):
        """
        :param data: data-frame
        :param table_name:
        :param columns: optional
        :return: num of records inserted
        """
        data.columns = map(str.upper, data.columns)

        if len(data) == 0:
            return 0, 0

        if not columns:
            columns = self.get_columns(table_name)
        try:
            num_chunks, list_of_df = self.split_df(data[columns], chunk_size=self.chunk_size)
        except KeyError:
            data = self.add_missing_columns(data, columns)
            num_chunks, list_of_df = self.split_df(data[columns], chunk_size=self.chunk_size)

        num_rows = 0
        with concurrent.futures.ThreadPoolExecutor() as executor:
            # Start the load operations and mark each future with its df
            future_to_db = \
                {executor.submit(self.concurrent_insert, frame, table_name, columns): frame for frame in list_of_df}

            for future in concurrent.futures.as_completed(future_to_db):
                frame = future_to_db[future]
                try:
                    res = future.result()
                    num_rows = num_rows + res
                    # print(f'printing data : {res}')
                except Exception as exc:
                    print('%r generated an exception: %s' % (frame, exc))

        return num_chunks, num_rows

    def insert_into_table(self, schema, table_name, data, columns=[]):
        """
        :param schema:
        :param table_name:
        :param data:
        :param columns:
        :return: num of records inserted
        """
        if self.connection.schema != schema:
            self.execute('USE SCHEMA ' + schema)

        if type(data) == type(pd.DataFrame()):
            data_list = data.values.tolist()
        else:
            data_list = data

        if type(data_list) != type(list()):
            raise Exception('data parameter is incompatible. Expected pandas.DataFrame or list')

        if not columns:
            query_col = self.get_columns(table_name)
            print(f'get columns from {table_name}. Query used : {query_col} ')
            res = self.execute(query_col)
            columns = [i[0] for i in res]
            columns = columns[:-1]

        if not columns:
            template_query = 'INSERT INTO ' + schema + '.' + table_name + ' VALUES '
        else:
            template_query = 'INSERT INTO ' + schema + '.' + table_name + ' (' + ','.join(columns) + ') VALUES '
        query = template_query

        if len(data_list) == 0:
            return 0

        for row in data_list:
            sub_query = '(' + ','.join([("'" + str(i).strip().replace("'", "`") + "'") if (
                    (str(i).strip() != '') and (str(i).strip() != 'nan') and
                    (str(i).strip().lower() != 'none')) else 'null' for i in row.values()]) + '),'
            # print(f'subquery {sub_query}')

            query += sub_query

        query = query[:-1] + ';'

        result = self.execute(query)
        result = result[0][0]
        return result

    def upsert_writer(self, source_table, target_table, keys=None, update_cols=None):
        """
        :param source_table: can be temp table from which the data is pulled
        :param target_table:
        :param keys: list of key columns eg:['ID',ID2']. If not passed,
        takes complete column names of target table
        :param update_cols: optional field, list of columns to update. If not passed,
        takes complete column names of target table
        :return: records_inserted, records_updated
        """
        table_columns = self.get_columns(target_table)
        insert_cols = '(' + ','.join([i for i in table_columns]) + ')'
        insert_vals = '(' + ','.join(['src.' + i for i in table_columns]) + ')'

        if not keys:
            on_keys = ' AND '.join(['target.' + i + ' = src.' + i for i in table_columns])
        else:
            on_keys = ' AND '.join(['target.' + i + ' = src.' + i for i in keys])

        table_columns.append('LOAD_TIME')

        if not update_cols:
            # print('update_cols param not passed')
            update_cols = ','.join(['target.' + i + ' = src.' + i for i in table_columns])

        statement = """MERGE INTO {target_table} AS target USING {source_table} AS src ON {on_keys}
        WHEN MATCHED THEN UPDATE SET {update_cols}
        WHEN NOT MATCHED THEN INSERT {insert_cols}
        VALUES {insert_vals}""".format(target_table=target_table,
                                       source_table=source_table,
                                       on_keys=on_keys,
                                       update_cols=update_cols,
                                       insert_cols=insert_cols,
                                       insert_vals=insert_vals)
        # print(statement)
        res = self.execute(statement)
        records_inserted, records_updated = res[0][0], res[0][1]
        return records_inserted, records_updated

    def close(self):
        # close connection
        self.connection.close()


""""testing purpose"""
# from utils.config_parser import CustomConfigParser as cp
#
# if __name__ == "__main__":
#     config = cp.config_parser('../config.ini')
#
#     s_user = config.get('snowflake_user')
#     s_password = config.get('snowflake_password')
#     s_account = config.get('snowflake_account')
#     s_warehouse = config.get('snowflake_warehouse')
#     s_database = config.get('snowflake_database')
#     s_schema = config.get('snowflake_schema')
#     s_survey_table = config.get('survey_table_name')
#
#     conn = SnowflakeConnector(s_user, s_password, s_account, s_warehouse, s_database, s_schema)
#     query_result = conn.execute('desc table ' + s_survey_table)
#     print(query_result)
