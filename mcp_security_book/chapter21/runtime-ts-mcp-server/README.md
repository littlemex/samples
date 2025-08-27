# AgentCore Runtime - Simple MCP Server

## 概要

このサンプルでは、Amazon Bedrock AgentCore ランタイム環境を使用して TypeScript ベースの MCP（Model Context Protocol）Server をホストする方法を説明します。現状 AgentCore Toolkit は Python を期待しているため、それ以外の言語の場合は [カスタムフローを使用してデプロイ](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/getting-started-custom.html) する必要があります。一般提供開始と AWS CDK 等の IaC の対応が望まれます。

### サンプル概要

**チェックポイント！**

- TypeScript ベースの MCP Server を利用
- AgentCore Runtime の MCP では Streamable HTTP のステートレスサポートが必要
- MCP Client は Python、TypeScript の両方で提供（SigV4 認証と OAuth 認証の両方をサポート）
- Python ベースの AgentCore Runtime へのデプロイスクリプトを提供

SigV4 については[こちら](https://aws.amazon.com/jp/builders-flash/202210/way-to-operate-api-2/) がわかりやすいです。

### 理解したいポイント

- [ ] 1. MCP Server のステートレス設定はどうやるのか？
- [ ] 2. MCP Client で SigV4 認証でのアクセスはどうやっているのか？
- [ ] 3. AgentCore Runtime へのデプロイに関する制約は何があるのか？
- [ ] 4. AgentCore Runtime のデプロイスクリプトはどうなっているのか？

## ファイル構成

このプロジェクトには以下の主要ファイルが含まれています：

- **client.ts**: TypeScript 実装の MCP Client です。SigV4 認証を使用して、ローカル MCP Server と Amazon Bedrock AgentCore Runtime の両方にアクセスできます。
- **client-oauth.ts**: TypeScript 実装の MCP Client です。OAuth JWT Bearer Token 認証を使用して AgentCore Runtime にアクセスします。
- **client.py**: Python 実装の MCP Client です。client.ts と同様に SigV4 認証でローカルと AgentCore Runtime へのアクセスに対応しています。
- **deploy.py**: MCP Server を AgentCore Runtime へデプロイするための便利スクリプトです。各ステップごとに実行できる機能が提供されています。
- **utils.py**: Cognito 設定、IAM ロール作成、認証テストなどの汎用的な機能を提供するユーティリティモジュールです。
- **deployment_config.json**: deploy.py の実行によって作成されるリソース情報が格納されるファイルです。べき等性を保ちながら更新されます。

## 前提条件

このチュートリアルを実行するには以下が必要です。

- Node.js v22 以降（MCP Server 用）
- Python 3.10+（MCP Client 用）
- Docker
- Amazon ECR（Elastic Container Registry）Docker イメージ保存用  
- Bedrock AgentCore へのアクセス権を持つ AWS アカウント  

## 事前準備

環境に応じて .env を修正してください。Python 環境では必ず uv を利用します。
```bash
uv venv && source .venv/bin/activate
uv sync

cp .env.example .env
```

## Step 1: 認証用の Amazon Cognito 設定

AgentCore Runtime には認証が必要です。Runtime の場合、Inbound Auth には AWS IAM（SigV4）と JWT Bearer Token の二種類のアクセス制御方式があります。deploy.py では両方の認証方式に対応するための設定を行っています。

Step 1 では、JWT Bearer Token 認証のために Amazon Cognito を設定します。utils.py の `setup_cognito_user_pool` 関数を使用して、Cognito ユーザープールとアプリケーション Client を作成します。作成したリソース情報は deployment_config.json に自動的に保存されます。

```bash
# JavaScript SDK は機能不足のため Python を利用したスクリプトでデプロイします
uv run deploy.py --step1
```

```bash
✓ Cognito 設定完了

  ユーザープール ID: N/A

  Client ID: 7jatnr1xxxx

  Discovery URL: https://cognito-idp.us-east-1.amazonaws.com/us-east-1_Hxxx/.well-known/openid-configuration
```

## Step 2: IAM 実行ロールの作成

開始する前に、AgentCore Runtime サービス自体が使用する IAM ロールを作成しましょう。このロールは、Runtime が AWS リソースにアクセスするために必要な権限を提供します。

deploy.py の `--step2` オプションを実行すると、utils.py の `update_agentcore_role` 関数を使用して、Runtime 自体に必要な権限を持つ IAM ロールが作成または更新されます。このロールには、Bedrock サービス、ECR、CloudWatch Logs、X-Ray などへのアクセス権限が含まれています。

なお、deploy.py を実行する際に `--put-role-policy` オプションを使用する場合は、deploy.py を実行するユーザー自体に必要な権限を付与するためのものであり、Step 2 で作成するロールとは異なります。Step 2 のロールは、呼び出される側の Runtime が他の AWS サービスにアクセスするために必要なロールです。

```bash
uv run deploy.py --step2
```

## Step 3: MCP Server の作成

次に、Chapter14 で作成したシンプルな MCP Server を AgentCore Runtime で要求される制約に応じて修正しました。`PORT=8000` を利用するために環境変数で PORT 指定するなどの変更が多少入っています。**変更箇所を確認してみましょう。**

このステップでは、TypeScript ベースの MCP Server のローカル開発環境をセットアップします。Server は Model Context Protocol に準拠し、AgentCore Runtime の要件を満たすように設計されています。

```bash
# 依存関係のインストールと build
npm install && npm run build

# ローカルで Server 立ち上げ
npm run start
```

## Step 4: Docker 経由での MCP Server デプロイメント

スターターツールキットを使用せずに MCP Server をデプロイするための手動手順です。イメージのビルド、Amazon ECR へのプッシュを実施します。

deploy.py の `--step4` オプションを実行すると、以下の処理が行われます：

1. Amazon ECR リポジトリの作成（存在しない場合）
2. Docker ビルダーの作成と設定
3. Docker イメージのビルドと ECR へのプッシュ
4. AgentCore Runtime の作成と設定

このステップでは、AWS SDK を使用して `bedrock-agentcore-control` サービスにアクセスし、MCP Server を AgentCore Runtime にデプロイします。デプロイされた Server の ARN は deployment_config.json に保存されます。

AgentCore Runtime の作成時に `authorizerConfiguration` パラメータを指定しないため、デフォルトで SigV4 認証が使用されます。JWT Bearer Token 認証を使用する場合は、`--oauth` オプションを指定します。

```bash
uv run deploy.py --step4
```

## Step 5: リモートアクセス用の設定保存

デプロイされた MCP Server を呼び出す前に、エージェント ARN（Step 4 から取得）と Cognito 設定を AWS Systems Manager Parameter Store と AWS Secrets Manager に保存して、簡単に取得できるようにします。

deploy.py の `--step5` オプションを実行すると、以下の処理が行われます。

1. Cognito 認証情報を AWS Secrets Manager に保存
2. エージェント ARN を AWS Systems Manager Parameter Store に保存

これにより、Client アプリケーションが必要な認証情報とエンドポイント情報を簡単に取得できるようになります。

```bash
uv run deploy.py --step5

# Auth の確認
uv run deploy.py --test-auth
```

## Step 6: MCP Client の使用

client.ts と client.py は、どちらも同じ機能を提供する MCP Client の実装です。言語の好みに応じて、TypeScript 版または Python 版を選択できます。両方とも SigV4 認証を使用して AgentCore Runtime にアクセスする機能と、認証なしでローカル MCP Server にアクセスする機能を備えています。

また、client-oauth.ts は OAuth JWT Bearer Token 認証を使用して AgentCore Runtime にアクセスする機能を提供します。

```bash
uv run client.py --remote  # AgentCore Runtime に接続（SigV4認証）
uv run client.py --local   # ローカル Server に接続
```

TypeScript 版を使用する場合、

```bash
npm run mcp:remote             # AgentCore Runtime に接続（SigV4認証）
npm run mcp:local              # ローカル Server に接続
npm run mcp:remote:debug       # debug モード
npm run mcp:remote:oauth       # OAuth認証で接続
npm run mcp:remote:oauth:debug # OAuth認証でdebugモード
```

## deployment_config.json について

`deployment_config.json` ファイルは、deploy.py スクリプトによって作成および更新される設定ファイルです。このファイルには以下の情報が格納されます。ただし、元々の参考とした公式 samples の名残であり実運用上は全ての設定を AWS Secret Manager に保存することを推奨します。[Issue#5](https://github.com/littlemex/samples/issues/5)

- **cognito**: ユーザープール ID、Client ID、ベアラートークン、ディスカバリー URL
- **iam_role**: ロール名と ARN
- **docker**: リポジトリ名、イメージ URI、ECR URI
- **agent_runtime**: エージェント名、ARN、ステータス、作成日時

このファイルはべき等性を保ちながら更新されるため、デプロイプロセスを中断して再開することができます。また、Client アプリケーションがこの情報を利用して AgentCore Runtime に接続する際に利用しています。

## 🎉 おめでとうございます！

AgentCore Runtime を用いたシンプルな TypeScript ベースの MCP Server をデプロイして動作確認することができました！

## 1. MCP Server のステートレス設定はどうやるのか？

Amazon Bedrock AgentCore Runtime で MCP Server を実行する場合、ステートレス通信モデルの採用が必須要件となります。`src/README.md` に詳細が記載されていますが、主なポイントは以下の通りです。

MCP Server のステートレス設定は、主に StreamableHTTPServerTransport の設定によって実現されます。具体的には以下のコード部分が重要です：

```typescript
const isStateless = process.env.MCP_STATELESS === 'true' || process.env.NODE_ENV === 'production';

const transport = new LoggingStreamableHTTPServerTransport({
  sessionIdGenerator: undefined,  // セッション ID を生成しない（ステートレスモード）
  enableJsonResponse: true,
  stateless: isStateless,         // 明示的にステートレスモードを設定
});
```

ここでの重要なポイントは、

1. `sessionIdGenerator: undefined` を設定することで、トランスポートはセッション ID を生成せず、ステートレスモードで動作します
2. `stateless: isStateless` パラメータを明示的に設定することで、ステートレスモードを有効にします
3. 環境変数 `MCP_STATELESS=true` または `NODE_ENV=production` を設定することで、ステートレスモードを有効にできます

ステートレスモードでは、リクエスト間で状態が共有されず、各リクエストは独立して処理されます。これにより、Server は複数のインスタンスに分散されても一貫した動作が保証され、AgentCore Runtime の要件を満たします。

また、AgentCore Runtime の技術的な要件として、Server は `0.0.0.0` アドレスでリッスンし、ポート `8000` を使用する必要があります。これは環境変数 `PORT=8000` を設定することで実現できます。MCP エンドポイントは `/mcp` パスで公開する必要があります。

## 2. MCP Client で SigV4 認証でのアクセスはどうやっているのか？

このプロジェクトでは、TypeScript (client.ts) と Python (client.py) の両方で SigV4 認証を実装しています。SigV4 (Signature Version 4) は AWS サービスへのリクエストを認証するための標準的な方法です。

### TypeScript 実装 (client.ts)

TypeScript 版では、AWS SDK for JavaScript の `@aws-sdk/signature-v4` パッケージを使用しています。

```typescript
import { SignatureV4 } from '@aws-sdk/signature-v4';
import { Sha256 } from '@aws-crypto/sha256-js';
import { defaultProvider } from '@aws-sdk/credential-provider-node';

// SigV4 署名オブジェクトの初期化
this.sigv4 = new SignatureV4({
  service: 'bedrock-agentcore',
  region: region,
  credentials: defaultProvider(),
  sha256: Sha256,
  applyChecksum: false,
});

// リクエスト署名の追加
const signedRequest = await this.sigv4.sign(request);
```

ポイント
1. `defaultProvider()` を使用して EC2 インスタンスの IAM ロールや AWS CLI の設定から認証情報を自動的に取得
2. `service: 'bedrock-agentcore'` で AgentCore サービスを指定
3. `sign()` メソッドでリクエストに署名を追加

### Python 実装 (client.py)

Python 版では、boto3 ライブラリの `botocore.auth.SigV4Auth` クラスを使用しています。

```python
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

# SigV4 認証の準備
self.session = boto3.Session()
self.credentials = self.session.get_credentials()
self.sigv4 = SigV4Auth(self.credentials, 'bedrock-agentcore', region)

# リクエストオブジェクトを作成
request = AWSRequest(
    method='POST',
    url=self.url,
    data=data,
    headers={
        'Content-Type': 'application/json',
        'Accept': 'application/json, text/event-stream'
    }
)

# SigV4 署名を追加
self.sigv4.add_auth(request)
```

ポイント
1. `boto3.Session()` を使用して AWS 認証情報を取得
2. `SigV4Auth` オブジェクトを作成し、サービス名 'bedrock-agentcore' を指定
3. `add_auth()` メソッドでリクエストに署名を追加

両実装とも、HTTP リクエストヘッダーに Authorization ヘッダーを追加し、AWS の認証情報を使用して生成された署名を含めることで、AgentCore Runtime へのアクセスを実現しています。

## 3. AgentCore Runtime へのデプロイに関する制約は何があるのか？

Amazon Bedrock AgentCore Runtime へのデプロイには、いくつかの重要な制約があります。

### ホスティング環境の制約

1. **コンテナ化の要件**：MCP Server は Docker コンテナとしてパッケージ化する必要があります
2. **アーキテクチャ**：ARM64 アーキテクチャをサポートする必要があります（deploy.py では `--platform linux/arm64` を指定）
3. **イメージレジストリ**：Amazon ECR (Elastic Container Registry) を使用する必要があります

### ネットワーク制約

1. **ホスト**：`0.0.0.0` でリッスンする必要があります
2. **ポート**：`8000` を使用する必要があります
3. **エンドポイント**：`/mcp` パスで MCP エンドポイントを公開する必要があります
4. **トランスポート**：ステートレス `streamable-http` トランスポートを使用する必要があります

### 認証制約

1. **認証方式**：Inbound Auth には AWS IAM と JWT Bearer Token の二種類のアクセス制御方式があります
2. **JWT 認証**：JWT Bearer Token を使用する場合は、IdP（例：Amazon Cognito）が必要です
3. **IAM ロール**：AgentCore Runtime 用の特定の権限を持つ IAM ロールが必要です

### プロトコル制約

1. **MCP バージョン**：サポートされている MCP プロトコルバージョンを使用する必要があります
2. **ステートレス通信**：リクエスト間で状態を保持しないステートレス通信モデルが必要です

これらの制約を満たすことで、AgentCore Runtime 上で MCP Server を正常に実行できます。deploy.py スクリプトは、これらの制約を考慮して設計しています。

## 4. AgentCore Runtime のデプロイスクリプトはどうなっているのか？

deploy.py スクリプトは、MCP Server を AgentCore Runtime にデプロイするための包括的なプロセスを自動化しています。このスクリプトは複数のステップに分かれており、各ステップは `--step<番号>` オプションで個別に実行できます。

### 主要なステップ

1. **Cognito 設定 (--step1)**
   - Amazon Cognito ユーザープールとアプリケーション Client を作成
   - JWT Bearer Token 認証のための設定を行う
   - 作成したリソース情報を deployment_config.json に保存

2. **IAM ロール作成 (--step2)**
   - AgentCore Runtime 用の IAM ロールを作成または更新
   - Bedrock サービス、ECR、CloudWatch Logs、X-Ray などへのアクセス権限を付与
   - ロール情報を deployment_config.json に保存

3. **MCP Server の作成 (--step3)**
   - 今回はすでに作ってあるが必要に応じて MCP Server を構築
   - echo でコメントを出すのみ
   - 必要に応じて MCP Server のテスト等を実装する

4. **Docker デプロイメント (--step4)**
   - Amazon ECR リポジトリの作成（存在しない場合）
   - Docker ビルダーの作成と設定
   - ARM64 アーキテクチャ用の Docker イメージをビルド
   - イメージを ECR にプッシュ
   - AgentCore Runtime の作成と設定
   - デプロイ情報を deployment_config.json に保存

5. **設定保存 (--step5)**
   - Cognito 認証情報を AWS Secrets Manager に保存
   - エージェント ARN を AWS Systems Manager Parameter Store に保存
   - Client アプリケーションが必要な情報を取得できるようにする

### 重要な実装ポイント

1. **べき等性**：スクリプトはべき等性を保ち、同じコマンドを複数回実行しても動作します
2. **エラーハンドリング**：各ステップで詳細なエラーハンドリングを実装しています
3. **設定管理**：deployment_config.json ファイルを使用して設定を保存・管理します
4. **認証テスト**：SigV4 と OAuth Bearer Token の両方の認証方法をテストする機能があります
5. **ロール更新**：既存の IAM ロールを最新の権限で自動的に更新します

```bash
# 全ステップを一度に実行
uv run deploy.py --all

# OAuth認証を使用して全ステップを実行
uv run deploy.py --all --oauth

# 個別のステップを実行
uv run deploy.py --step1  # Cognito 設定
uv run deploy.py --step2  # IAM ロール作成
uv run deploy.py --step4  # Docker デプロイメント
uv run deploy.py --step4 --oauth  # OAuth認証を使用してデプロイ
uv run deploy.py --step5  # 設定保存

# 現在の設定状態を表示
uv run deploy.py --status

# エージェントのステータスを確認
uv run deploy.py --check-status

# トークンを更新
uv run deploy.py --update-token

# 認証メソッドテストを実行（SigV4とOAuth Bearer Tokenの両方をテスト）
uv run deploy.py --test-auth

# SigV4 認証を使用して AgentCore Runtime の MCP ツールリストを取得
uv run deploy.py --sigv4-list-tools

# 実行ロールにポリシーを適用
uv run deploy.py --put-role-policy [--role-name <role-name>] [--policy-name <policy-name>]

# 実行ロールのポリシーを取得
uv run deploy.py --get-role-policy [--role-name <role-name>] [--policy-name <policy-name>]

# 現在の実行ロールの詳細情報を表示
uv run deploy.py --show-current-role
```

このスクリプトは、AWS SDK for Python (boto3) を使用して AWS サービスとやり取りし、Docker コマンドを実行して MCP Server をビルドおよびデプロイします。utils.py モジュールには、Cognito 設定、IAM ロール作成、認証テストなどの補助機能が実装されています。

## MCP Inspector から AgentCore Runtime に接続してみよう

MCP Inspector から AgentCore Runtime に接続してみてください。うまく接続できないはずです。
なぜか考えたり調べたりしてみましょう。`/answer/README.md` に回答が記載されています。
