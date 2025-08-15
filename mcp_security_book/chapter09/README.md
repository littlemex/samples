# Chapter 09

```bash
npm i
```

SSE Server 起動

```bash
npx ts-node server.ts 
サーバー起動: http://localhost:3001
SSEエンドポイント: http://localhost:3001/sse
クライアント接続: 新しいSSEセッション開始
SSEイベント送信: 接続確立メッセージ
SSEイベント送信: カウント=1
SSEイベント送信: カウント=2
SSEイベント送信: カウント=3
SSEセッション終了: クライアント切断
```

SSE Client 起動

```bash
npx ts-node client.ts 
SSE接続確立
受信データ: { message: '接続確立' }
受信データ: { count: 1, timestamp: '2025-08-15T03:08:13.708Z' }
受信データ: { count: 2, timestamp: '2025-08-15T03:08:14.708Z' }
受信データ: { count: 3, timestamp: '2025-08-15T03:08:15.710Z' }
```