#!/usr/bin/env python3
"""
txtファイルからプロンプトを読み込んでバッチテストするスクリプト

使用方法:
  python batch_test_lora.py --prompt-file test_prompts/base_model.txt
  python batch_test_lora.py --prompt-file test_prompts/sql_generation.txt --lora text2sql
"""

import argparse
from pathlib import Path
from typing import List, Optional
from vllm import LLM, SamplingParams
from vllm.lora.request import LoRARequest


def load_prompts(file_path: Path) -> List[str]:
    """
    txtファイルからプロンプトを読み込む

    - 1行1プロンプト
    - #で始まる行はコメント
    - 空行は無視
    """
    prompts = []
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            # コメント行と空行をスキップ
            if line and not line.startswith('#'):
                prompts.append(line)
    return prompts


def format_chat_prompt(user_message: str, system_message: Optional[str] = None) -> str:
    """
    TinyLlamaのチャットテンプレートを適用

    フォーマット:
    <|system|>
    システムメッセージ</s>
    <|user|>
    ユーザーメッセージ</s>
    <|assistant|>
    """
    if system_message:
        prompt = f"<|system|>\n{system_message}</s>\n<|user|>\n{user_message}</s>\n<|assistant|>\n"
    else:
        prompt = f"<|user|>\n{user_message}</s>\n<|assistant|>\n"
    return prompt


# LoRAアダプターの定義
LORA_ADAPTERS = {
    "text2sql": {
        "request": LoRARequest(
            lora_name="text2sql",
            lora_int_id=1,
            lora_path="sid321axn/tiny-llama-text2sql",
        ),
        "system_message": "You are a SQL expert. Generate SQL queries based on the user's request.",
    },
    "math": {
        "request": LoRARequest(
            lora_name="math",
            lora_int_id=2,
            lora_path="philimon/TinyLlama-gsm8k-lora",
        ),
        "system_message": "You are a math tutor. Solve the problem step by step.",
    },
    "function": {
        "request": LoRARequest(
            lora_name="function",
            lora_int_id=3,
            lora_path="unclecode/tinyllama-function-call-lora-adapter-250424",
        ),
        "system_message": "You are a helpful assistant that can call functions.",
    },
}


def main():
    parser = argparse.ArgumentParser(description="LoRAアダプターのバッチテスト")
    parser.add_argument(
        "--prompt-file",
        type=Path,
        required=True,
        help="プロンプトが記載されたtxtファイル",
    )
    parser.add_argument(
        "--lora",
        type=str,
        choices=list(LORA_ADAPTERS.keys()) + ["none"],
        default="none",
        help="使用するLoRAアダプター (none=ベースモデルのみ)",
    )
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
    parser.add_argument(
        "--output",
        type=Path,
        help="結果を保存するファイル (オプション)",
    )
    args = parser.parse_args()

    # プロンプトを読み込み
    print(f"📄 プロンプトファイル: {args.prompt_file}")
    prompts = load_prompts(args.prompt_file)
    print(f"✅ {len(prompts)}個のプロンプトを読み込みました\n")

    # LLMを初期化
    print(f"🚀 モデル初期化: {args.model}")
    llm = LLM(
        model=args.model,
        enable_lora=(args.lora != "none"),
        max_loras=1,
        max_lora_rank=64,
        gpu_memory_utilization=0.85,
    )

    # サンプリングパラメータ
    sampling_params = SamplingParams(
        temperature=args.temperature,
        top_p=0.95,
        max_tokens=args.max_tokens,
    )

    # LoRAアダプターの設定
    lora_request = None
    system_message = "You are a helpful assistant."

    if args.lora != "none":
        adapter = LORA_ADAPTERS[args.lora]
        lora_request = adapter["request"]
        system_message = adapter["system_message"]
        print(f"🎯 LoRAアダプター: {args.lora}")
    else:
        print(f"🎯 ベースモデルのみ")

    # プロンプトをチャットテンプレートでフォーマット
    formatted_prompts = [
        format_chat_prompt(prompt, system_message)
        for prompt in prompts
    ]

    # バッチ推論
    print(f"\n⚙️  推論実行中...\n")
    print("=" * 80)

    outputs = llm.generate(
        prompts=formatted_prompts,
        sampling_params=sampling_params,
        lora_request=lora_request,
    )

    # 結果を表示・保存
    results = []
    for i, (prompt, output) in enumerate(zip(prompts, outputs), 1):
        generated_text = output.outputs[0].text.strip()
        num_tokens = len(output.outputs[0].token_ids)

        result_text = f"""
--- テスト {i}/{len(prompts)} ---
プロンプト: {prompt}

生成結果:
{generated_text}

トークン数: {num_tokens}
{'-' * 80}
"""
        print(result_text)
        results.append(result_text)

    # ファイルに保存
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(f"モデル: {args.model}\n")
            f.write(f"LoRA: {args.lora}\n")
            f.write(f"プロンプトファイル: {args.prompt_file}\n")
            f.write(f"Temperature: {args.temperature}\n")
            f.write(f"Max tokens: {args.max_tokens}\n")
            f.write("=" * 80 + "\n\n")
            f.write("\n".join(results))
        print(f"\n💾 結果を保存: {args.output}")

    print("\n✅ バッチテスト完了！")


if __name__ == "__main__":
    main()
