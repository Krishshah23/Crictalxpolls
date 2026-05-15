#!/usr/bin/env python3
"""
Migration script to add applied_vote_ids column to user_boost table.
Run this once to update the database schema without losing data.
"""

import sqlite3
import json
from pathlib import Path

db_path = Path(__file__).parent / "instance" / "app.db"

if not db_path.exists():
    print(f"Database not found at {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    # Check if column already exists
    cursor.execute("PRAGMA table_info(user_boost)")
    columns = [col[1] for col in cursor.fetchall()]
    
    if "applied_vote_ids" in columns:
        print("✓ applied_vote_ids column already exists")
    else:
        print("Adding applied_vote_ids column to user_boost table...")
        cursor.execute("""
            ALTER TABLE user_boost
            ADD COLUMN applied_vote_ids JSON DEFAULT '[]'
        """)
        print("✓ Column added successfully")
        
        # Backfill: if a boost has applied_vote_id set, add it to applied_vote_ids
        cursor.execute("""
            SELECT id, applied_vote_id FROM user_boost WHERE applied_vote_id IS NOT NULL
        """)
        boosts = cursor.fetchall()
        
        for boost_id, vote_id in boosts:
            applied_ids = json.dumps([vote_id])
            cursor.execute("""
                UPDATE user_boost SET applied_vote_ids = ? WHERE id = ?
            """, (applied_ids, boost_id))
            print(f"  ✓ Boost {boost_id}: migrated applied_vote_id={vote_id} to applied_vote_ids")
        
        print("✓ All existing boosts migrated to new schema")
    
    conn.commit()
    print("\n✅ Migration complete! Your database is ready.")
    
except Exception as e:
    print(f"❌ Migration failed: {e}")
    conn.rollback()
    exit(1)
finally:
    conn.close()
