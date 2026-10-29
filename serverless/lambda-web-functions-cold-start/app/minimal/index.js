// Minimal Web Function: node:http only, no dependencies.
// Every response reports when this execution environment's process started and when
// it began listening, so the prober can tell a cold request from a warm one and
// split the cold-start delay into "before our code ran" and "our own startup".
'use strict';
const moduleStartMs = Date.now();
const http = require('node:http');
const { randomUUID } = require('node:crypto');

const ENV_ID = randomUUID();
const PROCESS_START_MS = Math.round(performance.timeOrigin);
const VARIANT = process.env.VARIANT || 'minimal';
let listenMs = 0;
let served = 0;

const server = http.createServer((req, res) => {
  served += 1;
  const body = JSON.stringify({
    variant: VARIANT,
    envId: ENV_ID,
    processStartMs: PROCESS_START_MS,
    moduleStartMs,
    listenMs,
    nowMs: Date.now(),
    served,
    path: req.url,
  });
  res.writeHead(200, { 'content-type': 'application/json', 'cache-control': 'no-store' });
  res.end(body);
});

const [host, port] = (process.env.AWS_LAMBDA_HTTP_ENDPOINT || 'localhost:3000').split(':');
server.listen(Number(port), host, () => {
  listenMs = Date.now();
  console.log(JSON.stringify({ msg: 'listening', variant: VARIANT, envId: ENV_ID,
    processStartMs: PROCESS_START_MS, moduleStartMs, listenMs }));
});

process.on('SIGTERM', () => {
  console.log(JSON.stringify({ msg: 'sigterm', envId: ENV_ID, served, aliveMs: Date.now() - PROCESS_START_MS }));
  process.exit(0);
});
