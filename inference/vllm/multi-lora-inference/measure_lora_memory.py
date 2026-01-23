#!/usr/bin/env python3
"""
LoRAアダプターのメモリ使用量を測定するスクリプト

このスクリプトは以下を測定します：
1. 各LoRAアダプターのディスクサイズ
2. LoRAアダプターがロードされたときのCPU RAMとGPU RAMの使用量
3. max_cpu_lorasパラメータの影響

使用例:
  python measure_lora_memory.py
  python measure_lora_memory.py --max-cpu-loras 10
  python measure_lora_memory.py --output lora_memory_report.txt
"""

import argparse
import os
import psutil
import subprocess
import time
from pathlib import Path
from typing import Dict, List

from huggingface_hub import snapshot_download
from vllm import LLM, SamplingParams
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
    """nvidia-smiを使ってGPU全体のメモリ使用量を取得"""
    try:
        result = subprocess.run(
            ['nvidia-smi', '--query-gpu=memory.used', '--format=csv,noheader,nounits'],
            capture_output=True,
            text=True,
            check=True
        )
        memory_mb = float(result.stdout.strip().split('\n')[0])
        return memory_mb
    except Exception:
        return 0.0


def get_cpu_memory_mb() -> Dict[str, float]:
    """CPU RAMの使用量を取得"""
    memory = psutil.virtual_memory()
    return {
        "total": memory.total / 1024 / 1024,
        "available": memory.available / 1024 / 1024,
        "used": memory.used / 1024 / 1024,
        "percent": memory.percent
    }


def get_process_memory_mb() -> float:
    """現在のプロセスのメモリ使用量を取得"""
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / 1024 / 1024


def get_lora_disk_size(lora_path: str) -> Dict[str, float]:
    """LoRAアダプターのディスクサイズを取得"""
    try:
        # HuggingFaceからダウンロード（キャッシュされている場合は使用）
        cache_dir = snapshot_download(lora_path)

        # ディレクトリ内のすべてのファイルサイズを合計
        total_size = 0
        file_sizes = {}

        for root, dirs, files in os.walk(cache_dir):
            for file in files:
                file_path = os.path.join(root, file)
                size = os.path.getsize(file_path)
                total_size += size
                file_sizes[file] = size / 1024 / 1024  # MB

        return {
            "total_mb": total_size / 1024 / 1024,
            "cache_dir": cache_dir,
            "files": file_sizes
        }
    except Exception as e:
        return {"error": str(e), "total_mb": 0}


def measure_lora_loading_memory(
    model_name: str,
    lora_adapters: List[Dict],
    max_cpu_loras: int
) -> Dict:
    """LoRAアダプターロード時のメモリ使用量を測定"""

    print(f"\n{'='*80}")
    print(f"📊 LoRAロード時のメモリ測定 (max_cpu_loras={max_cpu_loras})")
    print(f"{'='*80}")

    # 初期状態のメモリ
    cpu_mem_before = get_cpu_memory_mb()
    gpu_mem_before = get_gpu_memory_mb()
    process_mem_before = get_process_memory_mb()

    print(f"\n初期状態:")
    print(f"  CPU RAM使用量: {cpu_mem_before['used']:.2f} MB ({cpu_mem_before['percent']:.1f}%)")
    print(f"  プロセスメモリ: {process_mem_before:.2f} MB")
    print(f"  GPU メモリ: {gpu_mem_before:.2f} MB")

    # LLM初期化
    print(f"\n🚀 Multi-LoRAモデル初期化中...")
    llm = LLM(
        model=model_name,
        enable_lora=True,
        max_loras=len(lora_adapters),
        max_lora_rank=64,
        max_cpu_loras=max_cpu_loras,
        gpu_memory_utilization=0.85,
    )

    cpu_mem_after_init = get_cpu_memory_mb()
    gpu_mem_after_init = get_gpu_memory_mb()
    process_mem_after_init = get_process_memory_mb()

    print(f"✅ モデル初期化完了")
    print(f"  CPU RAM増加: {cpu_mem_after_init['used'] - cpu_mem_before['used']:.2f} MB")
    print(f"  プロセスメモリ増加: {process_mem_after_init - process_mem_before:.2f} MB")
    print(f"  GPU メモリ増加: {gpu_mem_after_init - gpu_mem_before:.2f} MB")

    # サンプリングパラメータ
    sampling_params = SamplingParams(temperature=0.0, max_tokens=50)

    # 各LoRAアダプターをロード
    print(f"\n🔄 {len(lora_adapters)}個のLoRAアダプターをロード中...")
    lora_memory_usage = []

    for i, adapter in enumerate(lora_adapters, 1):
        print(f"\n  {i}. {adapter['name']} をロード...")

        cpu_mem_before_lora = get_cpu_memory_mb()
        process_mem_before_lora = get_process_memory_mb()

        lora_request = LoRARequest(
            lora_name=adapter['name'],
            lora_int_id=i,
            lora_path=adapter['path'],
        )

        # LoRAを実際に使用して強制的にロード
        _ = llm.generate(
            prompts=["<|user|>\nTest</s>\n<|assistant|>\n"],
            sampling_params=sampling_params,
            lora_request=lora_request,
        )

        cpu_mem_after_lora = get_cpu_memory_mb()
        process_mem_after_lora = get_process_memory_mb()

        cpu_increase = cpu_mem_after_lora['used'] - cpu_mem_before_lora['used']
        process_increase = process_mem_after_lora - process_mem_before_lora

        print(f"     CPU RAM増加: {cpu_increase:.2f} MB")
        print(f"     プロセスメモリ増加: {process_increase:.2f} MB")

        lora_memory_usage.append({
            "name": adapter['name'],
            "cpu_increase_mb": cpu_increase,
            "process_increase_mb": process_increase,
        })

    # 最終状態
    cpu_mem_final = get_cpu_memory_mb()
    gpu_mem_final = get_gpu_memory_mb()
    process_mem_final = get_process_memory_mb()

    print(f"\n最終状態:")
    print(f"  CPU RAM使用量: {cpu_mem_final['used']:.2f} MB ({cpu_mem_final['percent']:.1f}%)")
    print(f"  プロセスメモリ: {process_mem_final:.2f} MB")
    print(f"  GPU メモリ: {gpu_mem_final:.2f} MB")

    # クリーンアップ
    del llm
    time.sleep(2)

    return {
        "max_cpu_loras": max_cpu_loras,
        "cpu_ram_before": cpu_mem_before,
        "cpu_ram_after": cpu_mem_final,
        "cpu_ram_increase": cpu_mem_final['used'] - cpu_mem_before['used'],
        "process_memory_before": process_mem_before,
        "process_memory_after": process_mem_final,
        "process_memory_increase": process_mem_final - process_mem_before,
        "gpu_memory_before": gpu_mem_before,
        "gpu_memory_after": gpu_mem_final,
        "gpu_memory_increase": gpu_mem_final - gpu_mem_before,
        "lora_memory_usage": lora_memory_usage,
    }


def main():
    parser = argparse.ArgumentParser(
        description="LoRAアダプターのメモリ使用量を測定"
    )
    parser.add_argument(
        "--model",
        type=str,
        default="TinyLlama/TinyLlama-1.1B-Chat-v1.0",
        help="ベースモデル",
    )
    parser.add_argument(
        "--max-cpu-loras",
        type=int,
        default=None,
        help="CPU側でキャッシュするLoRA数（デフォルト: max_lorasと同じ）",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="結果を保存するファイル",
    )

    args = parser.parse_args()

    print("="*80)
    print("🔬 LoRAアダプター メモリ測定")
    print("="*80)
    print(f"モデル: {args.model}")
    print(f"測定対象LoRA数: {len(LORA_ADAPTERS)}")

    # システム情報
    cpu_mem = get_cpu_memory_mb()
    print(f"\nシステム情報:")
    print(f"  CPU RAM総容量: {cpu_mem['total']:.2f} MB ({cpu_mem['total']/1024:.2f} GB)")
    print(f"  CPU RAM使用可能: {cpu_mem['available']:.2f} MB ({cpu_mem['available']/1024:.2f} GB)")

    # ステップ1: LoRAアダプターのディスクサイズを測定
    print(f"\n{'='*80}")
    print("📂 ステップ1: LoRAアダプターのディスクサイズ")
    print(f"{'='*80}")

    lora_disk_sizes = []
    for adapter in LORA_ADAPTERS:
        print(f"\n{adapter['name']} ({adapter['description']}):")
        size_info = get_lora_disk_size(adapter['path'])

        if "error" not in size_info:
            print(f"  総サイズ: {size_info['total_mb']:.2f} MB")
            print(f"  キャッシュ: {size_info['cache_dir']}")
            print(f"  主要ファイル:")
            for file, size in sorted(size_info['files'].items(), key=lambda x: -x[1])[:3]:
                print(f"    - {file}: {size:.2f} MB")

            lora_disk_sizes.append({
                "name": adapter['name'],
                "size_mb": size_info['total_mb'],
            })
        else:
            print(f"  エラー: {size_info['error']}")

    total_disk_size = sum(item['size_mb'] for item in lora_disk_sizes)
    print(f"\n📊 LoRAアダプター合計ディスクサイズ: {total_disk_size:.2f} MB ({total_disk_size/1024:.2f} GB)")

    # ステップ2: LoRAロード時のメモリ使用量を測定
    max_cpu_loras = args.max_cpu_loras if args.max_cpu_loras else len(LORA_ADAPTERS)
    memory_result = measure_lora_loading_memory(args.model, LORA_ADAPTERS, max_cpu_loras)

    # サマリー
    print(f"\n{'='*80}")
    print("📊 メモリ使用量サマリー")
    print(f"{'='*80}")

    print(f"\n【ディスクサイズ】")
    for item in lora_disk_sizes:
        print(f"  {item['name']}: {item['size_mb']:.2f} MB")
    print(f"  合計: {total_disk_size:.2f} MB")

    print(f"\n【ランタイムメモリ】")
    print(f"  プロセスメモリ増加: {memory_result['process_memory_increase']:.2f} MB")
    print(f"  CPU RAM増加: {memory_result['cpu_ram_increase']:.2f} MB")
    print(f"  GPU メモリ増加: {memory_result['gpu_memory_increase']:.2f} MB")

    print(f"\n【各LoRAロード時の増加量】")
    for lora in memory_result['lora_memory_usage']:
        print(f"  {lora['name']}:")
        print(f"    CPU RAM: +{lora['cpu_increase_mb']:.2f} MB")
        print(f"    プロセスメモリ: +{lora['process_increase_mb']:.2f} MB")

    # ファイルに保存
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)

        with open(args.output, 'w', encoding='utf-8') as f:
            f.write("LoRAアダプター メモリ測定結果\n")
            f.write("="*80 + "\n\n")
            f.write(f"モデル: {args.model}\n")
            f.write(f"max_cpu_loras: {max_cpu_loras}\n\n")

            f.write("ディスクサイズ:\n")
            for item in lora_disk_sizes:
                f.write(f"  {item['name']}: {item['size_mb']:.2f} MB\n")
            f.write(f"  合計: {total_disk_size:.2f} MB\n\n")

            f.write("ランタイムメモリ:\n")
            f.write(f"  プロセスメモリ増加: {memory_result['process_memory_increase']:.2f} MB\n")
            f.write(f"  CPU RAM増加: {memory_result['cpu_ram_increase']:.2f} MB\n")
            f.write(f"  GPU メモリ増加: {memory_result['gpu_memory_increase']:.2f} MB\n\n")

            f.write("各LoRAロード時の増加量:\n")
            for lora in memory_result['lora_memory_usage']:
                f.write(f"  {lora['name']}:\n")
                f.write(f"    CPU RAM: +{lora['cpu_increase_mb']:.2f} MB\n")
                f.write(f"    プロセスメモリ: +{lora['process_increase_mb']:.2f} MB\n")

        print(f"\n💾 結果を保存: {args.output}")

    print("\n✅ メモリ測定完了！")

    # 注意事項を表示
    print(f"\n{'='*80}")
    print("⚠️  重要な注意事項")
    print(f"{'='*80}")
    print(f"""
1. CPU RAM容量の考慮:
   - 現在の空き容量: {cpu_mem['available']/1024:.2f} GB
   - max_cpu_lorasが大きいと、多数のLoRAがCPU RAMに保持されます
   - 推奨: 空きRAMの50%以下に抑える

2. LoRA 1個あたりの推定サイズ:
   - ディスクサイズ: 約{total_disk_size/len(LORA_ADAPTERS):.2f} MB
   - ランタイム増加: 約{memory_result['process_memory_increase']/len(LORA_ADAPTERS):.2f} MB

3. max_cpu_lorasの推奨値:
   - 現在の設定: {max_cpu_loras}個
   - 理論的最大値（RAM 50%使用）: 約{int((cpu_mem['available']/2) / (total_disk_size/len(LORA_ADAPTERS)))}個
   - 実用的推奨値: 10-50個（頻繁に使うLoRAのみ）

4. ディスクキャッシュ:
   - LoRAアダプターは ~/.cache/huggingface/ にキャッシュされます
   - ディスク容量も確認してください
""")


if __name__ == "__main__":
    main()
