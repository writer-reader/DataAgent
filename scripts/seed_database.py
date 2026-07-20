"""生成示例数据：50 公司 / 500 员工 / 200 账户。

对应原项目 scripts/seed-database.ts。
用 Faker 生成，保持外键一致（people.company_id / accounts.* 均指向真实行）。
可重复执行：先清空再插入（幂等）。

用法: python scripts/seed_database.py
"""

import random
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from faker import Faker

from app.config import settings

# 固定随机种子 => 每次生成的数据一致，方便测试和复现
SEED = 42
fake = Faker()
Faker.seed(SEED)
random.seed(SEED)

# 与语义层 YAML 中 sample_values 保持一致
INDUSTRIES = ["Technology", "Finance", "Healthcare", "Retail", "Manufacturing"]
DEPARTMENTS = ["Engineering", "Sales", "Marketing", "HR", "Finance", "Operations"]
STATUSES = ["Active", "Inactive", "Suspended", "Closed"]
ACCOUNT_TYPES = ["Enterprise", "Business", "Starter"]

JOB_TITLES = {
    "Engineering": ["Software Engineer", "Senior Engineer", "Engineering Manager", "DevOps Engineer"],
    "Sales": ["Account Executive", "Sales Manager", "SDR", "VP of Sales"],
    "Marketing": ["Marketing Manager", "Content Strategist", "Growth Lead"],
    "HR": ["HR Manager", "Recruiter", "People Ops Specialist"],
    "Finance": ["Financial Analyst", "Controller", "CFO"],
    "Operations": ["Operations Manager", "Program Manager", "Chief of Staff"],
}

N_COMPANIES = 50
N_PEOPLE = 500
N_ACCOUNTS = 200


def seed_companies(conn: sqlite3.Connection) -> list[int]:
    """插入公司，返回 id 列表供外键引用。"""
    ids = []
    for _ in range(N_COMPANIES):
        cur = conn.execute(
            """INSERT INTO companies
               (name, industry, employee_count, revenue, founded_year, country, city)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                fake.company(),
                random.choice(INDUSTRIES),
                random.randint(10, 5000),
                round(random.uniform(1e6, 5e8), 2),   # 100 万 ~ 5 亿美元年营收
                random.randint(1980, 2023),
                fake.country(),
                fake.city(),
            ),
        )
        ids.append(cur.lastrowid)
    return ids


def seed_people(conn: sqlite3.Connection, company_ids: list[int]) -> list[int]:
    """插入员工，company_id 指向真实公司。"""
    ids = []
    for _ in range(N_PEOPLE):
        dept = random.choice(DEPARTMENTS)
        hire = fake.date_between(start_date="-10y", end_date="today")
        birth = fake.date_of_birth(minimum_age=22, maximum_age=65)
        cur = conn.execute(
            """INSERT INTO people
               (first_name, last_name, email, company_id, job_title,
                department, salary, hire_date, birth_date)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                fake.first_name(),
                fake.last_name(),
                fake.unique.email(),   # unique 保证不撞 UNIQUE 约束
                random.choice(company_ids),
                random.choice(JOB_TITLES[dept]),
                dept,
                round(random.uniform(40_000, 250_000), 2),
                hire.isoformat(),
                birth.isoformat(),
            ),
        )
        ids.append(cur.lastrowid)
    return ids


def seed_accounts(conn: sqlite3.Connection, company_ids: list[int], people_ids: list[int]) -> None:
    """插入账户，company_id / account_manager_id 均指向真实行。"""
    for i in range(N_ACCOUNTS):
        start = fake.date_between(start_date="-5y", end_date="-6m")
        end = start + timedelta(days=random.choice([365, 730, 1095]))  # 1/2/3 年合同
        monthly = round(random.uniform(500, 50_000), 2)
        # 生命周期收入 ≈ 月费 × 已履约月数（带扰动），保证数据逻辑自洽
        months_active = max(1, (min(end, date.today()) - start).days // 30)
        cur_status = random.choices(STATUSES, weights=[6, 2, 1, 1])[0]  # 多数 Active
        conn.execute(
            """INSERT INTO accounts
               (account_number, company_id, account_manager_id, status, account_type,
                monthly_value, total_revenue, contract_start_date, contract_end_date)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                f"ACC-{i + 1:05d}",
                random.choice(company_ids),
                random.choice(people_ids),
                cur_status,
                random.choice(ACCOUNT_TYPES),
                monthly,
                round(monthly * months_active * random.uniform(0.9, 1.1), 2),
                start.isoformat(),
                end.isoformat(),
            ),
        )


def main() -> None:
    db_file = settings.db_file
    if not db_file.exists():
        print("[seed] 数据库不存在，请先运行: python scripts/init_database.py")
        sys.exit(1)

    conn = sqlite3.connect(db_file)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        # 幂等：清空旧数据（注意顺序，先删有外键的子表）
        conn.execute("DELETE FROM accounts")
        conn.execute("DELETE FROM people")
        conn.execute("DELETE FROM companies")

        company_ids = seed_companies(conn)
        print(f"[seed] companies: {len(company_ids)}")
        people_ids = seed_people(conn, company_ids)
        print(f"[seed] people: {len(people_ids)}")
        seed_accounts(conn, company_ids, people_ids)
        print(f"[seed] accounts: {N_ACCOUNTS}")

        conn.commit()
    finally:
        conn.close()
    print("[seed] 完成 ✓")


if __name__ == "__main__":
    main()
