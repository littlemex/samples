"""
オフラインバッチ推論のサンプル

大量のプロンプトを効率的にバッチ処理する例です。
"""

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from tqdm import tqdm
from vllm import LLM, SamplingParams
from vllm.lora.request import LoRARequest


def load_prompts(input_file: Path) -> List[Dict[str, Any]]:
    """
    入力ファイルからプロンプトを読み込む

    Expected JSON format:
    [
        {
            "prompt": "...",
            "lora_adapter": "sql",  # optional
            "temperature": 0.0,     # optional
            "max_tokens": 256       # optional
        },
        ...
    ]
    """
    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    print(f"Loaded {len(data)} prompts from {input_file}")
    return data


def save_results(results: List[Dict[str, Any]], output_file: Path):
    """結果をJSONファイルに保存"""
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"Saved {len(results)} results to {output_file}")


def batch_inference(
    model_name: str,
    prompts_data: List[Dict[str, Any]],
    lora_adapters: Dict[str, str],
    max_loras: int = 8,
    max_lora_rank: int = 64,
    batch_size: int = 32,
) -> List[Dict[str, Any]]:
    """
    バッチ推論を実行

    Args:
        model_name: ベースモデル名
        prompts_data: プロンプトデータのリスト
        lora_adapters: LoRAアダプターの辞書 {name: path}
        max_loras: 同時LoRA数
        max_lora_rank: 最大rank
        batch_size: バッチサイズ

    Returns:
        推論結果のリスト
    """
    # LLMを初期化
    print(f"\nInitializing LLM: {model_name}")
    llm = LLM(
        model=model_name,
        enable_lora=True,
        max_loras=max_loras,
        max_lora_rank=max_lora_rank,
        gpu_memory_utilization=0.85,
        max_num_seqs=batch_size,
    )

    all_results = []

    # バッチごとに処理
    total_batches = (len(prompts_data) + batch_size - 1) // batch_size
    for batch_idx in tqdm(range(total_batches), desc="Processing batches"):
        start_idx = batch_idx * batch_size
        end_idx = min(start_idx + batch_size, len(prompts_data))
        batch = prompts_data[start_idx:end_idx]

        # バッチリクエストを準備
        requests = []
        for item in batch:
            prompt_text = item["prompt"]
            temperature = item.get("temperature", 0.0)
            max_tokens = item.get("max_tokens", 512)

            sampling_params = SamplingParams(
                temperature=temperature,
                top_p=item.get("top_p", 0.95),
                max_tokens=max_tokens,
            )

            # LoRAリクエストの作成
            lora_name = item.get("lora_adapter")
            if lora_name and lora_name in lora_adapters:
                lora_request = LoRARequest(
                    lora_name=lora_name,
                    lora_int_id=hash(lora_name) % (2**31),
                    lora_local_path=lora_adapters[lora_name],
                )
            else:
                lora_request = None

            requests.append((prompt_text, sampling_params, lora_request))

        # バッチ推論実行
        outputs = llm.generate(requests)

        # 結果を収集
        for i, output in enumerate(outputs):
            result = {
                "prompt": output.prompt,
                "generated": output.outputs[0].text,
                "lora_adapter": batch[i].get("lora_adapter"),
                "num_tokens": len(output.outputs[0].token_ids),
                "finish_reason": output.outputs[0].finish_reason,
            }
            all_results.append(result)

    return all_results


def main():
    parser = argparse.ArgumentParser(description="vLLM Multi-LoRA Offline Batch Inference")
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Input JSON file with prompts",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output JSON file for results",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="meta-llama/Llama-2-7b-hf",
        help="Base model name or path",
    )
    parser.add_argument(
        "--max-loras",
        type=int,
        default=8,
        help="Maximum number of concurrent LoRAs",
    )
    parser.add_argument(
        "--max-lora-rank",
        type=int,
        default=64,
        help="Maximum LoRA rank",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=32,
        help="Batch size for inference",
    )

    args = parser.parse_args()

    # LoRAアダプターの設定
    lora_adapters = {
        "sql": "./lora_adapters/sql-lora",
        "python": "./lora_adapters/python-lora",
        "math": "./lora_adapters/math-lora",
    }

    # プロンプトを読み込み
    prompts_data = load_prompts(args.input)

    # バッチ推論を実行
    results = batch_inference(
        model_name=args.model,
        prompts_data=prompts_data,
        lora_adapters=lora_adapters,
        max_loras=args.max_loras,
        max_lora_rank=args.max_lora_rank,
        batch_size=args.batch_size,
    )

    # 結果を保存
    save_results(results, args.output)

    print("\nBatch inference completed successfully!")


if __name__ == "__main__":
    main()
