#!/usr/bin/env python3
"""
Multi-LoRA servingのメモリ削減効果を測定するスクリプト

測定内容:
1. ベースモデルのみ
2. 個別LoRA × 3（それぞれ別のLLMインスタンス）
3. Multi-LoRA（1つのLLMインスタンスに3つのLoRA同時ロード）

理論的なメモリ削減量を定量化します。

使用例:
  python measure_memory_consumption.py
  python measure_memory_consumption.py --model TinyLlama/TinyLlama-1.1B-Chat-v1.0
  python measure_memory_consumption.py --output memory_report.txt
"""

import argparse
import gc
import time
from pathlib import Path
from typing import Dict, List
import torch
from vllm import LLM
from vllm.lora.request import LoRARequest


# LoRAアダプターの定義
LORA_ADAPTERS = [
    {
        "name": "text2sql",
        "path": "sid321axn/tiny-llama-text2sql",
        "description": "SQL生成LoRA",
    },
    {
        "name": "math",
        "path": "philimon/TinyLlama-gsm8k-lora",
        "description": "数学問題LoRA",
    },
    {
        "name": "function",
        "path": "unclecode/tinyllama-function-call-lora-adapter-250424",
        "description": "関数呼び出しLoRA",
    },
]


def get_gpu_memory_mb() -> float:
    """現在のGPUメモリ使用量をMB単位で取得"""
    if torch.cuda.is_available():
        return torch.cuda.memory_allocated() / 1024 / 1024
    return 0.0


def get_gpu_memory_reserved_mb() -> float:
    """GPUに予約されたメモリをMB単位で取得"""
    if torch.cuda.is_available():
        return torch.cuda.memory_reserved() / 1024 / 1024
    return 0.0


def clear_memory():
    """メモリをクリア"""
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.synchronize()
    time.sleep(2)


def measure_base_model(model_name: str) -> Dict:
    """ベースモデルのみのメモリ消費量を測定"""
    print("\n" + "=" * 80)
    print("📊 測定 1/3: ベースモデルのみ")
    print("=" * 80)

    clear_memory()
    memory_before = get_gpu_memory_mb()

    print(f"メモリ使用量（ロード前）: {memory_before:.2f} MB")

    # ベースモデルをロード
    print(f"🚀 モデル初期化中: {model_name}")
    llm = LLM(
        model=model_name,
        gpu_memory_utilization=0.85,
    )

    memory_after = get_gpu_memory_mb()
    memory_reserved = get_gpu_memory_reserved_mb()

    print(f"✅ ロード完了")
    print(f"メモリ使用量（ロード後）: {memory_after:.2f} MB")
    print(f"メモリ予約量: {memory_reserved:.2f} MB")

    base_memory = memory_after - memory_before

    print(f"\n📈 ベースモデル消費メモリ: {base_memory:.2f} MB")

    # クリーンアップ
    del llm
    clear_memory()

    return {
        "name": "ベースモデルのみ",
        "memory_mb": base_memory,
        "memory_allocated_mb": memory_after,
        "memory_reserved_mb": memory_reserved,
    }


def measure_individual_loras(model_name: str, lora_adapters: List[Dict]) -> List[Dict]:
    """各LoRAアダプターを個別にロードして測定"""
    print("\n" + "=" * 80)
    print("📊 測定 2/3: 個別LoRAインスタンス（×3）")
    print("=" * 80)

    results = []

    for i, adapter in enumerate(lora_adapters, 1):
        print(f"\n--- LoRA {i}/{len(lora_adapters)}: {adapter['name']} ---")

        clear_memory()
        memory_before = get_gpu_memory_mb()

        print(f"メモリ使用量（ロード前）: {memory_before:.2f} MB")

        # 個別のLLMインスタンスを作成（ベースモデル + LoRA）
        print(f"🚀 モデル + LoRA初期化中...")
        llm = LLM(
            model=model_name,
            enable_lora=True,
            max_loras=1,
            max_lora_rank=64,
            gpu_memory_utilization=0.85,
        )

        # LoRAを使って1回推論（実際にロードされるように）
        lora_request = LoRARequest(
            lora_name=adapter['name'],
            lora_int_id=i,
            lora_path=adapter['path'],
        )

        print(f"🔄 LoRAアダプターをロード中...")
        _ = llm.generate(
            prompts=["<|user|>\nTest</s>\n<|assistant|>\n"],
            lora_request=lora_request,
        )

        memory_after = get_gpu_memory_mb()
        memory_reserved = get_gpu_memory_reserved_mb()

        print(f"✅ ロード完了")
        print(f"メモリ使用量（ロード後）: {memory_after:.2f} MB")
        print(f"メモリ予約量: {memory_reserved:.2f} MB")

        consumed_memory = memory_after - memory_before

        print(f"\n📈 {adapter['name']} 消費メモリ: {consumed_memory:.2f} MB")

        results.append({
            "name": adapter['name'],
            "description": adapter['description'],
            "memory_mb": consumed_memory,
            "memory_allocated_mb": memory_after,
            "memory_reserved_mb": memory_reserved,
        })

        # クリーンアップ
        del llm
        clear_memory()

    total_individual = sum(r['memory_mb'] for r in results)
    print(f"\n📊 個別LoRA合計メモリ: {total_individual:.2f} MB")

    return results


def measure_multi_lora(model_name: str, lora_adapters: List[Dict]) -> Dict:
    """Multi-LoRA serving（3つ同時ロード）のメモリ消費量を測定"""
    print("\n" + "=" * 80)
    print("📊 測定 3/3: Multi-LoRA serving（3つ同時）")
    print("=" * 80)

    clear_memory()
    memory_before = get_gpu_memory_mb()

    print(f"メモリ使用量（ロード前）: {memory_before:.2f} MB")

    # Multi-LoRA対応のLLMインスタンスを作成
    print(f"🚀 Multi-LoRAモデル初期化中...")
    llm = LLM(
        model=model_name,
        enable_lora=True,
        max_loras=len(lora_adapters),
        max_lora_rank=64,
        max_cpu_loras=len(lora_adapters) * 2,
        gpu_memory_utilization=0.85,
    )

    # 全てのLoRAアダプターをロード
    print(f"🔄 {len(lora_adapters)}個のLoRAアダプターをロード中...")
    for i, adapter in enumerate(lora_adapters, 1):
        lora_request = LoRARequest(
            lora_name=adapter['name'],
            lora_int_id=i,
            lora_path=adapter['path'],
        )

        print(f"  - {adapter['name']} をロード...")
        _ = llm.generate(
            prompts=["<|user|>\nTest</s>\n<|assistant|>\n"],
            lora_request=lora_request,
        )

    memory_after = get_gpu_memory_mb()
    memory_reserved = get_gpu_memory_reserved_mb()

    print(f"✅ ロード完了")
    print(f"メモリ使用量（ロード後）: {memory_after:.2f} MB")
    print(f"メモリ予約量: {memory_reserved:.2f} MB")

    multi_lora_memory = memory_after - memory_before

    print(f"\n📈 Multi-LoRA 消費メモリ: {multi_lora_memory:.2f} MB")

    # クリーンアップ
    del llm
    clear_memory()

    return {
        "name": f"Multi-LoRA ({len(lora_adapters)}個同時)",
        "memory_mb": multi_lora_memory,
        "memory_allocated_mb": memory_after,
        "memory_reserved_mb": memory_reserved,
    }


def print_summary(base_result: Dict, individual_results: List[Dict], multi_lora_result: Dict):
    """結果サマリーを表示"""
    print("\n" + "=" * 80)
    print("📊 メモリ消費量サマリー")
    print("=" * 80)

    # 個別LoRAの合計
    total_individual = sum(r['memory_mb'] for r in individual_results)

    print(f"\n1️⃣  ベースモデルのみ:")
    print(f"    {base_result['memory_mb']:.2f} MB")

    print(f"\n2️⃣  個別LoRAインスタンス（×{len(individual_results)}）:")
    for r in individual_results:
        print(f"    - {r['name']}: {r['memory_mb']:.2f} MB")
    print(f"    合計: {total_individual:.2f} MB")

    print(f"\n3️⃣  Multi-LoRA serving:")
    print(f"    {multi_lora_result['memory_mb']:.2f} MB")

    # メモリ削減効果
    print(f"\n" + "=" * 80)
    print("💰 メモリ削減効果")
    print("=" * 80)

    memory_saved = total_individual - multi_lora_result['memory_mb']
    reduction_percent = (memory_saved / total_individual) * 100 if total_individual > 0 else 0

    print(f"\n個別インスタンス合計: {total_individual:.2f} MB")
    print(f"Multi-LoRA serving:    {multi_lora_result['memory_mb']:.2f} MB")
    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"削減量:                {memory_saved:.2f} MB")
    print(f"削減率:                {reduction_percent:.1f}%")

    if memory_saved > 0:
        print(f"\n✅ Multi-LoRA servingにより {memory_saved:.2f} MB ({reduction_percent:.1f}%) のメモリを節約！")
    else:
        print(f"\n⚠️  予想外: Multi-LoRAの方がメモリ消費が多い（測定誤差の可能性）")

    print(f"\n💡 理論的な利点:")
    print(f"   - ベースモデルは1つだけロード（共有）")
    print(f"   - LoRAアダプターは軽量（数MB～数百MB）")
    print(f"   - 個別インスタンスではベースモデルを{len(individual_results)}回ロード")


def main():
    parser = argparse.ArgumentParser(
        description="Multi-LoRA servingのメモリ削減効果を測定"
    )
    parser.add_argument(
        "--model",
        type=str,
        default="TinyLlama/TinyLlama-1.1B-Chat-v1.0",
        help="ベースモデル",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="結果を保存するファイル（オプション）",
    )

    args = parser.parse_args()

    if not torch.cuda.is_available():
        print("❌ エラー: CUDAが利用できません。GPUが必要です。")
        return

    print("=" * 80)
    print("🔬 Multi-LoRA Serving メモリ測定")
    print("=" * 80)
    print(f"モデル: {args.model}")
    print(f"GPU: {torch.cuda.get_device_name(0)}")
    print(f"GPU総メモリ: {torch.cuda.get_device_properties(0).total_memory / 1024 / 1024:.2f} MB")

    # 測定実行
    base_result = measure_base_model(args.model)
    individual_results = measure_individual_loras(args.model, LORA_ADAPTERS)
    multi_lora_result = measure_multi_lora(args.model, LORA_ADAPTERS)

    # サマリー表示
    print_summary(base_result, individual_results, multi_lora_result)

    # ファイルに保存
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)

        total_individual = sum(r['memory_mb'] for r in individual_results)
        memory_saved = total_individual - multi_lora_result['memory_mb']
        reduction_percent = (memory_saved / total_individual) * 100 if total_individual > 0 else 0

        with open(args.output, 'w', encoding='utf-8') as f:
            f.write("Multi-LoRA Serving メモリ測定結果\n")
            f.write("=" * 80 + "\n\n")
            f.write(f"モデル: {args.model}\n")
            f.write(f"GPU: {torch.cuda.get_device_name(0)}\n\n")

            f.write("1. ベースモデルのみ\n")
            f.write(f"   {base_result['memory_mb']:.2f} MB\n\n")

            f.write("2. 個別LoRAインスタンス\n")
            for r in individual_results:
                f.write(f"   - {r['name']}: {r['memory_mb']:.2f} MB\n")
            f.write(f"   合計: {total_individual:.2f} MB\n\n")

            f.write("3. Multi-LoRA serving\n")
            f.write(f"   {multi_lora_result['memory_mb']:.2f} MB\n\n")

            f.write("メモリ削減効果\n")
            f.write("=" * 80 + "\n")
            f.write(f"削減量: {memory_saved:.2f} MB\n")
            f.write(f"削減率: {reduction_percent:.1f}%\n")

        print(f"\n💾 結果を保存: {args.output}")

    print("\n✅ メモリ測定完了！")


if __name__ == "__main__":
    main()
