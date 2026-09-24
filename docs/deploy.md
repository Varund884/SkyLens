# Deploying SkyLens

Two services: the API on Azure Functions, the site on Azure Static Web Apps.
Everything else (the database, OpenAI, AI Search) already exists and is not
touched by a deploy — the batch jobs wrote their results into SQL and the site
only reads.

Do these in order. The site needs the API's URL, so the API goes first.

Set these once for the commands below:

```bash
RG=skylens-rg                 # the resource group everything lives in
LOC=canadacentral             # allowed by the subscription's region policy
FUNC=skylens-api-varun        # must be globally unique
STOR=skylensfuncvarun         # storage for the function app, lowercase, 3-24 chars
```

---

## 1. Resource group

```bash
az group create -n $RG -l $LOC --tags project=skylens
```

If the group already exists, just tag it — the policy in `infra/` expects it:

```bash
az group update -n $RG --tags project=skylens
```

## 2. The API on Azure Functions

```bash
az storage account create -n $STOR -g $RG -l $LOC --sku Standard_LRS --tags project=skylens

az functionapp create \
  --name $FUNC --resource-group $RG --storage-account $STOR \
  --consumption-plan-location $LOC \
  --runtime python --runtime-version 3.12 --functions-version 4 \
  --os-type Linux --tags project=skylens
```

**Give it the database credentials.** These are the same four values as your
local `.env` — paste them at the prompt rather than leaving them in shell history. Nothing else from `.env` is needed: no OpenAI key, no AI Search
key — the API never calls a model.

```bash
az functionapp config appsettings set -n $FUNC -g $RG --settings \
  SQL_SERVER=<your-server>.database.windows.net \
  SQL_DATABASE=<your-database> \
  SQL_USER=<your-user> \
  SQL_PASSWORD=<paste-it-here>
```

**Let Azure services reach the database.** Your SQL firewall currently allows
only your laptop's IP:

```bash
az sql server firewall-rule create \
  -g $RG -s <your-sql-server-name> -n AllowAzureServices \
  --start-ip-address 0.0.0.0 --end-ip-address 0.0.0.0
```

That special 0.0.0.0/0.0.0.0 pair means "Azure services", not "the internet".

**Publish.** Run from the repository root — `.funcignore` keeps the data
pipeline, the frontend and the notebooks out of the package:

```bash
func azure functionapp publish $FUNC
```

(Install the tool first if you need it: `brew tap azure/functions && brew install azure-functions-core-tools@4`.)

**Allow the browser to call it.** Azure Functions has its own CORS layer in
front of the application, so the API's own CORS settings are not enough:

```bash
az functionapp cors add -n $FUNC -g $RG --allowed-origins "https://<your-swa>.azurestaticapps.net"
```

You will not know the Static Web App's hostname until step 3, so come back and
run this then.

**Check it.** The database auto-pauses, so the first call can take up to a
minute and may time out once before it wakes:

```bash
curl https://$FUNC.azurewebsites.net/health
```

Expect `{"status":"ok","database":"connected", ...}`.

## 3. The site on Azure Static Web Apps

Do this in the portal, because it wires up GitHub for you.

1. **Create a resource → Static Web App**, plan **Free**, region nearest you.
2. Sign in to GitHub, pick the `SkyLens` repository and the `main` branch.
3. Build presets: **Custom**
   - App location: `web`
   - Api location: *(leave empty — the API is a separate Function App)*
   - Output location: `dist`
4. Create. Azure commits a workflow to `.github/workflows/azure-static-web-apps-*.yml` and runs it.

**Point the build at the API.** The generated workflow builds the site with
no idea where the API lives. Edit it and add an `env:` block to the
`Build And Deploy` step:

```yaml
      - name: Build And Deploy
        uses: Azure/static-web-apps-deploy@v1
        env:
          VITE_API_URL: https://skylens-api-varun.azurewebsites.net
        with:
          ...
```

Commit that, let it redeploy, then run the `az functionapp cors add` command
from step 2 with the real `*.azurestaticapps.net` hostname.

## 4. Entra ID on the admin page

`/admin` is already declared as requiring an authenticated user in
`web/public/staticwebapp.config.json`, and GitHub login is switched off there,
so Entra is the only way in.

Register the application:

```bash
az ad app create --display-name "SkyLens site" \
  --web-redirect-uris "https://<your-swa>.azurestaticapps.net/.auth/login/aad/callback"
```

Note the `appId` it prints, create a client secret for it in the portal
(**Entra ID → App registrations → SkyLens site → Certificates & secrets**),
then give both to the Static Web App:

```bash
az staticwebapp appsettings set -n <your-swa> --setting-names \
  AZURE_CLIENT_ID=<appId> AZURE_CLIENT_SECRET=<the secret value>
```

Open `https://<your-swa>.azurestaticapps.net/admin` in a private window. You
should be redirected to a Microsoft sign-in page, and land on the operations
view afterwards with your account name on it.

## 5. The policy

See `infra/README.md`. Create the definition, assign it to `$RG`, then prove it
denies an untagged resource. Do this **after** everything else exists, or the
policy will block your own deployments until you tag them.

## 6. Cost guardrails

```bash
az consumption budget create \
  --budget-name skylens-monthly --amount 10 --time-grain Monthly \
  --resource-group $RG --category Cost \
  --start-date $(date +%Y-%m-01) --end-date $(date -v+1y +%Y-%m-01)
```

Nothing here should cost more than a couple of dollars a month — Functions and
Static Web Apps both have free grants, and the database pauses when idle — but
a budget alert is the difference between noticing in a day and noticing on the
invoice.

---

## When something goes wrong

| Symptom | Cause |
|---|---|
| `/health` returns 503 | The database was asleep and did not wake inside the timeout. Call it again. |
| `/health` times out repeatedly | The SQL firewall rule for Azure services is missing, or `SQL_*` app settings are wrong. |
| The site loads but every panel errors | `VITE_API_URL` was not set at build time, so the browser is calling `/api` on the static host. Check the built bundle. |
| The site loads, the API works in curl, the browser shows a CORS error | The Function App's CORS list does not include the Static Web App's hostname. |
| `/admin` shows the page without asking anyone to sign in | You are running locally. The route is only protected once Static Web Apps serves it. |
| A deploy fails with `RequestDisallowedByPolicy` | The resource being created has no `project` tag. Add `--tags project=skylens`. |
