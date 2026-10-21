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

## The API is never unauthenticated

Both routes on the HTTP API (`POST /ocr`, `GET /health`) are declared with
`AuthorizationType: AWS_IAM` in [`cfn/template.yaml`](cfn/template.yaml), not the
`Target:` shorthand on `AWS::ApiGatewayV2::Api` (which creates a `$default`
route with **no** authorization at all). Every request must be SigV4-signed by
an IAM identity the caller's account grants `execute-api:Invoke` on this API's
ARN; an unsigned request is rejected by API Gateway with `403` before it ever
reaches the orchestrator Lambda or touches the MicroVM.
[`scripts/sigv4_request.py`](scripts/sigv4_request.py) signs requests with
whatever credentials boto3's default chain finds (the same ones your shell's
`aws` CLI commands use), and
[`scripts/invoke_example.sh`](scripts/invoke_example.sh) deliberately also
sends one *unsigned* `curl` to `/health` and expects (and checks for) `403`.

This is a real, enforced gate, not a hope: a stack deployed with this template
has no code path for an unauthenticated internet request to reach either the
orchestrator or the MicroVM. If you need the API reachable with no IAM
credentials at all (e.g. a public-facing product), put a proper authorizer
(Lambda authorizer / JWT / Cognito) in front instead of removing `AWS_IAM` --
do not ship this with `AuthorizationType: NONE`.

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

Being specific about this rather than implying more than was done. This
section originally said the stack had never been deployed; it has been since,
into a throwaway AWS sandbox account, and torn down again afterward.

- **Deployed and exercised end to end, in a real account (us-east-1):**
  `cloudformation deploy` created `AWS::Lambda::MicrovmImage`,
  `AWS::Lambda::Function` and the IAM-authorized HTTP API; `POST /ocr` against
  the live, SigV4-signed API correctly transcribed real Japanese test images
  (`paragraph.png`, `table.png`), byte-for-byte matching known ground truth,
  including the table rendered as `<table>` markup. An **unsigned** `curl` to
  the same URL got `403` before reaching Lambda, confirmed live, and
  `list_microvms()` showed a real `RUNNING` MicroVM (`microvm-0...`) at the
  same timestamp the OCR call returned. Measured from CloudWatch's own
  `REPORT` lines for the orchestrator Lambda (not client-side wall clock,
  which includes network noise unrelated to the system under test):
  - **Cold start (`run_microvm` through a ready, OCR'd reply): ~3.1s total
    orchestrator duration.** Far below the reference implementation's own
    11-82s, which tracks: that image mounts EFS over NFS and boots a Node.js
    app; this one has no EFS, no VPC egress, and a model two orders of
    magnitude smaller.
  - **Warm reuse (VM already `RUNNING`, fresh token minted, one HTTP round
    trip): ~250-340ms orchestrator duration**, of which the sidecar's own
    `/ocr` processing was 0.12-0.15s.
  - The stack was torn down after verification (`terminate_microvm` + stack
    delete + artifact bucket delete) rather than left running an
    internet-facing endpoint indefinitely; re-run `scripts/deploy.sh` to stand
    it back up.
- **Two real bugs this deployment found and fixed, that no amount of reading
  the reference implementation's source would have caught:**
  1. `AWS::Lambda::MicrovmImage` rejects the stack outright if
     `EnvironmentVariables`, `AdditionalOsCapabilities` or
     `EgressNetworkConnectors` are absent -- `aws cloudformation
     describe-events --change-set-name ...` reported `Required property
     [...] not found` for all three. The reference implementation's own
     template sets non-empty values for all three (it needs them), which
     reads as "these are optional, set only if needed" until you try
     omitting one. Fixed by setting all three to `[]` in `template.yaml`.
  2. The Dockerfile set `ENV INDRA_OCR_MODEL_DIR=/opt/indra-ocr/models`
     *before* the `RUN` step that downloads the model weights into that
     directory. `indra_ocr.models.model_dir()` checks that env var first and,
     if set, takes the "local folder, must already have the files" branch
     instead of downloading -- so the build failed with `ModelError: the
     model folder /opt/indra-ocr/models lacks det.onnx, rec.onnx, meta.json`,
     a straightforward chicken-and-egg ordering bug, visible only in the
     MicrovmImage build's own CloudWatch log group
     (`aws logs get-log-events --log-group-name
     /aws/lambda-microvms/<project>-image`). Fixed by moving the `ENV` line
     to after the download-and-copy `RUN` step.
- **Still not independently verified:** concurrent requests (see "No
  concurrency" below), `--math` mode, S3-ref mode (`{s3_bucket,s3_key}` --
  the code path was unit-tested but not exercised against a real bucket in
  this run), and whether `BaseMemoryMiB` can be lowered below 2048 (not
  re-tuned down from the reference implementation's default).

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
- **`BaseMemoryMiB` was not re-tuned down.** 2048 (matching the reference
  implementation's own default) worked and was not an independently
  established lower bound for a model this small -- it may well run on less.

## Layout

```
cfn/template.yaml          CloudFormation: MicrovmImage, roles, orchestrator Lambda, HTTP API
microvm/Dockerfile          Image build: Python base, indra-ocr, baked-in model weights
microvm/sidecar.py          Lifecycle hooks + /ocr, model loaded once at process start
microvm/make_sample.py      Build-time helper: tiny image used only to prewarm /validate
orchestrator/handler.py     API Gateway -> MicroVM proxy (run_microvm, token, S3 I/O)
scripts/deploy.sh           Create artifact bucket, build both zips, `cloudformation deploy`
scripts/invoke_example.sh   End-to-end example for both input modes, SigV4-signed
scripts/sigv4_request.py    SigV4-signs a request against the AWS_IAM-authorized API
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

The first `/ocr` call cold-starts the MicroVM (~3.1s measured, see "What was
actually verified" above); later calls while it's RUNNING or SUSPENDED reuse
it (~250-340ms measured). **Remember to tear the stack down
(`aws cloudformation delete-stack`, after `terminate_microvm` on any VM the
registry still points at) when you're done** -- it is an internet-facing API
Gateway endpoint, IAM-authorized but still internet-reachable, for as long as
the stack exists.
