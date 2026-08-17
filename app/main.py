from fastapi import FastAPI

from app.api.routes import api_router

app = FastAPI(title="Traction/EOS API")

app.include_router(api_router)


@app.get("/health")
def health():
    return {"status": "ok"}
