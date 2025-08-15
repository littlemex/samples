# 足し算をするだけの単純な MCP Server (Streamable HTTP)

このプロジェクトは、足し算をするだけの単純な MCP Server (Streamable HTTP) を実装したものです。

## 機能

- `add` ツールを提供し、2 つの数値を受け取り、その和を返します。
- 最新の計算結果を提供する `last-calculation` リソースを提供します。
- Streamable HTTP 形式の MCP Server として実装されています。
- Express.js を使用して HTTP サーバーを立ち上げます。

## 使い方

### 依存関係のインストール

```bash
npm install
```

### ビルド

```bash
npm run build
```

### 実行

```bash
npm start
```

この段階では、simple-add-server(version 1.0.0) が Streamable HTTP トランスポートを使用してポート 13000 で Client からの接続を待機している状態です。

## API の使用方法

### 初期化

```bash
curl -X POST http://localhost:13000/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{
    "jsonrpc": "2.0",
    "method": "initialize",
    "params": {
      "protocolVersion": "2025-06-18",
      "clientInfo": {
        "name": "curl-client",
        "version": "1.0.0"
      },
      "capabilities": {}
    },
    "id": 1
  }'
```

このリクエストは MCP におけるライフサイクルの Initialization で初期化ハンドシェイクを実施します。各フィールドの意味は以下の通りです。

- **protocolVersion**: 使用する MCP プロトコルのバージョンを指定します。この例では "2025-06-18" を使用しており、これは MCP の最新仕様バージョンです。
- **clientInfo**: Client の識別情報を提供します。name フィールドには "curl-client"、version には "1.0.0" を設定しています。
- **capabilities**: Client がサポートする機能を宣言します。この例では空のオブジェクトが設定されており、基本的な機能のみをサポートすることを示しています。

```bash
# 初期化リクエストを送信し、レスポンスヘッダーからセッション ID を取得する例
SESSION_ID=$(curl -X POST http://localhost:13000/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{
    "jsonrpc": "2.0",
    "method": "initialize",
    "params": {
      "protocolVersion": "2025-06-18",
      "clientInfo": {
        "name": "curl-client",
        "version": "1.0.0"
      },
      "capabilities": {}
    },
    "id": 1
  }' -i | grep -i mcp-session-id | cut -d' ' -f2 | tr -d '\r')

echo "セッション ID: $SESSION_ID"
```

Server は各 Client 接続に対して一意のセッション ID を生成します。この ID は接続の状態管理と複数の Client を区別するために使用されます。MCP はステートフルなプロトコルであり、適切なセッション管理が重要です。

上記コマンド実行でレスポンスヘッダーの `mcp-session-id` からセッション ID を取得し、以降のリクエストで使用します。

```bash
...
# MCP Server の出力ログ
MCP Streamable HTTP Server がポート 13000 でリッスン中
新規リクエスト: {
  jsonrpc: '2.0',
  method: 'initialize',
  params: {
    protocolVersion: '2025-06-18',
    clientInfo: { name: 'curl-client', version: '1.0.0' },
    capabilities: {}
  },
  id: 1
}
セッション初期化: 02d5d9de-4dfb-4dc6-afee-004bfac05d8b
```

**プロトコルバージョンの確認**: Server は同じプロトコルバージョン "2025-06-18" を返すことで、Client との互換性を確認しています。

**サーバー機能の宣言**: Server は以下の機能をサポートすることを宣言しています。

- **resources**: リソース機能をサポートし、同様にリソースリストの変更通知を送信できます。
- **completions**: 補完機能ですが今回は使わないので空です。

**サーバー情報**: serverInfo フィールドで Server の識別情報を提供しています。name は "simple-add-server"、version は "1.0.0" です。

### ツール一覧の取得

```bash
curl -X POST http://localhost:13000/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "Mcp-Session-Id: $SESSION_ID" \
  -H "Mcp-Protocol-Version: 2025-06-18" \
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/list",
    "id": 2
  }'
```

```json
{
  "result": {
    "tools": [
      {
        "name": "add",
        "title": "足し算ツール",
        "description": "2つの数値を足し算するシンプルなツール",
        "inputSchema": {
          "type": "object",
          "properties": {
            "a": {
              "type": "number",
              "description": "1つ目の数値"
            },
            "b": {
              "type": "number",
              "description": "2つ目の数値"
            }
          },
          "required": [
            "a",
            "b"
          ],
          "additionalProperties": false,
          "$schema": "http://json-schema.org/draft-07/schema#"
        }
      }
    ]
  },
  "jsonrpc": "2.0",
  "id": 2
}
```

```bash
# MCP Server の出力ログ
セッション 02d5d9de-4dfb-4dc6-afee-004bfac05d8b からのリクエスト: { jsonrpc: '2.0', method: 'tools/list', id: 2 }
```

### 足し算ツールの使用

add ツールを使ってみましょう。

```bash
curl -X POST http://localhost:13000/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "Mcp-Session-Id: $SESSION_ID" \
  -H "Mcp-Protocol-Version: 2025-06-18" \
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/call",
    "params": {
      "name": "add",
      "arguments": {
        "a": 5,
        "b": 3
      }
    },
    "id": 3
  }'
```

```json
{
  "result": {
    "content": [
      {
        "type": "text",
        "text": "8"
      }
    ]
  },
  "jsonrpc": "2.0",
  "id": 3
}
```

```bash
# MCP Server の出力ログ
セッション 02d5d9de-4dfb-4dc6-afee-004bfac05d8b からのリクエスト: {
  jsonrpc: '2.0',
  method: 'tools/call',
  params: { name: 'add', arguments: { a: 5, b: 3 } },
  id: 3
}
```

### リソース一覧の取得

```bash
curl -X POST http://localhost:13000/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "Mcp-Session-Id: $SESSION_ID" \
  -H "Mcp-Protocol-Version: 2025-06-18" \
  -d '{
    "jsonrpc": "2.0",
    "method": "resources/list",
    "id": 4
  }'
```

### 最新の計算結果リソースの読み取り

```bash
curl -X POST http://localhost:13000/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "Mcp-Session-Id: $SESSION_ID" \
  -H "Mcp-Protocol-Version: 2025-06-18" \
  -d '{
    "jsonrpc": "2.0",
    "method": "resources/read",
    "params": {
      "uri": "https://example.com/calculations/last"
    },
    "id": 5
  }'
```

### SSE ストリームの確立

Server-Sent Events (SSE) ストリームを確立して Server からのリアルタイム通知を受信するようなケースでは SSE 形式でのレスポンスを要求します。

- **-N フラグ**: curl のバッファリングを無効化し、ストリーミングデータをリアルタイムで表示
- **Accept**: text/event-stream: SSE 形式でのレスポンスを要求
- **GET メソッド**: 双方向通信の受信側チャネルを確立

```bash
curl -N -X GET http://localhost:13000/mcp \
  -H "Accept: text/event-stream" \
  -H "Mcp-Session-Id: $SESSION_ID" \
  -H "Mcp-Protocol-Version: 2025-06-18"
```

**セッションの終了**

```bash
curl -X DELETE http://localhost:13000/mcp \
  -H "Mcp-Session-Id: $SESSION_ID" \
  -H "Mcp-Protocol-Version: 2025-06-18"
```

## MCP Inspector

[MCP Inspector](https://github.com/modelcontextprotocol/inspector) は [Model Context Protocol](https://modelcontextprotocol.io) 公式のリポジトリで提供される MCP Server のテストとデバッグを行うための開発ツールです。CVE-2025-49596 (CVSS Score 9.4) の報告があったこともあり、セキュリティ脆弱性が多く含まれていることを想定して必ず機密性の高いデータが存在しない開発環境で検証を行ってください。

上記の手順で MCP Server を立ち上げた状態で以下のコマンドでローカル PC で MCP Inspector を起動してください。

> MCP Inspector は `6274, 6277` ポートを利用するため Amazon Elastic Compute Cloud (Amazon EC2) インスタンス上で Inspector を立ち上げて Port forward 等を利用してローカルから Inspector に接続する場合には 2 つのポート転送が必要なことに注意してください。

```bash
npx @modelcontextprotocol/inspector
```

起動後の設定は以下です（ただし、本リポジトリの mcp_security_book/prepare/cfn を利用した環境の場合）

- **Transport Type**: `Streamable HTTP`
- **URL**: `https://xxx.cloudfront.net/proxy/13000/mcp`

設定完了後に `Connect` ボタンを押下すると MCP Server と MCP Inspector が接続されます。

![](./images/inspector01.png)

![](./images/inspector02.png)
