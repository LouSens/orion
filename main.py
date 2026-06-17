"""Orion Reimburse — thin entry-point shim.

Run with:
  uvicorn backend.main:app --reload          # development
  python main.py                             # or directly
"""
from backend.main import app  # noqa: F401 — re-export for uvicorn

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="localhost", port=8000, reload=True)
