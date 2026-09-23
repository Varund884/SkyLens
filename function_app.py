"""Azure Functions entry point.

The site runs the same FastAPI application in three places — a laptop, a
container and Azure Functions — so there is one copy of the routing logic and
no "works locally" class of bug. Functions speaks ASGI, which is what FastAPI
already is, so this file only has to hand the app over.

Requests arrive as https://<app>.azurewebsites.net/api/<route>; the `api`
prefix is the Functions route prefix set in host.json, and the frontend's
VITE_API_URL is expected to include it.

Cold starts are slow on the consumption plan, and the database is serverless
and pauses when idle, so the first request after a quiet period can take the
better part of a minute. The connection helper retries while it wakes.
"""
import azure.functions as func

from api.main import app as fastapi_app

app = func.AsgiFunctionApp(app=fastapi_app, http_auth_level=func.AuthLevel.ANONYMOUS)
