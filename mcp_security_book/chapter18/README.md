# MCP Server セキュリティ脆弱性デモンストレーション

本プロジェクトは、Model Context Protocol (MCP) Server のセキュリティ脆弱性を実証し、それらを検知・防止するためのメカニズムを提供いたします。具体的には、Tool Poisoning 攻撃と Rug Pull 攻撃のデモンストレーションを通じて、MCP Server のツール定義が動的に変更される脆弱性とその対策を学習できます。

## 概要

MCP Server は、AI アシスタントが外部ツールにアクセスするための重要なインターフェースです。しかし、ツール定義が実行時に変更される可能性があり、これがセキュリティリスクとなります。本プロジェクトでは、以下の脆弱性を実装し、その対策を提供いたします。

**Tool Poisoning 攻撃**: 悪意のあるツールが正当なツールになりすます攻撃です。攻撃者は正当なツールと同じ名前で悪意のあるツールを登録し、ユーザーを欺くことができます。

**Rug Pull 攻撃**: 初期は正当に見えるツールが、後で悪意のある動作に変更される攻撃です。ユーザーの信頼を得た後、ツールの動作を変更することで被害を与えます。

## 技術仕様

**開発環境**: Node.js 18 以上、TypeScript 5.0 以上、Python 3.8 以上

**主要ライブラリ**: @modelcontextprotocol/sdk、Express.js、crypto モジュール

**セキュリティ機能**: SHA-256 ハッシュベースの整合性検証、_meta フィールドによるハッシュ値提供

## プロジェクト構成

```
samples/mcp_security_book/chapter18/
├── src/
│   ├── add.ts                    # MCP Server 実装（脆弱性デモ機能付き）
│   ├── security-utils.ts         # セキュリティユーティリティ
│   ├── client-validator.ts       # Client 側検証ツール
│   ├── tool-change-detector.py   # Python 変更検知スクリプト
│   ├── package.json
│   └── tsconfig.json
├── docs/
│   ├── implementation-details.md # 実装詳細ドキュメント
│   └── core/
│       └── hld.md               # 高レベル設計ドキュメント
└── README.md                    # 本ファイル
```

## セットアップ手順

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

Server は http://localhost:13000 で起動いたします。

## 使用方法

### 基本的な動作確認

MCP Server が正常に起動していることを確認いたします。

```bash
# Server の状態確認
curl http://localhost:13000/tool-status
```

### Tool Poisoning 攻撃のデモンストレーション

ツール説明を動的に変更して、Rug Pull 攻撃を実演いたします。

```bash
# ツール説明の変更
curl -X POST http://localhost:13000/change-description

# 変更後の状態確認
curl http://localhost:13000/tool-status
```

### Client 側検証ツールの使用

TypeScript で実装された Client 側検証ツールを使用して、ツール定義の整合性を検証いたします。

```bash
# 初回検証（ハッシュ値の保存）
npx ts-node client-validator.ts validate http://localhost:13000

# ツール説明変更後の検証
curl -X POST http://localhost:13000/change-description
npx ts-node client-validator.ts validate http://localhost:13000
```

### Python 変更検知スクリプトの使用

Python で実装された変更検知スクリプトを使用して、より詳細な分析を行います。

```bash
# 変更検知の実行
python tool-change-detector.py --server-url http://localhost:13000
```

## セキュリティ機能

### ハッシュベース検証

本システムでは、SHA-256 ハッシュアルゴリズムを使用してツール定義の整合性を検証いたします。ツール定義の名前、タイトル、説明、入力スキーマを正規化してからハッシュ値を計算することで、一貫性のある検証を実現しています。

### _meta フィールドによるハッシュ提供

MCP Server は、ツール定義の _meta フィールドにハッシュ値を含めて提供いたします。これにより、Client は MCP プロトコルレベルでツール定義の整合性を検証できます。

```json
{
  "_meta": {
    "hash": "abc123...",
    "version": "original",
    "serverName": "MCP Security Demo Server",
    "serverVersion": "1.0.0",
    "timestamp": "2024-01-01T00:00:00.000Z",
    "securityNote": "このハッシュ値を使用してツール定義の整合性を検証してください"
  }
}
```

### 変更検知とアラート

ツール定義に変更が検知された場合、システムは以下の情報を提供いたします。

1. 変更されたフィールドの詳細
2. 変更前後のハッシュ値
3. 変更のタイムスタンプ
4. セキュリティリスクの評価

## API エンドポイント

### GET /tool-status

現在のツール定義とハッシュ値を取得いたします。

**レスポンス例**:
```json
{
  "toolName": "add",
  "currentVersion": "original",
  "hash": "abc123...",
  "timestamp": "2024-01-01T00:00:00.000Z"
}
```

### POST /change-description

ツール説明を変更いたします（Rug Pull 攻撃のデモンストレーション用）。

**リクエスト**: 本文は不要です

**レスポンス**: 変更後のツール情報を返します

## テスト手順

### 1. 基本機能のテスト

```bash
# MCP Server の起動確認
npm start

# 別のターミナルで API テスト
curl http://localhost:13000/tool-status
```

### 2. 脆弱性デモンストレーションのテスト

```bash
# 初期状態のハッシュ保存
npx ts-node client-validator.ts validate http://localhost:13000

# ツール説明の変更
curl -X POST http://localhost:13000/change-description

# 変更の検知
npx ts-node client-validator.ts validate http://localhost:13000
```

### 3. Python スクリプトのテスト

```bash
# 変更検知スクリプトの実行
python tool-change-detector.py --server-url http://localhost:13000
```

## セキュリティ上の考慮事項

### ハッシュアルゴリズムの選択

SHA-256 ハッシュアルゴリズムを使用することで、高いセキュリティレベルを確保しています。このアルゴリズムは現在広く使用されており、十分な安全性を提供いたします。

### ツール定義の正規化

ツール定義をハッシュ化する前に正規化処理を行うことで、フォーマットの違いによる誤検知を防いでいます。

### 検証の自動化

定期的な検証を自動化することで、リアルタイムでの脅威検知が可能です。実運用環境では、CI/CD パイプラインに組み込むことを推奨いたします。

## トラブルシューティング

### Server が起動しない場合

ポート 13000 が既に使用されている可能性があります。以下のコマンドでポートの使用状況を確認してください。

```bash
# Linux/macOS の場合
lsof -i :13000

# Windows の場合
netstat -an | findstr :13000
```

### TypeScript のビルドエラー

Node.js のバージョンが 18 以上であることを確認してください。

```bash
node --version
```

### Python スクリプトの実行エラー

Python 3.8 以上がインストールされていることを確認し、必要なライブラリをインストールしてください。

```bash
python --version
pip install requests hashlib json
```

## 今後の拡張予定

### 証明書ベースの検証

デジタル署名を使用したより高度な検証メカニズムの実装を予定しています。

### 監査ログの強化

全ての変更を記録し、改ざん防止機能を持つ監査ログシステムの実装を検討しています。

### SIEM システムとの統合

Security Information and Event Management (SIEM) システムとの統合により、企業レベルのセキュリティ監視を実現する予定です。

## ライセンス

本プロジェクトは MIT ライセンスの下で公開されています。詳細については LICENSE ファイルをご確認ください。

## 貢献

プロジェクトへの貢献を歓迎いたします。Issue の報告や Pull Request の提出をお待ちしております。

## サポート

技術的な質問や問題については、GitHub の Issue を通じてお問い合わせください。セキュリティに関する重要な問題については、直接メンテナーにご連絡いただくことをお勧めいたします。

---

**注意**: 本プロジェクトは教育目的で作成されており、実際の攻撃に使用することは禁止されています。セキュリティ研究と学習のためにのみご使用ください。
