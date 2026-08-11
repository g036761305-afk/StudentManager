import os
from sqlalchemy import create_engine, text

# חיבור למסד הנתונים בענן (PostgreSQL)
CLOUD_DB_URL = "postgresql://students_db_5t2m_user:1sE8YDW4pWh3hSWQMcaU8E9sX5vNjINn@dpg-d9kgiclaeets73av85i0-a.ohio-postgres.render.com/students_db_5t2m"
engine = create_engine(CLOUD_DB_URL)

with engine.begin() as conn:
    # עדכון כל התלמידים שהמחזור שלהם מוגדר כרגע כ-כח ל-כט
    result = conn.execute(
        text("UPDATE students SET cycle = :new_cycle WHERE cycle = :old_cycle"),
        {"new_cycle": "כט", "old_cycle": "כח"}
    )
    print(f"העדכון הושלם בהצלחה! שונו {result.rowcount} רשומות.")