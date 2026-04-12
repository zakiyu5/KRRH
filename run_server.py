from waitress import serve
from app import app

print("Starting Waitress server on port 5353...")

if __name__ == "__main__":
    serve(app, host="0.0.0.0", port=5353)