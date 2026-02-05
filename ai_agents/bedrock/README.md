# AWS Bedrock Responses API - Lambda MCP 統合

AWS Bedrock Responses API と Lambda MCP プロトコルの実装サンプル。

## 実行手順

### 1. Lambda 関数のデプロイ

```bash
./deploy.sh
```

### 2. 環境変数の設定

```bash
cd test
cp .env.example .env
# .env ファイルを編集して、デプロイした Lambda の ARN を設定
```

### 3. テストの実行

```bash
python3 run_all_tests.py
```

## 実装内容

- **lambda-standard/**: Standard Lambda（VPC なし）の MCP ハンドラ
- **lambda-vpc/**: VPC Lambda の MCP ハンドラ
- **test/**: 統合テストスクリプト
- **deploy.sh**: Lambda 関数のデプロイスクリプト

## 検証項目

1. OpenAI 互換エンドポイント基本呼び出し
2. Lambda MCP 統合（tools/list, tools/call）
3. VPC Lambda
4. カスタム属性の伝播
5. パフォーマンス測定
6. ペイロードサイズ上限（1KB〜7MB）
7. GPT-OSS シーケンス長上限（128K トークン）
8. エラーハンドリング

## 必要な権限

- Lambda 関数の作成・更新
- IAM ロールの作成
- VPC 設定（VPC Lambda の場合）
- Bedrock の実行権限

## 参考

詳細な検証結果は Zenn 記事を参照してください。
