import logging

from fastapi import FastAPI

from app.api import routes_credits, routes_jobs, routes_models, routes_webhooks

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

app = FastAPI(title="genpipe", version="0.4.0")

app.include_router(routes_jobs.router)
app.include_router(routes_credits.router)
app.include_router(routes_models.router)
app.include_router(routes_webhooks.router)


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}
