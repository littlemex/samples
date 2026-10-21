# Indra OCR on AWS Lambda MicroVMs

Runs [Indra OCR](https://github.com/datalab-to/indra) (datalab.to's ~1M-parameter,
CPU-only OCR model) inside an [AWS Lambda MicroVM](https://aws.amazon.com/lambda/)
and fronts it with a small orchestrator Lambda behind an HTTP API, so a caller can
send an image or PDF over plain HTTP and get Markdown/text/JSON back.

## Why a MicroVM for a model this small

Indra OCR is tiny (CPU-only, ~1M parameters for the recognizer, ~7M for the whole
default pipeline), but a cold process pays ~1-3s just loading the ONNX Runtime
session before it OCRs anything. A classic Lambda "Event Function" reloads that
model on every cold start. A MicroVM can stay **suspended** (not billed) between
bursts of requests and **resume** with the model still loaded in memory in a few
seconds, which is the shape this workload actually wants: occasional bursts from
the same caller, not a steady trickle from many independent callers. See
[What this sample does not do](#what-this-sample-does-not-do) for where that
stops being true.

## A MicroVM has no public endpoint -- here is what stands in for one

This is the detail worth stating plainly, because it is not what "serverless
function with a URL" usually means: **a MicroVM cannot be called directly from
the internet.** The only way to reach one is:

1. An ordinary Lambda function (the **orchestrator**, [`orchestrator/handler.py`](orchestrator/handler.py))
   calls `boto3.client("lambda-microvms").run_microvm(...)`, gets back a
   `microvmId` and an internal `endpoint`.
2. The orchestrator calls `create_microvm_auth_token(microvmIdentifier=...,
   allowedPorts=[{"port": 8080}])` to mint a short-lived (<=55 min) token.
3. The orchestrator makes an HTTPS request to `https://{endpoint}{path}` with
   two special headers, `X-aws-proxy-auth: <token>` and
   `X-aws-proxy-port: 8080`, which the platform uses to proxy the call into the
   VM's sidecar on that port.

So the "endpoint" the API in front of this sample exposes is the **orchestrator's**
HTTP API, not the MicroVM's. The orchestrator is the only thing that can talk to
the VM at all.

```
caller --HTTP--> API Gateway --invoke--> orchestrator Lambda
                                              |
                                              | boto3 lambda-microvms:
                                              |   run_microvm / get_microvm /
                                              |   create_microvm_auth_token
                                              v
                                   MicroVM (Firecracker, suspend/resume)
                                     sidecar.py :8080
                                       - /aws/lambda-microvms/runtime/v1/{ready,validate,run}
                                       - /health
                                       - /ocr  <- indra_ocr, model loaded once at boot
```

None of the API shapes above (the `lambda-microvms` boto3 client, the lifecycle
hook path `/aws/lambda-microvms/runtime/v1/{ready,validate,run}`, the
`X-aws-proxy-auth`/`X-aws-proxy-port` proxy headers) were guessed. They were taken
from AWS's own reference implementation,
[`aws-samples/sample-multi-tenant-ai-agents-on-lambda-microvm`](https://github.com/aws-samples/sample-multi-tenant-ai-agents-on-lambda-microvm),
which at the time this was written is the only place that protocol is written
down outside AWS's internal docs. This sample is a much smaller relative of that
one: OCR is stateless and the model is baked into the image, so there is no EFS,
no VPC/NAT, no per-tenant DynamoDB registry, and no Bedrock wiring here.

## "S3 Files" does not reach a MicroVM -- here is what to use instead

Whoever is deploying this may reasonably expect a Lambda function's "S3 Files"
feature (a native filesystem view of an S3 bucket) to be available inside the
MicroVM, the same way it is for a classic Lambda function. **It is not.** The
same AWS reference implementation's own design notes say so directly
([`docs/design/storage-options.md`](https://github.com/aws-samples/sample-multi-tenant-ai-agents-on-lambda-microvm/blob/main/docs/design/storage-options.md)):

> Lambda "S3 Files" / function EFS config -- **Lambda-function-only features** --
> no MicroVM API surface exposes them.

What this sample does instead: the **orchestrator** (an ordinary Lambda function,
where S3 Files genuinely would work) uses the normal S3 SDK to read/write objects,
and forwards only the raw bytes to the MicroVM over the `X-aws-proxy-auth` HTTP
channel described above. `POST /ocr` on the public API accepts either:

```jsonc
// S3 in, S3 out -- the orchestrator does the S3 I/O; the VM only ever sees bytes
{"s3_bucket": "my-bucket", "s3_key": "inbox/page1.png",
 "s3_output_key": "results/page1.md", "format": "md"}

// or: bytes travel in the request/response body directly (fits small images;
// HTTP API caps bodies at 10 MB)
{"content_b64": "<base64>", "filename": "page1.png", "format": "md"}
```

## Why the model is baked into the image, and why arm64

`indra_ocr.models.model_dir()` downloads model weights from Hugging Face on
first use and caches them -- fine for a CLI, wrong for a MicroVM image: every
*first* launch of a fresh snapshot would need a network call before it could OCR
anything. [`microvm/Dockerfile`](microvm/Dockerfile) downloads the weights once at
**build** time and copies them into the image, so a running MicroVM never calls
Hugging Face.

The image is `arm64` (Graviton). indra-ocr is a pure-Python wheel with no
PyTorch dependency (it's ONNX Runtime-based), and its native dependencies
(`opencv-python-headless`, `onnxruntime`, `numpy`, `pypdfium2`) all ship
`manylinux_aarch64` wheels. Running indra-ocr under a genuine aarch64 Linux
container (not emulated; verified via Finch's own arm64 VM on an Apple Silicon
Mac, not QEMU) correctly OCR'd a real Japanese test image, no source build
required -- `uname -m` reported `aarch64`, `onnxruntime` loaded with
`CPUExecutionProvider`. Nothing arm64-specific was needed in the Dockerfile
beyond `--platform=linux/arm64` on the `FROM` line.

## What was actually verified, and what was not

Being specific about this rather than implying more than was done:

- **Verified, locally, end to end:** `microvm/sidecar.py` loads indra-ocr once,
  answers the three lifecycle hook paths with the right shapes, and `/ocr`
  correctly transcribes a real Japanese test image (exact match against known
  ground truth) in **0.15-0.19s per request** once the model is loaded -- run
  directly with `python3 microvm/sidecar.py` against a locally-downloaded model
  directory, no AWS involved. `orchestrator/handler.py`'s request-validation
  branches (missing fields, bad `format`, routing) pass unit tests with no AWS
  credentials in [`tests/test_handler_validation.py`](tests/test_handler_validation.py).
  `cfn/template.yaml` passes `aws cloudformation validate-template` against a
  real account (confirms YAML/intrinsic-function syntax and that
  `CAPABILITY_NAMED_IAM` is correctly required for the `AWS::IAM::Role`
  resources; it does not confirm the MicroVM resources actually build).
- **NOT deployed or tested end to end:** the CloudFormation stack itself (the
  actual `AWS::Lambda::MicrovmImage` build, `run_microvm`/`create_microvm_auth_token`
  calls against a real account, the orchestrator's S3 round trip, cold-start
  timing for this specific image). AWS Lambda MicroVMs GA'd 2026-06-22 and this
  was built from reading AWS's own reference sample's source rather than from a
  live deployment of this exact stack. **Deploy into a throwaway account/stack
  and confirm `POST /ocr` works before relying on this.**
- A few CloudFormation property choices are documented as unverified guesses
  rather than confirmed facts -- search `template.yaml` for the comments next
  to `AdditionalOsCapabilities` and `BaseMemoryMiB`.

## What this sample does not do

- **No concurrency.** One MicroVM, remembered in a single SSM parameter. Two
  overlapping cold starts can race (no conditional-update lock, unlike the
  DynamoDB-backed registry the reference implementation uses for its
  multi-tenant case). Fine for a single caller; add that lock before using this
  under real concurrent load.
- **No autoscaling / pooling.** If you need N requests in flight at once, you
  need N MicroVMs and a registry that tracks all of them, not the one slot this
  sample keeps.
- **No math OCR.** `--math` mode downloads extra model files and wasn't baked
  into the image; add it to `Dockerfile` and `sidecar.py`'s `load()` call if you
  need LaTeX output for formulas.
- **No independent cold-start measurement for this image.** The reference
  implementation's own cold-start investigation
  ([`docs/perf/cold-start.md`](https://github.com/aws-samples/sample-multi-tenant-ai-agents-on-lambda-microvm/blob/main/docs/perf/cold-start.md)
  in the same repo) is about a much heavier Node.js app with an EFS mount; this
  image's cold start was not measured because it was never deployed. Expect it
  to be smaller (no EFS, no Node boot, a tiny model) but don't assume a number
  until you've measured one.

## Layout

```
cfn/template.yaml          CloudFormation: MicrovmImage, roles, orchestrator Lambda, HTTP API
microvm/Dockerfile          Image build: Python base, indra-ocr, baked-in model weights
microvm/sidecar.py          Lifecycle hooks + /ocr, model loaded once at process start
microvm/make_sample.py      Build-time helper: tiny image used only to prewarm /validate
orchestrator/handler.py     API Gateway -> MicroVM proxy (run_microvm, token, S3 I/O)
scripts/deploy.sh           Create artifact bucket, build both zips, `cloudformation deploy`
scripts/invoke_example.sh   curl examples for both input modes
tests/test_handler_validation.py   No-AWS-needed unit tests for the orchestrator's request parsing
```

## Deploying

```bash
export AWS_REGION=us-east-1   # check MicroVMs' region availability for your account first
cd scripts
./deploy.sh my-indra-ocr-artifacts indra-ocr-microvm        # no S3 I/O mode
# or, to also allow {s3_bucket,s3_key} requests:
./deploy.sh my-indra-ocr-artifacts indra-ocr-microvm my-ocr-data-bucket

API=$(aws cloudformation describe-stacks --stack-name indra-ocr-microvm \
       --query 'Stacks[0].Outputs[?OutputKey==`ApiEndpoint`].OutputValue' --output text)
./invoke_example.sh "$API" /path/to/some-page.png md
```

The first `/ocr` call cold-starts the MicroVM (expect it to take a while --
unmeasured for this image, see above); later calls while it's RUNNING or
SUSPENDED reuse it.
