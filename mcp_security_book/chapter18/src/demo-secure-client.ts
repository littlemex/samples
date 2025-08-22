/**
 * Secure MCP Client のデモスクリプト
 * Client 側独立ハッシュ検証システムの動作確認
 */
import { SecureMCPClient } from './secure-mcp-client.js';

/**
 * デモの実行
 */
async function runDemo(): Promise<void> {
  console.log('='.repeat(60));
  console.log('🔒 Secure MCP Client デモ開始');
  console.log('='.repeat(60));

  const serverUrl = 'http://localhost:13000';
  const client = new SecureMCPClient(serverUrl);

  try {
    // Step 1: Client 初期化とベースライン取得
    console.log('\n📋 Step 1: Client 初期化とベースライン取得');
    await client.initialize();

    // Step 2: ベースライン表示
    console.log('\n📋 Step 2: ベースラインハッシュ表示');
    client.displayBaseline();

    // Step 3: 正常な Tool 呼び出し
    console.log('\n📋 Step 3: 正常な Tool 呼び出し（add）');
    try {
      const result1 = await client.callTool('add', { a: 5, b: 3 });
      console.log('Tool 実行結果:', result1.content[0]?.text);
    } catch (error) {
      console.error('Tool 呼び出しエラー:', error);
    }

    // Step 4: 全 Tool の検証状態確認
    console.log('\n📋 Step 4: 全 Tool の検証状態確認');
    const validationResults = await client.validateAllTools();
    validationResults.forEach((result) => {
      const status = result.isValid ? '✅ 安全' : '❌ 危険';
      console.log(`Tool ${result.toolName}: ${status}`);
      console.log(`  現在のハッシュ: ${result.currentHash}`);
      if (result.baselineHash) {
        console.log(`  ベースライン: ${result.baselineHash}`);
      }
    });

    // Step 5: Server 側で Tool 定義を変更
    console.log('\n📋 Step 5: Server 側で Tool 定義を変更');
    console.log('Server の /change-description エンドポイントを呼び出します...');

    try {
      const changeResponse = await fetch(`${serverUrl}/change-description`, {
        method: 'POST',
      });
      const changeData = await changeResponse.json();
      console.log('変更結果:', changeData.message);
      console.log('新しい説明:', changeData.currentDescription);
    } catch (error) {
      console.error('Tool 定義変更エラー:', error);
    }

    // Step 6: 変更後の Tool 呼び出し試行
    console.log('\n📋 Step 6: 変更後の Tool 呼び出し試行');
    console.log('⚠️  この呼び出しはセキュリティ検証で失敗するはずです');

    try {
      const result2 = await client.callTool('add', { a: 10, b: 7 });
      console.log('⚠️  予期しない成功:', result2.content[0]?.text);
    } catch (error) {
      console.log('✅ 期待通りセキュリティ検証で失敗しました');
      console.log('エラー:', (error as Error).message);
    }

    // Step 7: 変更後の検証状態確認
    console.log('\n📋 Step 7: 変更後の検証状態確認');
    const validationResults2 = await client.validateAllTools();
    validationResults2.forEach((result) => {
      const status = result.isValid ? '✅ 安全' : '❌ 危険';
      console.log(`Tool ${result.toolName}: ${status}`);
      if (!result.isValid) {
        console.log('  🚨 Tool 定義が変更されています！');
        console.log(`  現在のハッシュ: ${result.currentHash}`);
        console.log(`  ベースライン: ${result.baselineHash}`);
      }
    });

    // Step 8: Server の状態を元に戻す
    console.log('\n📋 Step 8: Server の状態を元に戻す');
    try {
      const revertResponse = await fetch(`${serverUrl}/change-description`, {
        method: 'POST',
      });
      const revertData = await revertResponse.json();
      console.log('復元結果:', revertData.message);
      console.log('復元後の説明:', revertData.currentDescription);
    } catch (error) {
      console.error('Tool 定義復元エラー:', error);
    }

    // Step 9: 復元後の Tool 呼び出し
    console.log('\n📋 Step 9: 復元後の Tool 呼び出し');
    try {
      const result3 = await client.callTool('add', { a: 15, b: 25 });
      console.log('✅ Tool 実行結果:', result3.content[0]?.text);
    } catch (error) {
      console.error('Tool 呼び出しエラー:', error);
    }
  } catch (error) {
    console.error('デモ実行エラー:', error);
  } finally {
    // セッション終了
    console.log('\n📋 セッション終了');
    await client.close();
  }

  console.log('\n' + '='.repeat(60));
  console.log('🔒 Secure MCP Client デモ完了');
  console.log('='.repeat(60));
}

/**
 * エラーハンドリング付きでデモを実行
 */
async function main(): Promise<void> {
  try {
    await runDemo();
  } catch (error) {
    console.error('デモ実行中にエラーが発生しました:', error);
    process.exit(1);
  }
}

/**
 * 使用方法の表示
 */
function showUsage(): void {
  console.log('\n=== Secure MCP Client デモ ===');
  console.log('このデモを実行する前に、以下の手順を実行してください:');
  console.log('');
  console.log('1. MCP Server を起動:');
  console.log('   npm run server');
  console.log('');
  console.log('2. 別のターミナルでデモを実行:');
  console.log('   npm run demo-secure');
  console.log('');
  console.log('デモの内容:');
  console.log('- Client 側独立ハッシュ検証システムの動作確認');
  console.log('- ベースラインハッシュの取得と保存');
  console.log('- Tool 定義変更の検出とセキュリティアラート');
  console.log('- 悪意ある Server からの偽装ハッシュ無視');
  console.log('');
}

// コマンドライン引数の処理
const args = process.argv.slice(2);
if (args.includes('--help') || args.includes('-h')) {
  showUsage();
  process.exit(0);
}

// スクリプトが直接実行された場合のみ main 関数を呼び出す
if (import.meta.url === `file://${process.argv[1]}`) {
  main().catch(console.error);
}
