import sqlite3

conn = sqlite3.connect("fashion.db")
c = conn.cursor()
c.execute("""
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  created_at TEXT
);
""")
conn.commit()
conn.close()
print("DB ready.")
