#!/usr/bin/env python
"""
Amazon Bedrock Guardrails の最小限の実装

このモジュールは、Amazon Bedrock Guardrails の設定、デプロイ、テストを行うための
最小限の機能を提供します。コンテンツフィルター、拒否トピック、機密情報フィルターなどの
基本的な設定を提供します。
"""

import argparse
import json
import logging
import os
import time
from typing import Dict, List, Optional

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

from utils.filter_configs import (
    get_basic_guardrail_config,
    get_allowed_tools_guardrail_config,
    get_allowed_tools_from_config,
)
from utils.tool_detection import run_tool_detection_test, print_analysis_report

# 環境変数の読み込み
load_dotenv()

# ロギングの設定
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# デバッグモードを有効にする場合はコメントを外す
# logger.setLevel(logging.DEBUG)


class GuardrailsManager:
    """Guardrails 管理クラス"""

    def __init__(self, region_name: Optional[str] = None):
        """初期化

        Args:
            region_name: AWS リージョン名
        """
        self.region_name = region_name or os.environ.get("AWS_REGION", "us-east-1")
        self.bedrock_guardrails_client = boto3.client(
            "bedrock", region_name=self.region_name
        )
        self.bedrock_runtime_client = boto3.client(
            "bedrock-runtime", region_name=self.region_name
        )
        self.sts_client = boto3.client("sts", region_name=self.region_name)
        self.account_id = self.sts_client.get_caller_identity().get("Account")
        self.model_id = os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-3-sonnet-20240229-v1:0")

    def create_guardrail(self, config: Dict) -> str:
        """ガードレールを作成する

        Args:
            config: ガードレール設定

        Returns:
            str: ガードレール ARN
        """
        try:
            # ブロックされたメッセージのデフォルト値
            blocked_input_messaging = "このプロンプトは許可されていません。"
            blocked_outputs_messaging = "この応答は許可されていません。"
            
            response = self.bedrock_guardrails_client.create_guardrail(
                name=config["name"],
                description=config.get("description", ""),
                blockedInputMessaging=blocked_input_messaging,
                blockedOutputsMessaging=blocked_outputs_messaging,
                contentPolicyConfig=config.get("contentPolicyConfig", {}),
                sensitiveInformationPolicyConfig=config.get(
                    "sensitiveInformationPolicyConfig", {}
                ),
                topicPolicyConfig=config.get("topicPolicyConfig", {}),
                contextualGroundingPolicyConfig=config.get(
                    "contextualGroundingPolicyConfig", {}
                ),
                wordPolicyConfig=config.get("wordPolicyConfig", {}),
                crossRegionConfig=config.get("crossRegionConfig", {
                    "guardrailProfileIdentifier": "us.guardrail.v1:0"
                }),
            )
            guardrail_arn = response["guardrailArn"]
            guardrail_id = guardrail_arn.split("/")[-1]
            logger.info(f"ガードレールを作成しました: {guardrail_arn}")
            return guardrail_id
        except ClientError as e:
            logger.error(f"ガードレールの作成に失敗しました: {e}")
            return ""

    def create_guardrail_version(self, guardrail_id: str) -> str:
        """ガードレールのバージョンを作成する

        Args:
            guardrail_id: ガードレール ID

        Returns:
            str: ガードレールバージョン
        """
        try:
            response = self.bedrock_guardrails_client.create_guardrail_version(
                guardrailIdentifier=guardrail_id
            )
            guardrail_version = response["guardrailVersion"]
            logger.info(f"ガードレールバージョンを作成しました: {guardrail_version}")
            return guardrail_version
        except ClientError as e:
            logger.error(f"ガードレールバージョンの作成に失敗しました: {e}")
            return ""

    def list_guardrails(self) -> List[Dict]:
        """ガードレールの一覧を取得する

        Returns:
            List[Dict]: ガードレールの一覧
        """
        try:
            response = self.bedrock_guardrails_client.list_guardrails()
            guardrails = response.get("guardrails", [])
            logger.info(f"ガードレールの一覧を取得しました: {len(guardrails)} 件")
            return guardrails
        except ClientError as e:
            logger.error(f"ガードレールの一覧取得に失敗しました: {e}")
            return []

    def get_guardrail(self, guardrail_id: str) -> Dict:
        """ガードレールの詳細を取得する

        Args:
            guardrail_id: ガードレール ID

        Returns:
            Dict: ガードレールの詳細
        """
        try:
            response = self.bedrock_guardrails_client.get_guardrail(
                guardrailIdentifier=guardrail_id
            )
            logger.info(f"ガードレールの詳細を取得しました: {guardrail_id}")
            return response
        except ClientError as e:
            logger.error(f"ガードレールの詳細取得に失敗しました: {e}")
            return {}

    def delete_guardrail(self, guardrail_id: str) -> bool:
        """ガードレールを削除する

        Args:
            guardrail_id: ガードレール ID

        Returns:
            bool: 削除成功の場合は True、失敗の場合は False
        """
        try:
            self.bedrock_guardrails_client.delete_guardrail(guardrailIdentifier=guardrail_id)
            logger.info(f"ガードレールを削除しました: {guardrail_id}")
            return True
        except ClientError as e:
            logger.error(f"ガードレールの削除に失敗しました: {e}")
            return False

    def create_basic_guardrail(self) -> str:
        """基本的なガードレールを作成する

        Returns:
            str: ガードレール ID
        """
        # 基本設定
        timestamp = int(time.time())
        config = get_basic_guardrail_config()
        
        # 名前と説明を設定
        config["name"] = f"basic-guardrail-{timestamp}"
        config["description"] = "基本的なガードレール"
        
        guardrail_id = self.create_guardrail(config)
        
        # ガードレールIDを保存
        if guardrail_id:
            self.save_guardrail_id(guardrail_id, policy_type="basic")
            
        return guardrail_id

    def create_allowed_tools_guardrail(self) -> str:
        """許可ツールリストによる制限のガードレールを作成する
        
        mcp_tools_config.jsonから安全なツールのリストを取得し、
        それ以外のツールを拒否するガードレールを作成する

        Returns:
            str: ガードレール ID
        """
        # 基本設定
        timestamp = int(time.time())
        
        # 許可ツールリストによる制限のガードレール設定を取得
        # 引数を指定しないことで、mcp_tools_config.jsonから安全なツールのリストを取得する
        config = get_allowed_tools_guardrail_config()
        
        # 名前と説明を設定
        config["name"] = f"allowed-tools-guardrail-{timestamp}"
        config["description"] = "許可ツールリストによる制限のガードレール（mcp_tools_config.jsonから安全なツールのリストを取得）"
        
        guardrail_id = self.create_guardrail(config)
        
        # ガードレールIDを保存
        if guardrail_id:
            self.save_guardrail_id(guardrail_id, policy_type="allowed_tools")
            
        return guardrail_id

    def invoke_model_with_guardrail(
        self, prompt: str, guardrail_id: str, guardrail_version: str = "DRAFT"
    ) -> Dict:
        """ガードレールを適用してモデルを呼び出す

        Args:
            prompt: プロンプト
            guardrail_id: ガードレール ID
            guardrail_version: ガードレールバージョン

        Returns:
            Dict: レスポンス
        """
        try:
            # プロンプトが空の場合はエラーを返す
            if not prompt:
                error_msg = "プロンプトが空です。テストケースにプロンプトを設定してください。"
                logger.error(error_msg)
                return {"error": error_msg}
            
            # モデル固有のリクエストボディを作成
            if "anthropic.claude" in self.model_id:
                request_body = {
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 1000,
                    "messages": [{"role": "user", "content": prompt}],
                }
            elif "amazon.titan" in self.model_id:
                request_body = {
                    "inputText": prompt,
                    "textGenerationConfig": {
                        "maxTokenCount": 1000,
                        "temperature": 0.7,
                        "topP": 0.9,
                    },
                }
            else:
                # デフォルトのリクエストボディ
                request_body = {"prompt": prompt, "max_tokens": 1000}

            # モデル呼び出し
            invoke_params = {
                "modelId": self.model_id,
                "body": json.dumps(request_body),
                "guardrailIdentifier": guardrail_id,
                "guardrailVersion": guardrail_version,
                "trace": "ENABLED",
            }
                
            response = self.bedrock_runtime_client.invoke_model(**invoke_params)
            
            # レスポンスの解析
            response_body = json.loads(response["body"].read().decode("utf-8"))
            
            # ガードレールのアクション情報を取得（デフォルトは "NONE"）
            guardrail_action = response_body.get("amazon-bedrock-guardrailAction", "NONE")
            
            # ガードレールのトレース情報を取得
            guardrail_trace = response_body.get("amazon-bedrock-trace", {})
            
            # デバッグ情報を出力
            logger.debug(f"レスポンスボディ: {json.dumps(response_body, ensure_ascii=False)[:500]}...")
            logger.debug(f"ガードレールアクション: {guardrail_action}")
            logger.debug(f"ガードレールトレース: {json.dumps(guardrail_trace, ensure_ascii=False)[:500]}...")
            
            # 注意: ガードレールの内部では "BLOCKED" というアクションが使われますが、
            # APIレスポンスとしては "INTERVENED" という値が返されます
            
            # 結果を整形
            result = {
                "guardrail_action": guardrail_action,
                "trace": guardrail_trace,
                "response": response_body,
                "model_id": self.model_id,
                "guardrail_id": guardrail_id,
                "guardrail_version": guardrail_version,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            
            return result
        except ClientError as e:
            logger.error(f"モデル呼び出しに失敗しました: {e}")
            return {"error": str(e)}

    def run_test_cases(self, guardrail_id: str, test_cases_file: str) -> Dict:
        """テストケースを実行する

        Args:
            guardrail_id: ガードレール ID
            test_cases_file: テストケースファイルのパス

        Returns:
            Dict: テスト結果
        """
        # テストケースの読み込み
        try:
            with open(test_cases_file, "r", encoding="utf-8") as f:
                file_content = json.load(f)
            
            # ファイル形式のチェック
            if isinstance(file_content, list):
                # 配列形式の場合はテストケースとして処理
                test_cases = file_content
                logger.info(f"テストケースを読み込みました: {len(test_cases)} 件")
            elif isinstance(file_content, dict):
                # オブジェクト形式の場合はエラーメッセージを表示
                logger.error(f"ファイル {test_cases_file} はテストケース形式ではありません。テストケースファイルは配列形式である必要があります。")
                return {
                    "error": f"ファイル {test_cases_file} はテストケース形式ではありません。テストケースファイルは配列形式である必要があります。",
                    "file_format": "object",
                    "expected_format": "array"
                }
            else:
                # その他の形式の場合もエラーメッセージを表示
                logger.error(f"ファイル {test_cases_file} は無効な形式です。JSONの配列形式である必要があります。")
                return {
                    "error": f"ファイル {test_cases_file} は無効な形式です。JSONの配列形式である必要があります。",
                    "file_format": str(type(file_content)),
                    "expected_format": "array"
                }
        except Exception as e:
            logger.error(f"テストケースの読み込みに失敗しました: {e}")
            return {"error": str(e)}
        
        results = []
        
        for i, test_case in enumerate(test_cases):
            logger.info(f"テストケース {i+1}/{len(test_cases)} を実行中: {test_case.get('name', 'unnamed')}")
            
            # 期待される結果
            expected_result = test_case.get("expected_result", "BLOCKED")
            
            # プロンプトの取得
            prompt = test_case.get("prompt", "")
            if not prompt and "tool_description" in test_case:
                # ツール説明からプロンプトを作成
                tool_description = test_case["tool_description"]
                prompt = f"""
                以下のツール説明を評価してください：

                ```
                {tool_description}
                ```

                このツールは安全ですか？使用しても問題ないでしょうか？
                """
            
            # プロンプトが空の場合はエラーメッセージを表示
            if not prompt:
                category = test_case.get("category", "unknown")
                name = test_case.get("name", "unnamed")
                error_msg = f"テストケース '{name}' (カテゴリ: {category}) のプロンプトが空です。テストケースファイルにプロンプトを設定してください。"
                logger.error(error_msg)
                
                # 結果を保存して次のテストケースに進む
                test_result = {
                    "test_case": test_case,
                    "result": {"error": error_msg},
                    "is_success": False,
                    "expected": expected_result,
                    "actual": "ERROR",
                }
                results.append(test_result)
                continue
            
            # モデル呼び出し
            result = self.invoke_model_with_guardrail(prompt, guardrail_id)
            
            # 実際の結果
            actual_result = result.get("guardrail_action", "NONE")
            
            # 結果の判定
            is_success = expected_result == actual_result
            
            # 結果の保存
            test_result = {
                "test_case": test_case,
                "result": result,
                "is_success": is_success,
                "expected": expected_result,
                "actual": actual_result,
            }
            results.append(test_result)
            
            # 結果の表示
            status = "成功" if is_success else "失敗"
            logger.info(f"テスト結果: {status} (期待: {expected_result}, 実際: {actual_result})")
            
            # デバッグモードの場合は詳細情報を表示
            if logger.level <= logging.DEBUG:
                logger.debug(f"テストケース名: {test_case.get('name', 'unnamed')}")
                logger.debug(f"カテゴリ: {test_case.get('category', 'unknown')}")
                logger.debug(f"プロンプト: {prompt}")
                
                # レスポンスの詳細を表示
                if "error" in result:
                    logger.debug(f"エラー: {result['error']}")
                else:
                    if "response" in result and isinstance(result["response"], dict):
                        if "content" in result["response"]:
                            logger.debug(f"レスポンス: {result['response']['content'][:200]}...")
                        elif "completion" in result["response"]:
                            logger.debug(f"レスポンス: {result['response']['completion'][:200]}...")
                        elif "outputText" in result["response"]:
                            logger.debug(f"レスポンス: {result['response']['outputText'][:200]}...")
                    
                    if "trace" in result and result["trace"]:
                        logger.debug(f"トレース情報: {json.dumps(result['trace'], ensure_ascii=False, indent=2)}")
            
            # 少し待機して API 制限に引っかからないようにする
            time.sleep(1)
        
        # 全体の結果を集計
        success_count = sum(1 for r in results if r["is_success"])
        total_count = len(results)
        success_rate = success_count / total_count if total_count > 0 else 0
        
        summary = {
            "total_tests": total_count,
            "success_tests": success_count,
            "success_rate": success_rate,
            "results": results,
        }
        
        logger.info(f"テスト完了: {success_count}/{total_count} 成功 (成功率: {success_rate:.2%})")
        
        return summary

    def save_results(self, results: Dict, output_file: str) -> None:
        """テスト結果を保存する

        Args:
            results: テスト結果
            output_file: 出力ファイルのパス
        """
        try:
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            logger.info(f"テスト結果を保存しました: {output_file}")
        except Exception as e:
            logger.error(f"テスト結果の保存に失敗しました: {e}")

    def save_guardrail_id(self, guardrail_id: str, policy_type: str = "basic", filename: str = "guardrail_ids.json") -> None:
        """ガードレールIDをJSONファイルに保存する

        Args:
            guardrail_id: ガードレール ID
            policy_type: ポリシータイプ（basic, allowed_tools など）
            filename: 保存先ファイル名
        """
        try:
            # 既存のJSONファイルがあれば読み込み、なければ新規作成
            guardrail_ids = {}
            if os.path.exists(filename):
                try:
                    with open(filename, "r", encoding="utf-8") as f:
                        guardrail_ids = json.load(f)
                except json.JSONDecodeError:
                    logger.warning(f"JSONファイルの解析に失敗しました。新規作成します: {filename}")
            
            # ガードレールIDを追加または更新
            guardrail_ids[policy_type] = guardrail_id
            
            # JSONファイルに書き込み
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(guardrail_ids, f, ensure_ascii=False, indent=2)
            
            logger.info(f"ガードレールIDをJSONファイルに保存しました: {filename}, policy_type: {policy_type}")
        except Exception as e:
            logger.error(f"ガードレールIDの保存に失敗しました: {e}")


def main():
    """メイン関数"""
    parser = argparse.ArgumentParser(description="Amazon Bedrock Guardrails の最小限の実装")
    
    # 基本設定
    parser.add_argument("--region", help="AWS リージョン名", default=os.environ.get("AWS_REGION", "us-east-1"))
    parser.add_argument("--model-id", help="Bedrock モデル ID", default=os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-3-sonnet-20240229-v1:0"))
    
    # ガードレール操作
    parser.add_argument("--list", action="store_true", help="ガードレールの一覧を表示")
    parser.add_argument("--create-basic", action="store_true", help="基本的なガードレールを作成")
    parser.add_argument("--create-allowed-tools", action="store_true", help="許可ツールリストによる制限のガードレールを作成（mcp_tools_config.jsonから安全なツールのリストを取得）")
    parser.add_argument("--delete", help="ガードレールを削除（ガードレール ID）")
    
    # テスト実行
    parser.add_argument("--test", help="テストを実行（ガードレール ID または 'basic', 'allowed_tools' などのタイプ。指定しない場合は guardrail_ids.json から 'test' タイプのIDを使用）")
    parser.add_argument("--test-case", "--test-cases", dest="test_cases", help="テストケースファイルのパス", default="data/japanese_test_cases.json")
    parser.add_argument("--test-prompt", help="システムプロンプトファイルのパス（指定した場合、プロンプト内のMCPツール定義をテスト）")
    parser.add_argument("--test-tool-detection", action="store_true", help="ツール検出テストを実行する")
    parser.add_argument("--max-chars", type=int, help="出力する説明文の最大文字数", default=500)
    parser.add_argument("--output", help="出力ファイルのパス", default="test_results.json")
    parser.add_argument("--debug", action="store_true", help="デバッグモードを有効にする")
    parser.add_argument("--verbose", action="store_true", help="詳細な出力を表示する")
    
    args = parser.parse_args()
    
    # デバッグモードまたは詳細モードが有効な場合はログレベルを設定
    if args.debug:
        logger.setLevel(logging.DEBUG)
        logger.debug("デバッグモードが有効になりました")
    elif args.verbose:
        logger.setLevel(logging.INFO)
        logger.info("詳細モードが有効になりました")
    
    manager = GuardrailsManager(region_name=args.region)
    if args.model_id:
        manager.model_id = args.model_id
    
    if args.list:
        guardrails = manager.list_guardrails()
        for guardrail in guardrails:
            # APIレスポンスの構造に合わせてキーを調整
            guardrail_id = guardrail.get('guardrailId', guardrail.get('id', 'unknown'))
            name = guardrail.get('name', 'unnamed')
            print(f"{guardrail_id}: {name}")
            # ARNも表示
            if 'guardrailArn' in guardrail:
                print(f"  ARN: {guardrail['guardrailArn']}")
    elif args.create_basic:
        guardrail_id = manager.create_basic_guardrail()
        if guardrail_id:
            print(f"基本的なガードレールを作成しました: {guardrail_id}")
        else:
            print("ガードレールの作成に失敗しました")
    elif args.create_allowed_tools:
        guardrail_id = manager.create_allowed_tools_guardrail()
        if guardrail_id:
            # 安全なツールのリストを取得して表示
            allowed_tools = get_allowed_tools_from_config()
            print(f"許可ツールリストによる制限のガードレールを作成しました: {guardrail_id}")
            print(f"許可ツール: {', '.join(allowed_tools)}")
        else:
            print("ガードレールの作成に失敗しました")
    elif args.delete:
        success = manager.delete_guardrail(args.delete)
        if success:
            print(f"ガードレールを削除しました: {args.delete}")
        else:
            print(f"ガードレールの削除に失敗しました: {args.delete}")
    elif args.test_tool_detection:
        guardrail_id = args.test
        
        # guardrail_ids.json からガードレールIDを取得
        if guardrail_id is None or guardrail_id in ["basic", "test", "allowed_tools"]:
            policy_type = guardrail_id if guardrail_id else "test"
            try:
                if os.path.exists("guardrail_ids.json"):
                    with open("guardrail_ids.json", "r", encoding="utf-8") as f:
                        guardrail_ids = json.load(f)
                    
                    if policy_type in guardrail_ids:
                        guardrail_id = guardrail_ids[policy_type]
                        print(f"{policy_type} タイプのガードレールIDを guardrail_ids.json から取得しました: {guardrail_id}")
                    else:
                        print(f"エラー: guardrail_ids.json に {policy_type} タイプのガードレールIDが見つかりません")
                        return
                else:
                    print("エラー: guardrail_ids.json が見つかりません")
                    return
            except Exception as e:
                print(f"エラー: guardrail_ids.json の読み込みに失敗しました: {e}")
                return
        
        # テスト実行前にガードレールIDを保存
        manager.save_guardrail_id(guardrail_id, policy_type="test")
        
        # 現在のディレクトリを基準にパスを設定
        base_dir = os.path.dirname(os.path.abspath(__file__))
        
        # テスト実行前の情報表示
        print(f"ガードレールID: {guardrail_id}")
        print(f"最大文字数: {args.max_chars}")
        print(f"デバッグモード: {'有効' if args.debug else '無効'}")
        print(f"詳細モード: {'有効' if args.verbose else '無効'}")
        print("ツール検出テストを開始します...")
        
        # ツール検出テストを実行
        analysis = run_tool_detection_test(
            base_dir,
            manager,
            guardrail_id,
            args.max_chars,
            args.debug or args.verbose
        )
        
        if "error" in analysis:
            print(f"テストの実行に失敗しました: {analysis['error']}")
        else:
            # 分析結果を表示
            print_analysis_report(analysis)
    
    elif args.test_prompt:
        print("この機能は現在サポートされていません。")
    elif args.test or args.test_cases:
        guardrail_id = args.test
        
        # guardrail_ids.json からガードレールIDを取得
        if guardrail_id is None or guardrail_id in ["basic", "test", "allowed_tools"]:
            policy_type = guardrail_id if guardrail_id else "test"
            try:
                if os.path.exists("guardrail_ids.json"):
                    with open("guardrail_ids.json", "r", encoding="utf-8") as f:
                        guardrail_ids = json.load(f)
                    
                    if policy_type in guardrail_ids:
                        guardrail_id = guardrail_ids[policy_type]
                        print(f"{policy_type} タイプのガードレールIDを guardrail_ids.json から取得しました: {guardrail_id}")
                    else:
                        print(f"エラー: guardrail_ids.json に {policy_type} タイプのガードレールIDが見つかりません")
                        return
                else:
                    print("エラー: guardrail_ids.json が見つかりません")
                    return
            except Exception as e:
                print(f"エラー: guardrail_ids.json の読み込みに失敗しました: {e}")
                return
        
        # テスト実行前にガードレールIDを保存
        manager.save_guardrail_id(guardrail_id, policy_type="test")
        
        # テスト実行前の情報表示
        print(f"ガードレールID: {guardrail_id}")
        print(f"テストケースファイル: {args.test_cases}")
        print(f"出力ファイル: {args.output}")
        print(f"デバッグモード: {'有効' if args.debug else '無効'}")
        print(f"詳細モード: {'有効' if args.verbose else '無効'}")
        print("テストを開始します...")
        
        results = manager.run_test_cases(guardrail_id, args.test_cases)
        if "error" in results:
            print(f"テストの実行に失敗しました: {results['error']}")
        else:
            print(f"テスト完了: {results['success_tests']}/{results['total_tests']} 成功 (成功率: {results['success_rate']:.2%})")
            manager.save_results(results, args.output)
            print(f"テスト結果を保存しました: {args.output}")
            
            # 詳細モードの場合は結果の概要を表示
            if args.verbose or args.debug:
                print("\nテスト結果の概要:")
                for i, result in enumerate(results["results"]):
                    test_case = result["test_case"]
                    name = test_case.get("name", f"テストケース{i+1}")
                    expected = result["expected"]
                    actual = result["actual"]
                    status = "成功" if result["is_success"] else "失敗"
                    print(f"  {i+1}. {name}: {status} (期待: {expected}, 実際: {actual})")
    else:
        parser.print_help()
        print("\n使用例:")
        print("  # ガードレールの一覧を表示")
        print("  uv run guardrails_manager.py --list")
        print("\n  # 基本的なガードレールを作成")
        print("  uv run guardrails_manager.py --create-basic")
        print("\n  # 許可ツールリストによる制限のガードレールを作成")
        print("  uv run guardrails_manager.py --create-allowed-tools")
        print("\n  # テストを実行（ガードレールIDを指定）")
        print("  uv run guardrails_manager.py --test your-guardrail-id --test-cases data/japanese_test_cases.json")
        print("\n  # テストを実行（guardrail_ids.json から 'test' タイプのIDを使用）")
        print("  uv run guardrails_manager.py --test-cases data/japanese_test_cases.json")
        print("\n  # テストを実行（guardrail_ids.json から 'basic' タイプのIDを使用）")
        print("  uv run guardrails_manager.py --test basic --test-cases data/japanese_test_cases.json")
        print("\n  # システムプロンプトのMCPツール定義をテスト")
        print("  uv run guardrails_manager.py --test-prompt path/to/system_prompt.md --test allowed_tools")
        print("\n  # ツール検出テストを実行")
        print("  uv run guardrails_manager.py --test-tool-detection --test allowed_tools")
        print("\n  # ガードレールを削除")
        print("  uv run guardrails_manager.py --delete your-guardrail-id")


if __name__ == "__main__":
    main()
