#!/usr/bin/env python3
"""Turn the prober's and the Web Functions' CloudWatch logs into cold-start numbers.

  analyze.py probes [--hours 24]   first-request vs warm latency, per variant and path
  analyze.py init   [--hours 24]   platform.initReport (Lambda's own init timing) per variant
  analyze.py idle   [--hours 24]   how long an environment sat idle before Lambda spun it down
  analyze.py edge   [--hours 24]   Lambda@Edge REPORT lines: cold inits and their first invocation
  analyze.py dump   [--hours 24]   write the raw probe records to probes.jsonl

--since / --until (epoch seconds) narrow any command to a window, for example to compare the
runs before and after a redeploy.

Uses only the AWS CLI (set AWS_CLI for a specific binary), no Python dependencies.
"""
import argparse
import json
import os
import statistics
import subprocess
import time
from collections import defaultdict

AWS = os.environ.get("AWS_CLI", "aws")
REGION = os.environ.get("AWS_REGION", "us-east-1")
VARIANTS = ["minimal", "express", "padded"]


WINDOW = {"since": None, "until": None}


def events(group, hours, pattern=None):
    start = WINDOW["since"] or time.time() - hours * 3600
    cmd = [AWS, "logs", "filter-log-events", "--region", REGION, "--log-group-name", group,
           "--start-time", str(int(start * 1000)), "--output", "json"]
    if WINDOW["until"]:
        cmd += ["--end-time", str(int(WINDOW["until"] * 1000))]
    if pattern:
        cmd += ["--filter-pattern", pattern]
    out = json.loads(subprocess.check_output(cmd) or b"{}")
    for e in out.get("events", []):
        try:
            yield e, json.loads(e["message"])
        except (json.JSONDecodeError, TypeError):
            continue


def stats(xs):
    xs = sorted(xs)
    if not xs:
        return "n=0"
    pct = lambda p: xs[min(len(xs) - 1, int(round(p * (len(xs) - 1))))]
    return (f"n={len(xs):3d}  median={statistics.median(xs):8.1f}  p90={pct(0.9):8.1f}"
            f"  min={xs[0]:8.1f}  max={xs[-1]:8.1f}")


def load_probes(project, hours):
    recs = [m for _, m in events(f"/aws/lambda/{project}-prober", hours, '{ $.type = "probe" }')]
    return [r for r in recs if r.get("type") == "probe"]


def cmd_probes(a):
    recs = load_probes(a.project, a.hours)
    runs = defaultdict(list)
    for r in recs:
        runs[(r["run"], r["variant"], r["path"])].append(r)
    cold, warm, not_cold, penalty, errors = (defaultdict(list) for _ in range(5))
    for (run, variant, path), rs in runs.items():
        rs.sort(key=lambda r: r["seq"])
        key = (variant, path)
        if any(r.get("status") != 200 for r in rs):
            errors[key].append(run)
            continue
        first, rest = rs[0], [r for r in rs[1:] if r["server"]["envId"] == rs[0]["server"]["envId"]]
        # Cold means the environment that answered was started after the request was sent.
        if first["seq"] != 0 or first["envAgeAtSendMs"] >= 0:
            not_cold[key].append(first["ttfbMs"])
            continue
        cold[key].append(first["ttfbMs"])
        warm[key] += [r["ttfbMs"] for r in rest]
        if rest:
            penalty[key].append(first["ttfbMs"] - statistics.median(r["ttfbMs"] for r in rest))
    print("ttfb in ms (request sent -> response headers), fresh TLS connection per request\n")
    for v in VARIANTS:
        for p in ("direct", "cloudfront"):
            k = (v, p)
            if not (cold[k] or warm[k] or not_cold[k] or errors[k]):
                continue
            print(f"{v:8s} {p:10s} cold first request  {stats(cold[k])}")
            print(f"{'':19s} warm (same env)     {stats(warm[k])}")
            print(f"{'':19s} cold - warm median  {stats(penalty[k])}")
            if not_cold[k] or errors[k]:
                print(f"{'':19s} first request found a warm env in {len(not_cold[k])} runs; {len(errors[k])} runs had errors")
            print()


def cmd_init(a):
    print("platform.initReport: Lambda's measurement of the init phase, in ms\n")
    for v in VARIANTS:
        dur, cpu, mem = [], [], []
        for _, m in events(f"/aws/lambda/web/{a.project}-{v}", a.hours, '{ $.type = "platform.initReport" }'):
            met = m.get("record", {}).get("metrics", {})
            if m.get("record", {}).get("status") == "success" and "totalDurationMs" in met:
                dur.append(met["totalDurationMs"])
                cpu.append(met.get("totalCpuTimeMs", 0))
                mem.append(met.get("maxMemoryUsageMb", 0))
        print(f"{v:8s} wall {stats(dur)}")
        print(f"{'':8s} cpu  {stats(cpu)}")
        print(f"{'':8s} mem  {stats(mem)} (MB)\n")


def cmd_idle(a):
    print("idle time before spin-down: last request on an environment -> platform.spinDownStart, in s\n")
    for v in VARIANTS:
        last_req, down = {}, {}
        for e, m in events(f"/aws/lambda/web/{a.project}-{v}", a.hours,
                           '{ ($.type = "platform.requestComplete") || ($.type = "platform.spinDownStart") }'):
            s = e["logStreamName"]
            if m["type"] == "platform.requestComplete":
                last_req[s] = max(last_req.get(s, 0), e["timestamp"])
            else:
                down[s] = e["timestamp"]
        idle = [(down[s] - last_req[s]) / 1000 for s in down if s in last_req]
        print(f"{v:8s} {stats(idle)}")


def cmd_edge(a):
    """The edge function logs to /aws/lambda/us-east-1.<name> in the Region that ran it."""
    import re
    group = f"/aws/lambda/us-east-1.{a.project}-edge-auth"
    cmd = [AWS, "logs", "filter-log-events", "--region", REGION, "--log-group-name", group,
           "--start-time", str(int((WINDOW["since"] or time.time() - a.hours * 3600) * 1000)),
           "--filter-pattern", "REPORT", "--output", "json"]
    if WINDOW["until"]:
        cmd += ["--end-time", str(int(WINDOW["until"] * 1000))]
    lines = [e["message"] for e in json.loads(subprocess.check_output(cmd) or b"{}").get("events", [])]
    dur = lambda l: float(re.search(r"\tDuration: ([\d.]+) ms", l).group(1))
    cold = [l for l in lines if "Init Duration" in l]
    warm = [dur(l) for l in lines if "Init Duration" not in l]
    print(f"Lambda@Edge ({REGION}): {len(lines)} invocations, {len(cold)} cold\n")
    print(f"init duration        {stats([float(re.search(r'Init Duration: ([\d.]+)', l).group(1)) for l in cold])}")
    print(f"first invocation     {stats([dur(l) for l in cold])}")
    print(f"warm invocation      {stats(warm)}")


def cmd_dump(a):
    recs = load_probes(a.project, a.hours)
    with open("probes.jsonl", "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    print(f"wrote {len(recs)} records to probes.jsonl")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["probes", "init", "idle", "edge", "dump"])
    ap.add_argument("--project", default="wf-coldstart")
    ap.add_argument("--hours", type=float, default=24)
    ap.add_argument("--since", type=float, help="epoch seconds; overrides --hours")
    ap.add_argument("--until", type=float, help="epoch seconds")
    a = ap.parse_args()
    WINDOW.update(since=a.since, until=a.until)
    {"probes": cmd_probes, "init": cmd_init, "idle": cmd_idle, "edge": cmd_edge, "dump": cmd_dump}[a.command](a)


if __name__ == "__main__":
    main()
