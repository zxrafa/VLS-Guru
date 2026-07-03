import os
import sys
sys.path.insert(0, "C:/Jogos/VLS Guru New")

from dotenv import load_dotenv
load_dotenv()

print("ENV SUPABASE_URL:", os.getenv("SUPABASE_URL"))
print("ENV SUPABASE_KEY:", os.getenv("SUPABASE_KEY"))

import database
print("database.use_supabase:", database.use_supabase)
print("database.SUPABASE_URL:", database.SUPABASE_URL)
print("database.SUPABASE_KEY:", database.SUPABASE_KEY)
