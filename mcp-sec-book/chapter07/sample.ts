import { spawn, ChildProcess } from 'child_process';

// 子プロセスを起動する関数
function runCommand(command: string, args: string[]): Promise<string> {
  return new Promise((resolve, reject) => {
    // 子プロセスを起動
    const childProcess: ChildProcess = spawn(command, args);

    let output = '';
    let errorOutput = '';

    // 標準出力からデータを受け取る
    childProcess.stdout?.on('data', (data: Buffer) => {
      output += data.toString();
    });

    // エラー出力からデータを受け取る
    childProcess.stderr?.on('data', (data: Buffer) => {
      errorOutput += data.toString();
    });

    // プロセスの終了を検知
    childProcess.on('close', (code: number) => {
      if (code === 0) {
        resolve(output);
      } else {
        reject(new Error(`コマンドが失敗しました: ${errorOutput}`));
      }
    });

    // エラーイベントを処理
    childProcess.on('error', (error: Error) => {
      reject(error);
    });
  });
}

// 関数を使用する例
async function main() {
  try {
    const result = await runCommand('echo', ['-e', 'hello\nmcp!']);
    console.log('コマンド実行結果:');
    console.log(result);
  } catch (error) {
    console.error('エラーが発生しました:', error);
  }
}

main();
