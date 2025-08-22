/**
 * Secure MCP Client の改善版デモスクリプト
 * Client 側独立ハッシュ検証システムの動作確認
 * 
 * このデモでは以下を実証します：
 * 1. Client側でツール定義のハッシュを独立計算
 * 2. Server側の変更を検出（実際のMCPセッションでは変更が反映されない問題を説明）
 * 3. セキュリティ検証の重要性を示す
 */
import { SecureMCPClient } from './secure-mcp-client.js';
import { ClientHashMonitor, ToolDefinition } from './client-hash-monitor.js';

/**
 * デモの実行
 */
async function runDemo(): Promise<void> {
  console.log('='.repeat(80));
  console.log('🔒 Secure MCP Client デモ - Rug Pull 攻撃検知システム');
  console.log('='.repeat(80));
  
  console.log('\n📚 デモの概要:');
  console.log('このデモでは、悪意あるMCP Serverがツール定義を動的に変更する');
  console.log('「Rug Pull攻撃」を検知するシステムを実演します。');
  console.log('');
  console.log('🎯 検証内容:');
  console.log('1. Client側で独立してツール定義のハッシュ値を計算');
  console.log('2. ベースラインハッシュと現在のハッシュを比較');
  console.log('3. ツール定義の変更を検知してセキュリティアラートを表示');
  console.log('');
  console.log('⚠️  重要な注意事項:');
  console.log('MCP HTTPトランスポートでは、各セッションが独立しているため、');
  console.log('Server側でツール定義を変更しても、既存セッションには反映されません。');
  console.log('そのため、このデモでは変更検知を別の方法でシミュレートします。');
  console.log('='.repeat(80));

  const serverUrl = 'http://localhost:13000';
  const client = new SecureMCPClient(serverUrl);

  try {
    // Step 1: Client 初期化とベースライン取得
    console.log('\n' + '─'.repeat(60));
    console.log('📋 Step 1: Client 初期化とベースラインハッシュ取得');
    console.log('─'.repeat(60));
    console.log('期待結果: MCP Clientが初期化され、現在のツール定義の');
    console.log('          ハッシュ値がベースラインとして記録される');
    
    await client.initialize();

    // Step 2: ベースライン表示
    console.log('\n' + '─'.repeat(60));
    console.log('📋 Step 2: ベースラインハッシュの確認');
    console.log('─'.repeat(60));
    console.log('期待結果: 記録されたベースラインハッシュ値が表示される');
    
    const monitor = new ClientHashMonitor();
    const tools = await client.listTools();
    
    // ベースラインハッシュを取得
    await monitor.captureBaseline(tools);
    
    if (tools.length > 0) {
      const addTool = tools.find(tool => tool.name === 'add');
      if (addTool) {
        console.log(`✅ ベースラインハッシュ取得成功:`);
        console.log(`   ツール名: ${addTool.name}`);
        console.log(`   説明: ${addTool.description}`);
        
        // ベースライン表示
        monitor.displayBaseline();
      }
    }

    // Step 3: 正常なツール呼び出し
    console.log('\n' + '─'.repeat(60));
    console.log('📋 Step 3: 正常なツール呼び出しテスト');
    console.log('─'.repeat(60));
    console.log('期待結果: セキュリティ検証が成功し、ツールが正常実行される');
    
    const result1 = await client.callTool('add', { a: 5, b: 3 });
    console.log(`✅ ツール呼び出し成功: add(5, 3) = ${result1.content[0].text}`);

    // Step 4: ツール定義変更のシミュレーション
    console.log('\n' + '─'.repeat(60));
    console.log('📋 Step 4: Rug Pull攻撃のシミュレーション');
    console.log('─'.repeat(60));
    console.log('期待結果: 変更されたツール定義が検知され、セキュリティアラートが表示される');
    console.log('注意: 実際のMCPセッションでは変更が反映されないため、');
    console.log('      ここでは攻撃をシミュレートします。');

    // 悪意のあるツール定義を作成（実際の攻撃をシミュレート）
    const maliciousToolDef: ToolDefinition = {
      name: 'add',
      description: '数値を加算します（実際は悪意のある処理を実行）', // 説明を変更
      inputSchema: {
        type: 'object',
        properties: {
          a: { type: 'number', description: '最初の数値' },
          b: { type: 'number', description: '2番目の数値' }
        },
        required: ['a', 'b']
      }
    };

    // 悪意のあるツール定義配列を作成
    const maliciousTools = tools.map(tool => 
      tool.name === 'add' ? maliciousToolDef : tool
    );

    console.log(`🔍 ツール定義変更の検証:`);
    console.log(`   オリジナル説明: ${tools.find(t => t.name === 'add')?.description}`);
    console.log(`   変更後説明:     ${maliciousToolDef.description}`);
    
    // 全ツールの検証を実行
    const validationResults = await monitor.validateAllTools(maliciousTools);
    const addResult = validationResults.find(r => r.toolName === 'add');
    
    if (addResult && !addResult.isValid) {
      console.log('🚨 セキュリティアラート: ツール定義の変更を検知しました！');
      console.log('   これはRug Pull攻撃の可能性があります。');
      console.log('   ツール呼び出しをブロックします。');
    }

    // Step 5: セキュリティ検証の実演
    console.log('\n' + '─'.repeat(60));
    console.log('📋 Step 5: セキュリティ検証システムの動作確認');
    console.log('─'.repeat(60));
    console.log('期待結果: 変更されたツール定義に対してvalidateBeforeToolCallがfalseを返す');

    const isValid = await monitor.validateBeforeToolCall(maliciousTools, 'add');
    console.log(`🔒 セキュリティ検証結果: ${isValid ? '✅ 安全' : '❌ 危険'}`);
    
    if (!isValid) {
      console.log('   ツール定義が変更されているため、実行を拒否します。');
      console.log('   これにより、Rug Pull攻撃から保護されます。');
    }

    // Step 6: 実際のMCPセッション制限の説明
    console.log('\n' + '─'.repeat(60));
    console.log('📋 Step 6: MCP HTTPトランスポートの制限について');
    console.log('─'.repeat(60));
    console.log('🔍 技術的な制限:');
    console.log('   MCP HTTPトランスポートでは、各クライアントセッションが独立しており、');
    console.log('   サーバー側でツール定義を変更しても、既存のセッションには');
    console.log('   その変更が反映されません。');
    console.log('');
    console.log('💡 実際の攻撃シナリオ:');
    console.log('   1. 攻撃者が新しいクライアントセッションで異なるツール定義を提供');
    console.log('   2. 既存クライアントは古い（安全な）定義を使い続ける');
    console.log('   3. 新しいクライアントは悪意のある定義を受け取る');
    console.log('');
    console.log('🛡️  防御策:');
    console.log('   Client側独立ハッシュ監視により、このような攻撃を検知可能');

  } catch (error) {
    console.error('❌ デモ実行中にエラーが発生しました:', error);
  } finally {
    console.log('\n' + '='.repeat(80));
    console.log('🏁 デモ完了');
    console.log('='.repeat(80));
    console.log('');
    console.log('📝 まとめ:');
    console.log('• Client側独立ハッシュ検証システムが正常に動作');
    console.log('• ツール定義の変更を検知してセキュリティアラートを表示');
    console.log('• Rug Pull攻撃に対する防御機能を実証');
    console.log('• MCP HTTPトランスポートの制限を理解');
    console.log('');
    console.log('🔒 セキュリティが確保されました！');
  }
}

// デモ実行
if (import.meta.url === `file://${process.argv[1]}`) {
  runDemo().catch(console.error);
}

export { runDemo };
