#!/usr/bin/env python3
"""
Function Calling能力をテストするスクリプト

このスクリプトは、JSONで定義された関数とユーザークエリを使用して、
モデルのfunction calling能力を評価します。

期待される出力形式:
<functioncall>
{"name": "function_name", "arguments": '{"param": "value"}'}
<|endoftext|>

使用例:
  python test_function_calling.py
  python test_function_calling.py --lora function --output results.txt
"""

import argparse
import json
from pathlib import Path
from typing import Dict, List
from vllm import LLM, SamplingParams
from vllm.lora.request import LoRARequest


def load_function_calling_tests(json_path: Path) -> List[Dict]:
    """JSONファイルからfunction callingテストケースを読み込む"""
    with open(json_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def format_functions_for_system(functions: List[Dict]) -> str:
    """関数定義をシステムメッセージ用にフォーマット"""
    functions_json = json.dumps(functions, indent=2)
    return f"You are a helpful assistant with access to the following functions. Use them when appropriate:\n\n{functions_json}\n\nTo call a function, respond with:\n<functioncall>\n{{\"name\": \"function_name\", \"arguments\": '{{\"param\": \"value\"}}'}}\n<|endoftext|>"


def format_chat_prompt(user_message: str, system_message: str) -> str:
    """TinyLlamaのチャットテンプレートを適用"""
    return f"<|system|>\n{system_message}</s>\n<|user|>\n{user_message}</s>\n<|assistant|>\n"


def parse_function_call(output: str) -> Dict:
    """モデル出力から関数呼び出しをパース"""
    try:
        # <functioncall>タグを探す
        if "<functioncall>" in output:
            start = output.index("<functioncall>") + len("<functioncall>")

            # 終了タグを探す
            end_tags = ["<|endoftext|>", "<|eot_id|>", "</s>"]
            end = len(output)
            for tag in end_tags:
                if tag in output[start:]:
                    end = start + output[start:].index(tag)
                    break

            # JSON部分を抽出
            json_str = output[start:end].strip()

            # JSONをパース
            function_call = json.loads(json_str)
            return {
                "success": True,
                "function_name": function_call.get("name"),
                "arguments": json.loads(function_call.get("arguments", "{}")),
                "raw": json_str,
            }
        else:
            return {
                "success": False,
                "error": "No <functioncall> tag found",
                "raw": output,
            }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "raw": output,
        }


def evaluate_function_call(parsed: Dict, expected_function: str, expected_args: Dict) -> Dict:
    """関数呼び出しが正しいかを評価"""
    if not parsed["success"]:
        return {
            "correct": False,
            "reason": f"Parse error: {parsed.get('error')}",
        }

    # 関数名チェック
    if parsed["function_name"] != expected_function:
        return {
            "correct": False,
            "reason": f"Wrong function: expected '{expected_function}', got '{parsed['function_name']}'",
        }

    # 引数チェック（必須パラメータのみ）
    args = parsed["arguments"]
    missing_args = []
    wrong_args = []

    for key, expected_value in expected_args.items():
        if key not in args:
            missing_args.append(key)
        elif args[key] != expected_value:
            wrong_args.append(f"{key}: expected {expected_value}, got {args[key]}")

    if missing_args or wrong_args:
        reasons = []
        if missing_args:
            reasons.append(f"Missing args: {', '.join(missing_args)}")
        if wrong_args:
            reasons.append(f"Wrong args: {', '.join(wrong_args)}")

        return {
            "correct": False,
            "reason": "; ".join(reasons),
        }

    return {
        "correct": True,
        "reason": "Perfect match",
    }


def main():
    parser = argparse.ArgumentParser(
        description="Function Calling能力をテスト"
    )
    parser.add_argument(
        "--test-file",
        type=Path,
        default=Path("test_prompts/function_calling.json"),
        help="テストケースJSONファイル",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="TinyLlama/TinyLlama-1.1B-Chat-v1.0",
        help="ベースモデル",
    )
    parser.add_argument(
        "--lora",
        type=str,
        choices=["none", "function"],
        default="function",
        help="使用するLoRAアダプター",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=200,
        help="最大生成トークン数",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.0,
        help="サンプリング温度（0=決定的）",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="結果を保存するファイル",
    )

    args = parser.parse_args()

    # テストケースを読み込み
    print(f"📄 テストファイル: {args.test_file}")
    test_cases = load_function_calling_tests(args.test_file)
    print(f"✅ {len(test_cases)}個のテストケースを読み込みました\n")

    # LLM初期化
    print(f"🚀 モデル初期化: {args.model}")
    llm = LLM(
        model=args.model,
        enable_lora=(args.lora != "none"),
        max_loras=1,
        max_lora_rank=64,
        gpu_memory_utilization=0.85,
    )

    # LoRA設定
    lora_request = None
    if args.lora == "function":
        lora_request = LoRARequest(
            lora_name="function",
            lora_int_id=1,
            lora_path="unclecode/tinyllama-function-call-lora-adapter-250424",
        )
        print(f"🎯 LoRA: Function Calling")
    else:
        print(f"🎯 ベースモデルのみ")

    # サンプリングパラメータ
    sampling_params = SamplingParams(
        temperature=args.temperature,
        top_p=0.95,
        max_tokens=args.max_tokens,
    )

    print(f"\n⚙️  Temperature: {args.temperature}, Max tokens: {args.max_tokens}")
    print("\n" + "=" * 100)
    print("🧪 Function Calling テスト開始")
    print("=" * 100)

    # テスト実行
    results = []
    correct_count = 0

    for i, test in enumerate(test_cases, 1):
        print(f"\n📌 テスト {i}/{len(test_cases)}")
        print(f"クエリ: {test['user_query']}")

        # システムメッセージを生成
        system_message = format_functions_for_system(test['functions'])

        # プロンプトをフォーマット
        formatted_prompt = format_chat_prompt(test['user_query'], system_message)

        # 推論実行
        outputs = llm.generate(
            prompts=[formatted_prompt],
            sampling_params=sampling_params,
            lora_request=lora_request,
        )

        generated_text = outputs[0].outputs[0].text.strip()
        num_tokens = len(outputs[0].outputs[0].token_ids)

        # 関数呼び出しをパース
        parsed = parse_function_call(generated_text)

        # 評価
        evaluation = evaluate_function_call(
            parsed,
            test.get('expected_function', ''),
            test.get('expected_args', {}),
        )

        is_correct = evaluation['correct']
        if is_correct:
            correct_count += 1

        # 結果表示
        status = "✅ 正解" if is_correct else "❌ 不正解"
        print(f"\n{status}")
        print(f"期待: {test.get('expected_function')}({test.get('expected_args')})")

        if parsed['success']:
            print(f"実際: {parsed['function_name']}({parsed['arguments']})")
        else:
            print(f"エラー: {parsed.get('error')}")

        print(f"理由: {evaluation['reason']}")
        print(f"出力:\n{generated_text[:200]}...")
        print("-" * 100)

        # 結果を保存
        results.append({
            "test_id": i,
            "user_query": test['user_query'],
            "expected_function": test.get('expected_function'),
            "expected_args": test.get('expected_args'),
            "generated_text": generated_text,
            "parsed": parsed,
            "evaluation": evaluation,
            "tokens": num_tokens,
        })

    # サマリー
    accuracy = (correct_count / len(test_cases)) * 100
    print("\n" + "=" * 100)
    print("📊 テスト結果サマリー")
    print("=" * 100)
    print(f"正解数: {correct_count}/{len(test_cases)}")
    print(f"精度: {accuracy:.1f}%")

    # ファイルに保存
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write("Function Calling テスト結果\n")
            f.write("=" * 100 + "\n\n")
            f.write(f"モデル: {args.model}\n")
            f.write(f"LoRA: {args.lora}\n")
            f.write(f"Temperature: {args.temperature}\n")
            f.write(f"正解数: {correct_count}/{len(test_cases)}\n")
            f.write(f"精度: {accuracy:.1f}%\n\n")

            for result in results:
                f.write(f"テスト {result['test_id']}\n")
                f.write(f"クエリ: {result['user_query']}\n")
                f.write(f"期待: {result['expected_function']}({result['expected_args']})\n")

                if result['parsed']['success']:
                    f.write(f"実際: {result['parsed']['function_name']}({result['parsed']['arguments']})\n")
                else:
                    f.write(f"エラー: {result['parsed'].get('error')}\n")

                f.write(f"評価: {result['evaluation']['reason']}\n")
                f.write(f"出力:\n{result['generated_text']}\n")
                f.write("-" * 100 + "\n\n")

        print(f"\n💾 結果を保存: {args.output}")

    print("\n✅ Function Callingテスト完了！")


if __name__ == "__main__":
    main()
