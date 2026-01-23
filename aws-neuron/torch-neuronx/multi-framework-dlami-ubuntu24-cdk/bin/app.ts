#!/usr/bin/env node
import 'source-map-support/register';
import * as cdk from 'aws-cdk-lib';
import { TorchNeuronStack } from '../lib/torch-neuron-stack';

const app = new cdk.App();

const stackName = app.node.tryGetContext('stackName') || 'TorchNeuron-CDK';
const instanceType = app.node.tryGetContext('instanceType') || 'trn2.3xlarge';
const useCapacityBlock = app.node.tryGetContext('useCapacityBlock') === 'true';
const capacityReservationId = app.node.tryGetContext('capacityReservationId') || '';
const subnetId = app.node.tryGetContext('subnetId') || '';
const volumeSize = parseInt(app.node.tryGetContext('volumeSize') || '500');

new TorchNeuronStack(app, stackName, {
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: process.env.CDK_DEFAULT_REGION || 'sa-east-1',
  },
  instanceType,
  useCapacityBlock,
  capacityReservationId,
  subnetId,
  volumeSize,
});
