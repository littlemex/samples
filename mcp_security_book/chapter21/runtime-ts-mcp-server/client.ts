#!/usr/bin/env node
/**
 * SigV4認証を使用するMCP Protocol Debug Client (TypeScript版)
 * 
 * Amazon Bedrock AgentCore Runtime に SigV4 認証でアクセスします。
 * EC2インスタンスのIAMロールを使用して認証を行います。
 * --local オプションで localhost:8000/mcp にも接続可能です。
 */

import { Command } from 'commander';
import { SignatureV4 } from '@aws-sdk/signature-v4';
import { Sha256 } from '@aws-crypto/sha256-js';
import { defaultProvider } from '@aws-sdk/credential-provider-node';
import { STSClient, GetCallerIdentityCommand } from '@aws-sdk/client-sts';
import { SSMClient, GetParameterCommand } from '@aws-sdk/client-ssm';
import type { HttpRequest } from '@aws-sdk/types';
// Node.js 18+ の標準 fetch を使用（node-fetch は削除）
import axios from 'axios';
import type { AxiosResponse } from 'axios';

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
    }
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

class MCPClient {
    private url: string;
    private useSigV4: boolean;
    private sigv4?: SignatureV4;

    constructor(url: string, region: string = 'us-east-1', useSigV4: boolean = true) {
        this.url = url;
        this.useSigV4 = useSigV4;

        if (useSigV4) {
            log.debug(`Initializing SigV4 client for region: ${region}`);
            this.sigv4 = new SignatureV4({
                service: 'bedrock-agentcore',
                region: region,
                credentials: defaultProvider(),
                sha256: Sha256,
                // Python版と同じ署名方式にするため、x-amz-content-sha256ヘッダーを除外
                applyChecksum: false,
            });
            log.debug('SigV4 authentication configured');
        } else {
            log.debug('Local client mode - no authentication');
        }
    }

    async sendRequest(payload: MCPRequest): Promise<MCPResponse> {
        log.debug(`Sending request: ${payload.method} (ID: ${payload.id})`);

        // Python版と同じJSONシリアライゼーション（スペースあり）
        // Pythonのjson.dumps()と同じ形式で出力
        const data = JSON.stringify(payload).replace(/,/g, ', ').replace(/:/g, ': ');
        log.debug(`Request payload size: ${data.length} bytes`);

        if (this.useSigV4 && this.sigv4) {
            // SigV4認証を使用する場合
            log.debug('Using SigV4 authentication');

            const url = new URL(this.url);

            // AWS SDK v3の標準的なリクエスト形式で作成
            // リクエストボディをUint8Arrayに変換（Python版と同じ）
            const bodyBytes = new TextEncoder().encode(data);

            const request: HttpRequest = {
                method: 'POST',
                hostname: url.hostname,
                path: url.pathname + url.search,
                protocol: url.protocol,
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json, text/event-stream',
                    'Host': url.hostname,
                },
                body: bodyBytes,
            };

            log.debug('Request before signing:', {
                method: request.method,
                hostname: request.hostname,
                path: request.path,
                headers: request.headers,
                bodyLength: bodyBytes.length,
                bodyString: data
            });

            // Python版との比較のためにリクエストボディを表示
            log.debug('Request body (exact):', JSON.stringify(data));
            log.debug('Request body (bytes):', Array.from(bodyBytes).slice(0, 50));
            log.debug('Request body content:', data);
            log.debug('Request body size:', data.length, 'chars');

            try {
                // SigV4署名を追加
                // AWS SDKのデバッグログを有効化
                if (debugMode) {
                    process.env.AWS_SDK_JS_LOG = 'debug';
                }

                const signedRequest = await this.sigv4.sign(request);
                log.debug('SigV4 signature added to request');
                log.debug('Signed headers:', signedRequest.headers);

                // 署名されたヘッダーのAuthorizationを確認
                if (signedRequest.headers.authorization) {
                    log.debug('Authorization header:', signedRequest.headers.authorization);
                    // SignedHeadersを確認
                    const authMatch = signedRequest.headers.authorization.match(/SignedHeaders=([^,]+)/);
                    if (authMatch) {
                        log.debug('SignedHeaders:', authMatch[1]);
                    }
                }

                // リクエストボディのハッシュを確認
                if (signedRequest.headers['x-amz-content-sha256']) {
                    log.debug('Content SHA256:', signedRequest.headers['x-amz-content-sha256']);
                }

                // 署名されたヘッダーを使用してaxiosリクエストを実行
                log.debug(`Sending POST request to: ${this.url}`);

                // 署名されたヘッダーをコピーし、必要なヘッダーを確実に設定
                const requestHeaders = {
                    ...signedRequest.headers,
                };

                log.debug('Final request headers:', requestHeaders);
                log.debug('Signed request body type:', typeof signedRequest.body);
                log.debug('Signed request body length:', signedRequest.body ? signedRequest.body.length : 0);

                // fetchを使用して、署名されたリクエストをそのまま送信
                // 署名されたボディを使用（正確なバイト配列で送信）
                log.debug('Sending fetch request with signed body');
                log.debug('Signed body type:', typeof signedRequest.body);
                log.debug('Signed body instanceof Uint8Array:', signedRequest.body instanceof Uint8Array);

                // axiosを使用して、署名されたリクエストを送信
                // Python版のhttpxと同様の動作を再現
                // Uint8ArrayをBufferに変換（axiosが要求する形式）
                const requestBody = signedRequest.body instanceof Uint8Array
                    ? Buffer.from(signedRequest.body)
                    : signedRequest.body;

                const response = await axios({
                    method: 'POST',
                    url: this.url,
                    headers: requestHeaders,
                    data: requestBody,
                    timeout: 30000,
                    // リクエストの変換を無効化
                    transformRequest: [],
                    transformResponse: [],
                    // レスポンスのバリデーションを無効化
                    validateStatus: () => true,
                });

                log.debug(`Response status: ${response.status}`);
                log.debug(`Response headers:`, response.headers);

                const responseText = typeof response.data === 'string' ? response.data : JSON.stringify(response.data);

                if (response.status === 200) {
                    const responseData = typeof response.data === 'object' ? response.data : JSON.parse(responseText);
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
                'Accept': 'application/json, text/event-stream',
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

        // 初期化リクエスト（Python版と同じ形式、キーの順序を統一）
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
            // Python版のデバッグ情報を追加
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
                data: error.response?.data
            });

            if (error.response?.status === 403) {
                console.log('\n🔍 403 Forbidden エラーの可能性:');
                console.log('1. IAMロールの権限が不足している');
                console.log('2. SigV4署名が正しくない');
                console.log('3. Agent ARNが無効または期限切れ');
                console.log('4. リージョンが間違っている');
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
        .name('sigv4-mcp-client')
        .description('MCP Protocol Debug Client (TypeScript)')
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
                new GetParameterCommand({ Name: '/mcp_server/runtime/agent_arn' })
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
if (require.main === module) {
    main().catch((error) => {
        console.error('Unhandled error:', error);
        process.exit(1);
    });
}