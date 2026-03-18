# XTTSv2 on AWS Neuron (NxD Inference) - 実装サンプル

本ディレクトリは、Zenn 記事「NxD Inference カスタムモデル統合インタフェース設計ガイド」の実装サンプルです。

## 概要

XTTSv2（音声合成 GPT モデル）を AWS Trainium (trn1) 上で動作させるための NxD Inference 統合実装を提供します。

## ディレクトリ構成

```
src/neuron_xttsv2/      # NxD Inference 統合の中核実装
  config.py             # XTTSv2InferenceConfig
  modeling_gpt.py       # NeuronGPTTransformer, NeuronGPTInstance
  model_wrapper_gpt.py  # ModelWrapperGPTPrefill / Decode
  application_gpt.py    # NeuronApplicationXTTSv2GPT (コーディネーター)
  state_dict.py         # XTTSv2 チェックポイント変換
examples/
  compile.py                # モデルのコンパイル（引数ベース）
  compile_bf16_script.py    # BF16 コンパイル（環境変数ベース、ブログ記事対応）
  e2e_xttsv2_neuron.py      # E2E 検証：CPU vs Neuron 性能・精度比較
  test_long_text_script.py  # 長文テキスト WER・レイテンシ測定
  run_inference.py          # 推論の実行
  benchmark_timing.py       # レイテンシ詳細ベンチマーク
  verify_structure.py       # 構造確認（CPU で実行可能）
```

## 必要な環境

- AWS Trainium インスタンス (trn1.2xlarge 以上)
- AWS Neuron SDK (neuronx-distributed-inference)
- Coqui TTS (XTTS v2 モデルの読み込みに必要)

詳細は記事を参照してください。
