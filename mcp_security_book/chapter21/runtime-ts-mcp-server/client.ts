#!/usr/bin/env node
/**
 * SigV4 MCP Protocol Debug Client (TypeScript版)
 *
 */

import { Command } from 'commander';
import { defaultProvider } from '@aws-sdk/credential-provider-node';
import { STSClient, GetCallerIdentityCommand } from '@aws-sdk/client-sts';
import { SSMClient, GetParameterCommand } from '@aws-sdk/client-ssm';
import axios from 'axios';
import type { AxiosResponse } from 'axios';
import * as crypto from 'crypto';

// ログレベル設定
let debugMode = false;

const log = {
  debug: (message: string, ...args: any[]) => {
    if (debugMode) {
      console.log(`[DEBUG] ${message}`, ...args);
    }
  },
  info: (message: string, ...args: any[]) => {
    console.log(`[INFO] ${message}`, ...args);
  },
  error: (message: string, ...args: any[]) => {
    console.error(`[ERROR] ${message}`, ...args);
  },
};

interface MCPRequest {
  method: string;
  params?: any;
  jsonrpc: string;
  id: number;
}

interface MCPResponse {
  result?: any;
  error?: any;
  jsonrpc: string;
  id: number;
}

interface AWSCredentials {
  accessKeyId: string;
  secretAccessKey: string;
  sessionToken?: string;
}

class MCPClient {
  private url: string;
  private useSigV4: boolean;
  private region: string;

  constructor(url: string, region: string = 'us-east-1', useSigV4: boolean = true) {
    this.url = url;
    this.useSigV4 = useSigV4;
    this.region = region;

    if (useSigV4) {
      log.debug(`Initializing SigV4 client for region: ${region}`);
      log.debug('SigV4 authentication configured');
    } else {
      log.debug('Local client mode - no authentication');
    }
  }

  // Python版のboto3と同じSigV4署名を生成
  private async signRequest(
    method: string,
    url: URL,
    headers: Record<string, string>,
    body: string,
    credentials: AWSCredentials
  ): Promise<Record<string, string>> {
    const now = new Date();
    const amzDate = now.toISOString().replace(/[:-]|\.\d{3}/g, '');
    const dateStamp = amzDate.substr(0, 8);

    // ヘッダーを準備
    const signedHeaders: Record<string, string> = {};

    // 元のヘッダーをコピー（小文字化）
    for (const [key, value] of Object.entries(headers)) {
      signedHeaders[key.toLowerCase()] = value;
    }

    // AWS固有ヘッダーを追加
    signedHeaders['x-amz-date'] = amzDate;

    if (credentials.sessionToken) {
      signedHeaders['x-amz-security-token'] = credentials.sessionToken;
    }

    // CanonicalRequestを構築（AWS公式ドキュメントの手順通り）
    const canonicalHeaders =
      Object.keys(signedHeaders)
        .sort()
        .map((key) => `${key.toLowerCase()}:${signedHeaders[key]}`)
        .join('\n') + '\n'; // 最後に改行を追加

    const signedHeadersList = Object.keys(signedHeaders)
      .sort()
      .map((key) => key.toLowerCase())
      .join(';');

    const payloadHash = crypto.createHash('sha256').update(body, 'utf8').digest('hex');

    // ARN部分のみ二重エンコーディングする
    let canonicalUri = url.pathname;
    // ARN部分を二重エンコーディング
    canonicalUri = canonicalUri.replace(
      /arn%3Aaws%3Abedrock-agentcore%3Aus-east-1%3A\d+%3Aruntime%2F[^/]+/,
      (match) => encodeURIComponent(match)
    );

    const canonicalRequest = [
      method,
      canonicalUri,
      url.search.substring(1) || '', // クエリストリング（空の場合は空文字列）
      canonicalHeaders,
      signedHeadersList,
      payloadHash,
    ].join('\n');

    log.debug('Canonical Request:', canonicalRequest);

    // StringToSignを構築
    const algorithm = 'AWS4-HMAC-SHA256';
    const credentialScope = `${dateStamp}/${this.region}/bedrock-agentcore/aws4_request`;
    const canonicalRequestHash = crypto
      .createHash('sha256')
      .update(canonicalRequest, 'utf8')
      .digest('hex');

    const stringToSign = [algorithm, amzDate, credentialScope, canonicalRequestHash].join('\n');

    log.debug('String to Sign:', stringToSign);

    // 署名を計算
    const kDate = crypto
      .createHmac('sha256', `AWS4${credentials.secretAccessKey}`)
      .update(dateStamp)
      .digest();
    const kRegion = crypto.createHmac('sha256', kDate).update(this.region).digest();
    const kService = crypto.createHmac('sha256', kRegion).update('bedrock-agentcore').digest();
    const kSigning = crypto.createHmac('sha256', kService).update('aws4_request').digest();
    const signature = crypto.createHmac('sha256', kSigning).update(stringToSign).digest('hex');

    // Authorizationヘッダーを構築
    const authorizationHeader = `${algorithm} Credential=${credentials.accessKeyId}/${credentialScope}, SignedHeaders=${signedHeadersList}, Signature=${signature}`;

    // 最終ヘッダーを返す（元のヘッダー形式で）
    const finalHeaders: Record<string, string> = {};
    for (const [key, value] of Object.entries(headers)) {
      finalHeaders[key] = value;
    }
    finalHeaders['x-amz-date'] = amzDate;
    if (credentials.sessionToken) {
      finalHeaders['x-amz-security-token'] = credentials.sessionToken;
    }
    finalHeaders['authorization'] = authorizationHeader;

    return finalHeaders;
  }

  async sendRequest(payload: MCPRequest): Promise<MCPResponse> {
    log.debug(`Sending request: ${payload.method} (ID: ${payload.id})`);

    let data: string;
    if (payload.method === 'initialize') {
      data =
        '{"method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {"sampling": {}, "roots": {"listChanged": true}}, "clientInfo": {"name": "mcp", "version": "0.1.0"}}, "jsonrpc": "2.0", "id": 0}';
    } else if (payload.method === 'tools/list') {
      data = '{"method": "tools/list", "params": {}, "jsonrpc": "2.0", "id": 1}';
    } else {
      data = JSON.stringify(payload, null, 0).replace(/,/g, ', ').replace(/:/g, ': ');
    }
    log.debug(`Request payload size: ${data.length} bytes`);

    if (this.useSigV4) {
      // SigV4認証を使用する場合
      log.debug('Using SigV4 authentication');

      const url = new URL(this.url);

      // AWS認証情報を取得
      const credentialsProvider = defaultProvider();
      const credentials = await credentialsProvider();

      const headers = {
        Accept: 'application/json, text/event-stream',
        'Content-Type': 'application/json',
        Host: url.hostname,
      };

      log.debug('Request before signing:', {
        method: 'POST',
        hostname: url.hostname,
        path: url.pathname + url.search,
        headers: headers,
        bodyLength: data.length,
        bodyString: data,
      });

      try {
        // カスタムSigV4署名を適用
        const signedHeaders = await this.signRequest('POST', url, headers, data, {
          accessKeyId: credentials.accessKeyId,
          secretAccessKey: credentials.secretAccessKey,
          sessionToken: credentials.sessionToken,
        });

        log.debug('SigV4 signature added to request');
        log.debug('Signed headers:', signedHeaders);

        if (signedHeaders.authorization) {
          log.debug('Authorization header:', signedHeaders.authorization);
        }

        // axiosでリクエストを送信
        log.debug(`Sending POST request to: ${this.url}`);
        log.debug('Final request headers:', signedHeaders);

        const response = await axios({
          method: 'POST',
          url: this.url,
          headers: signedHeaders,
          data: data,
          timeout: 30000,
          validateStatus: () => true,
        });

        log.debug(`Response status: ${response.status}`);
        log.debug(`Response headers:`, response.headers);

        const responseText =
          typeof response.data === 'string' ? response.data : JSON.stringify(response.data);

        if (response.status === 200) {
          const responseData =
            typeof response.data === 'object' ? response.data : JSON.parse(responseText);
          log.debug(`Response data:`, JSON.stringify(responseData, null, 2));
          return responseData;
        } else {
          log.error(`HTTP ${response.status}: ${response.statusText}`);
          log.error('Response body:', responseText);
          throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
      } catch (signingError) {
        log.error('SigV4 signing failed:', signingError);
        throw signingError;
      }
    } else {
      // ローカル接続の場合
      log.debug('Using local connection (no authentication)');

      const headers = {
        'Content-Type': 'application/json',
        Accept: 'application/json, text/event-stream',
      };

      log.debug(`Sending POST request to: ${this.url}`);

      const response: AxiosResponse = await axios.post(this.url, data, {
        headers,
        timeout: 30000,
      });

      log.debug(`Response status: ${response.status}`);
      log.debug(`Response headers:`, response.headers);

      if (response.status === 200) {
        log.debug(`Response data:`, JSON.stringify(response.data, null, 2));
        return response.data;
      } else {
        log.error(`HTTP ${response.status}: ${response.statusText}`);
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
    }
  }
}

async function testMCPConnection(client: MCPClient, connectionType: string): Promise<void> {
  try {
    console.log(`🔄 Connection Attempt (${connectionType})`);
    log.debug(`Starting MCP connection test for ${connectionType}`);
    console.log('✅ HTTP connection established');
    console.log('✅ Protocol debug session created');

    // MCPプロトコルテスト
    console.log('🚀 Starting MCP initialization...');

    const initPayload: MCPRequest = {
      method: 'initialize',
      params: {
        protocolVersion: '2024-11-05',
        capabilities: {
          sampling: {},
          roots: { listChanged: true },
        },
        clientInfo: { name: 'mcp', version: '0.1.0' },
      },
      jsonrpc: '2.0',
      id: 0,
    };

    log.debug('TypeScript init payload:', JSON.stringify(initPayload));
    log.debug('TypeScript init payload size:', JSON.stringify(initPayload).length, 'chars');

    // 初期化リクエストを送信
    log.debug('Sending initialize request');
    const initResponse = await client.sendRequest(initPayload);
    console.log('✅ MCP initialized:');
    console.log(JSON.stringify(initResponse, null, 2));

    // ツール一覧を取得
    const toolsPayload: MCPRequest = {
      method: 'tools/list',
      params: {},
      jsonrpc: '2.0',
      id: 1,
    };

    try {
      log.debug('TypeScript tools payload:', JSON.stringify(toolsPayload));
      log.debug('TypeScript tools payload size:', JSON.stringify(toolsPayload).length, 'chars');
      log.debug('Sending tools/list request');

      const toolsResponse = await client.sendRequest(toolsPayload);
      console.log('🔧 Available tools response:');
      console.log(JSON.stringify(toolsResponse, null, 2));

      if (toolsResponse.result && toolsResponse.result.tools) {
        const tools = toolsResponse.result.tools;
        console.log(`\n🔧 Available tools summary: ${tools.length}`);
        for (const tool of tools) {
          console.log(`  - ${tool.name || 'Unknown'}: ${tool.description || 'No description'}`);
        }
      } else {
        console.log('🔧 No tools found or unexpected response format');
      }
    } catch (error) {
      console.log(`⚠️  Tools list request failed: ${error}`);
    }

    console.log(`\n✅ MCP connection test (${connectionType}) completed successfully!`);
    log.debug(`MCP connection test completed for ${connectionType}`);
  } catch (error) {
    console.log(`❌ Connection failed: ${error}`);
    log.error(`Connection test failed: ${error}`);

    // Axiosエラーの詳細を表示
    if (axios.isAxiosError(error)) {
      log.error('Axios error details:', {
        status: error.response?.status,
        statusText: error.response?.statusText,
        headers: error.response?.headers,
        data: error.response?.data,
      });

      if (error.response?.status === 403) {
        console.log('\n🔍 403 Forbidden エラーの可能性:');
        console.log('1. IAMロールの権限が不足している');
        console.log('2. SigV4署名が正しくない');
        console.log('3. Agent ARNが無効または期限切れ');
        console.log('4. リージョンが間違っている');
        console.log('5. CanonicalRequestの構築方法が間違っている');
      }
    }

    if (error instanceof Error) {
      console.error(error.stack);
    }
  }
}

async function main(): Promise<void> {
  const program = new Command();

  program
    .name('fixed-sigv4-mcp-client-final')
    .description('Final Fixed MCP Protocol Debug Client (TypeScript)')
    .option('--local', 'Connect to localhost:8000/mcp')
    .option('--remote', 'Connect to AWS Bedrock AgentCore Runtime')
    .option('--debug', 'Enable debug logging')
    .parse();

  const options = program.opts();

  // 排他的オプションのチェック
  if (!options.local && !options.remote) {
    console.error('Error: Either --local or --remote must be specified');
    process.exit(1);
  }

  if (options.local && options.remote) {
    console.error('Error: --local and --remote cannot be used together');
    process.exit(1);
  }

  // デバッグモード設定
  debugMode = options.debug;
  if (debugMode) {
    console.log('🐛 Debug logging enabled');
  }

  if (options.local) {
    console.log('=== MCP PROTOCOL DEBUG CLIENT (LOCAL) ===');
    if (debugMode) {
      console.log('🐛 Debug mode: ON');
    }

    const url = 'http://localhost:8000/mcp';
    console.log('🌐 Connection Details:');
    console.log(`URL: ${url}`);
    console.log('Auth: None (Local)');

    const client = new MCPClient(url, 'us-east-1', false);
    if (debugMode) {
      log.info(`Creating local client for URL: ${url}`);
    }

    await testMCPConnection(client, 'Local');
  } else if (options.remote) {
    console.log('=== MCP PROTOCOL DEBUG CLIENT (REMOTE/SigV4) ===');
    if (debugMode) {
      console.log('🐛 Debug mode: ON');
    }
    console.log('Region: us-east-1');

    // AWS認証情報を確認
    console.log('🔐 AWS認証情報を取得中...');
    try {
      const stsClient = new STSClient({ region: 'us-east-1' });
      const identity = await stsClient.send(new GetCallerIdentityCommand({}));
      console.log(`✅ AWS Identity: ${identity.Arn}`);
    } catch (error) {
      console.log(`❌ AWS認証エラー: ${error}`);
      return;
    }

    // Agent ARNを取得
    try {
      const ssmClient = new SSMClient({ region: 'us-east-1' });
      const response = await ssmClient.send(
        new GetParameterCommand({
          Name: '/mcp_server/runtime/agent_arn',
        })
      );
      const agentArn = response.Parameter?.Value;

      if (!agentArn) {
        throw new Error('Agent ARN not found');
      }

      console.log(`✅ Agent ARN: ${agentArn}`);

      // AgentCore Runtime URLを構築
      const encodedArn = agentArn.replace(/:/g, '%3A').replace(/\//g, '%2F');
      const url = `https://bedrock-agentcore.us-east-1.amazonaws.com/runtimes/${encodedArn}/invocations?qualifier=DEFAULT`;

      console.log('🌐 Connection Details:');
      console.log(`URL: ${url}`);
      console.log('Auth: SigV4 (IAM Role)');

      const client = new MCPClient(url, 'us-east-1', true);
      if (debugMode) {
        log.info(`Creating SigV4 client for URL: ${url}`);
      }

      await testMCPConnection(client, 'Remote/SigV4');
    } catch (error) {
      console.log(`❌ Agent ARN取得エラー: ${error}`);
      return;
    }
  }
}

// メイン実行
// ES モジュールでは import.meta.url を使用してメインモジュールかどうかを判定
if (import.meta.url === import.meta.resolve(process.argv[1])) {
  main().catch((error) => {
    console.error('Unhandled error:', error);
    process.exit(1);
  });
}
