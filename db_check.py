import sqlite3

conn = sqlite3.connect('gpt_dalle_bot.db')

cursor = conn.cursor()
conn.execute("PRAGMA decoding = 'UTF-8'")
cursor.execute("SELECT * FROM chat_history")
rows = cursor.fetchall()
# cursor.execute('DELETE FROM chat_history')
# cursor.execute("ALTER TABLE chat_history ADD COLUMN state BOOLEAN DEFAULT FALSE")
conn.commit()

for row in rows:
    print(row[3])
    print(row)

conn.close()