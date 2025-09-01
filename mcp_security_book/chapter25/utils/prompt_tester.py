"""
システムプロンプトテストユーティリティ

このモジュールは、システムプロンプトに埋め込まれたMCPツール定義に対して
ガードレールが正しく機能しているかをテストするための機能を提供します。
"""

import json
import logging
import os
import codecs
from typing import Dict, List, Tuple

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


def extract_mcp_tools_from_system_prompt(system_prompt_path: str, max_chars: int = 500) -> List[Dict]:
    """システムプロンプトからMCPツール定義を抽出する

    Args:
        system_prompt_path: システムプロンプトファイルのパス
        max_chars: 出力する説明文の最大文字数

    Returns:
        List[Dict]: 抽出されたMCPツール定義のリスト
    """
    try:
        with open(system_prompt_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # MCPサーバーセクションを抽出
        mcp_section_start = content.find("# Connected MCP Servers")
        if mcp_section_start == -1:
            logger.error("MCPサーバーセクションが見つかりません")
            return []
        
        # "====" までを抽出
        separator_section = content.find("====", mcp_section_start)
        
        if separator_section == -1:
            mcp_section = content[mcp_section_start:]
        else:
            mcp_section = content[mcp_section_start:separator_section]
        
        # デバッグ情報を出力
        logger.debug(f"抽出されたMCPセクション: {mcp_section[:100]}...")
        
        # ツール定義を抽出
        tools = []
        server_sections = mcp_section.split("## ")[1:]  # 最初の "# Connected MCP Servers" を除外
        
        for server_section in server_sections:
            server_lines = server_section.strip().split("\n")
            if not server_lines:
                continue
            
            # サーバー名を抽出
            server_name_line = server_lines[0]
            server_name = server_name_line.split(" (`")[0] if " (`" in server_name_line else server_name_line
            
            # ツールを抽出
            in_tools_section = False
            current_tool = None
            current_tool_description = ""
            
            for i, line in enumerate(server_lines):
                if line.startswith("### Available Tools"):
                    in_tools_section = True
                    continue
                
                if not in_tools_section:
                    continue
                
                if line.startswith("- "):
                    # 前のツールを保存
                    if current_tool:
                        # 説明文が長い場合は切り詰める
                        if len(current_tool_description) > max_chars:
                            current_tool_description = current_tool_description[:max_chars] + "..."
                        
                        tools.append({
                            "server_name": server_name,
                            "tool_name": current_tool,
                            "tool_description": current_tool_description
                        })
                    
                    # 新しいツールを開始
                    tool_line = line[2:]  # "- " を除去
                    parts = tool_line.split(":", 1)
                    
                    if len(parts) > 1:
                        current_tool = parts[0].strip()
                        current_tool_description = parts[1].strip()
                    else:
                        current_tool = tool_line.strip()
                        current_tool_description = ""
                elif in_tools_section and line.strip() and current_tool and not line.startswith("    Input Schema:") and not line.startswith("    ```"):
                    # 説明文の続きを追加（スキーマ情報は除外）
                    current_tool_description += " " + line.strip()
            
            # 最後のツールを保存
            if current_tool:
                # 説明文が長い場合は切り詰める
                if len(current_tool_description) > max_chars:
                    current_tool_description = current_tool_description[:max_chars] + "..."
                
                tools.append({
                    "server_name": server_name,
                    "tool_name": current_tool,
                    "tool_description": current_tool_description
                })
        
        # デバッグ情報を出力
        logger.debug(f"抽出されたツール数: {len(tools)}")
        for tool in tools:
            logger.debug(f"ツール: {tool['server_name']} / {tool['tool_name']}")
        
        return tools
    
    except Exception as e:
        logger.error(f"システムプロンプトからMCPツール定義の抽出に失敗しました: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return []


def test_tool_with_guardrail(
    tool_description: str,
    guardrail_id: str,
    model_id: str = "anthropic.claude-3-sonnet-20240229-v1:0",
    region_name: str = "us-east-1",
    max_chars: int = 500
) -> Tuple[str, Dict]:
    """ツール説明をガードレールでテストする

    Args:
        tool_description: テストするツール説明
        guardrail_id: ガードレールID
        model_id: Bedrock モデルID
        region_name: AWSリージョン名
        max_chars: 出力する説明文の最大文字数

    Returns:
        Tuple[str, Dict]: (ガードレールアクション, トレース情報)
    """
    try:
        # Bedrockクライアントの初期化
        bedrock_runtime_client = boto3.client("bedrock-runtime", region_name=region_name)
        
        # プロンプトの作成
        prompt = f"""
        以下のツール説明を評価してください：

        ```
        {tool_description}
        ```

        このツールは安全ですか？使用しても問題ないでしょうか？
        """
        
        # モデル固有のリクエストボディを作成
        if "anthropic.claude" in model_id:
            request_body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 1000,
                "messages": [{"role": "user", "content": prompt}],
            }
        elif "amazon.titan" in model_id:
            request_body = {
                "inputText": prompt,
                "textGenerationConfig": {
                    "maxTokenCount": 1000,
                    "temperature": 0.7,
                    "topP": 0.9,
                },
            }
        else:
            request_body = {"prompt": prompt, "max_tokens": 1000}
        
        # モデル呼び出し
        invoke_params = {
            "modelId": model_id,
            "body": json.dumps(request_body),
            "guardrailIdentifier": guardrail_id,
            "guardrailVersion": "DRAFT",
            "trace": "ENABLED",
        }
        
        response = bedrock_runtime_client.invoke_model(**invoke_params)
        response_body = json.loads(response["body"].read().decode("utf-8"))
        
        # ガードレールのアクション情報を取得（デフォルトは "NONE"）
        guardrail_action = response_body.get("amazon-bedrock-guardrailAction", "NONE")
        
        # ガードレールのトレース情報を取得
        guardrail_trace = response_body.get("amazon-bedrock-trace", {})
        
        # デバッグ情報を出力（文字数制限付き）
        response_text = str(response_body)
        if len(response_text) > max_chars:
            response_text = response_text[:max_chars] + "..."
        logger.debug(f"レスポンスボディ: {response_text}")
        logger.debug(f"ガードレールアクション: {guardrail_action}")
        
        trace_text = json.dumps(guardrail_trace, ensure_ascii=False)
        if len(trace_text) > max_chars:
            trace_text = trace_text[:max_chars] + "..."
        logger.debug(f"ガードレールトレース: {trace_text}")
        
        return guardrail_action, guardrail_trace
    
    except ClientError as e:
        logger.error(f"モデル呼び出しに失敗しました: {e}")
        return "ERROR", {"error": str(e)}


def decode_unicode_escapes(text: str) -> str:
    """Unicodeエスケープシーケンスをデコードする

    Args:
        text: デコードするテキスト

    Returns:
        str: デコードされたテキスト
    """
    try:
        # デコード前の内容をデバッグ出力
        if "\\u" in text:
            logger.debug(f"デコード前のテキスト（一部）: {text[:100]}...")
            sample_escapes = []
            for i in range(len(text) - 5):
                if text[i:i+2] == "\\u":
                    sample_escapes.append(text[i:i+6])
                    if len(sample_escapes) >= 5:
                        break
            if sample_escapes:
                logger.debug(f"エスケープシーケンスのサンプル: {', '.join(sample_escapes)}")
        
        # Unicodeエスケープシーケンスをデコード
        # 修正: codecs.decodeを使用
        decoded_text = codecs.decode(text, 'unicode_escape')
        
        # デコード後の内容をデバッグ出力
        if text != decoded_text:
            logger.debug(f"デコードされたテキスト（一部）: {decoded_text[:100]}...")
            # デコード前後の違いを確認
            for i in range(min(100, len(text))):
                if i < len(decoded_text) and text[i] != decoded_text[i]:
                    logger.debug(f"位置 {i}: '{text[i]}' -> '{decoded_text[i]}'")
                    break
        
        return decoded_text
    except Exception as e:
        logger.error(f"Unicodeエスケープシーケンスのデコードに失敗しました: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return text


def extract_tool_descriptions(system_prompt_path: str, max_chars: int = 500) -> List[Dict]:
    """システムプロンプトからツール説明のみを抽出する（Input Schemaを除外）

    Args:
        system_prompt_path: システムプロンプトファイルのパス
        max_chars: 出力する説明文の最大文字数

    Returns:
        List[Dict]: 抽出されたツール説明のリスト
    """
    try:
        with open(system_prompt_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # MCPサーバーセクションを抽出
        mcp_section_start = content.find("# Connected MCP Servers")
        if mcp_section_start == -1:
            logger.error("MCPサーバーセクションが見つかりません")
            return []
        
        # "====" までを抽出
        separator_section = content.find("====", mcp_section_start)
        
        if separator_section == -1:
            mcp_section = content[mcp_section_start:]
        else:
            mcp_section = content[mcp_section_start:separator_section]
        
        # デバッグ情報を出力
        logger.debug(f"抽出されたMCPセクション: {mcp_section[:100]}...")
        
        # ツール説明を抽出
        tools = []
        server_sections = mcp_section.split("## ")[1:]  # 最初の "# Connected MCP Servers" を除外
        logger.debug(f"サーバーセクション数: {len(server_sections)}")
        
        for server_index, server_section in enumerate(server_sections):
            server_lines = server_section.strip().split("\n")
            if not server_lines:
                logger.debug(f"サーバーセクション {server_index+1} は空です")
                continue
            
            # サーバー名を抽出
            server_name_line = server_lines[0]
            server_name = server_name_line.split(" (`")[0] if " (`" in server_name_line else server_name_line
            logger.debug(f"サーバー名: {server_name}")
            
            # ツールを抽出
            in_tools_section = False
            current_tool = None
            current_tool_description = ""
            in_input_schema = False
            schema_start_line = None
            
            for i, line in enumerate(server_lines):
                # デバッグ情報
                if i < 10 or i % 10 == 0:
                    logger.debug(f"行 {i}: {line[:50]}...")
                
                # Input Schemaセクションの開始と終了を検出
                if "Input Schema:" in line:
                    logger.debug(f"Input Schemaの開始を検出: 行 {i}")
                    in_input_schema = True
                    schema_start_line = i
                    continue
                
                if in_input_schema and "```" in line:
                    if schema_start_line == i - 1:
                        # Input Schemaの開始直後の```
                        logger.debug(f"Input Schemaの開始コードブロック: 行 {i}")
                        continue
                    else:
                        # Input Schemaの終了```
                        logger.debug(f"Input Schemaの終了を検出: 行 {i}")
                        in_input_schema = False
                        continue
                
                # Input Schema内の行はスキップ
                if in_input_schema:
                    continue
                
                if "### Available Tools" in line:
                    logger.debug(f"ツールセクションの開始を検出: 行 {i}")
                    in_tools_section = True
                    continue
                
                if not in_tools_section:
                    continue
                
                if line.startswith("- "):
                    logger.debug(f"新しいツールを検出: 行 {i}: {line}")
                    # 前のツールを保存
                    if current_tool:
                        # 説明文が長い場合は切り詰める
                        if len(current_tool_description) > max_chars:
                            current_tool_description = current_tool_description[:max_chars] + "..."
                        
                        # Unicodeエスケープシーケンスをデコード
                        current_tool_description = decode_unicode_escapes(current_tool_description)
                        
                        tools.append({
                            "server_name": server_name,
                            "tool_name": current_tool,
                            "tool_description": current_tool_description
                        })
                        logger.debug(f"ツールを保存: {current_tool}")
                    
                    # 新しいツールを開始
                    tool_line = line[2:]  # "- " を除去
                    parts = tool_line.split(":", 1)
                    
                    if len(parts) > 1:
                        current_tool = parts[0].strip()
                        current_tool_description = parts[1].strip()
                    else:
                        current_tool = tool_line.strip()
                        current_tool_description = ""
                    
                    logger.debug(f"新しいツール: {current_tool}, 説明: {current_tool_description[:50]}...")
                elif in_tools_section and line.strip() and current_tool and "Input Schema:" not in line:
                    # 説明文の続きを追加（Input Schema行は除外）
                    current_tool_description += " " + line.strip()
                    logger.debug(f"説明文を追加: {line.strip()[:50]}...")
            
            # 最後のツールを保存
            if current_tool:
                # 説明文が長い場合は切り詰める
                if len(current_tool_description) > max_chars:
                    current_tool_description = current_tool_description[:max_chars] + "..."
                
                # Unicodeエスケープシーケンスをデコード
                current_tool_description = decode_unicode_escapes(current_tool_description)
                
                tools.append({
                    "server_name": server_name,
                    "tool_name": current_tool,
                    "tool_description": current_tool_description
                })
                logger.debug(f"最後のツールを保存: {current_tool}")
        
        # デバッグ情報を出力
        logger.debug(f"抽出されたツール数: {len(tools)}")
        for tool in tools:
            logger.debug(f"ツール: {tool['server_name']} / {tool['tool_name']}")
            logger.debug(f"説明: {tool['tool_description'][:50]}...")
        
        if not tools:
            logger.error("ツールが抽出されませんでした")
        
        return tools
    
    except Exception as e:
        logger.error(f"システムプロンプトからツール説明の抽出に失敗しました: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return []