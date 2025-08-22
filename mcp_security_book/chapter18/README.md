# MCP Server ツール定義変更検知サンプル

本プロジェクトは、悪意ある MCP Server を接続してしまった際の Rug Pulls 攻撃を想定したツール定義の動的な変更を検知・防止するためのサンプルを実装します。
対策を実装することが目的ではなく MCP への理解を深めることが主な目的です。

**Rug Pull 攻撃**: 初期は正当に見えるツールが、後で悪意のある動作に変更される攻撃です。ユーザーの信頼を得た後、ツールの説明を変更することで被害を与えます。

## 🔒 アーキテクチャ

2 種類の方法でツール定義の変更を検知するためにハッシュ値を提供します。

1 つめの方法は Server 側の `_meta` フィールドを利用してハッシュ値を提供します。実際には悪意ある MCP Server から提供されるハッシュ値を信用できるわけではないため対策というよりは `_meta` を含む仕様と実装理解のために追加しました。

2 つめの方法は Client 側で Server に依存しない形でベースラインハッシュ値を保存しておき、ツール操作のたびにベースラインと現在のハッシュ値を比較するという方法をとります。これも実運用時には [EDTI](./docs/etdi-hld.md) のようによりセキュアな方法を導入すべきでしょう。

## プロジェクト構成

```
chapter18/
├── src/
│   ├── add.ts                        # MCP Server 実装
│   ├── tool-definitions.json         # ツール定義の外部設定ファイル
│   ├── security-utils.ts             # セキュリティユーティリティ
│   ├── client-validator.ts           # 手動 Client 側検証ツール
│   ├── client-hash-monitor.ts        # Client 側ハッシュ監視システム
│   ├── secure-mcp-client.ts          # セキュリティ強化 MCP Client
│   ├── demo-listchanged-detection.ts # リアルタイムツール定義変更検出デモ
│   ├── server.ts                     # Express Server 実装
│   ├── *.test.ts                     # 包括的テストスイート
│   ├── types.ts                      # type
│   ├── package.json
│   └── tsconfig.json
├── docs/
│   └── etdi-hld.md                 # EDTI のハイレベルな仕様説明
└── README.md                       # 本ファイル
```

## Client 側検証(Function01) の基本手順

MCP Server のツール定義変更のための API を用意しているのでツール定義変更とハッシュ値の確認を手動で試してみましょう。

### 1. 依存関係のインストール

```bash
cd samples/mcp_security_book/chapter18/src
npm install
```

### 2. TypeScript のビルド

```bash
npm run build
```

### 3. MCP Server の起動

```bash
npm start
```

Server は http://localhost:13000 で起動します。

### 4. 基本的な動作確認

MCP Server が正常に起動していることを確認します。

```bash
# Server の状態確認
curl http://localhost:13000/tool-status |jq

# 初回検証（ハッシュ値の保存）、hash-storage.json に結果を保存
npm run validate
```

### 5. Tool 定義変更のデモンストレーション

ツール説明を動的に変更してみましょう。

`currentVersion` と `currentDescription` が変更されることを確認してみてください。

```bash
# ツール説明の変更
curl -X POST http://localhost:13000/change-description |jq

# 変更後の状態確認
curl http://localhost:13000/tool-status |jq
```

### 6. Client 側検証ツールの使用

TypeScript で実装された Client 側検証ツールを使用して、ツール定義の整合性を検証します。

```bash
# ツール説明変更後の検証（結果を確認してみましょう）
npm run validate

# 保存されたハッシュ値の一覧表示
npm run list
```

## リアルタイムツール定義検出デモ(Function02) の基本手順

`demo-listchanged-detection.ts` を使用してリアルタイムツール定義変更検出を確認できます。

スクリプトの中身を調査して何が起こっているのか理解しましょう。

### 1. デモの実行

```bash
# MCP Server を起動（別ターミナル）
npm start

# デモスクリプトの実行
npm run demo
```

### 2. デモの流れ

1. **初期化**: Secure MCP Client を初期化し、ベースラインハッシュを取得
2. **正常動作確認**: 初期状態でのツール呼び出しテスト
3. **ツール定義変更**: Server 側でツール定義を変更
4. **リアルタイム検出**: Client は listChanged 通知を受信し、セキュリティ検証を実行
5. **防御確認**: Client 側で変更されたツールの使用に関するアラートを発出

### 3. 確認できる機能

- ✅ Client 側ハッシュ計算による検証
- ✅ Server側 `_meta` ハッシュの表示
- ✅ リアルタイム listChanged 通知の受信
- ✅ ツール定義変更の即座の検出
- ✅ 危険なツールへのアラート

### 4. 演習(Optional)

`secure-mcp-client.ts` は typescript-sdk をあえて利用せずに簡易に実装しました。typescript-sdk を用いた Client 実装を試してみましょう。解答例を `src/answer` に配置しました。`src/exercise` に自分で実装してみましょう。

## 🛡️ セキュリティ機能

### Client 側ハッシュ計算

**ClientHashMonitor**: クラスが提供する主要機能

```typescript
// ベースラインハッシュの取得
await monitor.captureBaseline(tools);

// ツール呼び出し前の検証
const isValid = await monitor.validateBeforeToolCall(toolName, currentDefinition);

// 全ツールの検証
const results = await monitor.validateAllTools(currentTools);
```

### セキュリティ強化 MCP Client

**SecureMCPClient**: クラスが提供する機能

```typescript
// セキュリティ機能付き Client の初期化
const client = new SecureMCPClient(transport);
await client.initialize();

// セキュリティ検証付きツール呼び出し
const result = await client.callTool(toolName, args);
```

### ハッシュベース検証

本サンプルでは、SHA-256 ハッシュアルゴリズムを使用してツール定義の整合性を検証します。ツール定義の名前、タイトル、説明、入力スキーマを正規化してからハッシュ値を計算します。

### 変更検知とアラート

ツール定義に変更が検知された場合、システムは以下の情報を提供します：

1. 🚨 **セキュリティアラート**: 変更されたツールの詳細
2. 📊 **ハッシュ比較**: 期待値と現在値の比較
3. 🕒 **タイムスタンプ**: ベースライン取得時刻と現在時刻
4. 📋 **変更内容**: 変更前後の定義の詳細比較

## API エンドポイント

### GET `/tool-status`

現在のツール定義とハッシュ値を取得します。

### POST `/change-description`

ツール説明を変更します（ツール定義変更デモンストレーション用）。

**リクエスト**: 本文は不要です

**レスポンス**: 変更後のツール情報を返します

## トラブルシューティング

### Server が起動しない場合

ポート 13000 が既に使用されている可能性があります。以下のコマンドでポートの使用状況を確認してください。

```bash
lsof -i :13000
```

## 🎓 学習内容

1. **MCP プロトコルの理解**
   - SSE transport の実装
   - Notification の活用方法
   - `_meta` の活用方法

2. **セキュリティ設計**
   - Client 側独立検証の重要性
   - ハッシュベース整合性チェック
   - リアルタイム変更検出

**注意**: 本プロジェクトは教育目的で作成されており、実際の攻撃に使用することは禁止です。セキュリティ研究と学習のためにのみご使用ください。

> 時間の関係で実装や命名が一部残念なのはお許しを