import express from 'express';
import { z } from 'zod';
import { randomUUID } from 'node:crypto';
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StreamableHTTPServerTransport } from '@modelcontextprotocol/sdk/server/streamableHttp.js';
import { isInitializeRequest, ReadResourceResult } from '@modelcontextprotocol/sdk/types.js';

// 定数定義
const MCP_PORT = 13000;
const SERVER_NAME = 'simple-add-server';
const SERVER_VERSION = '1.0.0';
const RESOURCE_URI = 'https://example.com/calculations/last';

/**
 * 計算結果を表す型定義
 */
export interface CalculationResult {
  a: number;
  b: number;
  sum: number;
  timestamp: string;
}

// 最後に計算された足し算の結果を保存する変数
let lastCalculationResult: CalculationResult = {
  a: 0,
  b: 0,
  sum: 0,
  timestamp: new Date().toISOString(),
};

/**
 * 2つの数値を足し算する関数
 * @param a 1つ目の数値
 * @param b 2つ目の数値
 * @returns 足し算の結果
 */
export function addNumbers(a: number, b: number): number {
  return a + b;
}

/**
 * 足し算を実行し、結果を保存する関数
 * @param a 1つ目の数値
 * @param b 2つ目の数値
 * @returns 計算結果オブジェクト
 */
export function calculateAndSave(a: number, b: number): CalculationResult {
  const sum = addNumbers(a, b);

  const result: CalculationResult = {
    a,
    b,
    sum,
    timestamp: new Date().toISOString(),
  };

  // 結果を保存
  lastCalculationResult = result;

  return result;
}

/**
 * 最後に計算された結果を取得する関数
 * @returns 最後の計算結果
 */
export function getLastCalculation(): CalculationResult {
  return { ...lastCalculationResult };
}

/**
 * MCP Serverのインスタンスを作成し、ツールとリソースを登録する
 * @returns 設定済みのMCPサーバーインスタンス
 */
const getServer = (): McpServer => {
  const server = new McpServer({
    name: SERVER_NAME,
    version: SERVER_VERSION,
  });

  // 足し算ツールの登録
  server.registerTool(
    'add',
    {
      title: '足し算ツール',
      description: '2つの数値を足し算するシンプルなツール',
      inputSchema: {
        a: z.number().describe('1つ目の数値'),
        b: z.number().describe('2つ目の数値'),
      },
    },
    /**
     * 2つの数値を足し算し、結果を保存する
     * @param a 1つ目の数値
     * @param b 2つ目の数値
     * @returns 足し算の結果を含むレスポンスオブジェクト
     */
    async ({ a, b }: { a: number; b: number }) => {
      const result = calculateAndSave(a, b);

      return {
        content: [
          {
            type: 'text',
            text: `${result.sum}`,
          },
        ],
      };
    }
  );

  // 計算結果のリソースを登録
  server.registerResource(
    'last-calculation',
    RESOURCE_URI,
    {
      title: '最新の計算結果',
      description: '最後に実行された足し算の結果',
      mimeType: 'application/json',
    },
    async (): Promise<ReadResourceResult> => {
      const lastResult = getLastCalculation();
      return {
        contents: [
          {
            uri: RESOURCE_URI,
            text: JSON.stringify(lastResult),
            mimeType: 'application/json',
          },
        ],
      };
    }
  );

  return server;
};

// Expressアプリケーションの設定
const app = express();
app.use(express.json());

// セッションごとのトランスポートを保存するマップ
const transports: { [sessionId: string]: StreamableHTTPServerTransport } = {};

/**
 * 既存のセッションのリクエストを処理する
 * @param req リクエストオブジェクト
 * @param res レスポンスオブジェクト
 * @param sessionId セッションID
 */
const handleExistingSession = async (
  req: express.Request,
  res: express.Response,
  sessionId: string
): Promise<void> => {
  const transport = transports[sessionId];
  await transport.handleRequest(req, res, req.body);
};

/**
 * 新規セッションの初期化リクエストを処理する
 * @param req リクエストオブジェクト
 * @param res レスポンスオブジェクト
 */
const handleNewSession = async (req: express.Request, res: express.Response): Promise<void> => {
  const transport = new StreamableHTTPServerTransport({
    sessionIdGenerator: () => randomUUID(),
    enableJsonResponse: true, // JSONレスポンスを有効にして、セッションIDをヘッダーに含める
    onsessioninitialized: (sessionId: string) => {
      console.log(`セッション初期化: ${sessionId}`);
      transports[sessionId] = transport;
    },
  });

  // トランスポートをMCPサーバーに接続
  const server = getServer();
  await server.connect(transport);
  await transport.handleRequest(req, res, req.body);
};

/**
 * 無効なリクエストを処理する
 * @param res レスポンスオブジェクト
 */
const handleInvalidRequest = (res: express.Response): void => {
  res.status(400).json({
    jsonrpc: '2.0',
    error: {
      code: -32000,
      message: '有効なセッションIDが提供されていません',
    },
    id: null,
  });
};

/**
 * MCP POSTエンドポイントのハンドラ
 * @param req リクエストオブジェクト
 * @param res レスポンスオブジェクト
 */
const mcpPostHandler = async (req: express.Request, res: express.Response): Promise<void> => {
  const sessionId = req.headers['mcp-session-id'] as string | undefined;
  console.log(
    sessionId ? `セッション ${sessionId} からのリクエスト:` : '新規リクエスト:',
    req.body
  );

  try {
    if (sessionId && transports[sessionId]) {
      // 既存のトランスポートを再利用
      await handleExistingSession(req, res, sessionId);
    } else if (!sessionId && isInitializeRequest(req.body)) {
      // 新規初期化リクエスト
      await handleNewSession(req, res);
    } else {
      // 無効なリクエスト
      handleInvalidRequest(res);
    }
  } catch (error: unknown) {
    const errorMessage = error instanceof Error ? error.message : '不明なエラー';
    console.error('MCPリクエスト処理エラー:', errorMessage);

    if (!res.headersSent) {
      res.status(500).json({
        jsonrpc: '2.0',
        error: {
          code: -32603,
          message: '内部サーバーエラー',
          data: errorMessage, // エラー詳細を追加
        },
        id: null,
      });
    }
  }
};

// ルートの設定
app.post('/mcp', mcpPostHandler);

/**
 * SSEストリーム用のGETハンドラ
 */
app.get('/mcp', async (req: express.Request, res: express.Response) => {
  const sessionId = req.headers['mcp-session-id'] as string | undefined;
  if (!sessionId || !transports[sessionId]) {
    res.status(400).send('無効または欠落しているセッションID');
    return;
  }

  console.log(`セッション ${sessionId} のSSEストリームを確立`);
  const transport = transports[sessionId];
  await transport.handleRequest(req, res);
});

/**
 * セッション終了用のDELETEハンドラ
 */
app.delete('/mcp', async (req: express.Request, res: express.Response) => {
  const sessionId = req.headers['mcp-session-id'] as string | undefined;
  if (!sessionId || !transports[sessionId]) {
    res.status(400).send('無効または欠落しているセッションID');
    return;
  }

  console.log(`セッション ${sessionId} の終了リクエストを受信`);
  try {
    const transport = transports[sessionId];
    await transport.handleRequest(req, res);
  } catch (error: unknown) {
    const errorMessage = error instanceof Error ? error.message : '不明なエラー';
    console.error('セッション終了処理エラー:', errorMessage);
    if (!res.headersSent) {
      res.status(500).send('セッション終了処理エラー');
    }
  }
});

// サーバー起動
app.listen(MCP_PORT, () => {
  console.log(`MCP Streamable HTTP Server がポート ${MCP_PORT} でリッスン中`);
});

/**
 * サーバーシャットダウン処理
 * SIGINT（Ctrl+C）シグナルを受け取った時の処理
 */
process.on('SIGINT', async () => {
  console.log('サーバーをシャットダウンしています...');
  for (const sessionId in transports) {
    try {
      console.log(`セッション ${sessionId} のトランスポートを閉じています`);
      await transports[sessionId].close();
      delete transports[sessionId];
    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : '不明なエラー';
      console.error(`セッション ${sessionId} のトランスポート終了エラー:`, errorMessage);
    }
  }
  console.log('サーバーシャットダウン完了');
  process.exit(0);
});
