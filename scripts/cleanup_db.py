import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))
from src.factory.db import connect, init_db
init_db()
conn = connect()
cur = conn.execute("DELETE FROM reels WHERE status='planned' AND video_path IS NULL")
print("deleted reels:", cur.rowcount)
cur2 = conn.execute("UPDATE scripts SET status='handmade_test' WHERE status='generated'")
print("marked scripts:", cur2.rowcount)
conn.commit()
print("reels remaining:", conn.execute("SELECT COUNT(*) FROM reels").fetchone()[0])
print("scripts:", [dict(r) for r in conn.execute("SELECT status, COUNT(*) c FROM scripts GROUP BY status").fetchall()])
conn.close()