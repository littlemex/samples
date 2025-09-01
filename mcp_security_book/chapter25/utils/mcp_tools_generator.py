"""
MCP ツール情報生成ユーティリティ

このモジュールは、MCP ツール情報を生成するための機能を提供します。
正常バージョンと攻撃バージョンの MCP ツール情報を生成し、
システムプロンプトのテンプレート変数を置換するための関数を提供します。
"""

import json
import logging
import os
from typing import Dict

logger = logging.getLogger(__name__)


def generate_normal_mcp_tools_section(mcp_config_path: str) -> str:
    """正常な MCP ツール情報セクションを生成する

    Args:
        mcp_config_path: MCP 設定ファイルのパス

    Returns:
        str: 正常な MCP ツール情報セクション
    """
    try:
        # MCP 設定ファイルを読み込む
        with open(mcp_config_path, "r", encoding="utf-8") as f:
            mcp_config = json.load(f)
        
        # 攻撃ツールを含むサーバーを除外
        normal_servers = []
        for server in mcp_config.get("mcp_servers", []):
            if "malicious" not in server.get("name", "").lower():
                normal_servers.append(server)
        
        # MCP ツール情報セクションを生成
        mcp_section = "# Connected MCP Servers\n\n"
        
        for server in normal_servers:
            server_name = server.get("name", "")
            server_path = server.get("path", "")
            server_description = server.get("description", "")
            
            mcp_section += f"## {server_name} (`{server_path}`)\n\n"
            
            if server_description:
                mcp_section += f"{server_description}\n\n"
            
            mcp_section += "### Available Tools\n"
            
            for tool in server.get("tools", []):
                tool_name = tool.get("name", "")
                tool_description = tool.get("description", "")
                
                mcp_section += f"- {tool_name}: {tool_description}\n"
                
                # 入力スキーマ情報を追加
                if "input_schema" in tool:
                    mcp_section += "    Input Schema:\n"
                    mcp_section += "    ```\n"
                    mcp_section += json.dumps(tool["input_schema"], indent=4, ensure_ascii=False)
                    mcp_section += "\n    ```\n"
            
            mcp_section += "\n"
        
        return mcp_section
    
    except Exception as e:
        logger.error(f"正常な MCP ツール情報セクションの生成に失敗しました: {e}")
        return "# Connected MCP Servers\n\nMCP サーバー情報の生成に失敗しました。\n"


def generate_attack_mcp_tools_section(mcp_config_path: str) -> str:
    """攻撃ツールを含む MCP ツール情報セクションを生成する

    Args:
        mcp_config_path: MCP 設定ファイルのパス

    Returns:
        str: 攻撃ツールを含む MCP ツール情報セクション
    """
    try:
        # MCP 設定ファイルを読み込む
        with open(mcp_config_path, "r", encoding="utf-8") as f:
            mcp_config = json.load(f)
        
        # MCP ツール情報セクションを生成（すべてのサーバーを含む）
        mcp_section = "# Connected MCP Servers\n\n"
        
        for server in mcp_config.get("mcp_servers", []):
            server_name = server.get("name", "")
            server_path = server.get("path", "")
            server_description = server.get("description", "")
            
            mcp_section += f"## {server_name} (`{server_path}`)\n\n"
            
            if server_description:
                mcp_section += f"{server_description}\n\n"
            
            mcp_section += "### Available Tools\n"
            
            for tool in server.get("tools", []):
                tool_name = tool.get("name", "")
                tool_description = tool.get("description", "")
                
                mcp_section += f"- {tool_name}: {tool_description}\n"
                
                # 入力スキーマ情報を追加
                if "input_schema" in tool:
                    mcp_section += "    Input Schema:\n"
                    mcp_section += "    ```\n"
                    mcp_section += json.dumps(tool["input_schema"], indent=4, ensure_ascii=False)
                    mcp_section += "\n    ```\n"
            
            mcp_section += "\n"
        
        return mcp_section
    
    except Exception as e:
        logger.error(f"攻撃ツールを含む MCP ツール情報セクションの生成に失敗しました: {e}")
        return "# Connected MCP Servers\n\nMCP サーバー情報の生成に失敗しました。\n"


def replace_template_variables(template_path: str, output_path: str, mcp_tools_section: str) -> bool:
    """テンプレート変数を置換する

    Args:
        template_path: テンプレートファイルのパス
        output_path: 出力ファイルのパス
        mcp_tools_section: MCP ツール情報セクション

    Returns:
        bool: 成功した場合は True、失敗した場合は False
    """
    try:
        # テンプレートファイルを読み込む
        with open(template_path, "r", encoding="utf-8") as f:
            template_content = f.read()
        
        # テンプレート変数を置換
        output_content = template_content.replace("{{mcptool}}", mcp_tools_section)
        
        # 出力ファイルに書き込む
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(output_content)
        
        logger.info(f"テンプレート変数を置換しました: {output_path}")
        return True
    
    except Exception as e:
        logger.error(f"テンプレート変数の置換に失敗しました: {e}")
        return False


def generate_system_prompts(
    template_path: str,
    mcp_config_path: str,
    normal_output_path: str,
    attack_output_path: str
) -> Dict[str, bool]:
    """正常バージョンと攻撃バージョンのシステムプロンプトを生成する

    Args:
        template_path: テンプレートファイルのパス
        mcp_config_path: MCP 設定ファイルのパス
        normal_output_path: 正常バージョンの出力ファイルのパス
        attack_output_path: 攻撃バージョンの出力ファイルのパス

    Returns:
        Dict[str, bool]: 生成結果（"normal": 成功/失敗, "attack": 成功/失敗）
    """
    results = {"normal": False, "attack": False}
    
    # 正常バージョンの MCP ツール情報セクションを生成
    normal_mcp_section = generate_normal_mcp_tools_section(mcp_config_path)
    
    # 攻撃バージョンの MCP ツール情報セクションを生成
    attack_mcp_section = generate_attack_mcp_tools_section(mcp_config_path)
    
    # 正常バージョンのシステムプロンプトを生成
    results["normal"] = replace_template_variables(
        template_path, normal_output_path, normal_mcp_section
    )
    
    # 攻撃バージョンのシステムプロンプトを生成
    results["attack"] = replace_template_variables(
        template_path, attack_output_path, attack_mcp_section
    )
    
    return results


if __name__ == "__main__":
    # ロギングの設定
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    
    # 現在のディレクトリを基準にパスを設定
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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
        print(f"正常バージョンのシステムプロンプトを生成しました: {normal_output_path}")
    else:
        print("正常バージョンのシステムプロンプトの生成に失敗しました")
    
    if results["attack"]:
        print(f"攻撃バージョンのシステムプロンプトを生成しました: {attack_output_path}")
    else:
        print("攻撃バージョンのシステムプロンプトの生成に失敗しました")
