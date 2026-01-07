# PyTorch Neuron on TRN1 - CloudFormation Template

AWS Trainium (TRN1) インスタンス上でPyTorch Neuronを使用する環境をCloudFormationで構築します。

## 概要

このプロジェクトは、AWS TRN1インスタンス上にcode-server環境を構築し、PyTorch Neuronを使用した機械学習ワークロードを実行するためのインフラストラクチャを提供します。

## アーキテクチャ

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   CloudFront    │────│   Code-server    │────│ TRN1 Instance   │
│   Distribution  │    │   (Port 80)      │    │ + Neuron DLAMI  │
└─────────────────┘    └──────────────────┘    └─────────────────┘
         │                        │                       │
         └────────────────────────┼───────────────────────┘
                                  │
                         ┌──────────────────┐
                         │ SSM Session Mgr  │
                         │ (secure access)  │
                         └──────────────────┘
```

### 構成要素

- **TRN1インスタンス**: Neuron Deep Learning AMI搭載
- **Code-server**: ポート80でWebIDEを提供
- **CloudFront**: グローバル配信とセキュリティ
- **Lambda関数**: 自動化とヘルスチェック
- **SSM**: セキュアなインスタンス管理


```bash
./cfn_manager.sh --help
```