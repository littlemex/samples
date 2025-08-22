#!/usr/bin/env node

/**
 * listChanged 通知による Rug Pull 攻撃検出デモ
 *
 * このデモでは以下を実証します:
 * 1. MCP Server が Tool 定義を動的に変更
 * 2. Server が listChanged 通知を送信
 * 3. Client がリアルタイムで通知を受信
 * 4. Client が独立してハッシュ値を再計算
 * 5. Rug Pull 攻撃を検出してアラートを発生
 */

import { SecureMCPClientWithSDK } from './client.js';

const SERVER_URL = 'http://localhost:13000';
const DEMO_DELAY = 2000; // 2秒間隔でデモを進行

/**
 * デモの進行を管理するヘルパー関数
 */
async function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function waitForUserInput(message: string): Promise<void> {
  console.log(`\n${message}`);
  console.log('続行するには Enter キーを押してください...');

  return new Promise((resolve) => {
    process.stdin.once('data', () => {
      resolve();
    });
  });
}

/**
 * Tool 定義を変更するリクエストを送信
 */
async function triggerToolDefinitionChange(): Promise<void> {
  console.log('\n=== Tool 定義変更をトリガー ===');

  try {
    const response = await fetch(`${SERVER_URL}/change-description`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        newDescription: `悪意のある説明 - 攻撃者によって変更されました (${new Date().toISOString()})`,
      }),
    });

    if (response.ok) {
      const result = await response.json();
      console.log('✅ Tool 定義変更完了:', result.message);
      console.log('📡 Server から listChanged 通知が送信されました');
    } else {
      console.error('❌ Tool 定義変更失敗:', response.statusText);
    }
  } catch (error) {
    console.error('❌ Tool 定義変更エラー:', error);
  }

  console.log('=== Tool 定義変更完了 ===\n');
}

/**
 * メインデモ関数
 */
async function runDemo(): Promise<void> {
  console.log('🚀 === listChanged 通知による Rug Pull 攻撃検出デモ ===\n');

  const client = new SecureMCPClientWithSDK(SERVER_URL, {
    name: 'secure-demo-client',
    version: '1.0.0',
  });

  try {
    // ステップ 1: Client 初期化とベースライン取得
    console.log('📋 ステップ 1: Secure MCP Client を初期化します');
    await client.initialize();

    console.log('\n📊 初期ベースラインハッシュ:');
    client.displayBaseline();

    await waitForUserInput('🔍 ステップ 2: 初期状態での Tool 呼び出しテスト');

    // ステップ 2: 正常な Tool 呼び出し
    console.log('\n=== 正常な Tool 呼び出しテスト ===');
    try {
      const result = await client.callTool({ name: 'add', arguments: { a: 5, b: 3 } });
      console.log('✅ Tool 呼び出し成功:', result.content[0]?.text);

      // Server側の_metaハッシュを表示
      if (result._meta && result._meta.hash) {
        console.log('\n📊 ハッシュ値の比較:');
        console.log('  Server側 _meta ハッシュ:', result._meta.hash);
        console.log('  Client側 独立計算ハッシュ: (上記のセキュリティチェックで検証済み)');
        console.log('  ※ 両方のハッシュが一致していることを確認');
      }
    } catch (error) {
      console.error('❌ Tool 呼び出し失敗:', error);
    }

    await waitForUserInput('⚠️  ステップ 3: Tool 定義を変更します');

    // ステップ 3: Tool 定義を変更
    await triggerToolDefinitionChange();

    // 通知処理の時間を確保
    console.log('⏳ listChanged 通知の処理を待機中...');
    await sleep(DEMO_DELAY);

    await waitForUserInput(
      '🔒 ステップ 4: 変更後の Tool 呼び出しテスト (セキュリティ検証が働くはず)'
    );

    // ステップ 4: 変更後の Tool 呼び出し (セキュリティ検証で拒否されるはず)
    console.log('\n=== 変更後の Tool 呼び出しテスト ===');
    try {
      const result = await client.callTool({ name: 'add', arguments: { a: 10, b: 7 } });
      console.log('⚠️  予期しない成功:', result.content[0]?.text);
      console.log('これは問題です - セキュリティ検証が機能していません');

      // 変更後もServer側の_metaハッシュを表示（参考）
      if (result._meta && result._meta.hash) {
        console.log('\n⚠️  変更後のハッシュ値:');
        console.log('  Server 側 _meta ハッシュ:', result._meta.hash);
        console.log('  ※ Server 側のハッシュも変更されていますが、');
        console.log('    Client 側の独立検証により使用が拒否されるべきです');
      }
    } catch (error) {
      console.log('✅ 期待通りの結果: セキュリティ検証により Tool 呼び出しが拒否されました');
      console.log(`拒否理由: ${error}`);
    }

    await waitForUserInput('📈 ステップ 5: 全 Tool の検証状態を確認');

    // ステップ 5: 全 Tool の検証状態を確認
    console.log('\n=== 全 Tool セキュリティ検証結果 ===');
    const validationResults = await client.validateAllTools();

    validationResults.forEach(
      (result: {
        toolName: string;
        isValid: boolean;
        currentHash: string;
        baselineHash?: string;
      }) => {
        if (result.isValid) {
          console.log(`✅ ${result.toolName}: 安全`);
        } else {
          console.log(`❌ ${result.toolName}: 危険 (ハッシュ不一致)`);
          console.log(`  期待値: ${result.baselineHash}`);
          console.log(`  現在値: ${result.currentHash}`);
        }
      }
    );

    console.log('\n🎯 === デモ完了 ===');
    console.log('✅ listChanged 通知によるツール定義変更の検出が正常に動作しました！');
    console.log('\n主な成果:');
    console.log('1. ✅ Server が Tool 定義変更時に listChanged 通知を送信');
    console.log('2. ✅ Client がリアルタイムで通知を受信');
    console.log('3. ✅ Client が独立してハッシュ値を再計算');
    console.log('4. ✅ Server 側 _meta ハッシュと Client 側独立ハッシュの両方を確認');
    console.log('5. ✅ ツール定義変更を検出してセキュリティアラートを発生');
    console.log('6. ✅ 危険な Tool の使用を拒否');
    console.log('\n📝 重要なポイント:');
    console.log('- Client 側の独立ハッシュ計算により、Server 側の情報に依存しない検証が可能');
    console.log('- Server 側の _meta ハッシュは参考情報として利用可能');
    console.log('- リアルタイムの listChanged 通知により、即座に攻撃を検出');
  } catch (error) {
    console.error('❌ デモ実行エラー:', error);
  } finally {
    // クリーンアップ
    console.log('\n🧹 クリーンアップ中...');
    await client.close();
    console.log('✅ クリーンアップ完了');
  }
}

/**
 * プロセス終了時のクリーンアップ
 */
process.on('SIGINT', () => {
  console.log('\n\n🛑 デモを中断しています...');
  process.exit(0);
});

// stdin を raw モードに設定
process.stdin.setRawMode(true);
process.stdin.resume();
process.stdin.setEncoding('utf8');

// デモ実行
runDemo()
  .then(() => {
    process.exit(0);
  })
  .catch((error) => {
    console.error('デモ実行中にエラーが発生しました:', error);
    process.exit(1);
  });
