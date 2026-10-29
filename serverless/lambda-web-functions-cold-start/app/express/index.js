// A typical API shape: Express plus two AWS SDK v3 clients, loaded and constructed at
// startup the way most apps do it. The response is the same shape as the minimal
// variant so the prober can compare them directly.
'use strict';
const moduleStartMs = Date.now();
const { randomUUID } = require('node:crypto');
const express = require('express');
const { DynamoDBClient } = require('@aws-sdk/client-dynamodb');
const { S3Client } = require('@aws-sdk/client-s3');

const ENV_ID = randomUUID();
const PROCESS_START_MS = Math.round(performance.timeOrigin);
const VARIANT = process.env.VARIANT || 'express';
// Constructed but never called: the point is the cost of loading and building them.
const clients = { ddb: new DynamoDBClient({}), s3: new S3Client({}) };
let listenMs = 0;
let served = 0;

const app = express();
app.disable('x-powered-by');
app.use((req, res) => {
  served += 1;
  res.set('cache-control', 'no-store').json({
    variant: VARIANT,
    envId: ENV_ID,
    processStartMs: PROCESS_START_MS,
    moduleStartMs,
    listenMs,
    nowMs: Date.now(),
    served,
    path: req.url,
    clients: Object.keys(clients),
  });
});

const [host, port] = (process.env.AWS_LAMBDA_HTTP_ENDPOINT || 'localhost:3000').split(':');
app.listen(Number(port), host, () => {
  listenMs = Date.now();
  console.log(JSON.stringify({ msg: 'listening', variant: VARIANT, envId: ENV_ID,
    processStartMs: PROCESS_START_MS, moduleStartMs, listenMs }));
});

process.on('SIGTERM', () => {
  console.log(JSON.stringify({ msg: 'sigterm', envId: ENV_ID, served, aliveMs: Date.now() - PROCESS_START_MS }));
  process.exit(0);
});
