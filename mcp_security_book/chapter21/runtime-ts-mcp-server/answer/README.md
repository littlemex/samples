# AgentCore Runtime での OAuth 認証の詳細と実装ガイド

## MCP Inspector から AgentCore Runtime に接続できない理由

MCP Inspector から AgentCore Runtime に接続してみると、うまく接続できなかったはずです。
これは MCP Server の起動時にデフォルトで SigV4 認証が利用されるためです。

そして重要なポイントは、**SigV4 認証の仕組みによる認可は MCP 仕様ではサポートされていない**ため MCP Inspector やそのほかの一般的な MCP Client では SigV4 認証での接続ができません。AI Agent を自作する際には今回作成した client.ts のような実装を追加してあげれば AI Agent 側の MCP Client から AgentCore Runtime の MCP Server を SigV4 認証で利用することは可能です。

AgentCore Runtime では JWT Bearer Token 認証をサポートしており、deploy.py でも Cognito を IdP として利用できるように作ってあります。
**AgentCore Runtime の設定を JWT Bearer Token 認証に変更すれば問題なく MCP Inspector で接続できるようになります。**

## ID トークンと Access トークンの違い

OAuth 2.0 と OpenID Connect の認証フローでは、ID トークンと Access トークンの 2 種類のトークンが使用されます。これらは異なる目的と用途を持っています。

### ID トークン（ID Token）

- **目的**: ユーザーの身元（アイデンティティ）を証明するためのトークン
- **規格**: OpenID Connect (OIDC) の一部として定義されている
- **内容**: ユーザーに関する情報（ユーザー名、メールアドレス、電話番号など）を含む
- **形式**: JWT (JSON Web Token) 形式
- **用途**: クライアントアプリケーションがユーザーを認証するために使用
- **特徴**: 認証（Authentication）に関するトークン

### Access トークン（Access Token）

- **目的**: 保護されたリソースへのアクセス権限を表すトークン
- **規格**: OAuth 2.0 の一部として定義されている
- **内容**: スコープ（権限の範囲）に関する情報を含む
- **形式**: 必ずしも JWT である必要はない（ただし、多くの場合 JWT が使用される）
- **用途**: API やその他の保護されたリソースにアクセスするために使用
- **特徴**: 認可（Authorization）に関するトークン

## Amazon Bedrock AgentCore Runtime での JWT Bearer Token 認証

Amazon Bedrock AgentCore Runtime の JWT Bearer Token 認証では、**Access トークン（アクセストークン）を使用することが推奨されています**。これは以下の理由によります。

1. AgentCore Runtime は保護されたリソースであり、アクセス権限の検証が必要です
2. AWS の公式ドキュメントによると、「呼び出し元のエンティティまたはユーザーがエージェントを呼び出す際、IdP 固有のアクセストークンを Authorization ヘッダーのベアラートークンとして渡します」と説明されています
3. Access トークンはユーザーの機密情報を含まないため、セキュリティ上のリスクが低くなります

Cognito から取得したトークンは、ペイロード内の `token_use` フィールドで区別できます。

- `"token_use": "id"` の場合は ID トークン
- `"token_use": "access"` の場合は Access トークン

## OAuth 認証の実装方法

AgentCore Runtime で OAuth JWT Bearer Token 認証を使用するには、以下の手順で実装します。

### 1. デプロイ手順

#### Step 1: Cognito 設定

まず、JWT Bearer Token 認証のために Amazon Cognito を設定します。

```bash
# Cognito ユーザープールとアプリケーション Client を作成
uv run deploy.py --step1
```

このコマンドは以下の処理を行います。

- Amazon Cognito ユーザープールの作成
- アプリケーション Client の作成
- ユーザーの作成と初期パスワードの設定
- JWT トークンの取得
- 設定情報の deployment_config.json への保存

#### Step 2: IAM ロールの作成

次に、AgentCore Runtime が使用する IAM ロールを作成します。

```bash
# IAM ロールを作成または更新
uv run deploy.py --step2
```

このコマンドは以下の処理を行います。

- AgentCore Runtime 用の IAM ロールの作成または更新
- 必要な権限（Bedrock、ECR、CloudWatch Logs、X-Ray など）の付与
- ロール情報の deployment_config.json への保存

#### Step 3: MCP Server の準備

MCP Server を準備してください。本さんぷるでは足し算と引き算のツールを提供する MCP Server が提供されます。

#### Step 4: OAuth 認証を使用した AgentCore Runtime のデプロイ

OAuth JWT Bearer Token 認証を使用して AgentCore Runtime をデプロイします。

```bash
# OAuth 認証を使用してデプロイ
uv run deploy.py --step4 --oauth
```

このコマンドは以下の処理を行います。

- Amazon ECR リポジトリの作成（存在しない場合）
- Docker イメージのビルドと ECR へのプッシュ
- OAuth 認証を使用した AgentCore Runtime の作成
- デプロイ情報の deployment_config.json への保存

`--oauth` オプションを指定することで、deploy.py は以下の設定を行います。

```python
create_params["authorizerConfiguration"] = {
    "customJWTAuthorizer": {
        "discoveryUrl": self.config["cognito"]["discovery_url"],
        "allowedClients": [self.config["cognito"]["client_id"]]  # Cognito では allowedClients を使用
    }
}
```

#### Step 5: 設定の保存

最後に、認証情報とエンドポイント情報を AWS Secrets Manager と Parameter Store に保存します。

```bash
# 設定を保存
uv run deploy.py --step5
```

このコマンドは以下の処理を行います：
- Cognito 認証情報を AWS Secrets Manager に保存
- エージェント ARN を AWS Systems Manager Parameter Store に保存

#### 一括デプロイ

すべてのステップを一度に実行する場合は、以下のコマンドを使用します。

```bash
# OAuth 認証を使用して全ステップを実行
uv run deploy.py --all --oauth
```

### 2. 動作確認手順

#### OAuth クライアントを使用した接続テスト

client-oauth.ts を使用して AgentCore Runtime に接続します。

```bash
# OAuth 認証で接続
npm run mcp:remote:oauth

# デバッグモードで接続
npm run mcp:remote:oauth:debug
```

client-oauth.ts は以下の機能を提供します。

- AWS Secrets Manager から Cognito 認証情報を取得
- AWS Parameter Store からエージェント ARN を取得
- JWT Bearer Token を使用して AgentCore Runtime に接続
- MCP ツールのリストと実行

#### トークンの更新

JWT トークンの有効期限が切れた場合は、以下のコマンドでトークンを更新できます。

```bash
# トークンを更新
uv run deploy.py --update-token
```

#### 認証テスト

SigV4 認証と OAuth 認証のどちらが有効になっているのかをテストするには、以下のコマンドを使用します。

```bash
# 認証テストを実行
uv run deploy.py --test-auth
```

このコマンドは以下のテストを実行します。

1. OAuth Bearer Token 認証テスト
2. SigV4 認証テスト（AWS CLI）
3. SigV4 認証テスト（awscurl）

#### MCP Inspector での接続

OAuth 認証を使用してデプロイした AgentCore Runtime には、MCP Inspector から接続できます。

1. MCP Inspector を起動します。
   ```bash
   npx @modelcontextprotocol/inspector
   ```

2. 接続設定で以下を指定します
   - URL: AgentCore Runtime の URL（`https://bedrock-agentcore.{region}.amazonaws.com/runtimes/{encoded-arn}/invocations?qualifier=DEFAULT`）、deploy.py の `--test-auth` を実行すれば URL 情報も出力されます。
   - API Token Authentication
     - Headr Name: Authorization
     - Bearer Token: `jq -r '.cognito.bearer_token' ../deployment_config.json` で取得できる Bearer Token

3. 接続ボタンをクリックして接続します。

## client-oauth.ts の使用方法

client-oauth.ts は OAuth JWT Bearer Token 認証を使用して AgentCore Runtime に接続するための TypeScript クライアントです。

### 主な機能

- AWS Secrets Manager と Parameter Store から設定を取得
- JWT トークンの検証と有効期限チェック
- OAuth 認証を使用した MCP リクエストの送信
- MCP ツールのリストと実行
- リソースとプロンプトのリスト取得

### 使用方法

```bash
# 基本的な使用方法
npm run mcp:remote:oauth

# デバッグモードで実行（詳細なログを表示）
npm run mcp:remote:oauth:debug
```

### エラー処理

client-oauth.ts には、以下のようなエラー処理機能が組み込まれています。

- JWT トークンの有効期限チェック
- トークン種類（ID トークンか Access トークン）の検証
- Audience 不一致エラーの詳細な診断
- エラー発生時の解決方法の提案

## トラブルシューティング

Cognito を利用しない場合には本サンプルの OAuth 実装では動作しない可能性があります。場合によっては設定で `allowedClients` ではなく `allowedAudience` を利用する必要があるかもしれません。

### 1. Claim 'aud' value mismatch with configuration

このエラーは、JWT トークンの `aud` クレームと AgentCore Runtime の設定が一致しない場合に発生します。
Amazon Cognito の Access トークンには `aud` クレームが含まれていません。代わりに `client_id` クレームが含まれています。

#### Cognito の場合はどう実装しているか。

deploy.py の `step4_docker_deployment` メソッドで、以下のように `allowedClients` を使用しています。`allowedAudience` を指定すると上記のようなエラーが発生します。

```python
create_params["authorizerConfiguration"] = {
    "customJWTAuthorizer": {
        "discoveryUrl": self.config["cognito"]["discovery_url"],
        "allowedClients": [self.config["cognito"]["client_id"]]  # allowedAudience ではなく allowedClients を使用
    }
}
```

### 2. トークンの有効期限切れ

JWT トークンの有効期限が切れると、401 Unauthorized エラーが発生します。

#### 解決方法

トークンを更新します。

```bash
uv run deploy.py --update-token
```

### 3. ID トークンと Access トークンの選択

AgentCore Runtime では Access トークンを使用することが推奨されていますが、ID トークンも使用できます。

参考: **[Authenticate and authorize with Inbound Auth and Outbound Auth](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-oauth.html)**

#### Access トークンを使用する場合

```python
# deploy.py の修正
tokens = reauthenticate_user(client_id)
self.config["cognito"]["access_token"] = tokens["access_token"]
```

```typescript
// client-oauth.ts の修正
const token = this.config.cognito.access_token;
```

#### ID トークンを使用する場合

動作確認していません。

```python
# deploy.py の修正
tokens = reauthenticate_user(client_id)
self.config["cognito"]["id_token"] = tokens["id_token"]
```

```typescript
// client-oauth.ts の修正
const token = this.config.cognito.id_token;
```

## Amazon Bedrock AgentCore JWT 認証の詳細

### 認証設定オプション

AgentCore Runtime の JWT 認証には、以下の 2 つの設定オプションがあります。

参考: **[Authenticate and authorize with Inbound Auth and Outbound Auth](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-oauth.html)**


#### 1. `allowedAudience`
- JWT トークンの `aud` クレームを検証
- Auth0 などの OAuth プロバイダーで使用
- 設定例：
```json
{
  "customJWTAuthorizer": {
    "discoveryUrl": "https://example.auth0.com/.well-known/openid-configuration",
    "allowedAudience": ["api-identifier"]
  }
}
```

#### 2. `allowedClients`
- JWT トークンの `client_id` クレームを検証
- **Amazon Cognito で推奨される方式**
- 設定例：
```json
{
  "customJWTAuthorizer": {
    "discoveryUrl": "https://cognito-idp.us-east-1.amazonaws.com/pool-id/.well-known/openid-configuration",
    "allowedClients": ["client-id"]
  }
}
```

### Amazon Cognito トークンの特性

#### Access トークンに含まれるクレーム
- `client_id`: Cognito クライアント ID
- `token_use`: "access"
- `scope`: 許可されたスコープ
- `sub`: ユーザー識別子

#### ID トークンに含まれるクレーム
- `aud`: オーディエンス（通常はクライアント ID）
- `token_use`: "id"
- `email`: ユーザーのメールアドレス
- `sub`: ユーザー識別子

#### 実際のトークン例（Access トークン）
```json
{
  "sub": "943874a8-f031-7046-a35d-0871ea382e53",
  "iss": "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_Obf5pLxxx",
  "client_id": "544nkebp1l1cvj67cel6ao18vb",
  "token_use": "access",
  "scope": "aws.cognito.signin.user.admin",
  "exp": 1756312142,
  "iat": 1756308542,
  "username": "testuser"
}
```

## 推奨設定パターン

### Amazon Cognito の場合
```json
{
  "customJWTAuthorizer": {
    "discoveryUrl": "https://cognito-idp.{region}.amazonaws.com/{pool-id}/.well-known/openid-configuration",
    "allowedClients": ["{client-id}"]
  }
}
```

### Auth0 の場合
```json
{
  "customJWTAuthorizer": {
    "discoveryUrl": "https://{domain}/.well-known/openid-configuration",
    "allowedAudience": ["{api-identifier}"]
  }
}
```

## まとめ

AgentCore Runtime での MCP Server の活用の基礎をマスターできたのではないでしょうか！