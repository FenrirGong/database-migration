import pyodbc
import psycopg2

# SQL Server connection
sql_server_conn = pyodbc.connect(
    'DRIVER={ODBC Driver 17 for SQL Server};'
    'SERVER=172.21.73.210,1435;'
    'DATABASE=mip1;'
    'UID=mipadm;'
    'PWD=Mip74821'
)
sql_server_cursor = sql_server_conn.cursor()

# PostgreSQL connection
pg_conn = psycopg2.connect(
    dbname="jiaxin",
    user="postgres",
    password="vlinkplus",
    host="172.168.1.218",
    port="5432"
)
pg_cursor = pg_conn.cursor()

# Table to copy
table_name = 'maschinen'

# Get table schema from SQL Server
sql_server_cursor.execute(f"SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = '{table_name}'")
columns = sql_server_cursor.fetchall()

# Create table in PostgreSQL
create_table_query = f"CREATE TABLE {table_name} ("
for column in columns:
    column_name, data_type = column
    if data_type == 'int':
        pg_data_type = 'INTEGER'
    elif data_type == 'varchar' or data_type == 'nvarchar':
        pg_data_type = 'VARCHAR'
    elif data_type == 'datetime':
        pg_data_type = 'TIMESTAMP'
    else:
        pg_data_type = data_type.upper()
    create_table_query += f"{column_name} {pg_data_type}, "
create_table_query = create_table_query.rstrip(', ') + ');'
pg_cursor.execute(create_table_query)
pg_conn.commit()

# Copy data from SQL Server to PostgreSQL
sql_server_cursor.execute(f"SELECT * FROM {table_name}")
rows = sql_server_cursor.fetchall()
for row in rows:
    insert_query = f"INSERT INTO {table_name} VALUES ({', '.join(['%s'] * len(row))})"
    pg_cursor.execute(insert_query, row)
pg_conn.commit()

# Close connections
sql_server_cursor.close()
sql_server_conn.close()
pg_cursor.close()
pg_conn.close()