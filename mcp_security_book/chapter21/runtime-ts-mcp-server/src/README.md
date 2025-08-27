# TypeScript MCP Server 実装解説

このドキュメントでは、`add.ts` ファイルに実装された Model Context Protocol (MCP) Server の詳細について解説します。

## 目次

- [概要](#概要)
- [技術スタック](#技術スタック)
- [主要コンポーネント](#主要コンポーネント)
  - [Express Server](#express-server)
  - [MCP Server](#mcp-server)
  - [StreamableHTTPServerTransport](#streamablehttpservertransport)
  - [ツールとプロンプトの実装](#ツールとプロンプトの実装)
  - [ロギング機能](#ロギング機能)
  - [エラーハンドリング](#エラーハンドリング)
- [使用方法](#使用方法)
- [デプロイ方法](#デプロイ方法)

## 概要

このプロジェクトは、TypeScript を使用して Model Context Protocol (MCP) Server を実装したものです。MCP は、AI アシスタント（LLM）とデータソースやツールを標準化された方法で接続するためのオープンプロトコルです。この Server は、単純な計算機能（足し算・引き算）とグリーティングプロンプトを提供します。

Server は Express フレームワークを使用して HTTP エンドポイントを公開し、StreamableHTTPServerTransport を使用して MCP Client と通信します。また、詳細なロギング機能とエラーハンドリングも実装されています。

## 技術スタック

- **TypeScript**: 静的型付けによる堅牢なコード開発
- **Express**: HTTP Server フレームワーク
- **@modelcontextprotocol/sdk**: MCP の実装に使用する公式 SDK
- **Zod**: スキーマ検証ライブラリ
- **Node.js**: JavaScript 実行環境

## 主要コンポーネント

### Express Server

Server は Express フレームワークを使用して実装されており、以下のエンドポイントを提供しています：

- **POST /mcp**: MCP リクエストを処理するメインエンドポイント
- **GET /mcp**: 405 エラー（Method Not Allowed）を返す
- **GET /health**: ヘルスチェック用エンドポイント

```typescript
const PORT = 8000;
const app = express();
app.use(express.json());
app.use(responseCapture);

// エンドポイント定義
app.post('/mcp', async (req: Request, res: Response): Promise<void> => { /* ... */ });
app.get('/mcp', async (req: Request, res: Response): Promise<void> => { /* ... */ });
app.get('/health', (req: Request, res: Response): void => { /* ... */ });

app.listen(PORT, '0.0.0.0', (): void => { /* ... */ });
```

### MCP Server

MCP Server は `McpServer` クラスを使用して実装されています。Server は名前とバージョンで初期化され、ツールとプロンプトを登録します。

```typescript
const mcpServerCreate = (): McpServer => {
  const mcpServer = new McpServer({
    name: 'MCP-Server',
    version: '1.0.0',
  });

  // ツールとプロンプトの登録
  // ...

  return mcpServer;
};
```

### StreamableHTTPServerTransport

MCP Server は StreamableHTTPServerTransport を使用して Client と通信します。このトランスポートは HTTP を介した双方向通信をサポートし、Server から Client へのストリーミングを可能にします。

```typescript
class LoggingStreamableHTTPServerTransport extends StreamableHTTPServerTransport {
  async handleRequest(req: Request, res: Response, body: Record<string, unknown>): Promise<void> {
    // リクエスト処理のロギングと親クラスの呼び出し
    // ...
  }
}

const transport = new LoggingStreamableHTTPServerTransport({
  sessionIdGenerator: undefined,
  enableJsonResponse: true,
  stateless: isStateless,
});
```

このコードでは、StreamableHTTPServerTransport をカスタマイズして詳細なロギング機能を追加しています。

`sessionIdGenerator` を `undefined` に設定することで、トランスポートはステートレスモードで動作します。ステートレスモードでは、リクエスト間で状態が共有されず、各リクエストは独立して処理されます。これは Kubernetes のようなクラスタ環境や AWS Lambda などのサーバーレス環境で MCP Server を実行する場合に特に有用です。ステートレスモードでは、Server から Client への非同期メッセージ（Server 主導のメッセージ）はサポートされません。

設定には `stateless: isStateless` パラメータも含まれています。このパラメータは `sessionIdGenerator: undefined` と冗長に見えますが、MCP SDK の内部実装の違いによるものです。`sessionIdGenerator` は主にセッション ID の生成方法を制御し、`undefined` に設定するとセッション ID を生成しないことを意味します。一方、`stateless` パラメータは明示的にステートレスモードを有効にするためのフラグです。最新の MCP SDK では、`sessionIdGenerator: undefined` を設定するだけでステートレスモードが有効になりますが、互換性のために両方のパラメータを設定しています。

一方、`sessionIdGenerator` に関数を設定すると、その関数を使用してセッション ID が生成され、ステートフルモードで動作します。ステートフルモードでは、Server 側でセッション状態が維持され、Server から Client への非同期メッセージが可能になります。

### ツールとプロンプトの実装

Server は以下のツールとプロンプトを提供します：

1. **add ツール**: 2 つの数値を足し算する
2. **subtract ツール**: 2 つの数値を引き算する
3. **greeting-prompt プロンプト**: 名前を受け取って挨拶メッセージを生成する

```typescript
// 足し算ツール
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

// 引き算ツール
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

// グリーティングプロンプト
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
```

各ツールとプロンプトは、名前、メタデータ（タイトル、説明、入力スキーマ）、および実際の処理を行うハンドラー関数で構成されています。

### ロギング機能

Server は詳細なロギング機能を実装しており、リクエスト、レスポンス、エラーなどの情報をファイルとコンソールに記録します。

```typescript
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
```

また、Express のレスポンスをキャプチャするミドルウェアも実装されています：

```typescript
// レスポンスをキャプチャするためのミドルウェア
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
```

### エラーハンドリング

Server は try-catch ブロックを使用して様々なエラーをキャッチし、適切なエラーレスポンスを返します。また、エラーの詳細もログに記録されます。

```typescript
try {
  // Server 処理
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
```

## 使用方法

Server を起動するには、以下のコマンドを実行します：

```bash
# 依存関係のインストール
npm install

# ビルド
npm run build

# Server の起動
npm run start
```

環境変数 `PORT` を設定することで、Server のポート番号を変更できます：

```bash
PORT=3000 npm run start
```

また、環境変数 `MCP_STATELESS` または `NODE_ENV` を設定することで、ステートレスモードを有効にできます：

```bash
MCP_STATELESS=true npm run start
# または
NODE_ENV=production npm run start
```

Amazon Bedrock AgentCore Runtime では MCP はステートレスモードを期待しているため、`add.ts` では以下のようにステートレスモードを設定しています：

```typescript
const isStateless = process.env.MCP_STATELESS === 'true' || process.env.NODE_ENV === 'production';

// トランスポート設定
const transportConfig = {
  sessionIdGenerator: undefined,  // セッション ID を生成しない（ステートレスモード）
  enableJsonResponse: true,
  stateless: isStateless,         // 明示的にステートレスモードを設定
};
```

この設定により、Amazon Bedrock AgentCore Runtime 上で MCP Server が正しく動作します。

```bash
MCP_STATELESS=true npm run start
# または
NODE_ENV=production npm run start
```
