<picture>
  <source media="(prefers-color-scheme: dark)" srcset="readme-kit/assets/divider-dark.svg">
  <img src="readme-kit/assets/divider-light.svg" width="100%" alt="">
</picture>

# <img src="readme-kit/assets/icons/terminal.svg" width="32" align="top" alt="">&nbsp; Setting it up from a fresh clone

Everything below runs from the repository root in Windows PowerShell with the AWS CLI v2 signed in to the
account. If scripts are blocked, run them as `powershell -ExecutionPolicy Bypass -File deploy.ps1`.
Day-to-day work once it is running is in [OPERATIONS.md](OPERATIONS.md).

| Section | What it covers |
|---|---|
| [1. The fal key](#1-the-fal-key) | a key that can only call models, kept in Secrets Manager |
| [2. The styles](#2-the-styles) | `gateway/styles.json`: each LoRA's address and phrase, kept out of git |
| [3. Deploy](#3-deploy) | the first `./deploy.ps1` |
| [What is in the repository](#what-is-in-the-repository) | every file and what it holds |

## 1. The fal key

In a fal.ai account with credit, create a key that can only call models, and store it in Secrets Manager.
The stack reads it from there but does not create it.

```powershell
pip install fal                 # the fal CLI
fal auth login                  # opens a browser
fal keys create --preset API --desc indian-painting-gateway   # prints FAL_KEY='...'
aws secretsmanager create-secret --region ap-south-1 --name indian-painting-gateway/fal-key --secret-string "<the FAL_KEY value>"
```

## 2. The styles

Copy `styles.example.json` to `gateway/styles.json` and fill in each LoRA's https address. Each style also
has the phrase the API adds to a prompt that doesn't name it
([API.md](API.md#the-style-phrase)). The Lambda serves no request unless every style in the file has an
https `lora_url` and a `phrase`, and `deploy.ps1` refuses to run without the file.

`gateway/styles.json` is in `.gitignore`: anyone holding a LoRA address can download the weights. The
current addresses can be recovered from the deployed Lambda, whose package contains `gateway/styles.json`:

```powershell
Invoke-WebRequest -UseBasicParsing (aws lambda get-function --function-name indian-painting-gateway --region ap-south-1 --query Code.Location --output text) -OutFile lambda.zip
Expand-Archive lambda.zip lambda-package
Copy-Item lambda-package\gateway\styles.json gateway\styles.json
Remove-Item -Recurse lambda.zip, lambda-package
```

To upload a new LoRA file to fal's CDN instead (with `FAL_KEY` set in the environment):

```powershell
pip install fal-client
python -c "import fal_client; print(fal_client.upload_file('kangra_flux_lora_v1.safetensors'))"
```

## 3. Deploy

```powershell
./deploy.ps1
```

It creates the artifacts bucket on its first run, deploys the CloudFormation stack and prints the API URL.
What each run does is drawn in [OPERATIONS.md](OPERATIONS.md#deploying-a-change).

When `styles.json` or the fal key changes, also update the local `.env` and the GitHub secrets
(`gh secret set STYLES_JSON < gateway/styles.json`, `gh secret set FAL_KEY`).

## What is in the repository

| Path | What it holds |
|---|---|
| `gateway/handler.py` | Lambda entry point: the two routes and their replies |
| `gateway/generation.py` | The request contract, the style phrase, and the arguments sent to fal |
| `gateway/fal_queue.py` | The only code that talks to fal: submit, check, collect |
| `gateway/daily_limit.py` | The daily image counter in DynamoDB |
| `gateway/settings.py` | Reads the Lambda environment and `styles.json` |
| `gateway/styles.json` | Each style's LoRA address and phrase (not in git) |
| `styles.example.json` | The shape of `styles.json` |
| `template.yaml` | The CloudFormation stack |
| `deploy.ps1`, `stack.ps1` | Packaging and deployment; `stack.ps1` names the region and the stack |
| `.env` | Local copies of the secrets: fal key, styles, gateway URL (not in git) |
| `docs/images/` | The paintings in the README and the comparisons in [DESIGN.md](DESIGN.md) |
| `docs/readme-kit/` | The README kit: `kit.json`, the generated `assets/`, the tools and the style guide |
| `.github/workflows/readme-check.yml` | Checks the README and `docs/` on every change to them |

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="readme-kit/assets/footer-dark.svg">
  <img src="readme-kit/assets/footer-light.svg" width="100%" alt="Kangra and Mughal, one prompt away. AI CoE, IIT Kharagpur, Indian miniature painting.">
</picture>
