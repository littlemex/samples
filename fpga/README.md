# AWS FPGA Development Environment - CloudFormation Template

AWS F2 FPGA インスタンス上で FPGA 開発環境を構築するための CloudFormation テンプレートです。

## 概要

このプロジェクトは、AWS F2 FPGA インスタンス（f2.2xlarge ~ f2.24xlarge）上に開発環境を構築します。FPGA Developer AMI を使用し、Xilinx Vivado/Vitis 開発ツールと AWS FPGA SDK が事前インストールされています。

## 対応インスタンスタイプ

以下の F2 FPGA インスタンスタイプをサポートしています：

| インスタンスタイプ | FPGA | vCPU | メモリ | ネットワーク | 推奨用途 |
|-----------------|------|------|--------|------------|---------|
| f2.2xlarge | 1 | 8 | 32 GiB | 最大 12.5 Gbps | 開発・テスト |
| f2.4xlarge | 2 | 16 | 64 GiB | 最大 12.5 Gbps | 中規模開発 |
| f2.6xlarge | 4 | 24 | 96 GiB | 12.5 Gbps | 本格的な開発 |
| f2.12xlarge | 8 | 48 | 192 GiB | 25 Gbps | 大規模開発 |
| f2.24xlarge | 16 | 96 | 384 GiB | 50 Gbps | 最大規模開発 |

## アーキテクチャ

```
┌─────────────────────────────────────┐
│   F2 FPGA Instance                  │
│   ┌─────────────────────────────┐   │
│   │  FPGA Developer AMI         │   │
│   │  - Ubuntu 24.04 / Rocky 8   │   │
│   │  - Vivado/Vitis 2025.1      │   │
│   │  - AWS FPGA SDK             │   │
│   └─────────────────────────────┘   │
└─────────────────────────────────────┘
                │
        ┌───────┴────────┐
        │                │
    ┌───▼────┐    ┌─────▼─────┐
    │  SSH   │    │    SSM    │
    └────────┘    └───────────┘
```

### 構成要素

- **F2 FPGA インスタンス**: FPGA Developer AMI を使用
- **FPGA Developer AMI**: Xilinx Vivado/Vitis と AWS FPGA SDK がプリインストール
- **SSM Session Manager**: セキュアなインスタンス管理（推奨）
- **SSH**: オプションの SSH アクセス（Key Pair 指定時）

## 特徴

✅ **最新の FPGA Developer AMI** - Vivado/Vitis 2025.1 環境
✅ **自動 AMI 検索** - 最新の FPGA Developer AMI を自動取得
✅ **複数インスタンスタイプ対応** - f2.2xlarge ~ f2.24xlarge
✅ **柔軟なアクセス方法** - SSM または SSH
✅ **事前構成済み環境** - AWS FPGA SDK、開発ツールがインストール済み
✅ **簡単デプロイ** - シンプルな CLI ツールで管理

## FPGA Developer AMI について

### 最新版の確認方法

FPGA Developer AMI の最新版を確認するには、以下のいずれかの方法を使用します：

#### 方法1: 提供されているスクリプトを使用

```bash
# 最新の Ubuntu 版 FPGA Developer AMI を取得（デフォルト: us-east-1）
./get_fpga_ami.sh

# 別のリージョンで検索
./get_fpga_ami.sh us-west-2

# Rocky Linux 版を検索
./get_fpga_ami.sh us-east-1 rocky
```

#### 方法2: AWS CLI で直接検索

```bash
# Ubuntu 版の最新 FPGA Developer AMI を取得
aws ec2 describe-images \
  --region us-east-1 \
  --owners amazon \
  --filters \
    "Name=name,Values=*FPGA Developer AMI*Ubuntu*" \
    "Name=state,Values=available" \
    "Name=architecture,Values=x86_64" \
  --query 'sort_by(Images, &CreationDate)[-1].[ImageId,Name,CreationDate]' \
  --output table

# Rocky Linux 版の最新 FPGA Developer AMI を取得
aws ec2 describe-images \
  --region us-east-1 \
  --owners amazon \
  --filters \
    "Name=name,Values=*FPGA Developer AMI*Rocky*" \
    "Name=state,Values=available" \
    "Name=architecture,Values=x86_64" \
  --query 'sort_by(Images, &CreationDate)[-1].[ImageId,Name,CreationDate]' \
  --output table
```

#### 方法3: AWS ドキュメントで確認

最新の AMI 情報は以下のドキュメントで確認できます：
- [AWS FPGA Developer Kit Documentation](https://awsdocs-fpga-f2.readthedocs-hosted.com/)

### 現在の AMI バージョン（2025年1月時点）

| バージョン | AMI ID | Vivado/Vitis | OS | リージョン |
|----------|--------|--------------|-----|---------|
| 1.18.0 | ami-0cb1b6ae2ff99f8bf | 2025.1 | Rocky Linux 8.10 | us-east-1 |
| 1.18.0 | ami-098b2ed4c92602975 | 2025.1 | Ubuntu 24.04 | us-east-1 |

## 使用方法

このプロジェクトでは、2つのデプロイ方法を提供しています：

1. **直接 AMI ID 指定方式**（`main.yml` / `ec2.yml`）- AMI ID を直接パラメータで指定
2. **SSM パラメータ参照方式**（`main-ssm.yml` / `ec2-ssm.yml`）- SSM Parameter Store から AMI ID を動的に解決（推奨）

### 前提条件

- AWS CLI 設定済み
- 適切な IAM 権限
- Session Manager Plugin（SSM 接続時に必要）
- （オプション）EC2 Key Pair（SSH アクセス時に必要）

### 方式1: SSM パラメータ参照方式（推奨）

この方式は、Neuron DLAMI と同じように SSM パラメータから AMI ID を動的に解決します。

#### セットアップ

```bash
# 1. 最新の FPGA Developer AMI ID を SSM パラメータストアに保存
./setup_ssm_parameter.sh us-east-1 ubuntu

# 他のリージョンでも実行する場合
./setup_ssm_parameter.sh us-west-2 ubuntu

# Rocky Linux を使用する場合
./setup_ssm_parameter.sh us-east-1 rocky
```

#### デプロイ

```bash
# 2. テンプレート検証
./cfn_manager.sh validate

# 3. SSM パラメータ参照方式でデプロイ
# 注意: テンプレートファイル名を main-ssm.yml に変更
cp main-ssm.yml main.yml.bak
cp ec2-ssm.yml ec2.yml.bak
mv main.yml main-direct.yml
mv ec2.yml ec2-direct.yml
mv main-ssm.yml main.yml
mv ec2-ssm.yml ec2.yml

./cfn_manager.sh create

# 4. 接続情報表示
./cfn_manager.sh outputs

# 5. SSM で接続
./cfn_manager.sh connect

# 元に戻す場合
mv main.yml main-ssm.yml
mv ec2.yml ec2-ssm.yml
mv main-direct.yml main.yml
mv ec2-direct.yml ec2.yml
```

#### SSM パラメータの更新

AMI が更新された場合、以下のコマンドで SSM パラメータを更新できます：

```bash
./setup_ssm_parameter.sh us-east-1 ubuntu
```

CloudFormation スタックを再デプロイすると、自動的に最新の AMI ID が使用されます。

### 方式2: 直接 AMI ID 指定方式

シンプルに AMI ID を直接指定する方式です。

#### クイックスタート

```bash
# 1. 最新の FPGA Developer AMI を確認
./get_fpga_ami.sh

# 2. テンプレート検証
./cfn_manager.sh validate

# 3. デフォルト設定でデプロイ（f2.6xlarge、us-east-1）
./cfn_manager.sh create

# 4. 接続情報表示
./cfn_manager.sh outputs

# 5. SSM で接続
./cfn_manager.sh connect
```

### カスタム設定でデプロイ

```bash
# インスタンスタイプとリージョンを指定
./cfn_manager.sh create -n my-fpga -t f2.12xlarge -r us-west-2

# 特定の AMI ID を使用
./cfn_manager.sh create -a ami-0cb1b6ae2ff99f8bf

# SSH アクセスを有効化（Key Pair 指定）
./cfn_manager.sh create -k my-keypair -c 203.0.113.0/24

# ボリュームサイズを変更（デフォルト: 500GB）
./cfn_manager.sh create -v 1000
```

### スタック管理

```bash
# スタック状態確認
./cfn_manager.sh status -n my-fpga

# スタック出力表示
./cfn_manager.sh outputs -n my-fpga

# 最近のイベント表示
./cfn_manager.sh events -n my-fpga

# エラーログ表示
./cfn_manager.sh logs -n my-fpga

# スタック削除
./cfn_manager.sh delete -n my-fpga
```

### インスタンスへの接続

#### SSM Session Manager 経由（推奨）

```bash
# CFN Manager から接続
./cfn_manager.sh connect -n my-fpga

# または直接 AWS CLI で接続
aws ssm start-session --target <INSTANCE_ID> --region us-east-1
```

#### SSH 経由（Key Pair 指定時のみ）

```bash
# パブリック IP を取得
./cfn_manager.sh outputs -n my-fpga

# SSH で接続
ssh -i ~/.ssh/my-keypair.pem ubuntu@<PUBLIC_IP>
```

## FPGA 開発環境

デプロイされたインスタンスには以下の開発環境が含まれています：

### インストール済みツール

- **Xilinx Vivado/Vitis 2025.1** - FPGA 設計・開発ツール
- **AWS FPGA SDK** - `/home/ubuntu/aws-fpga` にクローン済み
- **開発ツール**: git, wget, curl, vim, htop, tree, jq

### AWS FPGA SDK のセットアップ

```bash
# AWS FPGA SDK 環境をセットアップ
cd ~/aws-fpga
source sdk_setup.sh

# Vivado 環境をセットアップ
source /tools/Xilinx/Vivado/2025.1/settings64.sh
```

### 作業ディレクトリ

- **FPGA ワークスペース**: `/home/ubuntu/fpga-workspace`
- **AWS FPGA SDK**: `/home/ubuntu/aws-fpga`

### サンプルプロジェクト

AWS FPGA SDK には多数のサンプルが含まれています：

```bash
# CL（Custom Logic）サンプル
ls ~/aws-fpga/hdk/cl/examples/

# ホストアプリケーションサンプル
ls ~/aws-fpga/sdk/linux_kernel_drivers/
```

## カスタマイズ

### CloudFormation パラメータ

| パラメータ | デフォルト | 説明 |
|-----------|-----------|------|
| InstanceName | FPGADevelopment | インスタンス名 |
| InstanceType | f2.6xlarge | インスタンスタイプ |
| InstanceVolumeSize | 500 | EBS ボリュームサイズ（GB） |
| FpgaAmiId | ami-098b2ed4c92602975 | FPGA Developer AMI ID |
| KeyPairName | (空) | SSH Key Pair 名（オプション） |
| AllowedSSHCidr | 0.0.0.0/0 | SSH 許可 CIDR |

### IAM ロールのカスタマイズ

`ec2.yml` の `FPGAInstanceRole` セクションで、必要な権限を追加・変更できます：

```yaml
Policies:
  - PolicyName: FPGADevelopmentPolicy
    PolicyDocument:
      Statement:
        - Effect: Allow
          Action:
            - ec2:DescribeFpgaImages
            - ec2:CreateFpgaImage
            # 追加の権限をここに記述
          Resource: '*'
```

## トラブルシューティング

### よくある問題

#### 1. スタック作成失敗

```bash
# エラーログを確認
./cfn_manager.sh logs -n my-fpga

# リージョンでインスタンスタイプが利用可能か確認
aws ec2 describe-instance-type-offerings \
  --region us-east-1 \
  --filters Name=instance-type,Values=f2.6xlarge
```

#### 2. AMI が見つからない

```bash
# 別のリージョンで検索
./get_fpga_ami.sh us-west-2

# Rocky Linux 版を試す
./get_fpga_ami.sh us-east-1 rocky
```

#### 3. SSM 接続エラー

```bash
# SSM Agent のステータス確認
aws ssm describe-instance-information \
  --region us-east-1 \
  --filters Key=InstanceIds,Values=<INSTANCE_ID>

# Session Manager Plugin のインストール確認
session-manager-plugin --version
```

#### 4. Vivado ライセンスエラー

Xilinx Vivado/Vitis を使用する際は、適切なライセンスが必要です：
- ノードロックライセンス
- フローティングライセンス
- クラウドライセンス

詳細は [Xilinx Licensing](https://www.xilinx.com/products/design-tools/vivado/vivado-ml.html#licensing) を参照してください。

### ログ確認

```bash
# UserData 実行ログ
sudo cat /var/log/cloud-init-output.log

# セットアップ完了確認
cat /tmp/userdata-complete.txt
```

## コスト見積もり

F2 インスタンスのコストは以下の通りです（us-east-1、オンデマンド価格、2025年1月時点）：

| インスタンスタイプ | 時間単価 | 月額（730時間） |
|-----------------|---------|----------------|
| f2.2xlarge | $1.65 | $1,204.50 |
| f2.4xlarge | $3.30 | $2,409.00 |
| f2.6xlarge | $4.95 | $3,613.50 |
| f2.12xlarge | $9.90 | $7,227.00 |
| f2.24xlarge | $19.80 | $14,454.00 |

※ 上記は参考価格です。最新の料金は [AWS 料金表](https://aws.amazon.com/ec2/pricing/on-demand/) を確認してください。
※ EBS ストレージ、データ転送などの追加コストが発生します。

### コスト削減のヒント

- スポットインスタンスの使用（最大 90% 割引）
- 使用していない時はインスタンスを停止
- 不要な EBS ボリュームの削除
- リザーブドインスタンスの検討（長期利用時）

## 参考リンク

- [AWS FPGA Developer Kit Documentation](https://awsdocs-fpga-f2.readthedocs-hosted.com/)
- [AWS FPGA GitHub Repository](https://github.com/aws/aws-fpga)
- [F2 Instances](https://aws.amazon.com/ec2/instance-types/f2/)
- [Xilinx Vivado Design Suite](https://www.xilinx.com/products/design-tools/vivado.html)

## ライセンス

このプロジェクトは参考実装として提供されています。本番環境で使用する前に、セキュリティ要件とコンプライアンス要件を確認してください。

## コントリビューション

改善提案やバグ報告は歓迎します。
