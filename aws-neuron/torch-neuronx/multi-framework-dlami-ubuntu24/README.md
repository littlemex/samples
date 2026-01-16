# AWS Neuron Code-server - CloudFormation Template

AWS Neuronインスタンス（Inf2/Trn1/Trn1n/Trn2）上でcode-server環境を構築し、PyTorch Neuronを使用した機械学習ワークロードを実行するためのCloudFormationテンプレートです。

## 概要

このプロジェクトは、AWS Neuron対応インスタンス上にcode-server環境を構築し、CloudFront経由でアクセス可能なWeb IDE環境を提供します。**Ubuntu 24.04 Neuron DLAMI**をデフォルトで使用し、最新のPyTorch NeuronとNeuronツールが事前インストールされています。

## 対応インスタンスタイプ

以下のAWS Neuron対応インスタンスタイプをサポートしています：

- **inf2.*** - AWS Inferentia2 (推論最適化)
  - 例: inf2.xlarge, inf2.8xlarge, inf2.24xlarge, inf2.48xlarge
- **trn1.*** - AWS Trainium (学習最適化)
  - 例: trn1.2xlarge, trn1.32xlarge
- **trn1n.*** - AWS Trainium 1n (学習最適化、高性能ネットワーク)
  - 例: trn1n.32xlarge
- **trn2.*** - AWS Trainium2 (次世代学習最適化)
  - 例: trn2.3xlarge, trn2.8xlarge, trn2.16xlarge
  - ※ trn2u.*は非対応

## アーキテクチャ

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────────┐
│   CloudFront    │────│   Code-server    │────│ Neuron Instance     │
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

- **Neuronインスタンス**: Deep Learning AMI Neuron (Ubuntu 24.04) を自動選択
- **Code-server**: ポート80でWebIDEを提供
- **CloudFront**: グローバル配信とセキュリティ
- **Lambda関数**: 自動化とヘルスチェック
- **SSM**: セキュアなインスタンス管理

## 特徴

✅ **Ubuntu 24.04 DLAMI** - 最新のNeuron SDKとPyTorch環境
✅ **自動DLAMI選択** - SSMパラメータから最新のDLAMI IDを自動取得
✅ **複数インスタンス対応** - inf2/trn1/trn1n/trn2すべてに対応
✅ **事前構成済み環境** - PyTorch Neuron、NxD、各種ツールがインストール済み
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

# デフォルト設定でデプロイ（Ubuntu 24.04、trn1.2xlarge、us-east-1）
./cfn_manager.sh create

# インスタンスタイプとリージョンを指定
./cfn_manager.sh create -t inf2.8xlarge -r us-west-2

# カスタム設定
./cfn_manager.sh create -n my-neuron-env -t trn2.8xlarge -u developer

# 進捗監視
./cfn_manager.sh monitor -n my-neuron-env

# 接続情報表示
./cfn_manager.sh outputs -n my-neuron-env
```

### アクセス

```bash
# ブラウザでオープン
./cfn_manager.sh open -n my-neuron-env

# SSMでEC2に接続
./cfn_manager.sh connect -n my-neuron-env
```

### 削除

```bash
./cfn_manager.sh delete -n my-neuron-env
```

## Neuron環境

デプロイされたインスタンスには以下のNeuron環境が含まれています（Ubuntu 24.04の場合）：

- **PyTorch 2.9 + Torch NeuronX** - `/opt/aws_neuronx_venv_pytorch_2_9`
- **PyTorch 2.9 + NxD Training** - `/opt/aws_neuronx_venv_pytorch_2_9_nxd_training`
- **PyTorch 2.9 + NxD Inference** - `/opt/aws_neuronx_venv_pytorch_2_9_nxd_inference`
- **JAX 0.7 NeuronX** - `/opt/aws_neuronx_venv_jax_0_7`
- **vLLM 0.11.0 + Torch NeuronX** - `/opt/aws_neuronx_venv_pytorch_inference_vllm`

### 使用例

```bash
# Neuron環境をアクティベート
source /opt/aws_neuronx_venv_pytorch_2_9/bin/activate

# Neuronツール確認
neuron-ls
neuron-top
```

## カスタマイズ

### パラメータ

主要なパラメータは以下の通りです：

| パラメータ | デフォルト | 説明 |
|-----------|-----------|------|
| InstanceType | trn1.2xlarge | インスタンスタイプ |
| InstanceOperatingSystem | Ubuntu-24 | OS（Ubuntu-24固定） |
| CodeServerUser | coder | code-serverのユーザー名 |
| HomeFolder | /work | ホームフォルダ |
| InstanceVolumeSize | 200 | EBSボリュームサイズ（GB） |

## トラブルシューティング

### ログ確認

```bash
# CloudFormationイベントログ
./cfn_manager.sh logs -n my-neuron-env

# スタック状態確認
./cfn_manager.sh status -n my-neuron-env
```

### よくある問題

1. **スタック作成失敗**
   - リージョンでインスタンスタイプが利用可能か確認
   - サービスクォータの確認

2. **code-server接続エラー**
   - CloudFrontの配信完了を待つ（初回は10-15分）
   - パスワードが正しいか確認

3. **Neuron環境が見つからない**
   - 正しいDLAMIが選択されているか確認
   - SSMドキュメント実行ログを確認

## ヘルプ

```bash
./cfn_manager.sh --help
```

## 参考リンク

- [AWS Neuron Documentation](https://awsdocs-neuron.readthedocs-hosted.com/)
- [Neuron DLAMI User Guide](https://awsdocs-neuron.readthedocs-hosted.com/en/latest/dlami/index.html)
- [PyTorch Neuron](https://awsdocs-neuron.readthedocs-hosted.com/en/latest/frameworks/torch/index.html)

## ライセンス

このプロジェクトのライセンスについては、各ファイルのヘッダーを参照してください。
