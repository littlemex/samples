# AWS GPU Code-server - CloudFormation Template

AWS GPUインスタンス（G5/G6）上でcode-server環境を構築し、PyTorch + NVIDIA GPUを使用した機械学習ワークロードを実行するためのCloudFormationテンプレートです。

## 概要

このプロジェクトは、AWS GPU対応インスタンス上にcode-server環境を構築し、CloudFront経由でアクセス可能なWeb IDE環境を提供します。**Deep Learning OSS Nvidia Driver AMI GPU PyTorch 2.9 (Ubuntu 24.04)** をデフォルトで使用し、最新のPyTorch + NVIDIA Driverが事前インストールされています。

## 対応インスタンスタイプ

以下のAWS GPU対応インスタンスタイプをサポートしています：

- **g5.*** - NVIDIA A10G GPU（コストパフォーマンス重視）
  - 例: g5.xlarge, g5.2xlarge, g5.4xlarge, g5.8xlarge, g5.12xlarge, g5.16xlarge, g5.24xlarge, g5.48xlarge
- **g6.*** - NVIDIA L4 GPU（推論最適化）
  - 例: g6.xlarge, g6.2xlarge, g6.4xlarge, g6.8xlarge, g6.12xlarge, g6.16xlarge, g6.24xlarge, g6.48xlarge

## アーキテクチャ

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────────┐
│   CloudFront    │────│   Code-server    │────│ GPU Instance        │
│   Distribution  │    │   (Port 80)      │    │ + Ubuntu 24.04 DLAMI│
└─────────────────┘    └──────────────────┘    └─────────────────────┘
         │                        │                       │
         └────────────────────────┼───────────────────────┘
                                  │
                         ┌──────────────────┐
                         │ SSM Session Mgr  │
                         │ (secure access)  │
                         └──────────────────┘
```

### 構成要素

- **GPUインスタンス**: Deep Learning OSS Nvidia Driver AMI GPU PyTorch 2.9 (Ubuntu 24.04) を自動選択
- **Code-server**: ポート80でWebIDEを提供
- **CloudFront**: グローバル配信とセキュリティ
- **Lambda関数**: 自動化とヘルスチェック
- **SSM**: セキュアなインスタンス管理

## 特徴

✅ **Ubuntu 24.04 GPU DLAMI** - 最新のPyTorch 2.9 + NVIDIA Driver
✅ **自動DLAMI選択** - SSMパラメータから最新のDLAMI IDを自動取得
✅ **G5/G6対応** - NVIDIA A10G / L4 GPUインスタンス対応
✅ **事前構成済み環境** - PyTorch、CUDA、cuDNN、各種ツールがインストール済み
✅ **セキュアアクセス** - CloudFront + パスワード認証
✅ **簡単デプロイ** - シンプルなCLIツールで管理

## 使用方法

### 前提条件

- AWS CLI設定済み
- 適切なIAM権限
- Session Manager Plugin（SSM接続時に必要）

### デプロイ

```bash
# テンプレート検証
./cfn_manager.sh validate

# デフォルト設定でデプロイ（Ubuntu 24.04、g5.xlarge、us-east-1）
./cfn_manager.sh create

# インスタンスタイプとリージョンを指定
./cfn_manager.sh create -t g5.2xlarge -r us-west-2

# カスタム設定
./cfn_manager.sh create -n my-gpu-env -t g6.8xlarge -u developer

# 進捗監視
./cfn_manager.sh monitor -n my-gpu-env

# 接続情報表示
./cfn_manager.sh outputs -n my-gpu-env
```

### アクセス

```bash
# ブラウザでオープン
./cfn_manager.sh open -n my-gpu-env

# SSMでEC2に接続
./cfn_manager.sh connect -n my-gpu-env
```

### 削除

```bash
./cfn_manager.sh delete -n my-gpu-env
```

## GPU環境

デプロイされたインスタンスには以下が含まれています：

- **PyTorch 2.9** - GPU対応
- **NVIDIA Driver** - 最新の安定版
- **CUDA Toolkit** - PyTorchと互換性のあるバージョン
- **cuDNN** - CUDA用ディープラーニングライブラリ

### GPU確認

```bash
# GPU情報確認
nvidia-smi

# PyTorchでGPU確認
python3 -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}'); print(f'GPU count: {torch.cuda.device_count()}')"
```

## カスタマイズ

### パラメータ

主要なパラメータは以下の通りです：

| パラメータ | デフォルト | 説明 |
|-----------|-----------|------|
| InstanceType | g5.xlarge | インスタンスタイプ |
| InstanceOperatingSystem | Ubuntu-24 | OS（Ubuntu-24固定） |
| CodeServerUser | coder | code-serverのユーザー名 |
| HomeFolder | /work | ホームフォルダ |
| InstanceVolumeSize | 200 | EBSボリュームサイズ（GB） |

## トラブルシューティング

### ログ確認

```bash
# CloudFormationイベントログ
./cfn_manager.sh logs -n my-gpu-env

# スタック状態確認
./cfn_manager.sh status -n my-gpu-env
```

### よくある問題

1. **スタック作成失敗**
   - リージョンでインスタンスタイプが利用可能か確認
   - サービスクォータの確認

2. **code-server接続エラー**
   - CloudFrontの配信完了を待つ（初回は10-15分）
   - パスワードが正しいか確認

3. **GPU認識エラー**
   - `nvidia-smi`でGPUドライバーを確認
   - CUDA環境変数を確認

## ヘルプ

```bash
./cfn_manager.sh --help
```

## 参考リンク

- [AWS Deep Learning AMI Documentation](https://docs.aws.amazon.com/dlami/latest/devguide/what-is-dlami.html)
- [PyTorch GPU DLAMI (Ubuntu 24.04)](https://docs.aws.amazon.com/dlami/latest/devguide/aws-deep-learning-x86-gpu-pytorch-2.9-ubuntu-24-04.html)
- [PyTorch Documentation](https://pytorch.org/docs/stable/index.html)

## ライセンス

このプロジェクトのライセンスについては、各ファイルのヘッダーを参照してください。
