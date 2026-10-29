# Measuring AWS Lambda Web Functions cold starts

[Lambda Web Functions](https://docs.aws.amazon.com/lambda/latest/dg/web-functions.html) run an
ordinary Node.js HTTP server on Lambda: one execution environment serves many requests at once,
Lambda keeps spare environments ahead of demand, and an endpoint scales to zero when idle. The
documentation is explicit that cold starts still exist (the first request after scale-to-zero,
or any request that arrives when no warm environment has room, waits for a new one) and that
there is no minimum-environments setting. It does not say how long that wait is. This sample
measures it.

It deploys three Web Functions that differ in one thing each, puts them behind an authenticated
CloudFront distribution, and runs a scheduled prober that calls them after they have scaled to
zero.

| Variant | What is in the package | Zip size |
|---|---|---|
| `minimal` | [`app/minimal/index.js`](app/minimal/index.js): `node:http`, no dependencies | ~1 KB |
| `express` | [`app/express/index.js`](app/express/index.js): Express 5 and two AWS SDK v3 clients built at startup | ~4.6 MB |
| `padded` | the minimal server plus a 200 MB incompressible file it never reads | ~200 MB |

## Results

Measured in us-east-1 on 2026-10-29 and 2026-10-30 (JST), about nine hours of runs every ten
minutes, with the prober in the same Region. `ttfb` is request written to response headers on a
fresh TLS connection. Medians, with the 90th percentile in parentheses.

**First request after scale-to-zero, called directly (SigV4, no CloudFront)**

| Variant | Cold, first request | Warm, same environment | `platform.initReport` wall / CPU | Cold minus init | Runs |
|---|---|---|---|---|---|
| `minimal` | 386 ms (425) | 32 ms | 253 ms / 139 ms | 133 ms | 17 |
| `express` | 633 ms (747) | 32 ms | 492 ms / 315 ms | 141 ms | 17 |
| `padded` | 1,051 ms (1,222) | 29 ms | 917 ms / 141 ms | 134 ms | 16 |

- What the platform adds on top of the init phase is about the same for every variant (133 to
  141 ms, including the ~30 ms round trip that a warm request also pays). The rest is your
  process: loading the code and starting to listen.
- Package size alone costs time: 200 MB of unread data made the init phase about 660 ms longer
  while its CPU time stayed the same as `minimal`.
- An idle environment was spun down after a median of 334 to 343 seconds over the whole period (`analyze.py idle`).

**The same, through CloudFront with a Cognito token**

| Variant | Edge function fetches JWKS at first request | JWKS embedded (`EMBED_JWKS=1`) |
|---|---|---|
| `minimal` | 1,241 ms (1,341), 18 runs | 784 ms (921), 9 runs |
| `express` | 1,492 ms (1,646), 18 runs | 973 ms (1,101), 9 runs |
| `padded` | 1,932 ms (2,019), 18 runs | 1,546 ms (1,641), 9 runs |

The front door has its own cold start. The Lambda@Edge function was also idle for ten minutes
before every run, so it started cold each time: init 162 ms, and its first invocation took
506 ms because it fetched the user pool's JWKS from Cognito. With the keys written into the
code at deploy time, the first invocation took 33 ms (init 172 ms). About 0.2 s of the
remaining difference to the direct path is not broken down by this sample.

**100 requests at once, from zero** (all sent within 40 to 42 ms, one run each)

| Variant and path | Environments started | Median | Max |
|---|---|---|---|
| `minimal`, direct | 20 | 339 ms | 419 ms |
| `express`, direct | 9 | 519 ms | 574 ms |
| `minimal`, CloudFront | 16 | 662 ms | 765 ms |

Every request waited for a new environment, and none waited longer than a single cold start.

## Nothing here is reachable without a Cognito token

The endpoints are never exposed as they are:

```
prober --(Cognito access token)--> CloudFront --viewer-request--> Lambda@Edge (JWT check)
                                        |
                                        | origin request signed by CloudFront (OAC, SigV4)
                                        v
                       Web Function endpoint (AuthType IamAuth)
```

- **Endpoints are `IamAuth`.** An unsigned request to the endpoint domain gets `403`. Each Web
  Function has a resource-based policy that allows `cloudfront.amazonaws.com` to invoke it only
  when `aws:SourceArn` is this distribution. CloudFormation has no resource for that policy yet,
  so [`scripts/deploy.sh`](scripts/deploy.sh) sets it with `aws lambda-web put-resource-policy`.
- **CloudFront signs origin requests** through an origin access control with origin type
  `lambda` and signing behavior `always-amz-auth`, as the
  [CloudFront integration](https://docs.aws.amazon.com/lambda/latest/dg/web-functions-endpoint-access-control.html)
  section requires.
- **CloudFront admits only Cognito access tokens.** A viewer-request Lambda@Edge function
  ([in the template](cfn/template.yaml)) verifies the RS256 signature against the user pool's
  keys and checks the issuer, `token_use`, `client_id`, the scope and the expiry, then removes
  the `Authorization` header before the request goes on. A missing or forged token gets `401`
  at the edge and never reaches an origin.
- **The token is machine-to-machine.** The user pool has no users; the prober uses the client
  credentials grant with a secret that CloudFormation stores in Secrets Manager.

Same-account principals whose identity policy allows `lambda:InvokeWebFunctionEndpoint` can
still sign requests to the endpoints directly. The prober does exactly that for its `direct`
measurements, and its role is limited to these three endpoint ARNs.

Checked after deploying (2026-10-29): no token `401`, forged token `401`, direct unsigned `403`,
valid token `200`.

## How a cold request is measured

[`prober/prober.py`](prober/prober.py) runs on a schedule that is longer than the idle time
after which Lambda spins an environment down (about six minutes in these runs; see below). On
each run it sends, to all three variants in parallel, one request and then five more, each on a
fresh TLS connection, and logs:

- `ttfbMs`: request written to response headers received. This is where a cold start shows.
- `envAgeAtSendMs`: how old the answering environment's process was when the request was sent,
  from the server's own `performance.timeOrigin`. A negative value means the process started
  after the request was sent, so the request waited for a new environment. Only those are
  counted as cold.
- the five following requests, on the same environment, as the warm baseline for that run.

Runs alternate between two paths: through CloudFront with a token, and `direct`, where the
prober signs the request to the endpoint itself. The difference between the two is the cost of
the front door, not of the Web Function.

[`scripts/analyze.py`](scripts/analyze.py) reads the prober's log group and the Web Functions'
own system logs (`platform.initReport` for Lambda's measurement of the init phase,
`platform.spinDownStart` for when an idle environment was removed).

## Deploying

Needs an AWS CLI release that has the `lambda-web` commands (2.39 or later) and Node.js with npm
for the Express package. Lambda@Edge functions must be created in us-east-1, so the whole sample
deploys there.

```bash
export AWS_REGION=us-east-1
./scripts/deploy.sh
```

The schedule is created disabled. To start measuring, deploy again with it enabled and with the
public keys embedded in the edge function (see the results for why):

```bash
export AWS_REGION=us-east-1
export SCHEDULE_STATE=ENABLED
export SCHEDULE_RATE_MINUTES=10
export EMBED_JWKS=1
./scripts/deploy.sh
```

After a few hours:

```bash
export AWS_REGION=us-east-1
python3 scripts/analyze.py probes --hours 6
python3 scripts/analyze.py init --hours 6
python3 scripts/analyze.py idle --hours 6
```

A one-off burst from zero:

```bash
aws lambda invoke --region us-east-1 --function-name wf-coldstart-prober \
  --cli-binary-format raw-in-base64-out \
  --payload '{"mode": "burst", "variant": "minimal", "concurrency": 100, "path": "direct"}' \
  --cli-read-timeout 310 burst.json
```

To remove everything:

```bash
export AWS_REGION=us-east-1
./scripts/teardown.sh
```

CloudFront deletes the Lambda@Edge replicas some time after the distribution is gone. If the
main stack stops in `DELETE_FAILED` on the edge function, run the script again later.

## Layout

```
app/minimal/index.js     the dependency-free server
app/express/             Express 5 + AWS SDK v3 server (package.json, package-lock.json)
prober/prober.py         scheduled prober (cold + warm requests, both paths, burst mode)
cfn/artifacts.yaml       versioned bucket for packages, readable only by this project's revisions
cfn/template.yaml        Web Functions, Cognito, Lambda@Edge, CloudFront, prober, schedule
scripts/deploy.sh        build, upload, deploy, set the Web Function resource policies
scripts/analyze.py       numbers from the logs
scripts/teardown.sh      delete both stacks and the package bucket
```
