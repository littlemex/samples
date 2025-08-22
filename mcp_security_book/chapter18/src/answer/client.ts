/**
 * typescript-sdk を使用したセキュリティ強化 MCP Client
 *
 * このクライアントは以下の機能を提供します：
 * - Tool 呼び出し前のハッシュ検証
 * - listChanged 通知のリアルタイム処理
 * - Rug Pull 攻撃の検出と防御
 */

import { Client, ClientOptions } from '@modelcontextprotocol/sdk/client/index.js';
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js';
import {
  CallToolRequest,
  CallToolResult,
  Tool,
  McpError,
  ErrorCode,
  Notification,
} from '@modelcontextprotocol/sdk/types.js';
import { ClientHashMonitor, ToolDefinition } from '../client-hash-monitor.js';

/**
 * typescript-sdk を使用したセキュリティ強化 MCP Client
 */
export class SecureMCPClientWithSDK extends Client {
  private hashMonitor: ClientHashMonitor;
  private serverUrl: string;
  private httpTransport?: StreamableHTTPClientTransport;

  constructor(
    serverUrl: string,
    clientInfo: { name: string; version: string },
    options?: ClientOptions
  ) {
    super(clientInfo, options);
    this.serverUrl = serverUrl;
    this.hashMonitor = new ClientHashMonitor();
  }

  /**
   * サーバーに接続して初期化
   */
  async initialize(): Promise<void> {
    console.log('\n=== Secure MCP Client (SDK版) 初期化開始 ===');

    // StreamableHTTPClientTransport を作成
    this.httpTransport = new StreamableHTTPClientTransport(new URL(this.serverUrl + '/mcp'));

    // 通知ハンドラーを設定
    // SDK の通知ハンドラーは現在のバージョンでは直接設定できないため、
    // connect 後に transport のイベントリスナーを使用

    // サーバーに接続
    await this.connect(this.httpTransport);

    // 通知を受信するためのイベントリスナーを設定
    // StreamableHTTPClientTransport は SSE を使用して通知を受信
    if (this.httpTransport) {
      // 通知ハンドラーを内部的に設定
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (this as any).onNotification = async (notification: Notification): Promise<void> => {
        await this.handleNotification(notification);
      };
    }

    console.log('✅ MCP セッション初期化完了');

    // Tool リストを取得してベースラインを記録
    const toolsResult = await this.listTools();
    const tools = this.convertToolsToDefinitions(toolsResult.tools);
    await this.hashMonitor.captureBaseline(tools);

    console.log('✅ Secure MCP Client 初期化完了');
    console.log('=== 初期化完了 ===\n');
  }

  /**
   * SDK の Tool 型を ToolDefinition 型に変換
   */
  private convertToolsToDefinitions(tools: Tool[]): ToolDefinition[] {
    return tools.map((tool) => ({
      name: tool.name,
      title: tool.title || '',
      description: tool.description || '',
      inputSchema: tool.inputSchema,
    }));
  }

  /**
   * 通知を処理
   */
  private async handleNotification(notification: Notification): Promise<void> {
    if (notification.method === 'notifications/tools/list_changed') {
      await this.handleListChangedNotification(notification.params);
    }
  }

  /**
   * listChanged 通知を処理してセキュリティ検証を実行
   */
  private async handleListChangedNotification(data: unknown): Promise<void> {
    console.log('\n🚨 === Tool 定義変更通知受信 ===');
    console.log('通知データ:', JSON.stringify(data, null, 2));

    try {
      // 最新の Tool リストを取得
      console.log('最新の Tool リストを取得中...');
      const toolsResult = await this.listTools();
      const currentTools = this.convertToolsToDefinitions(toolsResult.tools);

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
   * Tool を呼び出す（セキュリティ検証付き）
   * SDK の callTool メソッドをオーバーライド
   */
  override async callTool(params: CallToolRequest['params']): Promise<CallToolResult> {
    // Tool 呼び出し前の必須検証
    console.log(`\n=== Tool ${params.name} 呼び出し前セキュリティチェック ===`);

    // 最新の Tool リストを取得
    const toolsResult = await this.listTools();
    const currentTools = this.convertToolsToDefinitions(toolsResult.tools);

    // Client 側独立ハッシュ検証
    const isValid = await this.hashMonitor.validateBeforeToolCall(currentTools, params.name);

    if (!isValid) {
      const error = `セキュリティ検証失敗: Tool ${params.name} の使用を拒否しました`;
      console.error(`❌ ${error}`);
      throw new McpError(ErrorCode.InvalidRequest, error);
    }

    console.log(`✅ Tool ${params.name} のセキュリティ検証完了`);
    console.log('=== セキュリティチェック完了 ===\n');

    // 親クラスの callTool を呼び出して実際に Tool を実行
    const result = await super.callTool(params);

    // Server から返された _meta 情報をログ出力（参考情報として）
    if (result._meta) {
      console.log('\n--- Server からの _meta 情報（参考） ---');
      console.log(JSON.stringify(result._meta, null, 2));
      console.log('注意: セキュリティ検証は Client 側の独立計算に基づいています');
      console.log('--- _meta 情報終了 ---\n');
    }

    return result as CallToolResult;
  }

  /**
   * 全 Tool の現在状態を検証
   */
  async validateAllTools(): Promise<
    {
      toolName: string;
      isValid: boolean;
      currentHash: string;
      baselineHash?: string;
    }[]
  > {
    const toolsResult = await this.listTools();
    const currentTools = this.convertToolsToDefinitions(toolsResult.tools);
    return await this.hashMonitor.validateAllTools(currentTools);
  }

  /**
   * ベースラインハッシュの一覧を表示
   */
  displayBaseline(): void {
    this.hashMonitor.displayBaseline();
  }

  /**
   * セッションを終了
   */
  override async close(): Promise<void> {
    console.log('\n=== MCP セッション終了 ===');

    // セッションを終了
    if (this.httpTransport) {
      await this.httpTransport.terminateSession();
    }

    await super.close();
    console.log('✅ セッション終了完了');
  }

  /**
   * 現在のセッション ID を取得
   */
  getSessionId(): string | undefined {
    return this.httpTransport?.sessionId;
  }

  /**
   * Client が初期化済みかどうかを確認
   */
  isReady(): boolean {
    return this.httpTransport !== undefined;
  }
}
