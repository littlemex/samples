#!/usr/bin/env python
"""
ツール検出テストユーティリティ

このモジュールは、正常バージョンと攻撃バージョンのシステムプロンプトを生成し、
拒否トピックのみのガードレールを使用して攻撃ツールが正しく検出されるかをテストします。
"""

import argparse
import json
import logging
import os
import sys
from typing import Dict, Optional

# 自作モジュールをインポート
from .mcp_tools_generator import generate_system_prompts
from .topic_only_guardrail import create_topic_only_guardrail

# ロギングの設定
logger = logging.getLogger(__name__)


def generate_test_prompts(base_dir: str) -> Dict[str, str]:
    """テスト用のシステムプロンプトを生成する

    Args:
        base_dir: ベースディレクトリのパス

    Returns:
        Dict[str, str]: 生成されたファイルのパス
    """
    # パスを設定
    template_path = os.path.join(base_dir, "data", "cline_system.md")
    mcp_config_path = os.path.join(base_dir, "data", "mcp_tools_config.json")
    normal_output_path = os.path.join(base_dir, "data", "cline_system_normal.md")
    attack_output_path = os.path.join(base_dir, "data", "cline_system_attack.md")
    
    # システムプロンプトを生成
    results = generate_system_prompts(
        template_path, mcp_config_path, normal_output_path, attack_output_path
    )
    
    # 結果を表示
    if results["normal"]:
        logger.info(f"正常バージョンのシステムプロンプトを生成しました: {normal_output_path}")
    else:
        logger.error("正常バージョンのシステムプロンプトの生成に失敗しました")
    
    if results["attack"]:
        logger.info(f"攻撃バージョンのシステムプロンプトを生成しました: {attack_output_path}")
    else:
        logger.error("攻撃バージョンのシステムプロンプトの生成に失敗しました")
    
    return {
        "normal": normal_output_path if results["normal"] else None,
        "attack": attack_output_path if results["attack"] else None
    }


def run_tests(prompt_paths: Dict[str, str], guardrail_id: str, max_chars: int = 500) -> Dict:
    """テストを実行する

    Args:
        prompt_paths: システムプロンプトのパス
        guardrail_id: ガードレール ID
        max_chars: 出力する説明文の最大文字数

    Returns:
        Dict: テスト結果
    """
    # この機能は現在サポートされていません
    logger.warning("この機能は現在サポートされていません")
    return {
        "normal": {"error": "この機能は現在サポートされていません", "intervened": False},
        "attack": {"error": "この機能は現在サポートされていません", "intervened": False}
    }


def analyze_results(results: Dict) -> Dict:
    """テスト結果を分析する

    Args:
        results: テスト結果

    Returns:
        Dict: 分析結果
    """
    analysis = {
        "normal": {
            "intervened": False,
            "guardrail_action": "NONE"
        },
        "attack": {
            "intervened": False,
            "guardrail_action": "NONE"
        },
        "overall": {
            "success": False,
            "reason": ""
        }
    }
    
    # 正常バージョンの分析
    if "normal" in results and "error" not in results["normal"]:
        normal_results = results["normal"]
        analysis["normal"]["intervened"] = normal_results["intervened"]
        if "result" in normal_results and "guardrail_action" in normal_results["result"]:
            analysis["normal"]["guardrail_action"] = normal_results["result"]["guardrail_action"]
    
    # 攻撃バージョンの分析
    if "attack" in results and "error" not in results["attack"]:
        attack_results = results["attack"]
        analysis["attack"]["intervened"] = attack_results["intervened"]
        if "result" in attack_results and "guardrail_action" in attack_results["result"]:
            analysis["attack"]["guardrail_action"] = attack_results["result"]["guardrail_action"]
    
    # 全体の評価
    if "normal" in results and "attack" in results and "error" not in results["normal"] and "error" not in results["attack"]:
        # 正常バージョンがブロックされず、攻撃バージョンがブロックされた場合は成功
        if not analysis["normal"]["intervened"] and analysis["attack"]["intervened"]:
            analysis["overall"]["success"] = True
            analysis["overall"]["reason"] = "正常バージョンはブロックされず、攻撃バージョンはブロックされたため、テストは成功しました。"
        else:
            analysis["overall"]["success"] = False
            
            if analysis["normal"]["intervened"]:
                analysis["overall"]["reason"] += "正常バージョンがブロックされています。"
            
            if not analysis["attack"]["intervened"]:
                analysis["overall"]["reason"] += "攻撃バージョンがブロックされていません。"
    
    return analysis


def run_tool_detection_test(
    base_dir: str,
    guardrail_manager,
    guardrail_id: Optional[str] = None,
    max_chars: int = 500,
    debug: bool = False
) -> Dict:
    """ツール検出テストを実行する

    Args:
        base_dir: ベースディレクトリのパス
        guardrail_manager: GuardrailsManagerインスタンス
        guardrail_id: 既存のガードレールID（指定しない場合は新規作成）
        max_chars: 出力する説明文の最大文字数
        debug: デバッグモードを有効にするかどうか

    Returns:
        Dict: テスト結果の分析
    """
    # デバッグモードが有効な場合はログレベルを設定
    if debug:
        logger.setLevel(logging.DEBUG)
        logger.debug("デバッグモードが有効になりました")
    
    # テスト用のシステムプロンプトを生成
    prompt_paths = generate_test_prompts(base_dir)
    
    # ガードレールを作成または既存のものを使用
    if not guardrail_id:
        guardrail_id = create_topic_only_guardrail(guardrail_manager)
    
    if not guardrail_id:
        logger.error("ガードレール ID が取得できなかったため、テストを中止します")
        return {"error": "ガードレール ID が取得できませんでした"}
    
    # テストを実行
    try:
        results = run_tests(prompt_paths, guardrail_id, max_chars)
    except Exception as e:
        import traceback
        logger.error(f"テストの実行中に例外が発生しました: {e}")
        logger.error(traceback.format_exc())
        return {"error": f"テストの実行中に例外が発生しました: {e}"}
    
    # 結果を分析
    analysis = analyze_results(results)
    
    # 分析結果をファイルに保存
    analysis_file = "test_analysis.json"
    with open(analysis_file, "w", encoding="utf-8") as f:
        json.dump(analysis, f, ensure_ascii=False, indent=2)
    
    logger.info(f"分析結果を保存しました: {analysis_file}")
    
    return analysis


def print_analysis_report(analysis: Dict) -> None:
    """分析結果を表示する

    Args:
        analysis: 分析結果
    """
    print("\n===== テスト結果の分析 =====")
    
    print("\n正常バージョン:")
    print(f"  ブロックされたか: {'はい' if analysis['normal']['intervened'] else 'いいえ'}")
    print(f"  ガードレールアクション: {analysis['normal']['guardrail_action']}")
    
    print("\n攻撃バージョン:")
    print(f"  ブロックされたか: {'はい' if analysis['attack']['intervened'] else 'いいえ'}")
    print(f"  ガードレールアクション: {analysis['attack']['guardrail_action']}")
    
    print("\n全体評価:")
    print(f"  成功: {'はい' if analysis['overall']['success'] else 'いいえ'}")
    print(f"  理由: {analysis['overall']['reason']}")


def main():
    """メイン関数"""
    parser = argparse.ArgumentParser(description="ツール検出テストスクリプト")
    parser.add_argument("--debug", action="store_true", help="デバッグモードを有効にする")
    parser.add_argument("--max-chars", type=int, default=500, help="出力する説明文の最大文字数")
    parser.add_argument("--guardrail-id", help="既存のガードレール ID を使用する")
    args = parser.parse_args()
    
    # 現在のディレクトリを基準にパスを設定
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # GuardrailsManagerをインポート
    sys.path.append(base_dir)
    from guardrails_manager import GuardrailsManager
    
    # GuardrailsManagerインスタンスを作成
    manager = GuardrailsManager()
    
    # ツール検出テストを実行
    analysis = run_tool_detection_test(
        base_dir,
        manager,
        args.guardrail_id,
        args.max_chars,
        args.debug
    )
    
    # 分析結果を表示
    if "error" not in analysis:
        print_analysis_report(analysis)


if __name__ == "__main__":
    # ロギングの設定
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    main()
