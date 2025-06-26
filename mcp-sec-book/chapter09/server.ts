import express from 'express';
import { SSEMessage, CONFIG } from './types';

const app = express();

// SSEエンドポイント
app.get(CONFIG.ENDPOINT, (req, res) => {
  console.log('クライアント接続: 新しいSSEセッション開始');
  
  // SSEヘッダーを設定
  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');
  
  // 初期メッセージ送信
  sendMessage(res, { message: "接続確立" });
  console.log('SSEイベント送信: 接続確立メッセージ');
  
  // 定期的なメッセージ送信
  let count = 0;
  const intervalId = setInterval(() => {
    const data = { 
      count: ++count, 
      timestamp: new Date().toISOString() 
    };
    sendMessage(res, data);
    console.log(`SSEイベント送信: カウント=${count}`);
  }, CONFIG.INTERVAL_MS);
  
  // クライアント切断時の処理
  req.on('close', () => {
    clearInterval(intervalId);
    console.log('SSEセッション終了: クライアント切断');
  });
});

// メッセージ送信ヘルパー関数
function sendMessage(res: express.Response, data: SSEMessage): void {
  const eventId = `event-${Date.now()}`;
  const message = `id: ${eventId}\ndata: ${JSON.stringify(data)}\n\n`;
  res.write(message);
}

// サーバー起動
app.listen(CONFIG.PORT, () => {
  console.log(`サーバー起動: http://${CONFIG.HOST}:${CONFIG.PORT}`);
  console.log(`SSEエンドポイント: http://${CONFIG.HOST}:${CONFIG.PORT}${CONFIG.ENDPOINT}`);
});
