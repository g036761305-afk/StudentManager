from sqlalchemy import create_engine, text

# חיבור למסד הנתונים בענן (PostgreSQL)
CLOUD_DB_URL = "postgresql://students_db_5t2m_user:1sE8YDW4pWh3hSWQMcaU8E9sX5vNjINn@dpg-d9kgiclaeets73av85i0-a.ohio-postgres.render.com/students_db_5t2m"
engine = create_engine(CLOUD_DB_URL)

with engine.begin() as conn:
    # עדכון כל התלמידים שה-ID שלהם קטן מ-1219 והם במחזור 'כט' בחזרה ל-'כח'
    result = conn.execute(
        text("UPDATE students SET cycle = :new_cycle WHERE id < :max_id AND cycle = :target_cycle"),
        {"new_cycle": "כח", "max_id": 1219, "target_cycle": "כט"}
    )
    print(f"העדכון הושלם בהצלחה! שונו {result.rowcount} תלמידים בחזרה למחזור כח.")