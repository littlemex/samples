import { 
  ToolDefinition, 
  saveToolHash, 
  verifyToolDefinition, 
  listAllHashes 
} from './security-utils.js';

/**
 * MCP Server からツール情報を取得する関数
 * @param serverUrl サーバーのURL
 * @returns ツール定義の配列
 */
async function fetchToolDefinitions(serverUrl: string): Promise<ToolDefinition[]> {
  try {
    const response = await fetch(`${serverUrl}/tool-status`);
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    
    const data = await response.json();
    return [data.toolDefinition]; // 単一のツールを配列として返す
  } catch (error) {
    console.error('ツール定義の取得に失敗しました:', error);
    throw error;
  }
}

/**
 * MCP Server のツール定義を検証し、必要に応じてハッシュを保存する関数
 * @param serverUrl サーバーのURL
 * @param serverVersion サーバーのバージョン
 */
export async function validateAndStoreToolDefinitions(
  serverUrl: string, 
  serverVersion: string = '1.0.0'
): Promise<void> {
  console.log(`\n=== MCP Server ツール定義検証開始 ===`);
  console.log(`Server URL: ${serverUrl}`);
  console.log(`Server Version: ${serverVersion}`);
  
  try {
    const toolDefinitions = await fetchToolDefinitions(serverUrl);
    const serverPath = new URL(serverUrl).host;
    
    for (const toolDefinition of toolDefinitions) {
      console.log(`\n--- ツール "${toolDefinition.name}" の検証 ---`);
      
      const verification = await verifyToolDefinition(
        serverPath,
        serverVersion,
        toolDefinition
      );
      
      console.log(`検証結果: ${verification.message}`);
      console.log(`現在のハッシュ: ${verification.currentHash}`);
      
      if (verification.previousHash) {
        console.log(`以前のハッシュ: ${verification.previousHash}`);
      }
      
      if (verification.isNew) {
        await saveToolHash(serverPath, serverVersion, toolDefinition);
        console.log('✅ 新しいツールのハッシュを保存しました。');
      } else if (!verification.isValid) {
        console.log('🚨 警告: ツール定義が変更されています！');
        console.log('   これは Rug Pull 攻撃の可能性があります。');
        console.log('   ツールの使用を中止し、管理者に連絡してください。');
        
        // 変更されたツールの詳細を表示
        console.log('\n--- 変更されたツール定義 ---');
        console.log(JSON.stringify(toolDefinition, null, 2));
      } else {
        console.log('✅ ツール定義は安全です。');
      }
    }
    
  } catch (error) {
    console.error('検証プロセスでエラーが発生しました:', error);
    throw error;
  }
  
  console.log(`\n=== 検証完了 ===\n`);
}

/**
 * 保存されているすべてのハッシュを表示する関数
 */
export async function displayStoredHashes(): Promise<void> {
  console.log('\n=== 保存されているツールハッシュ一覧 ===');
  
  try {
    const hashes = await listAllHashes();
    
    if (hashes.length === 0) {
      console.log('保存されているハッシュはありません。');
      return;
    }
    
    hashes.forEach((record, index) => {
      console.log(`\n${index + 1}. ${record.toolName}`);
      console.log(`   Server: ${record.serverPath} (v${record.serverVersion})`);
      console.log(`   Hash: ${record.hash}`);
      console.log(`   保存日時: ${record.timestamp}`);
      console.log(`   説明: ${record.toolDefinition.description}`);
    });
    
  } catch (error) {
    console.error('ハッシュ一覧の取得に失敗しました:', error);
  }
  
  console.log('\n=== 一覧表示完了 ===\n');
}

/**
 * メイン実行関数
 */
async function main(): Promise<void> {
  const args = process.argv.slice(2);
  const command = args[0];
  
  switch (command) {
    case 'validate':
      const serverUrl = args[1] || 'http://localhost:13000';
      const serverVersion = args[2] || '1.0.0';
      await validateAndStoreToolDefinitions(serverUrl, serverVersion);
      break;
      
    case 'list':
      await displayStoredHashes();
      break;
      
    case 'help':
    default:
      console.log('\n=== MCP Client Validator ===');
      console.log('使用方法:');
      console.log('  npm run validate [server-url] [server-version]  - ツール定義を検証');
      console.log('  npm run list                                    - 保存されたハッシュを表示');
      console.log('  npm run help                                    - このヘルプを表示');
      console.log('\n例:');
      console.log('  npm run validate http://localhost:13000 1.0.0');
      console.log('  npm run list');
      break;
  }
}

// スクリプトが直接実行された場合のみmain関数を呼び出す
if (import.meta.url === `file://${process.argv[1]}`) {
  main().catch(console.error);
}
