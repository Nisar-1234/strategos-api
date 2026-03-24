import os
import subprocess
import sys
import uvicorn

db_url = os.environ.get("DATABASE_URL_SYNC", "")
if db_url:
    os.environ["ALEMBIC_DATABASE_URL"] = db_url
    print(f"Running Alembic migrations...")
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        capture_output=True, text=True
    )
    print(result.stdout)
    if result.returncode != 0:
        print(f"Migration warning: {result.stderr}")
    else:
        print("Migrations complete.")

port = int(os.environ.get("PORT", 8000))
uvicorn.run("app.main:app", host="0.0.0.0", port=port)
