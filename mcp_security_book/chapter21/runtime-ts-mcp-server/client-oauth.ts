#!/usr/bin/env node
/**
 * OAuth JWT 認証を使用した MCP クライアント
 * AWS Secrets Manager と Parameter Store から設定を取得
 * 
 * 注意: AWS Bedrock AgentCore Runtime の JWT Bearer Token 認証では、
 * Access トークン（token_use: "access"）を使用することが推奨されています。
 */

import * as fs from 'fs';
import * as path from 'path';
import fetch from 'node-fetch';
import { Command } from 'commander';
import { 
  SecretsManagerClient, 
  GetSecretValueCommand 
} from '@aws-sdk/client-secrets-manager';
import { 
  SSMClient, 
  GetParameterCommand 
} from '@aws-sdk/client-ssm';

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

// 現在のディレクトリを使用
const __dirname = process.cwd();

interface CognitoConfig {
  pool_id: string;
  client_id: string;
  bearer_token: string;
  access_token?: string;
  id_token?: string;
  discovery_url: string;
}

interface DeploymentConfig {
  cognito: CognitoConfig;
  agent_arn: string;
}

interface MCPRequest {
  jsonrpc: string;
  id: number;
  method: string;
  params?: any;
}

interface MCPResponse {
  jsonrpc: string;
  id: number;
  result?: any;
  error?: {
    code: number;
    message: string;
    data?: any;
  };
}

class OAuthMCPClient {
  private config: DeploymentConfig;
  private serverUrl: string;
  private region: string;

  constructor() {
    this.config = {
      cognito: {
        pool_id: '',
        client_id: '',
        bearer_token: '',
        discovery_url: ''
      },
      agent_arn: ''
    };
    this.region = process.env.AWS_REGION || 'us-east-1';
    this.serverUrl = '';
  }

  /**
   * AWS Secrets Manager から Cognito 認証情報を取得
   */
  private async getCognitoCredentials(): Promise<CognitoConfig> {
    try {
      console.log('🔐 Secrets Manager から Cognito 認証情報を取得中...');
      
      const client = new SecretsManagerClient({ region: this.region });
      const command = new GetSecretValueCommand({
        SecretId: 'mcp_server/cognito/credentials',
      });
      
      const response = await client.send(command);
      
      if (!response.SecretString) {
        throw new Error('Cognito 認証情報が見つかりません');
      }
      
      const credentials = JSON.parse(response.SecretString) as CognitoConfig;
      console.log('✅ Cognito 認証情報を取得しました');
      log.debug(`Client ID: ${credentials.client_id}`);
      log.debug(`Discovery URL: ${credentials.discovery_url}`);
      
      return credentials;
    } catch (error) {
      console.error('❌ Cognito 認証情報の取得に失敗しました:', error);
      throw error;
    }
  }

  /**
   * AWS Parameter Store からエージェント ARN を取得
   */
  private async getAgentArn(): Promise<string> {
    try {
      console.log('🔍 Parameter Store からエージェント ARN を取得中...');
      
      const client = new SSMClient({ region: this.region });
      const command = new GetParameterCommand({
        Name: '/mcp_server/runtime/agent_arn',
      });
      
      const response = await client.send(command);
      
      if (!response.Parameter?.Value) {
        throw new Error('エージェント ARN が見つかりません');
      }
      
      const agentArn = response.Parameter.Value;
      console.log('✅ エージェント ARN を取得しました');
      log.debug(`Agent ARN: ${agentArn}`);
      
      return agentArn;
    } catch (error) {
      console.error('❌ エージェント ARN の取得に失敗しました:', error);
      throw error;
    }
  }

  /**
   * クライアントを初期化
   */
  async initialize(): Promise<void> {
    try {
      // Cognito 認証情報を取得
      this.config.cognito = await this.getCognitoCredentials();
      
      // エージェント ARN を取得
      this.config.agent_arn = await this.getAgentArn();
      
      // AgentCore Runtime のエンドポイント URL を構築
      const agentArn = this.config.agent_arn;
      const encodedArn = agentArn.replace(/:/g, '%3A').replace(/\//g, '%2F');
      this.region = agentArn.split(':')[3];
      
      // URL を構築
      this.serverUrl = `https://bedrock-agentcore.${this.region}.amazonaws.com/runtimes/${encodedArn}/invocations?qualifier=DEFAULT`;
      
      console.log('🔧 OAuth MCP クライアント初期化完了');
      console.log(`📍 サーバー URL: ${this.serverUrl}`);
      console.log(`🔑 Client ID: ${this.config.cognito.client_id}`);
      console.log(`🔖 トークン種類: ${this.getTokenType()}`);
      console.log(`🎯 トークン Audience: ${this.getTokenAudience()}`);
      console.log(`⏰ トークン有効期限: ${this.getTokenExpiration()}`);
      
      log.debug('OAuth MCP クライアント初期化の詳細情報:');
      log.debug(`エージェント ARN: ${agentArn}`);
      log.debug(`リージョン: ${this.region}`);
    } catch (error) {
      console.error('❌ クライアント初期化エラー:', error);
      throw error;
    }
  }

  /**
   * JWT トークンの有効期限を取得
   */
  private getTokenExpiration(): string {
    try {
      const token = this.config.cognito.bearer_token;
      const payload = JSON.parse(Buffer.from(token.split('.')[1], 'base64').toString());
      const exp = new Date(payload.exp * 1000);
      log.debug(`トークン有効期限の詳細: ${payload.exp} (${exp.toISOString()})`);
      return exp.toLocaleString('ja-JP');
    } catch (error) {
      log.error('トークン有効期限の取得に失敗:', error);
      return '不明';
    }
  }

  /**
   * JWT トークンの種類を取得（ID トークンか Access トークンか）
   */
  private getTokenType(): string {
    try {
      const token = this.config.cognito.bearer_token;
      const payload = JSON.parse(Buffer.from(token.split('.')[1], 'base64').toString());
      log.debug(`トークンペイロード: ${JSON.stringify(payload, null, 2)}`);
      return payload.token_use || '不明';
    } catch (error) {
      log.error('トークン種類の取得に失敗:', error);
      return '不明';
    }
  }

  /**
   * JWT トークンの audience クレームを取得
   */
  private getTokenAudience(): string {
    try {
      const token = this.config.cognito.bearer_token;
      const payload = JSON.parse(Buffer.from(token.split('.')[1], 'base64').toString());
      if (typeof payload.aud === 'string') {
        log.debug(`トークン Audience (文字列): ${payload.aud}`);
        return payload.aud;
      } else if (Array.isArray(payload.aud)) {
        log.debug(`トークン Audience (配列): ${JSON.stringify(payload.aud)}`);
        return payload.aud.join(', ');
      }
      log.debug('トークンに Audience が見つかりません');
      return '不明';
    } catch (error) {
      log.error('トークン Audience の取得に失敗:', error);
      return '不明';
    }
  }

  /**
   * JWT トークンが有効かチェック
   */
  private isTokenValid(): boolean {
    try {
      const token = this.config.cognito.bearer_token;
      const payload = JSON.parse(Buffer.from(token.split('.')[1], 'base64').toString());
      const now = Math.floor(Date.now() / 1000);
      
      log.debug(`トークン検証: 現在時刻=${now}, 有効期限=${payload.exp}`);
      
      // 有効期限をチェック
      if (payload.exp <= now) {
        log.error(`トークンの有効期限が切れています: ${new Date(payload.exp * 1000).toLocaleString('ja-JP')}`);
        return false;
      }
      
      // トークンの種類をチェック（Access トークンが推奨）
      const tokenType = payload.token_use;
      if (tokenType !== 'access') {
        console.warn(`⚠️ 警告: 現在のトークンは ${tokenType} トークンです。AgentCore Runtime では Access トークンが推奨されています。`);
        log.debug(`トークン種類の警告: ${tokenType} (推奨: access)`);
      }
      
      log.debug('トークン検証: 有効なトークンです');
      return true;
    } catch (error) {
      log.error('トークン検証に失敗:', error);
      return false;
    }
  }

  /**
   * 認証付きリクエストを送信
   */
  private async makeAuthenticatedRequest(
    endpoint: string,
    mcpRequest: MCPRequest
  ): Promise<MCPResponse> {
    if (!this.isTokenValid()) {
      throw new Error('JWT トークンが無効です。有効期限が切れているか、適切なトークン種類（Access トークン）ではない可能性があります。');
    }

    const url = `${this.serverUrl}${endpoint}`;
    
    console.log(`📤 リクエスト送信: ${mcpRequest.method}`);
    console.log(`🌐 URL: ${url}`);

    // SigV4 クライアントと同じ JSON 形式を使用
    let requestBody: string;
    if (mcpRequest.method === 'initialize') {
      requestBody = '{"method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {"sampling": {}, "roots": {"listChanged": true}}, "clientInfo": {"name": "mcp", "version": "0.1.0"}}, "jsonrpc": "2.0", "id": 0}';
    } else if (mcpRequest.method === 'tools/list') {
      requestBody = '{"method": "tools/list", "params": {}, "jsonrpc": "2.0", "id": 1}';
    } else {
      requestBody = JSON.stringify(mcpRequest);
    }
    
    log.debug(`リクエスト本文: ${requestBody}`);
    log.debug(`リクエストサイズ: ${requestBody.length} バイト`);

    log.debug(`リクエストヘッダー: Authorization: Bearer ${this.config.cognito.bearer_token.substring(0, 10)}...`);
    
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${this.config.cognito.bearer_token}`,
        'Content-Type': 'application/json',
        'Accept': 'application/json, text/event-stream'
      },
      body: requestBody
    });

    console.log(`📥 レスポンス: ${response.status} ${response.statusText}`);
    log.debug(`レスポンスヘッダー: ${JSON.stringify(Object.fromEntries(response.headers.entries()), null, 2)}`);

    if (!response.ok) {
      const errorText = await response.text();
      console.error(`❌ HTTP エラー: ${response.status}`);
      console.error(`📄 エラー詳細: ${errorText}`);
      log.debug(`エラーレスポンス全文: ${errorText}`);
      
      if (response.status === 401) {
        throw new Error('認証エラー: JWT トークンが無効または期限切れです');
      }
      
      throw new Error(`HTTP ${response.status}: ${errorText}`);
    }

    const result: MCPResponse = await response.json() as MCPResponse;
    log.debug(`レスポンス本文: ${JSON.stringify(result, null, 2)}`);
    
    if (result.error) {
      console.error(`❌ MCP エラー: ${result.error.message}`);
      log.debug(`MCP エラー詳細: ${JSON.stringify(result.error, null, 2)}`);
      throw new Error(`MCP エラー [${result.error.code}]: ${result.error.message}`);
    }

    return result;
  }

  /**
   * MCP サーバー初期化
   */
  async initializeMCP(): Promise<MCPResponse> {
    console.log('\n🚀 MCP サーバーを初期化中...');
    
    const request: MCPRequest = {
      jsonrpc: '2.0',
      id: 0,
      method: 'initialize',
      params: {
        protocolVersion: '2024-11-05',
        capabilities: {
          sampling: {},
          roots: {
            listChanged: true
          }
        },
        clientInfo: {
          name: 'mcp',
          version: '0.1.0'
        }
      }
    };

    return await this.makeAuthenticatedRequest('', request);
  }

  /**
   * 利用可能なツールのリストを取得
   */
  async listTools(): Promise<MCPResponse> {
    console.log('\n🔧 利用可能なツールを取得中...');
    
    const request: MCPRequest = {
      jsonrpc: '2.0',
      id: 1,
      method: 'tools/list',
      params: {}
    };

    return await this.makeAuthenticatedRequest('', request);
  }

  /**
   * 指定されたツールを呼び出し
   */
  async callTool(toolName: string, arguments_: Record<string, any> = {}): Promise<MCPResponse> {
    console.log(`\n⚡ ツール "${toolName}" を実行中...`);
    
    const request: MCPRequest = {
      jsonrpc: '2.0',
      id: 3,
      method: 'tools/call',
      params: {
        name: toolName,
        arguments: arguments_
      }
    };

    return await this.makeAuthenticatedRequest('', request);
  }

  /**
   * リソースのリストを取得
   */
  async listResources(): Promise<MCPResponse> {
    console.log('\n📁 利用可能なリソースを取得中...');
    
    const request: MCPRequest = {
      jsonrpc: '2.0',
      id: 4,
      method: 'resources/list'
    };

    return await this.makeAuthenticatedRequest('', request);
  }

  /**
   * プロンプトのリストを取得
   */
  async listPrompts(): Promise<MCPResponse> {
    console.log('\n💬 利用可能なプロンプトを取得中...');
    
    const request: MCPRequest = {
      jsonrpc: '2.0',
      id: 5,
      method: 'prompts/list'
    };

    return await this.makeAuthenticatedRequest('', request);
  }

  /**
   * サーバー情報を表示
   */
  displayServerInfo(): void {
    console.log('\n📊 サーバー情報:');
    console.log(`  エージェント ARN: ${this.config.agent_arn}`);
    console.log(`  リージョン: ${this.region}`);
    console.log(`  サーバー URL: ${this.serverUrl}`);
    console.log(`  Cognito Client ID: ${this.config.cognito.client_id}`);
    console.log(`  Discovery URL: ${this.config.cognito.discovery_url}`);
  }
}

/**
 * メイン実行関数
 */
async function main() {
  try {
    // コマンドラインオプションを設定
    const program = new Command();
    program
      .description('OAuth JWT 認証を使用した MCP クライアント')
      .option('--debug', 'デバッグログを有効にする')
      .parse();

    const options = program.opts();
    
    // デバッグモード設定
    debugMode = options.debug;
    if (debugMode) {
      console.log('🐛 デバッグログが有効です');
    }
    
    console.log('🌟 OAuth MCP クライアント開始');
    console.log('='.repeat(50));

    // クライアントを初期化
    const client = new OAuthMCPClient();
    
    // AWS から設定を取得して初期化
    await client.initialize();
    
    // サーバー情報を表示
    client.displayServerInfo();

    // 1. MCP サーバーを初期化
    const initResult = await client.initializeMCP();
    console.log('✅ 初期化完了:', JSON.stringify(initResult.result, null, 2));

    // 2. 利用可能なツールを取得
    const toolsResult = await client.listTools();
    console.log('✅ ツールリスト:', JSON.stringify(toolsResult.result, null, 2));

    // 3. greet ツールがある場合は実行
    if (toolsResult.result?.tools?.some((tool: any) => tool.name === 'greet')) {
      const greetResult = await client.callTool('greet', { name: 'OAuth User' });
      console.log('✅ greet ツール実行結果:', JSON.stringify(greetResult.result, null, 2));
    }

    // 4. リソースリストを取得
    try {
      const resourcesResult = await client.listResources();
      console.log('✅ リソースリスト:', JSON.stringify(resourcesResult.result, null, 2));
    } catch (error) {
      console.log('ℹ️  リソースリスト取得をスキップ:', (error as Error).message);
    }

    // 5. プロンプトリストを取得
    try {
      const promptsResult = await client.listPrompts();
      console.log('✅ プロンプトリスト:', JSON.stringify(promptsResult.result, null, 2));
    } catch (error) {
      console.log('ℹ️  プロンプトリスト取得をスキップ:', (error as Error).message);
    }

    console.log('\n🎉 すべての操作が完了しました！');

  } catch (error) {
    console.error('\n❌ エラーが発生しました:');
    console.error(error);
    
    if (error instanceof Error) {
      if (error.message.includes('認証エラー') || error.message.includes('期限切れ') || error.message.includes('無効')) {
        console.log('\n💡 解決方法:');
        console.log('1. 新しい JWT トークン（Access トークン）を取得してください');
        console.log('2. deployment_config.json の bearer_token を更新してください');
        console.log('3. python deploy.py --update-token を実行してください');
        console.log('\n注意: AWS Bedrock AgentCore Runtime の JWT Bearer Token 認証では、');
        console.log('Access トークン（token_use: "access"）を使用することが推奨されています。');
      }
      
      // Audience 不一致エラーの場合
      if (error.message.includes('Claim \'aud\' value mismatch')) {
        try {
          // トークンの内容を直接解析
          const token = JSON.parse(fs.readFileSync('./deployment_config.json', 'utf-8')).cognito.bearer_token;
          const payload = JSON.parse(Buffer.from(token.split('.')[1], 'base64').toString());
          const tokenAudience = typeof payload.aud === 'string' ? payload.aud : 
                               Array.isArray(payload.aud) ? payload.aud.join(', ') : '不明';
          const clientId = JSON.parse(fs.readFileSync('./deployment_config.json', 'utf-8')).cognito.client_id;
          
          console.log('\n🔍 Audience 不一致エラーの解決方法:');
          console.log(`現在のトークンの Audience: ${tokenAudience}`);
          console.log(`設定されている Audience: ${clientId}`);
          console.log('\n以下のいずれかの方法で解決してください:');
          console.log('1. deploy.py を修正して、authorizerConfiguration の allowedAudience に正しい値を設定する');
          console.log(`   例: "allowedAudience": ["${tokenAudience}"]`);
          console.log('2. 正しい Audience を持つ新しいトークンを取得する');
        } catch (parseError) {
          console.log('\n🔍 Audience 不一致エラーが発生しました。');
          console.log('deploy.py を修正して、authorizerConfiguration の allowedAudience に正しい値を設定してください。');
        }
      }
    }
    
    process.exit(1);
  }
}

// メイン関数を実行
main();

export { OAuthMCPClient };
