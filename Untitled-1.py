import pyodbc
import psycopg2
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
    """增强日志函数（支持GUI输出）"""
    logging.info(message)
    print(message)
    if text_widget:
        append_to_log(text_widget, message, color)

def log_error(message, text_widget=None):
    """增强日志函数（支持GUI输出）"""
    logging.error(message)
    print(f"❌ {message}")
    if text_widget:
        append_to_log(text_widget, message, "red")

def connect_to_sql_server(config):
    """连接SQL Server"""
    conn_str = (
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={config['server']};"
        f"DATABASE={config['database']};"
        f"UID={config['user']};"
        f"PWD={config['password']}"
    )
    conn = pyodbc.connect(conn_str)
    return conn, conn.cursor()

def connect_to_postgres(config):
    """连接PostgreSQL（启用autocommit）"""
    conn = psycopg2.connect(**config)
    conn.autocommit = True
    return conn, conn.cursor()

def migrate_table(sql_cursor, pg_cursor, table_name, text_widget,progress, total_rows):
    """迁移单表逻辑（带进度反馈）"""
    try:
        # 获取表结构
        sql_cursor.execute(f"""
            SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = '{table_name}'
        """)
        columns = sql_cursor.fetchall()

        # 创建目标表
        create_sql = f"DROP TABLE IF EXISTS {table_name}; CREATE TABLE {table_name} ("
        for col in columns:
            name, sql_type, max_length = col
            pg_type = map_sqlserver_type_to_pg(sql_type, max_length)
            create_sql += f"{name} {pg_type}, "
        create_sql = create_sql.rstrip(', ') + ")"
        pg_cursor.execute(create_sql)
        log_info(f"表结构创建成功: {table_name}", text_widget)

        # 迁移数据
        sql_cursor.execute(f"SELECT * FROM {table_name}")
        rows = sql_cursor.fetchall()
        columns_names = [desc[0] for desc in sql_cursor.description]
        insert_sql = f"""
            INSERT INTO {table_name} ({', '.join(columns_names)})
            VALUES ({', '.join(['%s']*len(columns_names))})
        """

        for idx, row in enumerate(rows):
            pg_cursor.execute(insert_sql, row)
            # 更新进度条
            step_value = 100 / total_rows
            root.after(0, lambda current_step=step_value: progress.step(current_step))
            root.update_idletasks()  # 确保进度条更新
        # pg_cursor.executemany(insert_sql, rows)
        log_info(f"数据迁移完成: {len(rows)} 条记录", text_widget)
        time.sleep(0.9)  # 添加延迟，放慢进度条滚动速度

    except Exception as e:
        log_error(f"迁移失败: {str(e)}", text_widget)
        raise

def migrate_tables(sql_cursor, pg_cursor, tables, text_widget, progress, total):
    """批量迁移核心逻辑"""
    for idx, table in enumerate(tables):
        if not is_running:
            raise Exception("迁移被用户取消")
        log_info(f"正在迁移表 {table}...", text_widget)

        # 获取表的总行数
        sql_cursor.execute(f"SELECT COUNT(*) FROM {table}")
        total_rows = sql_cursor.fetchone()[0]

        migrate_table(sql_cursor, pg_cursor, table, text_widget, progress, total_rows)
        
        # 更新进度条
        step_value = 100 / len(tables)
        root.after(0, lambda current_step=step_value: progress.step(current_step))
        root.update_idletasks()  # 确保进度条更新
        time.sleep(0.9)  # 添加延迟，放慢进度条滚动速度
def load_config(config_file='config.yaml'):
    """加载配置文件"""
    with open(config_file, 'r') as f:
        return yaml.safe_load(f)

def run_migration_task(root, text_widget, progress):
    """迁移任务包装函数"""
    global is_running
    config = load_config()
    total_tables = len(config['tables'])
    
    try:
        log_info("正在连接 SQL Server...", text_widget)
        sql_conn, sql_cursor = connect_to_sql_server(config['sql_server'])
        log_info("正在连接 PostgreSQL...", text_widget)
        pg_conn, pg_cursor = connect_to_postgres(config['postgres'])
        
        migrate_tables(
            sql_cursor, 
            pg_cursor, 
            config['tables'], 
            text_widget, 
            progress, 
            total_tables
        )
        messagebox.showinfo("成功", "迁移任务完成！")
        
    except Exception as e:
        log_error(f"迁移失败: {str(e)}", text_widget)
        messagebox.showerror("错误", f"迁移失败: {str(e)}")
    finally:
        # 恢复界面状态
    
        for widget in root.winfo_children():
            if isinstance(widget, tk.Button) and widget.cget("text") == "开始迁移":
                widget.config(state=tk.NORMAL)
            elif isinstance(widget, tk.Button) and widget.cget("text") == "取消":
                widget.config(state=tk.DISABLED)
        # 正确设置进度条
        is_running = False
        progress["value"] = 0

def start_migration(root, text_widget, progress):
    """开始迁移按钮处理函数"""
    global is_running
    is_running = True
    
    # 更新界面状态
    for widget in root.winfo_children():
        if isinstance(widget, tk.Button):
            if widget.cget("text") == "开始迁移":
                widget.config(state=tk.DISABLED)
            elif widget.cget("text") == "取消":
                widget.config(state=tk.NORMAL)
    
    # 启动任务线程
    threading.Thread(
        target=run_migration_task, 
        args=(root, text_widget, progress),
        daemon=True
    ).start()

def stop_migration():
    """取消迁移按钮处理函数"""
    global is_running
    is_running = False

def append_to_log(text_widget, message, color):
    """安全更新Text组件（线程安全）"""
    text_widget.config(state=tk.NORMAL)
    text_widget.insert(tk.END, f"{message}\n", "color")
    text_widget.tag_config("color", foreground=color)
    text_widget.see(tk.END)
    text_widget.config(state=tk.DISABLED)

def create_gui():
    """创建增强版GUI界面"""
    global root
    root = tk.Tk()
    root.title("SQL 迁移工具 v2.0")
    
    # 日志显示区
    log_text = tk.Text(root, height=10, state=tk.DISABLED)
    log_text.pack(pady=10, padx=10, fill=tk.BOTH, expand=True)
    
    # 进度条
    progress = ttk.Progressbar(root, mode='determinate', length=300, maximum=100)
    progress.pack(pady=10)
    
    # 控制按钮
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

def map_sqlserver_type_to_pg(sql_type, max_length):
    """完整类型映射（支持更多类型）"""
    type_map = {
        'int': 'INT',
        'nvarchar': f'VARCHAR({max_length})' if max_length else 'TEXT',
        'datetime': 'TIMESTAMP',
        'datetime2': 'TIMESTAMP',  # 处理datetime2
        'float': 'DOUBLE PRECISION',
        'bit': 'BOOLEAN',
        'uniqueidentifier': 'UUID',  # GUID类型
        'decimal': 'NUMERIC',  # 小数类型
        'image': 'BYTEA',  # 二进制类型
        'xml': 'XML',  # XML类型
        'money': 'MONEY',  # 金额类型（PostgreSQL有对应类型）
    }
    return type_map.get(sql_type.lower(), 'TEXT')  # 默认使用TEXT处理未知类型

if __name__ == '__main__':
    create_gui()