# AgentCore Runtime - Simple MCP Server

## 概要

このチュートリアルでは、Amazon Bedrock AgentCore ランタイム環境を使用して TypeScript ベースの MCP（Model Context Protocol）Server をホストする方法を説明します。現状 Toolkit は Python を期待しているためそれ以外の言語の場合は[カスタムフローを使用してデプロイ](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/getting-started-custom.html)する必要があります。一般提供開始と AWS CDK 等の IaC の対応が望まれます。

### チュートリアル概要

- IdP は Amazon Cognito を使用して JWT トークンアクセス
- Typescript ベースの MCP Server を利用
- AgentCore Runtime の MCP では Streamable HTTP のステートレスをサポートが必要

## 前提条件

このチュートリアルを実行するには以下が必要です。

- Node.js v22 以降（MCP Server 用）
- Python 3.10+（MCP Client 用）
- Docker
- Amazon ECR（Elastic Container Registry）Docker イメージ保存用  
- Bedrock AgentCore へのアクセス権を持つ AWS アカウント  

## AgentCore Runtime 制約

- **ホスト:** `0.0.0.0`  
- **ポート:** `8000`  
- **トランスポート:** ステートレス `streamable-http`  
- **エンドポイントパス:** `POST /mcp`  

## 事前準備

環境に応じて .env を修正してください。

```bash
uv venv && source .venv/bin/activate
uv sync

cp .env.example .env
```

## Step 1: 認証用の Amazon Cognito 設定

AgentCore Runtime には認証が必要です。Amazon Cognito を使用して、デプロイされた MCP Server へのアクセス用 JWT トークンを提供します。Runtime の場合、Inbound Auth には AWS IAM と JWT Bearer Token の二種類のアクセス制御方式がありますが、今回は JWT Bearer Token を用いたアクセスを実装するため IdP が必要です。今回は Amazon Cognito を利用するため Step 1 では Amazon Cognito を設定します。

AgentCore Runtime で使用するのに必要な Cognito ユーザープールとアプリケーションクライアントが正常に作成されることが期待です。`deployment_config.json` に作成したリソース情報が追記されていきます。

```bash
# javascript SDK は機能不足のため Python を利用したスクリプトでデプロイします
uv run deploy.py --step1
```

```bash
✓ Cognito 設定完了

  ユーザープール ID: N/A

  Client ID: 7jatnr1xxxx

  Discovery URL: https://cognito-idp.us-east-1.amazonaws.com/us-east-1_Hxxx/.well-known/openid-configuration
```

## ステップ 2: IAM 実行ロールの作成

開始する前に、AgentCore Runtime 用の IAM ロールを作成しましょう。このロールは、Runtime が動作するために必要な権限を提供します。

```bash
uv run deploy.py --step2
```

## ステップ 3: MCP Server の作成

次に、Chapter14 で作成したシンプルな MCP Server を AgentCore Runtime で要求される制約に応じて修正しました。`PORT=8000` を利用するために環境変数で PORT 指定するなどの変更が多少入っています。**変更箇所を確認してみましょう。**


```bash
# 依存関係のインストールと build
npm install && npm run build

# ローカルで Server 立ち上げ
PORT=13000 npm run start
```

## ステップ 4: Docker 経由での MCP Server デプロイメント

スターターツールキットを使用せずに MCP Server をデプロイするための手動手順です。イメージのビルド、Amazon ECR へのプッシュを実施します。

```bash
uv run deploy.py --step4
```

## ステップ 5: リモートアクセス用の設定保存

デプロイされた MCP Server を呼び出す前に、エージェント ARN（ステップ 4 から取得）と Cognito 設定を AWS Systems Manager Parameter Store と AWS Secrets Manager に保存して、簡単に取得できるようにしましょう：


## ステップ 6: リモートテスト Client の作成

次に、デプロイされた MCP Server をテストする Client を作成しましょう。この Client は、AWS から必要な認証情報を取得し、デプロイされた Server に接続します：

## ステップ 7: デプロイされた MCP Server のテスト

リモート Client を使用して、デプロイされた MCP Server をテストしましょう：

```bash
python my_mcp_client_remote.py
```

## ステップ 8: MCP ツールのリモート呼び出し

次に、ツールをリストするだけでなく、実際に呼び出して完全な MCP 機能を実証する拡張 Client を作成しましょう：

### invoke_mcp_tools.py



### ツール呼び出しのテスト

MCP ツールを実際に呼び出してテストしましょう：

```bash
python invoke_mcp_tools.py
```

## 次のステップ

AgentCore ランタイムに MCP Server を正常にデプロイできたので、次のことができます：

1. **ツールの追加**: MCP Server に追加のツールを拡張する
2. **カスタム認証**: カスタム JWT 認証機能を実装する
3. **統合**: 他の AgentCore サービスと統合する

## 🎉 おめでとうございます！

AgentCore Runtime を用いたシンプルな Typescript ベースの MCP Server をデプロイして動作確認することができました！

