# Indian painting gateway

An HTTP API that paints a prompt in the **Kangra** or **Mughal** miniature style. It runs the
two FLUX.1-dev LoRAs from [Indian-painting-generator](https://github.com/abhilashab4/Indian-painting-generator)
on fal.ai, behind AWS API Gateway in ap-south-1, with a daily image limit.

It answers exactly like that repo's Modal app and, like it, needs no key, so a page written for
it only changes the base URL.

```
Base URL   https://n5pz0b1to2.execute-api.ap-south-1.amazonaws.com/v1
```

## Using the API

**1. Start an image.** `POST /` with a JSON body. Only `prompt` is required.

| Field | Default | Allowed |
|---|---|---|
| `prompt` | (required) | up to 2,000 characters |
| `style` | `"kangra"` | `"kangra"` or `"mughal"` |
| `steps` | `20` | 1 to 50 |
| `guidance` | `3.5` | 0 to 35 |
| `width`, `height` | `768` | 256 to 1536, rounded down to a multiple of 16 |
| `lora_scale` | `1.0` | 0 to 2 (how strongly the style is applied) |

The reply is `{"call_id": "...", "status": "queued"}`.

**2. Collect it.** `GET /result/{call_id}` every few seconds. It answers `202` with
`{"status": "processing"}` until the image is ready, then `200` with the image itself (PNG, or
JPEG above 1024 x 1024). The `X-Image-Url` header gives a public link to the same image.

You don't need to write "Kangra painting" in your prompt: if the prompt doesn't name its style,
the API adds "Kangra miniature painting" or "Mughal miniature painting" to the end.

An image usually takes 10 to 15 seconds. The first one after a quiet spell takes about a minute
while the style is loaded.

```js
const API = "https://n5pz0b1to2.execute-api.ap-south-1.amazonaws.com/v1";

async function paint(prompt, style = "kangra") {
  const start = await fetch(`${API}/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt, style }),
  });
  if (!start.ok) throw new Error(await reason(start));
  const { call_id } = await start.json();

  for (;;) {
    await new Promise((resolve) => setTimeout(resolve, 3000));
    const result = await fetch(`${API}/result/${call_id}`);
    if (result.status === 202) continue;
    if (!result.ok) throw new Error(await reason(result));
    return URL.createObjectURL(await result.blob()); // use as <img src>
  }
}

async function reason(response) {
  const body = await response.json().catch(() => ({}));
  return body.error || body.message || response.statusText;
}
```

| Status | Meaning |
|---|---|
| `400` | Something in the body is wrong; `error` says what. |
| `404` | Unknown `call_id`, or the result has expired. |
| `429` | Today's images have been used. Resets at midnight IST. |
| `500` | The image failed; `error` gives the reason. |
| `502` | The image service refused the job; `error` gives the reason. |

## Running it

All commands run from this folder in PowerShell. If scripts are blocked, prefix them with
`powershell -ExecutionPolicy Bypass -File`.

**Change the daily limit.** By default the API starts up to 1,000 images a day.

```powershell
./deploy.ps1 -ImagesPerDay 600
```

**Change or add a style.** Upload the LoRA to fal (or any https address fal can download), put
its URL and phrase in `gateway/styles.json`, and run `./deploy.ps1`.

`gateway/styles.json` is kept out of git, because anyone holding a LoRA's address can download
the weights. A fresh clone starts by copying `styles.example.json` to `gateway/styles.json` and
filling in the addresses, which are kept in the GitHub secret `STYLES_JSON`; `deploy.ps1`
refuses to run without the file. When you change `styles.json` or the fal key, update the
matching GitHub secret too (`gh secret set STYLES_JSON < gateway/styles.json`).

### What it costs

- **fal.ai**, per image: $0.035 per megapixel, so about $0.02 at 768 x 768 and $0.08 at
  1536 x 1536. At the default limit the worst day is 1,000 images: about $20 at the default
  size, $83 if every image were the largest size. When the fal balance runs out, new images fail
  with a `502` that says so; top it up at fal.ai.
- **AWS**: Lambda, API Gateway and DynamoDB come to cents a month at this scale. The Secrets
  Manager secret is $0.40 a month.

### Where things are

| What | Where |
|---|---|
| Stack (API, Lambda, usage table) | CloudFormation `indian-painting-gateway`, ap-south-1 |
| Lambda package | S3 `indian-painting-gateway-artifacts-<account id>` |
| fal key (API-only) | Secrets Manager `indian-painting-gateway/fal-key`, made by hand, not by the stack; copy in GitHub secret `FAL_KEY` |
| LoRA files | fal CDN, addresses in `gateway/styles.json` (not in git); copy in GitHub secret `STYLES_JSON` |
| Logs | CloudWatch `/aws/lambda/indian-painting-gateway`, kept 30 days |
| Local copies of the secrets | `.env` in this folder (not in git): fal key, styles, gateway URL |

The LoRA addresses are unlisted rather than private: anyone who has one can download the file.
They appear only in `styles.json` and the Lambda, never in replies.

### Taking it down

```powershell
$account = aws sts get-caller-identity --query Account --output text
aws cloudformation delete-stack --stack-name indian-painting-gateway --region ap-south-1
aws s3 rb "s3://indian-painting-gateway-artifacts-$account" --force --region ap-south-1
aws secretsmanager delete-secret --secret-id indian-painting-gateway/fal-key --region ap-south-1
fal keys list   # then: fal keys revoke <id>   (the fal CLI: pip install fal)
```

## Design notes

- **Why fal, not a GPU on AWS.** On 20 November 2026 the account had no GPU quota for SageMaker
  or EC2 in any region checked, and an always-on GPU endpoint would cost $1,100 to $1,800 a month.
  fal bills per image and needs no quota.
- **Why the style phrase is added.** With a fixed seed, both LoRAs left a plain prompt
  photographic; with the phrase they drew flat miniatures, clearly unlike FLUX alone with the
  same phrase.
- **Why there is no key.** The API serves one trusted student, and the Modal app it replaces was
  open too (decided by the owner on 20 November 2026). Anyone who finds the URL can use it, so
  the daily image limit (`gateway/daily_limit.py`, counted in DynamoDB) is what caps spending.
  There is no request-rate limit, so polling as often as a page likes is fine.
- **Results** come back as image bytes, not a redirect, to match the Modal app. Images above one
  megapixel are JPEG so the base64 reply stays under Lambda's 6 MB limit.

## Known gaps

- No unit tests. The API was checked end to end on 20 November 2026: preflight, bad style,
  missing prompt, invalid JSON, out-of-range steps, bad and unknown `call_id`, and real images
  in both styles.
- The account's Lambda concurrency limit was 10 on 20 November 2026; a raise to 1,000 was
  requested that day. Until it is granted, many requests at the same moment can get `500` or
  `502` with no `error` field; retrying a moment later works. Check with
  `aws service-quotas get-service-quota --service-code lambda --quota-code L-B99A9384 --region ap-south-1`.
