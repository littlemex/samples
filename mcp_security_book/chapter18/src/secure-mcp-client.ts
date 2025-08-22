import { ClientHashMonitor, ToolDefinition } from './client-hash-monitor.js';
import { EventSource } from 'eventsource';

/**
 * MCP リクエスト/レスポンスの型定義
 */
interface MCPRequest {
  jsonrpc: string;
  method: string;
  params?: Record<string, unknown>;
  id: string | number;
}

interface MCPResponse {
  jsonrpc: string;
  result?: unknown;
  error?: {
    code: number;
    message: string;
    data?: unknown;
  };
  id: string | number;
}

interface ToolsListResponse {
  tools: Array<{
    name: string;
    title?: string;
    description: string;
    inputSchema?: Record<string, unknown>;
  }>;
}

interface CallToolResponse {
  content: Array<{
    type: string;
    text?: string;
  }>;
  _meta?: Record<string, unknown>;
}

/**
 * セキュリティ強化された MCP Client
 * 全ての Tool 呼び出し前にハッシュ検証を実行
 * listChanged 通知を受信してリアルタイムでセキュリティ検証を実行
 */
export class SecureMCPClient {
  private hashMonitor: ClientHashMonitor;
  private serverUrl: string;
  private sessionId: string | null = null;
  private isInitialized = false;
  private eventSource: EventSource | null = null;
  private notificationHandlers: Map<string, (data: unknown) => void> = new Map();

  constructor(serverUrl: string) {
    this.serverUrl = serverUrl;
    this.hashMonitor = new ClientHashMonitor();
  }

  /**
   * MCP Server に HTTP リクエストを送信
   * @param request リクエストオブジェクト
   * @returns レスポンスオブジェクト
   */
  private async sendRequest(request: MCPRequest): Promise<MCPResponse> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      Accept: 'application/json, text/event-stream',
    };

    if (this.sessionId) {
      headers['mcp-session-id'] = this.sessionId;
    }

    const response = await fetch(`${this.serverUrl}/mcp`, {
      method: 'POST',
      headers,
      body: JSON.stringify(request),
    });

    // セッション ID を取得
    const newSessionId = response.headers.get('mcp-session-id');
    if (newSessionId) {
      this.sessionId = newSessionId;
    }

    const data = await response.json();
    return data as MCPResponse;
  }

  /**
   * Client を初期化し、ベースラインハッシュを取得
   */
  async initialize(): Promise<void> {
    console.log('\n=== Secure MCP Client 初期化開始 ===');

    // Initialize セッション
    const initRequest: MCPRequest = {
      jsonrpc: '2.0',
      method: 'initialize',
      params: {
        protocolVersion: '2025-06-18',
        capabilities: {},
        clientInfo: {
          name: 'secure-mcp-client',
          version: '1.0.0',
        },
      },
      id: 1,
    };

    const initResponse = await this.sendRequest(initRequest);
    if (initResponse.error) {
      throw new Error(`初期化エラー: ${initResponse.error.message}`);
    }

    console.log('✅ MCP セッション初期化完了');

    // Tool リストを取得してベースラインを記録
    const tools = await this.listTools();
    await this.hashMonitor.captureBaseline(tools);

    // SSE 接続を開始してリアルタイム通知を受信
    await this.startNotificationListener();

    this.isInitialized = true;
    console.log('✅ Secure MCP Client 初期化完了');
    console.log('=== 初期化完了 ===\n');
  }

  /**
   * Tool リストを取得
   * @returns Tool 定義の配列
   */
  async listTools(): Promise<ToolDefinition[]> {
    const request: MCPRequest = {
      jsonrpc: '2.0',
      method: 'tools/list',
      id: Date.now(),
    };

    const response = await this.sendRequest(request);
    if (response.error) {
      throw new Error(`Tool リスト取得エラー: ${response.error.message}`);
    }

    const result = response.result as ToolsListResponse;
    return result.tools.map((tool) => ({
      name: tool.name,
      title: tool.title,
      description: tool.description,
      inputSchema: tool.inputSchema,
    }));
  }

  /**
   * Tool を呼び出す（セキュリティ検証付き）
   * @param toolName Tool 名
   * @param args Tool の引数
   * @returns Tool の実行結果
   */
  async callTool(toolName: string, args: Record<string, unknown>): Promise<CallToolResponse> {
    if (!this.isInitialized) {
      throw new Error('Client が初期化されていません。initialize() を先に呼び出してください。');
    }

    // Tool 呼び出し前の必須検証
    console.log(`\n=== Tool ${toolName} 呼び出し前セキュリティチェック ===`);

    // 最新の Tool リストを取得
    const currentTools = await this.listTools();

    // Client 側独立ハッシュ検証
    const isValid = await this.hashMonitor.validateBeforeToolCall(currentTools, toolName);

    if (!isValid) {
      const error = `セキュリティ検証失敗: Tool ${toolName} の使用を拒否しました`;
      console.error(`❌ ${error}`);
      throw new Error(error);
    }

    console.log(`✅ Tool ${toolName} のセキュリティ検証完了`);
    console.log('=== セキュリティチェック完了 ===\n');

    // Tool を実行
    const request: MCPRequest = {
      jsonrpc: '2.0',
      method: 'tools/call',
      params: {
        name: toolName,
        arguments: args,
      },
      id: Date.now(),
    };

    const response = await this.sendRequest(request);
    if (response.error) {
      throw new Error(`Tool 実行エラー: ${response.error.message}`);
    }

    const result = response.result as CallToolResponse;

    // Server から返された _meta 情報をログ出力（参考情報として）
    if (result._meta) {
      console.log('\n--- Server からの _meta 情報（参考） ---');
      console.log(JSON.stringify(result._meta, null, 2));
      console.log('注意: セキュリティ検証は Client 側の独立計算に基づいています');
      console.log('--- _meta 情報終了 ---\n');
    }

    return result;
  }

  /**
   * 全 Tool の現在状態を検証
   * @returns 検証結果
   */
  async validateAllTools(): Promise<
    {
      toolName: string;
      isValid: boolean;
      currentHash: string;
      baselineHash?: string;
    }[]
  > {
    if (!this.isInitialized) {
      throw new Error('Client が初期化されていません。initialize() を先に呼び出してください。');
    }

    const currentTools = await this.listTools();
    return await this.hashMonitor.validateAllTools(currentTools);
  }

  /**
   * ベースラインハッシュの一覧を表示
   */
  displayBaseline(): void {
    this.hashMonitor.displayBaseline();
  }

  /**
   * SSE 接続を開始してリアルタイム通知を受信
   */
  private async startNotificationListener(): Promise<void> {
    if (!this.sessionId) {
      throw new Error('セッション ID が設定されていません');
    }

    console.log('\n=== SSE 通知リスナー開始 ===');

    // listChanged 通知ハンドラーを登録
    this.registerNotificationHandler('notifications/tools/list_changed', async (data) => {
      await this.handleListChangedNotification(data);
    });

    // SSE 接続を開始
    const sseUrl = `${this.serverUrl}/mcp?mcp-session-id=${this.sessionId}&mcp-protocol-version=2025-06-18`;
    this.eventSource = new EventSource(sseUrl);

    this.eventSource.onopen = (): void => {
      console.log('✅ SSE 接続確立完了');
    };

    this.eventSource.onmessage = (event): void => {
      try {
        const notification = JSON.parse(event.data);
        this.handleNotification(notification);
      } catch (error) {
        console.error('通知解析エラー:', error);
      }
    };

    this.eventSource.onerror = (error): void => {
      console.error('SSE 接続エラー:', error);
    };

    console.log('✅ SSE 通知リスナー設定完了');
    console.log('=== 通知リスナー開始完了 ===\n');
  }

  /**
   * 通知ハンドラーを登録
   * @param method 通知メソッド名
   * @param handler ハンドラー関数
   */
  private registerNotificationHandler(method: string, handler: (data: unknown) => void): void {
    this.notificationHandlers.set(method, handler);
    console.log(`通知ハンドラー登録: ${method}`);
  }

  /**
   * 受信した通知を処理
   * @param notification 通知オブジェクト
   */
  private handleNotification(notification: unknown): void {
    const notif = notification as { method?: string; params?: unknown };
    if (notif.method) {
      const handler = this.notificationHandlers.get(notif.method);
      if (handler) {
        console.log(`\n🔔 通知受信: ${notif.method}`);
        handler(notif.params || {});
      } else {
        console.log(`未処理の通知: ${notif.method}`);
      }
    }
  }

  /**
   * listChanged 通知を処理してセキュリティ検証を実行
   * @param data 通知データ
   */
  private async handleListChangedNotification(data: unknown): Promise<void> {
    console.log('\n🚨 === Tool 定義変更通知受信 ===');
    console.log('通知データ:', JSON.stringify(data, null, 2));

    try {
      // 最新の Tool リストを取得
      console.log('最新の Tool リストを取得中...');
      const currentTools = await this.listTools();

      // 全 Tool のセキュリティ検証を実行
      console.log('セキュリティ検証を実行中...');
      const validationResults = await this.hashMonitor.validateAllTools(currentTools);

      // 検証結果を分析
      const compromisedTools = validationResults.filter((result) => !result.isValid);

      if (compromisedTools.length > 0) {
        console.error('\n🚨 セキュリティアラート: Rug Pull 攻撃を検出しました！');
        console.error(`変更された Tool 数: ${compromisedTools.length}`);

        compromisedTools.forEach((tool) => {
          console.error(`❌ Tool ${tool.toolName}:`);
          console.error(`  期待値: ${tool.baselineHash}`);
          console.error(`  現在値: ${tool.currentHash}`);
        });

        console.error(
          '\n⚠️  これらの Tool の使用は危険です。攻撃者によって定義が変更された可能性があります。'
        );
      } else {
        console.log('\n✅ セキュリティ検証完了: 全ての Tool が安全です');
      }
    } catch (error) {
      console.error('listChanged 通知処理エラー:', error);
    }

    console.log('=== Tool 定義変更通知処理完了 ===\n');
  }

  /**
   * セッションを終了
   */
  async close(): Promise<void> {
    // SSE 接続を終了
    if (this.eventSource) {
      console.log('SSE 接続を終了中...');
      this.eventSource.close();
      this.eventSource = null;
    }

    if (this.sessionId) {
      console.log('\n=== MCP セッション終了 ===');

      // セッション終了リクエスト
      const headers: Record<string, string> = {
        'mcp-session-id': this.sessionId,
      };

      try {
        await fetch(`${this.serverUrl}/mcp`, {
          method: 'DELETE',
          headers,
        });

        console.log('✅ セッション終了完了');
      } catch (error) {
        console.error('セッション終了エラー:', error);
      }

      this.sessionId = null;
      this.isInitialized = false;
    }
  }

  /**
   * 現在のセッション ID を取得
   * @returns セッション ID
   */
  getSessionId(): string | null {
    return this.sessionId;
  }

  /**
   * Client が初期化済みかどうかを確認
   * @returns 初期化済みの場合 true
   */
  isReady(): boolean {
    return this.isInitialized;
  }
}
