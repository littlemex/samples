import express, { Request, Response, NextFunction } from 'express';
import { StreamableHTTPServerTransport } from '@modelcontextprotocol/sdk/server/streamableHttp.js';
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { z } from 'zod';
import fs from 'fs';
import path from 'path';
import util from 'util';
import { fileURLToPath } from 'url';

// ESモジュール用のディレクトリパス取得
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// ロガー関数の定義
const logToFile = (message: string): void => {
  const logDir = path.join(__dirname, '../logs');
  if (!fs.existsSync(logDir)) {
    fs.mkdirSync(logDir, { recursive: true });
  }
  const logFile = path.join(logDir, `mcp-server-${new Date().toISOString().split('T')[0]}.log`);
  const logMessage = `[${new Date().toISOString()}] ${message}\n`;
  fs.appendFileSync(logFile, logMessage);
  console.log(message);
};

// 詳細なオブジェクトロギング
const logObject = (prefix: string, obj: unknown): void => {
  try {
    const detailed = util.inspect(obj, { showHidden: false, depth: 10, colors: false });
    logToFile(`${prefix}:\n${detailed}`);
  } catch (e) {
    logToFile(`${prefix} (シリアライズ失敗): ${e}`);
  }
};

// レスポンスをキャプチャするためのミドルウェア（シンプルな実装に変更）
const responseCapture = (req: Request, res: Response, next: NextFunction): void => {
  // 元のメソッドを保存
  const originalSend = res.send;
  const originalJson = res.json;

  // send メソッドをオーバーライド
  res.send = function (body?: unknown): Response {
    logToFile(`レスポンス送信 (send): ${body}`);
    return originalSend.call(this, body);
  };

  // json メソッドをオーバーライド
  res.json = function (body?: Record<string, unknown>): Response {
    logToFile(`レスポンス送信 (json):`);
    try {
      logToFile(JSON.stringify(body, null, 2));
    } catch (e) {
      logToFile(`JSONシリアライズに失敗: ${e}`);
    }
    return originalJson.call(this, body);
  };

  next();
};

const PORT = 8000;
const app = express();
app.use(express.json());
app.use(responseCapture);

// MCPサーバーの作成関数
const mcpServerCreate = (): McpServer => {
  const mcpServer = new McpServer({
    name: 'MCP-Server',
    version: '1.0.0',
  });

  mcpServer.registerTool(
    'add',
    {
      title: 'Addition Tool',
      description: 'Add two numbers',
      inputSchema: { a: z.number(), b: z.number() },
    },
    async ({ a, b }) => ({
      content: [{ type: 'text', text: String(a + b) }],
    })
  );

  mcpServer.registerTool(
    'subtract',
    {
      title: 'Subtraction Tool',
      description: 'Subtracts two numbers',
      inputSchema: { a: z.number(), b: z.number() },
    },
    async ({ a, b }) => ({
      content: [{ type: 'text', text: String(a - b) }],
    })
  );

  mcpServer.registerPrompt(
    'greeting-prompt',
    {
      title: 'Greeting Prompt',
      description: 'Prompt stored on MCP Server',
      argsSchema: { name: z.string() },
    },
    ({ name }) => ({
      messages: [
        {
          role: 'user',
          content: {
            type: 'text',
            text: `Hello ${name}!`,
          },
        },
      ],
    })
  );

  return mcpServer;
};

app.post('/mcp', async (req: Request, res: Response): Promise<void> => {
  // 目立つログ出力
  console.log('\n');
  console.log('*******************************************************');
  console.log('*                                                     *');
  console.log('*  🎉🎉🎉 クライアントからの接続を検出しました 🎉🎉🎉  *');
  console.log('*                                                     *');
  console.log('*******************************************************');
  console.log('\n');

  logToFile('=== POST リクエスト受信 ===');
  logToFile(`リクエスト元IP: ${req.ip}`);
  logToFile(`リクエストパス: ${req.path}`);
  logToFile('リクエストヘッダー:');
  logToFile(JSON.stringify(req.headers, null, 2));
  logToFile('リクエストボディ:');
  try {
    logToFile(JSON.stringify(req.body, null, 2));
  } catch (e) {
    logToFile(`ボディのJSONシリアライズに失敗: ${e}`);
  }

  const server = mcpServerCreate();
  logToFile('MCPサーバーを作成しました');

  try {
    logToFile('StreamableHTTPServerTransportを初期化中...');
    const isStateless =
      process.env.MCP_STATELESS === 'true' || process.env.NODE_ENV === 'production';

    // トランスポート設定の詳細をログ
    const transportConfig = {
      sessionIdGenerator: undefined,
      enableJsonResponse: true,
      stateless: isStateless,
    };
    logObject('トランスポート設定', transportConfig);

    // トランスポートをラップして詳細なログを記録
    class LoggingStreamableHTTPServerTransport extends StreamableHTTPServerTransport {
      async handleRequest(req: Request, res: Response, body: Record<string, unknown>): Promise<void> {
        logToFile('=== LoggingTransport: handleRequest 開始 ===');
        logToFile('リクエストメソッド: ' + req.method);
        logToFile('リクエストURL: ' + req.url);
        logObject('リクエストヘッダー詳細', req.headers);
        logObject('リクエストボディ詳細', body);

        try {
          logToFile('親クラスのhandleRequestを呼び出し中...');
          await super.handleRequest(req, res, body);
          logToFile('親クラスのhandleRequestが正常に完了しました');
        } catch (error) {
          logToFile(`親クラスのhandleRequestでエラーが発生: ${error}`);
          if (error instanceof Error) {
            logToFile(`エラー名: ${error.name}`);
            logToFile(`エラーメッセージ: ${error.message}`);
            logToFile(`スタックトレース: ${error.stack}`);
          }
          throw error;
        }
        logToFile('=== LoggingTransport: handleRequest 完了 ===');
      }
    }

    const transport = new LoggingStreamableHTTPServerTransport(transportConfig);
    logToFile('StreamableHTTPServerTransportを初期化しました');

    logToFile('サーバーをトランスポートに接続中...');

    // サーバーの詳細をログ
    logToFile('MCPサーバー設定:');
    try {
      // サーバーオブジェクトの詳細をログ（安全にプロパティにアクセス）
      const serverConfig = {
        type: server.constructor.name,
        tools: [
          { name: 'add', description: 'Add two numbers' },
          { name: 'subtract', description: 'Subtracts two numbers' },
          { name: 'greeting-prompt', description: 'Prompt stored on MCP Server' },
        ],
      };
      logObject('MCPサーバー', serverConfig);
      logToFile(`利用可能なツール数: ${serverConfig.tools.length}`);
      serverConfig.tools.forEach((tool, index) => {
        logToFile(`ツール ${index + 1}:`);
        logToFile(`  名前: ${tool.name}`);
        logToFile(`  説明: ${tool.description}`);
      });
    } catch (e) {
      logToFile(`サーバー設定のログ記録に失敗: ${e}`);
    }

    try {
      await server.connect(transport);
      logToFile('サーバーをトランスポートに接続しました');
    } catch (connectError) {
      logToFile(`サーバー接続エラー: ${connectError}`);
      if (connectError instanceof Error) {
        logToFile(`接続エラー名: ${connectError.name}`);
        logToFile(`接続エラーメッセージ: ${connectError.message}`);
        logToFile(`接続エラースタックトレース: ${connectError.stack}`);
      }
      throw connectError;
    }

    logToFile('リクエスト処理を開始します...');
    logToFile('MCP初期化リクエストの処理を開始...');

    // リクエストの種類を判断
    if (req.body && req.body.jsonrpc === '2.0') {
      logToFile(`JSON-RPC メソッド: ${req.body.method || 'メソッド未指定'}`);
      logToFile(`JSON-RPC ID: ${req.body.id || 'ID未指定'}`);

      if (req.body.method === 'initialize') {
        logToFile('=== MCP initialize リクエスト検出 ===');
        logObject('initialize パラメータ', req.body.params);

        // 目立つログ出力（初期化リクエスト）
        console.log('\n');
        console.log('*******************************************************');
        console.log('*                                                     *');
        console.log('*  🚀🚀🚀 MCP初期化リクエストを受信しました 🚀🚀🚀  *');
        console.log('*                                                     *');
        console.log('*******************************************************');
        console.log('\n');
      } else if (req.body.method === 'tools/list') {
        // 目立つログ出力（ツールリスト取得リクエスト）
        console.log('\n');
        console.log('*******************************************************');
        console.log('*                                                     *');
        console.log('*  🔍🔍🔍 ツールリスト取得リクエストを受信 🔍🔍🔍  *');
        console.log('*                                                     *');
        console.log('*******************************************************');
        console.log('\n');
      } else if (req.body.method === 'tools/call') {
        // 目立つログ出力（ツール呼び出しリクエスト）
        const toolName = req.body.params?.name || '不明';
        console.log('\n');
        console.log('*******************************************************');
        console.log('*                                                     *');
        console.log(`*  🛠️🛠️🛠️ ツール「${toolName}」の呼び出しリクエスト 🛠️🛠️🛠️  *`);
        console.log('*                                                     *');
        console.log('*******************************************************');
        console.log('\n');
      }
    }

    try {
      await transport.handleRequest(req, res, req.body);
      logToFile('リクエスト処理が正常に完了しました');

      // 目立つログ出力（リクエスト処理成功）
      console.log('\n');
      console.log('*******************************************************');
      console.log('*                                                     *');
      console.log('*  ✅✅✅ リクエスト処理が成功しました ✅✅✅  *');
      console.log('*                                                     *');
      console.log('*******************************************************');
      console.log('\n');
    } catch (handleError) {
      logToFile(`リクエスト処理エラー: ${handleError}`);
      if (handleError instanceof Error) {
        logToFile(`処理エラー名: ${handleError.name}`);
        logToFile(`処理エラーメッセージ: ${handleError.message}`);
        logToFile(`処理エラースタックトレース: ${handleError.stack}`);
      }
      throw handleError;
    }

    res.on('close', (): void => {
      logToFile('リクエストがクローズされました');
      transport.close();
      server.close();
    });
  } catch (error) {
    logToFile(`エラー発生: ${error}`);
    if (error instanceof Error) {
      logToFile(`エラー名: ${error.name}`);
      logToFile(`エラーメッセージ: ${error.message}`);
      logToFile(`スタックトレース: ${error.stack}`);
    }

    if (!res.headersSent) {
      logToFile('500エラーレスポンスを送信します');
      res.status(500).json({
        jsonrpc: '2.0',
        error: {
          code: -32603,
          message: 'Internal server error',
        },
        id: null,
      });
    } else {
      logToFile('ヘッダーは既に送信済みのため、エラーレスポンスは送信しません');
    }
  }
});

app.get('/mcp', async (req: Request, res: Response): Promise<void> => {
  logToFile('=== GET リクエスト受信 ===');
  logToFile(`リクエスト元IP: ${req.ip}`);
  logToFile(`リクエストパス: ${req.path}`);
  logToFile('リクエストヘッダー:');
  logToFile(JSON.stringify(req.headers, null, 2));
  logToFile('405エラーレスポンスを送信します');

  res.writeHead(405).end(
    JSON.stringify({
      jsonrpc: '2.0',
      error: {
        code: -32000,
        message: 'Method not allowed.',
      },
      id: null,
    })
  );
});

// ヘルスチェックエンドポイントを追加
app.get('/health', (req: Request, res: Response): void => {
  logToFile('=== ヘルスチェックリクエスト受信 ===');
  logToFile(`リクエスト元IP: ${req.ip}`);
  logToFile(`リクエストパス: ${req.path}`);
  logToFile('リクエストヘッダー:');
  logToFile(JSON.stringify(req.headers, null, 2));

  // 200 OKレスポンスを返す
  res.status(200).json({
    status: 'healthy',
    timestamp: new Date().toISOString(),
    version: '1.0.0',
  });
});

app.listen(PORT, '0.0.0.0', (): void => {
  logToFile(`Bedrock agentcore Typescript MCP server running on port ${PORT}`);
  logToFile(`サーバー起動時刻: ${new Date().toISOString()}`);
  logToFile(`プロセスID: ${process.pid}`);
  logToFile(`Node.jsバージョン: ${process.version}`);
  logToFile(`実行環境: ${process.env.NODE_ENV || 'development'}`);
});