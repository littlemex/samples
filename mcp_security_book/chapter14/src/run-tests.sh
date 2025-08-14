#!/bin/bash

echo "依存関係をインストール中..."
npm install

echo "TypeScriptをコンパイル中..."
npx tsc

if [ $? -eq 0 ]; then
  echo "コンパイル成功。テストを実行中..."
  node add.test.js
else
  echo "コンパイルエラー。テストを実行できません。"
  exit 1
fi

echo "テスト完了"
