from sqlalchemy import text
from .database import engine


def add_is_admin_column():
   
    with engine.begin() as connection:
        try:
            # Check if column exists
            check_query = text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='users' AND column_name='is_admin'
            """)
            result = connection.execute(check_query)
            
            if result.fetchone() is None:
                # Column doesn't exist, add it
                alter_query = text("""
                    ALTER TABLE users 
                    ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT FALSE
                """)
                connection.execute(alter_query)
                print("✓ Column 'is_admin' added to users table successfully!")
            else:
                print("✓ Column 'is_admin' already exists in users table")
        except Exception as e:
            print(f"Error adding is_admin column: {e}")
            raise

