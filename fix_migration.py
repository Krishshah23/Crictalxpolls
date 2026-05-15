import sqlite3
import json

conn = sqlite3.connect('instance/app.db')
cursor = conn.cursor()

try:
    # Add the column
    cursor.execute("ALTER TABLE user_boost ADD COLUMN applied_vote_ids TEXT DEFAULT '[]'")
    print("✓ Column added successfully")
    
    # Backfill existing data
    cursor.execute("SELECT id, applied_vote_id FROM user_boost WHERE applied_vote_id IS NOT NULL")
    boosts = cursor.fetchall()
    
    for boost_id, vote_id in boosts:
        applied_ids = json.dumps([vote_id])
        cursor.execute("UPDATE user_boost SET applied_vote_ids = ? WHERE id = ?", (applied_ids, boost_id))
        print(f"  ✓ Boost {boost_id}: migrated vote_id {vote_id}")
    
    conn.commit()
    print("\n✅ Migration complete!")
    
except Exception as e:
    print(f"❌ Error: {e}")
    conn.rollback()
finally:
    conn.close()
