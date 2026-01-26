# TorchNeuron Code Server - CDK版

AWS Trainium/Inferentia用のDeep Learning AMI NeuronでCode Serverを起動するCDKプロジェクトです。

## 📖 背景

### なぜCDKを使うのか？

このプロジェクトは、**EC2 Capacity BlockをCloudFormationで使用できない制限**を回避するためにCDKを採用しています。

#### CloudFormationの制限

EC2 Capacity Blockを使用するには、以下の**2つのプロパティを同時に設定**する必要があります：

1. **`InstanceMarketOptions.MarketType = "capacity-block"`**
2. **`CapacityReservationSpecification.CapacityReservationTarget`**

しかし、CloudFormationの`AWS::EC2::Instance`リソースには以下の制限があります：

| プロパティ | CloudFormation対応 | 公式ドキュメント |
|-----------|-------------------|-----------------|
| `InstanceMarketOptions` | ❌ **サポートされていない** | [AWS::EC2::Instance - CloudFormation](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-ec2-instance.html) |
| `CapacityReservationSpecification` | ✅ サポート済み | [AWS::EC2::Instance - Properties](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-ec2-instance.html#cfn-ec2-instance-capacityreservationspecification) |

> **公式ドキュメントより:**
>
> "The `AWS::EC2::Instance` resource does not support the `InstanceMarketOptions` property. To use Capacity Blocks, you must use a Launch Template."
>
> 参考: [EC2 Capacity Blocks for ML - User Guide](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-capacity-blocks.html)

#### CDKによる解決方法

CDKでは**Launch Template**（`AWS::EC2::LaunchTemplate`）を使用することで、この制限を回避できます：

```typescript
// Launch Templateで両方のプロパティを設定可能
const launchTemplate = new ec2.CfnLaunchTemplate(this, 'LaunchTemplate', {
  launchTemplateData: {
    // ✅ InstanceMarketOptionsを設定可能
    instanceMarketOptions: {
      marketType: 'capacity-block',
    },
    // ✅ CapacityReservationSpecificationも設定可能
    capacityReservationSpecification: {
      capacityReservationTarget: {
        capacityReservationId: props.capacityReservationId,
      },
    },
  },
});

// Launch Templateを使用してインスタンスを起動
new ec2.CfnInstance(this, 'Instance', {
  launchTemplate: {
    launchTemplateId: launchTemplate.ref,
    version: launchTemplate.attrLatestVersionNumber,
  },
});
```

参考:
- [AWS::EC2::LaunchTemplate - CloudFormation](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-ec2-launchtemplate.html)
- [InstanceMarketOptionsRequest - EC2 API Reference](https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_InstanceMarketOptionsRequest.html)

**CDKの利点:**
- TypeScriptの型安全性により、Launch Templateの複雑な設定を扱いやすい
- CloudFormationテンプレートを直接記述するよりも保守性が高い
- プログラマティックに条件分岐や動的な設定が可能

## ✨ 特徴

- **Capacity Block管理**: キャパシティブロックの検索・購入・管理を一括で実行
- **Parameter Store統合**: キャパシティブロック情報を自動保存・読み込み
- **セキュリティグループ自動設定**: IPアドレスベースのアクセス制御を自動化
- **最新AMI自動取得**: SSM Parameter Storeから最新のDeep Learning AMI Neuronを自動取得
- **設定ファイル管理**: `config.json`で設定を一元管理、AMI IDなどをハードコードしない
- **SSM接続**: Session Manager経由での安全なアクセス
- **自動パスワード生成**: Secrets Managerで安全なパスワード管理

## 📋 前提条件

- AWS CLI設定済み
- Node.js 18以上
- AWS CDK CLI（プロジェクト内にインストール済み）
- Capacity Block予約（Capacity Block使用時）

## 🚀 使用方法

### ステップ1: Capacity Block管理（Capacity Block使用時のみ）

Capacity Blockを使用する場合、まず利用可能なブロックを検索・購入します：

```bash
# 1. 利用可能なCapacity Blockを検索（24時間）
./scripts/manage-capacity-block.sh search -t trn2.3xlarge -d 24 -r sa-east-1

# 2. Capacity Blockを購入
./scripts/manage-capacity-block.sh purchase \
  --offering-id cb-XXXXX \
  --start-time 2026-01-27T00:00:00Z \
  -r sa-east-1

# 購入時に自動的にParameter Storeへの保存確認が表示されます（yes推奨）

# 3. Parameter Storeから読み込み（確認）
./scripts/manage-capacity-block.sh load-params -r sa-east-1

# 4. 購入済みCapacity Blockの一覧表示
./scripts/manage-capacity-block.sh list -r sa-east-1

# 5. Capacity Blockの詳細表示
./scripts/manage-capacity-block.sh describe --reservation-id cr-XXXXX -r sa-east-1
```

**Parameter Store統合の利点:**
- Reservation IDとSubnet IDを手動で管理する必要がなくなります
- デプロイ時に自動的にParameter Storeから読み込まれます
- リージョンごとに個別に管理されます（`/capacity-block/{region}/reservation-id`）

### ステップ2: デプロイ

#### クイックスタート（推奨）

統合スクリプトを使用して、デプロイからCode Serverセットアップまで一括で実行：

```bash
# 1. 依存関係のインストール（初回のみ）
npm install

# 2. CDKブートストラップ（初回のみ）
npx cdk bootstrap aws://ACCOUNT_ID/sa-east-1

# 3. デプロイ + Code Serverセットアップ
./scripts/deploy.sh
```

#### Capacity Blockを使用する場合

Parameter Storeに保存済みの場合（IDの指定不要）:
```bash
./scripts/deploy.sh --use-capacity-block -r sa-east-1
```

手動でIDを指定する場合:
```bash
./scripts/deploy.sh \
  --use-capacity-block \
  --capacity-reservation-id cr-XXXXX \
  --subnet-id subnet-XXXXX \
  -r sa-east-1
```

#### 特定IPからのアクセスを許可

```bash
# セキュリティグループに自動的にインバウンドルールを追加
./scripts/deploy.sh --allowed-ip 203.0.113.10/32 -r sa-east-1
```

#### その他のオプション

```bash
# インスタンスタイプを指定
./scripts/deploy.sh -t inf2.8xlarge

# デプロイ済みスタックの情報を表示
./scripts/deploy.sh --show-info -r sa-east-1

# Code Serverセットアップをスキップ
./scripts/deploy.sh --skip-setup

# スタック削除
./scripts/deploy.sh --destroy
```

---

### 手動デプロイ（個別実行）

#### 1. 依存関係のインストール

```bash
npm install
```

#### 2. 設定ファイルの確認

`config.json`で設定を確認・変更できます：

```json
{
  "regions": {
    "sa-east-1": {
      "amiSsmParameter": "/aws/service/neuron/dlami/multi-framework/ubuntu-24.04/latest/image_id"
    }
  },
  "defaultVolumeSize": 500,
  "codeServerUser": "coder",
  "homeFolder": "/work"
}
```

#### 3. CDKのブートストラップ（初回のみ）

```bash
npx cdk bootstrap aws://ACCOUNT_ID/REGION
```

例：
```bash
npx cdk bootstrap aws://776010787911/sa-east-1
```

#### 4. CDKデプロイ

##### 通常のデプロイ（Capacity Blockなし）

```bash
AWS_REGION=sa-east-1 npm run deploy -- --require-approval never
```

##### Capacity Blockを使用したデプロイ

```bash
AWS_REGION=sa-east-1 npm run deploy -- \
  -c useCapacityBlock=true \
  -c capacityReservationId=cr-XXXXX \
  -c subnetId=subnet-XXXXX \
  --require-approval never
```

**パラメータ説明**:
- `useCapacityBlock`: Capacity Blockを使用する場合は`true`
- `capacityReservationId`: Capacity Reservation ID（例: `cr-06670284d2d99ffea`）
- `subnetId`: Capacity ReservationのAZと同じAZのサブネットID
- `instanceType`: インスタンスタイプ（デフォルト: `trn2.3xlarge`）
- `volumeSize`: EBSボリュームサイズ（デフォルト: 500GB）

#### 5. Code Serverセットアップ（手動）

デプロイ後、Code Serverをセットアップ：

```bash
# インスタンスIDを取得
INSTANCE_ID=$(aws cloudformation describe-stacks \
  --stack-name TorchNeuron-CDK \
  --region sa-east-1 \
  --query 'Stacks[0].Outputs[?OutputKey==`InstanceId`].OutputValue' \
  --output text)

# Secret ARNを取得
SECRET_ARN=$(aws secretsmanager list-secrets \
  --region sa-east-1 \
  --query "SecretList[?contains(Name, 'CodeServerPassword')].ARN | [0]" \
  --output text)

# セットアップ実行
./scripts/setup-code-server.sh \
  -i $INSTANCE_ID \
  -r sa-east-1 \
  -s $SECRET_ARN \
  --wait
```

#### 6. 接続

デプロイ完了後、Code Serverにアクセス：

```bash
# パスワード取得
aws secretsmanager get-secret-value \
  --secret-id $SECRET_ARN \
  --region sa-east-1 \
  --query 'SecretString' \
  --output text

# SSM接続
aws ssm start-session --target $INSTANCE_ID --region sa-east-1

# ブラウザでアクセス
# http://[PUBLIC_DNS]
```

#### 7. 削除

```bash
AWS_REGION=sa-east-1 npm run destroy
```

## 📁 ファイル構成

```
.
├── bin/
│   └── app.ts                           # CDKアプリケーションエントリーポイント
├── lib/
│   └── torch-neuron-stack.ts            # メインスタック定義
├── scripts/
│   ├── deploy.sh                        # 統合デプロイスクリプト（デプロイ+セットアップ）
│   ├── manage-capacity-block.sh         # Capacity Block管理スクリプト
│   ├── run-tasks.sh                     # 汎用タスクランナー（JSON定義を実行）
│   └── setup-code-server.sh             # Code Serverセットアップスクリプト
├── tasks/
│   └── code-server-setup.json           # Code Serverセットアップタスク定義（17ステップ）
├── config.json                          # 設定ファイル（AMI、リージョン等）
├── cdk.json                             # CDK設定
├── package.json                         # Node.js依存関係
└── README.md                            # このファイル
```

### スクリプトの詳細

#### `scripts/manage-capacity-block.sh`
Capacity Blockの検索・購入・管理を行うスクリプト。

**コマンド:**
- `search`: 利用可能なCapacity Blockを検索
- `purchase`: Capacity Blockを購入（自動でParameter Store保存確認）
- `list`: 購入済みCapacity Blockを一覧表示
- `describe`: Capacity Blockの詳細情報を表示
- `cancel`: Capacity Blockをキャンセル
- `save-params`: パラメータをParameter Storeに保存
- `load-params`: Parameter Storeからパラメータを読み込み

**Parameter Store統合:**
- 購入時に自動的にReservation IDとSubnet IDをParameter Storeに保存
- リージョンごとに個別管理（`/capacity-block/{region}/reservation-id`）
- deploy.shで自動読み込み（IDの手動指定不要）

#### `scripts/deploy.sh`
CDKデプロイとCode Serverセットアップを統合した便利スクリプト。

**特徴:**
- CDKデプロイから自動でCode Serverセットアップまで実行
- Capacity Block対応（Parameter Storeから自動読み込み）
- セキュリティグループ自動設定（`--allowed-ip`オプション）
- インスタンスタイプやリージョンの柔軟な指定
- デプロイ済みスタック情報表示（`--show-info`オプション）
- スタック削除機能

#### `scripts/setup-code-server.sh`
Code Serverをインスタンスにセットアップする汎用スクリプト。元の`setup_coder_ubuntu24.sh`の全機能を含む完全版。

**特徴:**
- SSM send-commandを使用した安全なセットアップ
- 任意のEC2インスタンスに適用可能（Neuron以外でも使用可）
- パスワードの柔軟な指定（Secrets Manager、直接指定、ランダム生成）
- **失敗箇所からの再開機能**（`--start-from`オプション）
- **ドライラン機能**（`--dry-run`、実行前の確認）
- **状態管理**（`--clean-state`で最初からやり直し）
- 詳細なログ出力

**使用例:**
```bash
# 基本的な使用
./scripts/setup-code-server.sh -i i-XXXXX -s arn:aws:secretsmanager:...

# 失敗したタスクから再開
./scripts/setup-code-server.sh -i i-XXXXX -s arn:... --start-from 09-install-code-server

# ドライラン（実行内容の確認）
./scripts/setup-code-server.sh -i i-XXXXX --dry-run

# 状態をクリーンして最初から実行
./scripts/setup-code-server.sh -i i-XXXXX -s arn:... --clean-state
```

**状態管理:**
- 進捗状態は`/tmp/task-state-{instance-id}.json`に保存
- 完了済みタスクは自動でスキップ（冪等性）
- 失敗時は停止し、修正後に再開可能

**セットアップ内容（17ステップ）:**

| ステップ | タスク名 | 説明 | 冪等性 |
|---------|---------|------|-------|
| 01 | configure-needrestart | needrestart設定の変更 | ✅ 完全 |
| 02 | cleanup-neuron-repo | 古いNeuronリポジトリ削除 | ✅ 完全 |
| 03 | wait-for-dpkg-lock | dpkgロック待機（最大5分） | ✅ 完全 |
| 04 | install-base-packages | 基本パッケージインストール（nginx, nodejs, python3等） | ✅ 完全 |
| 05 | create-user | ユーザー作成とパスワード設定 | ✅ 完全 |
| 06 | configure-sudo | sudo権限設定（パスワードなし） | ⚠️ 上書き |
| 07 | create-home-dir | ホームディレクトリ作成（/work） | ✅ 完全 |
| 08 | configure-profile | プロファイル設定（.bashrc、環境変数） | ⚠️ 上書き |
| 09 | install-code-server | Code Serverインストール | ✅ 完全 |
| 10 | configure-code-server | Code Server設定（argon2ハッシュパスワード） | ⚠️ 上書き |
| 11 | configure-vscode-settings | VS Code User設定（テレメトリ無効化等） | ⚠️ 上書き |
| 12 | configure-nginx | nginx設定（リバースプロキシ、デフォルトサイト削除） | ⚠️ 上書き |
| 13 | create-systemd-service | systemdサービスUnit作成 | ⚠️ 上書き |
| 14 | enable-and-start-service | サービス有効化と起動 | ⚠️ 再起動 |
| 15 | install-vscode-extensions | VS Code拡張機能（AWS Toolkit, Amazon Q, Cline） | ⚠️ 再インストール |
| 16 | create-code-command | `code`コマンドのラッパースクリプト作成 | ⚠️ 上書き |
| 17 | verify-installation | インストール検証（サービス状態、ポート確認） | ✅ 完全 |

- ✅ 完全: 何度実行しても安全
- ⚠️ 上書き/再起動/再インストール: 設定ファイルを上書きまたはサービス再起動（意図的な動作）

#### `scripts/run-tasks.sh`
JSONタスク定義ファイルを実行する汎用タスクランナー。

**特徴:**
- JSON形式のタスク定義を読み込み、順次実行
- 変数置換機能（`{{VAR_NAME}}`形式）
- 状態ファイルによる進捗管理
- 冪等性保証（完了済みタスクはスキップ）
- 失敗箇所からの再開機能
- ドライラン機能

#### `tasks/code-server-setup.json`
Code Serverセットアップの全手順を定義したJSONファイル（17タスク）。

**変数:**
- `USER`: Code Serverユーザー名（デフォルト: `coder`）
- `PASSWORD`: Code Serverパスワード
- `HOME_DIR`: ホームディレクトリ（デフォルト: `/work`）
- `INTERNAL_PORT`: Code Server内部ポート（デフォルト: `8080`）
- `NGINX_PORT`: nginx外部ポート（デフォルト: `80`）

## 🔧 設定のカスタマイズ

### リージョンの追加

`config.json`に新しいリージョンを追加：

```json
{
  "regions": {
    "us-east-1": {
      "amiSsmParameter": "/aws/service/neuron/dlami/multi-framework/ubuntu-24.04/latest/image_id"
    },
    "sa-east-1": {
      "amiSsmParameter": "/aws/service/neuron/dlami/multi-framework/ubuntu-24.04/latest/image_id"
    }
  }
}
```

### インスタンスタイプの変更

デプロイ時に指定：

```bash
./scripts/deploy.sh -t inf2.8xlarge -r sa-east-1
```

### Code Serverセットアップのカスタマイズ

#### タスクの追加

`tasks/code-server-setup.json`の`tasks`配列に新しいタスクを追加：

```json
{
  "id": "18-custom-task",
  "name": "Custom Task",
  "description": "カスタムタスクの説明",
  "commands": [
    "echo 'Running custom task for user: {{USER}}'",
    "# 追加のコマンド"
  ]
}
```

#### 変数の変更

`tasks/code-server-setup.json`の`variables`セクションを編集：

```json
{
  "variables": {
    "USER": "coder",
    "PASSWORD": "",
    "HOME_DIR": "/work",
    "INTERNAL_PORT": "8080",
    "NGINX_PORT": "80"
  }
}
```

変数は`{{VAR_NAME}}`形式でタスク内で参照できます。

#### タスク順序の変更

JSON内のタスクの順序を入れ替えるだけで実行順序が変更されます（IDは任意）。

## ⚠️ 重要な注意事項

### Capacity Block使用時

1. **Subnet AZ一致**: SubnetのAZとCapacity ReservationのAZが一致している必要があります
   ```bash
   # Capacity ReservationのAZ確認
   aws ec2 describe-capacity-reservations \
     --capacity-reservation-ids cr-XXXXX \
     --region sa-east-1 \
     --query 'CapacityReservations[0].AvailabilityZone'

   # SubnetのAZ確認
   aws ec2 describe-subnets \
     --subnet-ids subnet-XXXXX \
     --region sa-east-1 \
     --query 'Subnets[0].AvailabilityZone'
   ```

2. **Launch Template必須**: Capacity Blockは`AWS::EC2::Instance`の`InstanceMarketOptions`プロパティをサポートしないため、Launch Templateを使用します

3. **両方のプロパティ必要**:
   - `InstanceMarketOptions.MarketType = "capacity-block"`
   - `CapacityReservationSpecification.CapacityReservationTarget`

## 🐛 トラブルシューティング

### AMI IDが見つからないエラー

SSM Parameterが存在するか確認：

```bash
aws ssm get-parameter \
  --name /aws/service/neuron/dlami/multi-framework/ubuntu-24.04/latest/image_id \
  --region sa-east-1
```

### Capacity Reservation利用不可

Capacity Reservationの状態を確認：

```bash
aws ec2 describe-capacity-reservations \
  --capacity-reservation-ids cr-XXXXX \
  --region sa-east-1 \
  --query 'CapacityReservations[0].[State,AvailableInstanceCount]'
```

### Parameter Storeの値を確認

保存されたCapacity Block情報を確認：

```bash
# Reservation ID確認
aws ssm get-parameter \
  --name /capacity-block/sa-east-1/reservation-id \
  --region sa-east-1

# Subnet ID確認
aws ssm get-parameter \
  --name /capacity-block/sa-east-1/subnet-id \
  --region sa-east-1
```

### Code Serverにアクセスできない

1. セキュリティグループを確認：
```bash
# インスタンスのセキュリティグループを確認
aws ec2 describe-instances \
  --instance-ids i-XXXXX \
  --region sa-east-1 \
  --query 'Reservations[0].Instances[0].SecurityGroups'
```

2. nginxの状態を確認：
```bash
# SSM経由で確認
aws ssm start-session --target i-XXXXX --region sa-east-1
sudo systemctl status nginx
sudo systemctl status code-server@coder
```

3. セキュリティグループルールを手動追加：
```bash
./scripts/deploy.sh --show-info -r sa-east-1  # Security Group IDを取得
aws ec2 authorize-security-group-ingress \
  --group-id sg-XXXXX \
  --protocol tcp \
  --port 80 \
  --cidr YOUR_IP/32 \
  --region sa-east-1
```

### Code Serverセットアップが途中で失敗した場合

1. エラーメッセージとタスクIDを確認
2. 問題を修正（パッケージの依存関係、ネットワーク等）
3. 失敗したタスクから再開：
```bash
# 例: タスク09で失敗した場合
./scripts/setup-code-server.sh \
  -i i-XXXXX \
  -r sa-east-1 \
  -s arn:aws:secretsmanager:... \
  --start-from 09-install-code-server
```

4. SSM Command Invocationで詳細ログを確認：
```bash
# エラーメッセージに表示されたCommand IDを使用
aws ssm get-command-invocation \
  --command-id COMMAND_ID \
  --instance-id i-XXXXX \
  --region sa-east-1
```

5. 状態ファイルをリセットして最初からやり直す場合：
```bash
./scripts/setup-code-server.sh \
  -i i-XXXXX \
  -r sa-east-1 \
  -s arn:aws:secretsmanager:... \
  --clean-state
```

## 📚 参考資料

- [AWS CDK Documentation](https://docs.aws.amazon.com/cdk/)
- [AWS Neuron Documentation](https://awsdocs-neuron.readthedocs-hosted.com/)
- [EC2 Capacity Blocks](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-capacity-blocks.html)
