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

# SQL Server适配器
class SQLServerAdapter(DatabaseAdapter):
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
        # 这里可以自定义PostgreSQL类型映射规则
        return SQLServerAdapter().map_type(source_type, max_length)  # 继承原有映射
    
    def get_placeholders(self, count):
        return ', '.join(['%s'] * count)

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

# Oracle适配器（可选）
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
        # 实现Oracle类型映射规则
        pass

def get_adapter(db_type):
    adapters = {
        'sqlserver': SQLServerAdapter(),
        'postgres': PostgreSQLAdapter(),
        'mysql': MySQLAdapter(),
        'oracle': OracleAdapter()  # 若需支持需安装cx_Oracle
    }
    return adapters[db_type]

def load_config(config_file='config-v1.0.yaml'):
    with open(config_file, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    return config

def migrate_table(
    source_adapter, target_adapter,
    table_name, text_widget, progress, total_rows
):
    try:
        # 获取源表结构
        source_adapter.cursor.execute(source_adapter.get_columns_query(table_name))
        columns = source_adapter.cursor.fetchall()

        # 创建目标表
        create_sql = f"DROP TABLE IF EXISTS {table_name}; CREATE TABLE {table_name} ("
        for col in columns:
            name, sql_type, max_length = col[:3]  # 根据适配器返回格式调整
            pg_type = target_adapter.map_type(sql_type, max_length)
            create_sql += f"{name} {pg_type}, "
        create_sql = create_sql.rstrip(', ') + ")"
        target_adapter.cursor.execute(create_sql)
        log_info(f"表结构创建成功: {table_name}", text_widget)

        # 数据迁移
        source_adapter.cursor.execute(f"SELECT * FROM {table_name}")
        rows = source_adapter.cursor.fetchall()
        columns_names = [desc[0] for desc in source_adapter.cursor.description]
        placeholders = target_adapter.get_placeholders(len(columns_names))
        insert_sql = f"""
            INSERT INTO {table_name} ({', '.join(columns_names)})
            VALUES ({placeholders})
        """

        for idx, row in enumerate(rows):
            target_adapter.cursor.execute(insert_sql, row)
            step_value = 100 / total_rows
            root.after(0, lambda current_step=step_value: progress.step(current_step))
            root.update_idletasks()
        
        log_info(f"数据迁移完成: {len(rows)} 条记录", text_widget)
        
    except Exception as e:
        log_error(f"迁移失败: {str(e)}", text_widget)
        raise

def migrate_tables(
    source_adapter, target_adapter,
    tables, text_widget, progress
):
    total_tables = len(tables)
    for idx, table in enumerate(tables):
        if not is_running:
            raise Exception("迁移被用户取消")
        log_info(f"正在迁移表 {table}...", text_widget)
        
        # 获取表的总行数
        source_adapter.cursor.execute(f"SELECT COUNT(*) FROM {table}")
        total_rows = source_adapter.cursor.fetchone()[0]

        migrate_table(
            source_adapter, target_adapter,
            table, text_widget, progress, total_rows
        )
        
        step_value = 100 / total_tables
        root.after(0, lambda current_step=step_value: progress.step(current_step))
        root.update_idletasks()
        time.sleep(0.9)

def run_migration_task(root, text_widget, progress):
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
        migrate_tables(
            source_adapter, target_adapter,
            config['tables'],
            text_widget, progress
        )
        messagebox.showinfo("成功", "迁移任务完成！")
        
    except Exception as e:
        log_error(f"迁移失败: {str(e)}", text_widget)
        messagebox.showerror("错误", f"迁移失败: {str(e)}")
    finally:
        source_adapter.disconnect()
        target_adapter.disconnect()
        
        for widget in root.winfo_children():
            if isinstance(widget, tk.Button) and widget.cget("text") == "开始迁移":
                widget.config(state=tk.NORMAL)
            elif isinstance(widget, tk.Button) and widget.cget("text") == "取消":
                widget.config(state=tk.DISABLED)
        progress["value"] = 0
        is_running = False

def start_migration(root, text_widget, progress):
    global is_running
    is_running = True
    
    for widget in root.winfo_children():
        if isinstance(widget, tk.Button):
            if widget.cget("text") == "开始迁移":
                widget.config(state=tk.DISABLED)
            elif widget.cget("text") == "取消":
                widget.config(state=tk.NORMAL)
    
    threading.Thread(
        target=run_migration_task, 
        args=(root, text_widget, progress),
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
    root.title("数据库迁移工具 v3.0")
    
    log_text = tk.Text(root, height=10, state=tk.DISABLED)
    log_text.pack(pady=10, padx=10, fill=tk.BOTH, expand=True)
    
    progress = ttk.Progressbar(root, mode='determinate', length=300, maximum=100)
    progress.pack(pady=10)
    
    control_frame = tk.Frame(root)
    start_btn = tk.Button(
        control_frame, 
        text="开始迁移", 
        command=lambda: start_migration(root, log_text, progress)
    )
    cancel_btn = tk.Button(
        control_frame, 
        text="取消", 
        state=tk.DISABLED, 
        command=stop_migration
    )
    start_btn.pack(side=tk.LEFT, padx=5)
    cancel_btn.pack(side=tk.LEFT, padx=5)
    control_frame.pack()
    
    root.mainloop()

if __name__ == '__main__':
    create_gui()