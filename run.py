# run.py
import uvicorn
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.config import PORT, HOST

if __name__ == "__main__":
    print(f"===========================================================")
    print(f" 🚀 MINECRAFT SERVER MANAGER STARTING...")
    print(f" 🏠 Dashboard URL: http://{HOST}:{PORT}")
    print(f"===========================================================")

    # "app:create_app" refers to the create_app factory in app/__init__.py
    uvicorn.run(
        "app:create_app",
        host=HOST,
        port=PORT,
        reload=True,
        factory=True
    )
