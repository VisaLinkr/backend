from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
import os

load_dotenv()

SQLALCHEMY_DATABASE_URL = os.getenv("SQLALCHEMY_DATABASE_URL")

engine = create_engine(SQLALCHEMY_DATABASE_URL)
# # app/database.py (engine 만든 직후 어딘가)
# from sqlalchemy import text
# with engine.connect() as conn:
#     whoami = conn.execute(text("""
#         SELECT
#           current_database()    AS db,
#           current_user          AS usr,
#           current_schema()      AS cur_schema,
#           current_setting('search_path') AS search_path,
#           inet_server_addr()::text AS srv_addr,   -- 소켓이면 NULL일 수 있음
#           inet_server_port()::text AS srv_port
#     """)).mappings().one()
#     print("[DB][WHOAMI]", dict(whoami))

#     where_users = conn.execute(text("""
#         SELECT schemaname, tablename
#         FROM pg_tables
#         WHERE tablename = 'users'
#         ORDER BY schemaname;
#     """)).all()
#     print("[DB][WHERE_USERS_TABLE]", where_users)
    
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        db.rollback()  
        print(f"DB Transaction Rolled Back due to Error: {e}")
        raise
    finally:
        db.close()