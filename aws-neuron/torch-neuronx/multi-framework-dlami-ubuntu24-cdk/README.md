# TorchNeuron Code Server - CDK版

AWS Trainium/Inferentia用のDeep Learning AMI NeuronでCode Serverを起動するCDKプロジェクトです。

## ✨ 特徴

- **Capacity Block対応**: EC2 Capacity Blockを使用した予約済みキャパシティでの起動
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

### 1. 依存関係のインストール

```bash
npm install
```

### 2. 設定ファイルの確認

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

### 3. CDKのブートストラップ（初回のみ）

```bash
npx cdk bootstrap aws://ACCOUNT_ID/REGION
```

例：
```bash
npx cdk bootstrap aws://776010787911/sa-east-1
```

### 4. デプロイ

#### 通常のデプロイ（Capacity Blockなし）

```bash
AWS_REGION=sa-east-1 npm run deploy -- --require-approval never
```

#### Capacity Blockを使用したデプロイ

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

### 5. 接続

デプロイ完了後、Outputsに表示されるSSMコマンドで接続：

```bash
aws ssm start-session --target i-XXXXX --region sa-east-1
```

### 6. 削除

```bash
AWS_REGION=sa-east-1 npm run destroy
```

## 📁 ファイル構成

```
.
├── bin/
│   └── app.ts                 # CDKアプリケーションエントリーポイント
├── lib/
│   └── torch-neuron-stack.ts  # メインスタック定義
├── config.json                # 設定ファイル（AMI、リージョン等）
├── cdk.json                   # CDK設定
├── package.json               # Node.js依存関係
└── README.md                  # このファイル
```

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
AWS_REGION=sa-east-1 npm run deploy -- \
  -c instanceType=inf2.8xlarge \
  --require-approval never
```

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

## 📚 参考資料

- [AWS CDK Documentation](https://docs.aws.amazon.com/cdk/)
- [AWS Neuron Documentation](https://awsdocs-neuron.readthedocs-hosted.com/)
- [EC2 Capacity Blocks](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-capacity-blocks.html)
