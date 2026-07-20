"""初始化 SQLite 数据库：建表 + 索引。

对应原项目 scripts/init-database.ts，表结构完全一致。
用法: python scripts/init_database.py
"""

import sqlite3
import sys
from pathlib import Path

# 让脚本可以直接运行（不依赖 pip install -e .）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings

DDL = """
-- 公司表
CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    industry TEXT NOT NULL,
    employee_count INTEGER,
    revenue REAL,
    founded_year INTEGER,
    country TEXT,
    city TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 员工表
CREATE TABLE IF NOT EXISTS people (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    company_id INTEGER,
    job_title TEXT,
    department TEXT,
    salary REAL,
    hire_date DATE,
    birth_date DATE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (company_id) REFERENCES companies(id)
);

-- 客户账户表
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_number TEXT UNIQUE NOT NULL,
    company_id INTEGER,
    account_manager_id INTEGER,
    status TEXT NOT NULL,
    account_type TEXT NOT NULL,
    monthly_value REAL,
    total_revenue REAL,
    contract_start_date DATE,
    contract_end_date DATE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (company_id) REFERENCES companies(id),
    FOREIGN KEY (account_manager_id) REFERENCES people(id)
);

-- 查询性能索引
CREATE INDEX IF NOT EXISTS idx_people_company_id ON people(company_id);
CREATE INDEX IF NOT EXISTS idx_accounts_company_id ON accounts(company_id);
CREATE INDEX IF NOT EXISTS idx_accounts_manager_id ON accounts(account_manager_id);
CREATE INDEX IF NOT EXISTS idx_people_email ON people(email);
CREATE INDEX IF NOT EXISTS idx_accounts_number ON accounts(account_number);
"""


def main() -> None:
    db_file = settings.db_file
    db_file.parent.mkdir(parents=True, exist_ok=True)

    print(f"[init] 数据库路径: {db_file}")
    conn = sqlite3.connect(db_file)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(DDL)
        conn.commit()
        print("[init] 建表完成: companies, people, accounts")
    finally:
        conn.close()
    print("[init] 完成 ✓")


if __name__ == "__main__":
    main()
