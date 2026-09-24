"""Azure Functions entry point.

The site runs the same FastAPI application in three places — a laptop, a
container and Azure Functions — so there is one copy of the routing logic and
no "works locally" class of bug. Functions speaks ASGI, which is what FastAPI
already is, so this file only has to hand the app over.

The route is declared explicitly as "{*route}" with no leading slash. Azure
joins the route prefix from host.json to the template with a separator of its
own, so a leading slash here produces "api//{*route}", which ASP.NET Core
rejects as an invalid template — and the host then refuses to start at all,
reporting only that it is unavailable.

host.json sets an empty route prefix, so requests arrive as
https://<app>.azurewebsites.net/<route> and FastAPI sees exactly the paths it
declares. Azure forwards the whole path unchanged, so a prefix here would have
to be repeated in every FastAPI route.

The database is serverless and pauses when idle, so the first request after a
quiet period can take the better part of a minute. The connection helper
retries while it wakes.
"""
import azure.functions as func

from api.main import app as fastapi_app

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)
_asgi = func.AsgiMiddleware(fastapi_app)


@app.route(route="{*route}", auth_level=func.AuthLevel.ANONYMOUS)
async def http_app_func(req: func.HttpRequest, context: func.Context) -> func.HttpResponse:
    """Hand every request under the route prefix to FastAPI."""
    return await _asgi.handle_async(req, context)
