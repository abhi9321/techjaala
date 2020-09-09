import concurrent.futures
import math
from datetime import datetime

import numpy as np
import psycopg2
import yaml
import linecache
import sys


def print_exception():
    exc_type, exc_obj, tb = sys.exc_info()
    f = tb.tb_frame
    line_no = tb.tb_lineno
    filename = f.f_code.co_filename
    linecache.checkcache(filename)
    line = linecache.getline(filename, line_no, f.f_globals)
    print('EXCEPTION IN ({}, LINE {} "{}"): {}'.format(filename, line_no, line.strip(), exc_obj))


class PostgresConnector:
    chunk_size = 16000

    def __init__(self, user, password, host, database, schema):
        """
        :param user:
        :param password:
        :param database:
        :param schema:
        """

        self.user = user
        self.password = password
        self.host = host
        self.database = database
        self.schema = schema
        self.connection = self._connection()

    def _connection(self):
        try:
            connection = psycopg2.connect(user=self.user,
                                          password=self.password,
                                          host=self.host,
                                          database=self.database,
                                          options=f'-c search_path={self.schema}', )
            return connection
        except (Exception, psycopg2.Error) as error:
            print(f"Error while connecting to PostgreSQL: {error}")
            raise error

    def execute(self, sql):
        """ runs all selector queries"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(sql)
                self.connection.commit()
                try:
                    count = cursor.rowcount
                    res = cursor.fetchall()
                except psycopg2.ProgrammingError:
                    res = count
            return res
        except psycopg2.Error as e:
            # print(sql)
            raise e

    def split_df(self, df, chunk_size):
        """
        :param df:
        :param chunk_size:
        :return: num_chunks, list_of_df
        """
        list_of_df = list()
        # df = df.drop_duplicates()
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

        # print(f' finding columns : {table_name} ')
        res = self.execute(query_col)
        columns = [i[0] for i in res]
        columns = columns[:-1]
        return columns

    def get_primary_keys(self, table_name):
        """
        :param table_name:
        :return: list of primary key columns for a given table
        """
        query_sql = """SELECT c.column_name
                    FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE as c 
                    left join INFORMATION_SCHEMA.TABLE_CONSTRAINTS as t
                    on t.constraint_name = c.constraint_name
                    WHERE t.TABLE_NAME = '""" + table_name + """'
                    AND t.TABLE_SCHEMA = '""" + self.schema + """'
                    AND c.constraint_schema = '""" + self.schema + """'
                    AND t.constraint_type = 'PRIMARY KEY'"""
        # print(query_sql)
        # print(f' fetching primary keys : {table_name} ')
        res = self.execute(query_sql)
        keys = [i[0] for i in res]
        return keys

    @staticmethod
    def add_missing_columns(df, columns):
        """Formats the DF and adds missing columns"""
        df_columns = list(df.columns)
        table_columns = columns
        col_not_in_df = set(table_columns) - set(df_columns)
        # print(f' missing columns from df : {col_not_in_df}')
        for col in col_not_in_df:
            df[col] = ''
        df = df[table_columns]
        # print(f' added missing columns to df')
        # print(f' final df col length : {len(df.columns)}')
        return df

    def insert_frame(self, frame, table_name, columns, on_keys, update_cols):
        try:
            # remove nan, null, quotes from df
            frame.fillna(value=np.nan, inplace=True)
            frame.fillna('', inplace=True)
            frame.replace({"'": '`'}, regex=True, inplace=True)
            frame_list = frame.values.tolist()
            on_keys = ','.join([i for i in on_keys])
            merge_sql = f"""INSERT INTO {self.schema}.{table_name} ({','.join(columns)}) VALUES """

            for row in frame_list:
                # format list of lines from frame_list
                sub_query = str(tuple(row)).replace("\'\'", 'NULL') + ','
                merge_sql += sub_query

            query = f"""{merge_sql[:-1]} ON CONFLICT ({on_keys}) DO UPDATE SET {update_cols} """
            # print(query)
            result = self.execute(query)
            num_rows = result

            return num_rows
        except Exception as e:
            print_exception()

            print(
                f'error occurred while executing query for table : {table_name} '
                f'error: {e}')
            print(query)
            raise e

    def upsert_writer(self, data, table_name, keys=None, update_cols=None, dedup=False):
        """
        :param dedup:
        :param data: data-frame for loading
        :param table_name: target table
        :param keys: list of primary keys on which the df to be compared with
        :param update_cols: list columns which can be updated for matched data set
        :return: num of affected records

        """
        # data.to_csv('test.csv', index=False)
        time_format = "%Y-%m-%dT%H:%M:%SZ"
        load_time = datetime.utcnow().strftime(time_format)
        if len(data) == 0:
            return 0, 0

        columns = self.get_columns(table_name)

        # format on conflict keys
        if not keys:
            keys = self.get_primary_keys(table_name)

        if update_cols:
            update_cols = ','.join([i + ' = excluded.' + i for i in update_cols])
        else:  # add load_time at end
            update_cols = ','.join([i + ' = excluded.' + i for i in columns]) + ", load_time = '" + load_time + "'"
        try:
            data = data[columns]
            if dedup:
                if keys:
                    data = data.drop_duplicates(subset=keys, keep='last')
                else:
                    data = data.drop_duplicates()
            num_chunks, list_of_df = self.split_df(data, chunk_size=self.chunk_size)
        except KeyError:
            data = self.add_missing_columns(data, columns)
            data = data[columns]
            if dedup:
                if keys:
                    data = data.drop_duplicates(subset=keys, keep='last')
                else:
                    data = data.drop_duplicates()

            num_chunks, list_of_df = self.split_df(data, chunk_size=self.chunk_size)
        num_rows = 0
        with concurrent.futures.ThreadPoolExecutor() as executor:
            # Start the load operations and mark each future with its df
            future_to_db = \
                {executor.submit(self.insert_frame, frame, table_name,
                                 columns, keys, update_cols): frame for frame in list_of_df}

            for future in concurrent.futures.as_completed(future_to_db):
                f = future_to_db[future]
                try:
                    res = future.result()
                    num_rows = num_rows + res
                except Exception as exc:
                    print(exc, f.columns)
                    raise exc

        return num_chunks, num_rows

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
        return result

    def insert_writer(self, df, table_name):
        """
        :param df: data-frame for loading
        :param table_name: target table
        :return: num of affected records

        """
        time_format = "%Y-%m-%dT%H:%M:%SZ"
        load_time = datetime.utcnow().strftime(time_format)
        if len(df) == 0:
            return 0, 0

        columns = self.get_columns(table_name)
        try:
            num_chunks, list_of_df = self.split_df(df[columns], chunk_size=self.chunk_size)
        except KeyError:
            data = self.add_missing_columns(df, columns)
            num_chunks, list_of_df = self.split_df(data[columns], chunk_size=self.chunk_size)

        num_rows = 0
        with concurrent.futures.ThreadPoolExecutor() as executor:
            # Start the load operations and mark each future with its df
            future_to_db = \
                {executor.submit(self.concurrent_insert, frame, table_name,
                                 columns): frame for frame in list_of_df}

            for future in concurrent.futures.as_completed(future_to_db):
                f = future_to_db[future]
                try:
                    res = future.result()
                    num_rows = num_rows + res
                except Exception as exc:
                    print(exc, f.columns)
                    raise exc

        return num_chunks, num_rows

    def truncate_table(self, table_name):
        self.execute(f'TRUNCATE TABLE {table_name}')

    def close(self):
        # close connection
        self.connection.close()


""""testing purpose"""
# from utils.config_parser import CustomConfigParser as cp

if __name__ == "__main__":
    with open(r'../sync/config.yaml') as file:
        config = yaml.load(file, Loader=yaml.FullLoader)
    # print(config)
    # exit()
    config = config.get('dev')['database']

    p_user = config.get('user')
    p_password = config.get('password')
    p_host = config.get('host')
    p_database = config.get('database')
    p_schema = config.get('schema')

    # print(p_user, p_password, p_host, p_database, p_schema)

    conn = PostgresConnector(p_user, p_password, p_host, p_database, p_schema)
    # query_result = conn.execute("select to_char(max(updated_at),'yyyy-MM-ddThh:mm:ss.000Z') from orders")
    # from orders")
    query_result = conn.execute('SELECT version();')
    print(query_result)
