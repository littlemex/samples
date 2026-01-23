#!/usr/bin/env python3
"""
同じプロンプトを複数のLoRAアダプターで比較するスクリプト

Multi-LoRA servingの真価：
- 1つのベースモデルインスタンスで複数のLoRAアダプターを使用
- 同じプロンプトに対する各アダプターの出力を並べて比較

使用例:
  python compare_lora_adapters.py --prompt-file test_prompts/sql_generation.txt
  python compare_lora_adapters.py --prompt "What is 2+2?" --output results.txt
"""

import argparse
from pathlib import Path
from typing import List, Dict
from vllm import LLM, SamplingParams
from vllm.lora.request import LoRARequest


def load_prompts(file_path: Path) -> List[str]:
    """txtファイルからプロンプトを読み込む"""
    prompts = []
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                prompts.append(line)
    return prompts


def format_chat_prompt(user_message: str, system_message: str) -> str:
    """TinyLlamaのチャットテンプレートを適用"""
    return f"<|system|>\n{system_message}</s>\n<|user|>\n{user_message}</s>\n<|assistant|>\n"


# LoRAアダプターの定義
LORA_CONFIGS = {
    "base": {
        "name": "ベースモデル",
        "request": None,
        "system_message": "You are a helpful assistant.",
    },
    "text2sql": {
        "name": "SQL生成LoRA",
        "request": LoRARequest(
            lora_name="text2sql",
            lora_int_id=1,
            lora_path="sid321axn/tiny-llama-text2sql",
        ),
        "system_message": "You are a SQL expert.",
    },
    "math": {
        "name": "数学LoRA",
        "request": LoRARequest(
            lora_name="math",
            lora_int_id=2,
            lora_path="philimon/TinyLlama-gsm8k-lora",
        ),
        "system_message": "You are a math tutor.",
    },
    "function": {
        "name": "関数呼び出しLoRA",
        "request": LoRARequest(
            lora_name="function",
            lora_int_id=3,
            lora_path="unclecode/tinyllama-function-call-lora-adapter-250424",
        ),
        "system_message": "You are a function calling assistant.",
    },
}


def compare_lora_outputs(
    llm: LLM,
    prompt: str,
    lora_keys: List[str],
    sampling_params: SamplingParams,
) -> Dict[str, Dict]:
    """
    同じプロンプトを複数のLoRAアダプターで実行して結果を比較

    Returns:
        {
            "lora_key": {
                "name": "...",
                "output": "...",
                "tokens": int
            }
        }
    """
    results = {}

    for lora_key in lora_keys:
        config = LORA_CONFIGS[lora_key]

        # チャットテンプレートを適用
        formatted_prompt = format_chat_prompt(prompt, config["system_message"])

        # 推論実行
        outputs = llm.generate(
            prompts=[formatted_prompt],
            sampling_params=sampling_params,
            lora_request=config["request"],
        )

        generated_text = outputs[0].outputs[0].text.strip()
        num_tokens = len(outputs[0].outputs[0].token_ids)

        results[lora_key] = {
            "name": config["name"],
            "output": generated_text,
            "tokens": num_tokens,
        }

    return results


def print_comparison(prompt: str, results: Dict[str, Dict]):
    """比較結果を見やすく表示"""
    print("=" * 100)
    print(f"📝 プロンプト: {prompt}")
    print("=" * 100)

    for lora_key, result in results.items():
        print(f"\n🎯 {result['name']} ({lora_key})")
        print("-" * 100)
        print(result['output'])
        print(f"\n📊 トークン数: {result['tokens']}")
        print("-" * 100)

    print("\n" + "=" * 100 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="同じプロンプトを複数のLoRAアダプターで比較"
    )

    # プロンプト指定
    prompt_group = parser.add_mutually_exclusive_group(required=True)
    prompt_group.add_argument(
        "--prompt",
        type=str,
        help="単一のプロンプト文字列",
    )
    prompt_group.add_argument(
        "--prompt-file",
        type=Path,
        help="プロンプトが記載されたtxtファイル",
    )

    # LoRA選択
    parser.add_argument(
        "--loras",
        type=str,
        nargs="+",
        choices=list(LORA_CONFIGS.keys()),
        default=["base", "text2sql", "math", "function"],
        help="比較するLoRAアダプター（複数指定可）",
    )

    # モデル設定
    parser.add_argument(
        "--model",
        type=str,
        default="TinyLlama/TinyLlama-1.1B-Chat-v1.0",
        help="ベースモデル",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=150,
        help="最大生成トークン数",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.7,
        help="サンプリング温度",
    )

    # 出力設定
    parser.add_argument(
        "--output",
        type=Path,
        help="結果を保存するファイル（オプション）",
    )

    args = parser.parse_args()

    # プロンプトを取得
    if args.prompt:
        prompts = [args.prompt]
        print(f"📄 単一プロンプトモード")
    else:
        prompts = load_prompts(args.prompt_file)
        print(f"📄 プロンプトファイル: {args.prompt_file}")
        print(f"✅ {len(prompts)}個のプロンプトを読み込みました")

    # LLM初期化（Multi-LoRA有効）
    print(f"\n🚀 モデル初期化: {args.model}")
    print(f"🎯 使用するLoRAアダプター: {', '.join(args.loras)}")

    llm = LLM(
        model=args.model,
        enable_lora=True,
        max_loras=len([k for k in args.loras if k != "base"]),
        max_lora_rank=64,
        gpu_memory_utilization=0.85,
    )

    # サンプリングパラメータ
    sampling_params = SamplingParams(
        temperature=args.temperature,
        top_p=0.95,
        max_tokens=args.max_tokens,
    )

    print(f"\n⚙️  Temperature: {args.temperature}, Max tokens: {args.max_tokens}")
    print("\n" + "=" * 100)
    print("🔄 Multi-LoRA比較開始")
    print("=" * 100 + "\n")

    # 各プロンプトで比較
    all_results = []

    for i, prompt in enumerate(prompts, 1):
        print(f"\n📌 プロンプト {i}/{len(prompts)}")

        # 各LoRAで推論
        results = compare_lora_outputs(
            llm=llm,
            prompt=prompt,
            lora_keys=args.loras,
            sampling_params=sampling_params,
        )

        # 結果を表示
        print_comparison(prompt, results)

        # 保存用にフォーマット
        comparison = {
            "prompt": prompt,
            "results": results,
        }
        all_results.append(comparison)

    # ファイルに保存
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(f"Multi-LoRA比較結果\n")
            f.write(f"モデル: {args.model}\n")
            f.write(f"LoRA: {', '.join(args.loras)}\n")
            f.write(f"Temperature: {args.temperature}\n")
            f.write(f"Max tokens: {args.max_tokens}\n")
            f.write("=" * 100 + "\n\n")

            for comparison in all_results:
                f.write(f"プロンプト: {comparison['prompt']}\n")
                f.write("=" * 100 + "\n\n")

                for lora_key, result in comparison['results'].items():
                    f.write(f"{result['name']} ({lora_key})\n")
                    f.write("-" * 100 + "\n")
                    f.write(result['output'] + "\n")
                    f.write(f"\nトークン数: {result['tokens']}\n")
                    f.write("-" * 100 + "\n\n")

                f.write("\n\n")

        print(f"💾 結果を保存: {args.output}")

    print("\n✅ Multi-LoRA比較完了！")
    print("\n💡 重要な観察ポイント:")
    print("  - SQLプロンプトにMath LoRAを使うとどうなるか？")
    print("  - 各LoRAが専門外のタスクでどう振る舞うか？")
    print("  - ベースモデルと比較してLoRAの効果は明確か？")


if __name__ == "__main__":
    main()
