import pyodbc
import psycopg2
import mysql.connector
import cx_Oracle  # 若需Oracle支持需安装
import logging
import tkinter as tk
from tkinter import messagebox, ttk
import threading
import yaml
import time

# 全局状态标志
is_running = False

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='sync_table.log',
    filemode='a'
)

def log_info(message, text_widget=None, color="green"):
    logging.info(message)
    print(message)
    if text_widget:
        append_to_log(text_widget, message, color)

def log_error(message, text_widget=None):
    logging.error(message)
    print(f"❌ {message}")
    if text_widget:
        append_to_log(text_widget, message, "red")

# 适配器基类
class DatabaseAdapter:
    def __init__(self):
        self.conn = None
        self.cursor = None
    
    def connect(self, config):
        raise NotImplementedError
    
    def disconnect(self):
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()
    
    def get_columns_query(self, table_name):
        raise NotImplementedError
    
    def map_type(self, source_type, max_length):
        raise NotImplementedError
    
    def get_placeholders(self, count):
        raise NotImplementedError
    
    def get_all_tables(self):
        raise NotImplementedError

# SQL Server适配器（已修复database属性问题）
class SQLServerAdapter(DatabaseAdapter):
    def __init__(self):
        super().__init__()
        self.database = None  # 新增数据库名称存储
    
    def connect(self, config):
        conn_str = (
            f"DRIVER={{ODBC Driver 17 for SQL Server}};"
            f"SERVER={config['server']};"
            f"DATABASE={config['database']};"
            f"UID={config['user']};"
            f"PWD={config['password']}"
        )
        self.conn = pyodbc.connect(conn_str)
        self.cursor = self.conn.cursor()
        self.database = config['database']  # 存储数据库名称
    
    def get_columns_query(self, table_name):
        return f"""
            SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = '{table_name}'
        """
    
    def map_type(self, source_type, max_length):
        type_map = {
            'int': 'INT',
            'nvarchar': f'VARCHAR({max_length})' if max_length else 'TEXT',
            'datetime': 'TIMESTAMP',
            'datetime2': 'TIMESTAMP',
            'float': 'DOUBLE PRECISION',
            'bit': 'BOOLEAN',
            'uniqueidentifier': 'UUID',
            'decimal': 'NUMERIC',
            'image': 'BYTEA',
            'xml': 'XML',
            'money': 'MONEY'
        }
        return type_map.get(source_type.lower(), 'TEXT')
    
    def get_placeholders(self, count):
        return ', '.join(['%s'] * count)
    
    def get_all_tables(self):
        self.cursor.execute("""
            SELECT TABLE_NAME 
            FROM INFORMATION_SCHEMA.TABLES 
            WHERE 
                TABLE_TYPE = 'BASE TABLE' AND 
                TABLE_NAME NOT LIKE 'sys%' AND 
                TABLE_CATALOG = ?
        """, (self.database,))  # 使用存储的数据库名称
        return [row[0].lower() for row in self.cursor.fetchall()]

# PostgreSQL适配器
class PostgreSQLAdapter(DatabaseAdapter):
    def connect(self, config):
        self.conn = psycopg2.connect(**config)
        self.conn.autocommit = True
        self.cursor = self.conn.cursor()
    
    def get_columns_query(self, table_name):
        return f"""
            SELECT column_name, data_type, character_maximum_length
            FROM information_schema.columns
            WHERE table_name = '{table_name}'
        """
    
    def map_type(self, source_type, max_length):
        return SQLServerAdapter().map_type(source_type, max_length)
    
    def get_placeholders(self, count):
        return ', '.join(['%s'] * count)
    
    def get_all_tables(self):
        self.cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE 
                table_schema = 'public' AND 
                table_type = 'BASE TABLE'
        """)
        return [row[0].lower() for row in self.cursor.fetchall()]

# MySQL适配器
class MySQLAdapter(DatabaseAdapter):
    def connect(self, config):
        self.conn = mysql.connector.connect(**config)
        self.cursor = self.conn.cursor(buffered=True)
    
    def get_columns_query(self, table_name):
        return f"SHOW FULL COLUMNS FROM {table_name}"
    
    def map_type(self, source_type, max_length):
        mappings = {
            'int': 'INT',
            'nvarchar': f'VARCHAR({max_length})' if max_length else 'TEXT',
            'datetime': 'DATETIME',
            'bit': 'TINYINT(1)',
            'money': 'DECIMAL(10,2)',
            'text': 'TEXT',
            'blob': 'LONGBLOB'
        }
        return mappings.get(source_type.lower(), 'TEXT')
    
    def get_placeholders(self, count):
        return ', '.join(['%s'] * count)
    
    def get_all_tables(self):
        self.cursor.execute("SHOW TABLES")
        return [row[0].lower() for row in self.cursor.fetchall()]

# Oracle适配器
class OracleAdapter(DatabaseAdapter):
    def connect(self, config):
        self.conn = cx_Oracle.connect(
            f"{config['user']}/{config['password']}@{config['host']}/{config['service_name']}"
        )
        self.cursor = self.conn.cursor()
    
    def get_columns_query(self, table_name):
        return f"""
            SELECT COLUMN_NAME, DATA_TYPE, DATA_LENGTH
            FROM ALL_TAB_COLUMNS
            WHERE TABLE_NAME = '{table_name.upper()}'
        """
    
    def map_type(self, source_type, max_length):
        return {
            'NUMBER': 'NUMBER',
            'VARCHAR2': f'VARCHAR2({max_length})',
            'DATE': 'DATE'
        }.get(source_type, 'VARCHAR2(255)')
    
    def get_placeholders(self, count):
        return ', '.join([':{}'.format(i+1) for i in range(count)])
    
    def get_all_tables(self):
        self.cursor.execute(f"""
            SELECT TABLE_NAME 
            FROM ALL_TABLES 
            WHERE 
                OWNER = '{self.conn.username.upper()}' AND 
                TABLE_TYPE = 'TABLE'
        """)
        return [row[0].lower() for row in self.cursor.fetchall()]

def get_adapter(db_type):
    adapters = {
        'sqlserver': SQLServerAdapter(),
        'postgres': PostgreSQLAdapter(),
        'mysql': MySQLAdapter(),
        'oracle': OracleAdapter()
    }
    return adapters[db_type]

def load_config(config_file='config-v1.0.yaml'):
    with open(config_file, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def migrate_table(source_adapter, target_adapter, table_name, text_widget, progress, total_rows):
    try:
        # 获取表结构
        source_adapter.cursor.execute(source_adapter.get_columns_query(table_name))
        columns = source_adapter.cursor.fetchall()

        # 创建目标表
        create_sql = f"DROP TABLE IF EXISTS {table_name}; CREATE TABLE {table_name} ("
        for col in columns:
            name, sql_type, max_length = col[:3]
            pg_type = target_adapter.map_type(sql_type, max_length)
            create_sql += f"{name} {pg_type}, "
        create_sql = create_sql.rstrip(', ') + ")"
        log_info(f"执行建表SQL: {create_sql}", text_widget)
        target_adapter.cursor.execute(create_sql)
        
        # 验证表创建
        target_adapter.cursor.execute(f"SELECT * FROM {table_name} WHERE 1=0")
        
        # 数据迁移
        source_adapter.cursor.execute(f"SELECT * FROM {table_name}")
        rows = source_adapter.cursor.fetchall()
        columns_names = [desc[0] for desc in source_adapter.cursor.description]
        placeholders = target_adapter.get_placeholders(len(columns_names))
        insert_sql = f"INSERT INTO {table_name} ({', '.join(columns_names)}) VALUES ({placeholders})"
        log_info(f"执行插入SQL: {insert_sql}", text_widget)
        
        # 批量插入
        batch_size = 1000
        for i in range(0, len(rows), batch_size):
            target_adapter.cursor.executemany(insert_sql, rows[i:i+batch_size])
            step_value = (i + batch_size)/total_rows * 100
            root.after(0, progress.step, step_value)
            root.update_idletasks()
        
        log_info(f"数据迁移完成: {len(rows)} 条记录", text_widget)
        
    except Exception as e:
        log_error(f"迁移失败: {table_name} {str(e)}", text_widget)
        raise

def migrate_tables(source_adapter, target_adapter, tables, text_widget, progress):
    total_tables = len(tables)
    for idx, table in enumerate(tables):
        if not is_running:
            raise Exception("迁移被用户取消")
        
        # 表存在性验证
        try:
            source_adapter.cursor.execute(f"SELECT 1 FROM {table} WHERE 1=0")
            source_adapter.cursor.fetchone()
        except Exception as e:
            log_error(f"源表不存在: {table}", text_widget)
            continue

        log_info(f"正在迁移表 {table}...", text_widget)
        
        # 获取行数
        source_adapter.cursor.execute(f"SELECT COUNT(*) FROM {table}")
        total_rows = source_adapter.cursor.fetchone()[0]

        try:
            migrate_table(source_adapter, target_adapter, table, text_widget, progress, total_rows)
        except Exception as e:
            log_error(f"表迁移失败: {table} {str(e)}", text_widget)
            continue
        
        step_value = 100 / total_tables
        root.after(0, progress.step, step_value)
        root.update_idletasks()

def run_migration_task(root, text_widget, progress, migrate_all):
    global is_running
    config = load_config()
    source_type = config['source']['type']
    target_type = config['target']['type']
    
    source_adapter = get_adapter(source_type)
    target_adapter = get_adapter(target_type)
    print(f"源数据库类型: {source_type}, 目标数据库类型: {target_type}")

    try:
        log_info("正在连接源数据库...", text_widget)
        source_adapter.connect(config['source']['config'])
        log_info("正在连接目标数据库...", text_widget)
        target_adapter.connect(config['target']['config'])
        
        tables = source_adapter.get_all_tables() if migrate_all else [t.lower() for t in config['tables']]
        log_info(f"本次迁移表列表: {tables}", text_widget)
        
        migrate_tables(source_adapter, target_adapter, tables, text_widget, progress)
        messagebox.showinfo("成功", "迁移任务完成！")
        
    except Exception as e:
        log_error(f"迁移失败: {str(e)}", text_widget)
        messagebox.showerror("错误", f"迁移失败: {str(e)}")
    finally:
        source_adapter.disconnect()
        target_adapter.disconnect()
        for widget in root.winfo_children():
            if isinstance(widget, tk.Button):
                widget.config(state=tk.NORMAL if widget.cget("text") == "开始迁移" else tk.DISABLED)
        progress["value"] = 0
        is_running = False

def start_migration(root, text_widget, progress):
    global is_running
    is_running = True
    for widget in root.winfo_children():
        if isinstance(widget, tk.Button):
            widget.config(state=tk.DISABLED if widget.cget("text") == "开始迁移" else tk.NORMAL)
    threading.Thread(
        target=run_migration_task, 
        args=(root, text_widget, progress, root.migrate_all_var.get()),
        daemon=True
    ).start()

def stop_migration():
    global is_running
    is_running = False

def append_to_log(text_widget, message, color):
    text_widget.config(state=tk.NORMAL)
    text_widget.insert(tk.END, f"{message}\n", "color")
    text_widget.tag_config("color", foreground=color)
    text_widget.see(tk.END)
    text_widget.config(state=tk.DISABLED)

def create_gui():
    global root
    root = tk.Tk()
    root.title("数据库迁移工具 v3.3")
    
    log_text = tk.Text(root, height=10, state=tk.DISABLED)
    log_text.pack(pady=10, padx=10, fill=tk.BOTH, expand=True)
    
    progress = ttk.Progressbar(root, mode='determinate', length=300, maximum=100)
    progress.pack(pady=10)
    
    options_frame = tk.Frame(root)
    root.migrate_all_var = tk.IntVar()
    tk.Checkbutton(options_frame, text="迁移整个库", variable=root.migrate_all_var).pack(pady=5)
    options_frame.pack()
    
    control_frame = tk.Frame(root)
    tk.Button(control_frame, text="开始迁移", command=lambda: start_migration(root, log_text, progress)).pack(side=tk.LEFT, padx=5)
    tk.Button(control_frame, text="取消", state=tk.DISABLED, command=stop_migration).pack(side=tk.LEFT, padx=5)
    control_frame.pack()
    
    root.mainloop()

if __name__ == '__main__':
    create_gui()