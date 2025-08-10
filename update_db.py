import sqlite3

# Connect to the existing database file
conn = sqlite3.connect('users.db')
c = conn.cursor()

# Use ALTER TABLE to add the new 'media' column to the chat_messages table
try:
    c.execute("ALTER TABLE chat_messages ADD COLUMN media TEXT")
    conn.commit()
    print("Successfully added 'media' column to the chat_messages table.")
except sqlite3.OperationalError as e:
    # This handles the case where the column might have already been added
    print(f"Error: {e}")
    print("The 'media' column might already exist. No action needed.")
finally:
    # Always close the connection
    conn.close()

