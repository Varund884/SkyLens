# Governance

Everything in this project runs in one resource group. The rule below is the
guardrail on that group: a resource cannot be created there unless it says
which project it belongs to. That is the mechanism behind every cloud cost
report that can tell you what a project actually costs — without an enforced
tag, the answer is guesswork by the end of the first month.

The policy is written as a definition plus an assignment, which is the split
Azure uses everywhere: the definition says what the rule is, the assignment
says where it applies and how hard it bites.

## Create the definition

```bash
az policy definition create \
  --name skylens-require-project-tag \
  --display-name "Require a project tag on resources" \
  --description "Resources must carry project=skylens so cost and ownership can be attributed." \
  --mode Indexed \
  --rules policy-require-project-tag.rules.json \
  --params policy-require-project-tag.params.json
```

`Indexed` mode applies the rule only to resource types that support tags, so
it does not fail resources that have nowhere to put one.

## Assign it to the resource group

```bash
SUB=$(az account show --query id -o tsv)

az policy assignment create \
  --name skylens-require-project-tag \
  --display-name "Require a project tag (SkyLens)" \
  --policy skylens-require-project-tag \
  --scope "/subscriptions/$SUB/resourceGroups/<your-resource-group>"
```

## Prove it works

```bash
# Denied: no tag.
az storage account create -n skylenspolicytest -g <your-resource-group> -l canadacentral --sku Standard_LRS

# Allowed: tagged.
az storage account create -n skylenspolicytest -g <your-resource-group> -l canadacentral --sku Standard_LRS \
  --tags project=skylens
```

The first command fails with `RequestDisallowedByPolicy` and names this
assignment. Delete the test account afterwards.

## Tag what already exists

The policy only governs new resources; existing ones are unaffected until they
are next updated. Tag them in one pass:

```bash
for id in $(az resource list -g <your-resource-group> --query "[].id" -o tsv); do
  az resource tag --ids "$id" --tags project=skylens --is-incremental
done
```

## Switching it to audit-only

Assign with `--params '{"effect":{"value":"Audit"}}'` to record violations in
the compliance report without blocking anything. Useful when a rule is being
introduced to a group that already has resources in it.
