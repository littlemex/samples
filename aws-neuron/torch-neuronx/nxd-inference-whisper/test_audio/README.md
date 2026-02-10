# テスト音声ファイル

このディレクトリに音声ファイルを配置して、Whisper モデルでテストできます。

## 音声ファイルの取得方法

### 方法 1: LibriSpeech サンプル (英語)

LibriSpeech ASR corpus (CC BY 4.0) から英語の音声サンプルをダウンロードできます。

```bash
cd test_audio

# LibriSpeech サンプルをダウンロード
wget -q https://www.openslr.org/resources/12/dev-clean.tar.gz -O - | \
  tar -xz --strip-components=4 LibriSpeech/dev-clean/1272/128104/1272-128104-0000.flac

# FLAC → WAV 変換 (soundfile 使用)
python3 << 'EOF'
import soundfile as sf
audio, sr = sf.read('1272-128104-0000.flac')
sf.write('librispeech_sample.wav', audio, sr)
print(f"✓ Converted to WAV: {len(audio)/sr: .2f} seconds, {sr} Hz")
EOF

# テスト実行
cd ..
python3 03_inference.py --compiled-path models/whisper-tiny-compiled-tp2 --audio test_audio/librispeech_sample.wav
```

**ライセンス**: CC BY 4.0 (商用利用可能、帰属表示が必要)

### 方法 2: 自分の音声を録音

```bash
# Ubuntu/Linux の場合
arecord -d 10 -f cd -t wav test_audio/my_recording.wav

# macOS の場合
rec -r 16000 -c 1 test_audio/my_recording.wav trim 0 10
```

### 方法 3: YouTube などから音声を抽出

```bash
# yt-dlp を使用 (YouTube からダウンロード)
pip install yt-dlp
yt-dlp -x --audio-format wav -o "test_audio/youtube_sample.%(ext)s" "https://www.youtube.com/watch?v=VIDEO_ID"

# ffmpeg で音声を抽出
ffmpeg -i input_video.mp4 -vn -acodec pcm_s16le -ar 16000 -ac 1 test_audio/extracted_audio.wav
```

## 対応フォーマット

Whisper は以下の音声フォーマットに対応しています:

- **WAV** (.wav) - 推奨
- **MP3** (.mp3)
- **FLAC** (.flac)
- **M4A** (.m4a)
- **OGG** (.ogg)

## 推奨設定

- **サンプリングレート**: 16000 Hz (Whisper の内部処理で 16kHz に変換されます)
- **チャンネル数**: モノラル (1ch)
- **ビット深度**: 16-bit PCM

## テスト用音声データセット

### LibriSpeech (英語)
- **URL**: https://www.openslr.org/12
- **ライセンス**: CC BY 4.0
- **内容**: 英語の朗読音声

### Common Voice (多言語)
- **URL**: https://commonvoice.mozilla.org/
- **ライセンス**: CC0
- **内容**: 100+ 言語の音声データ

### JVS Corpus (日本語)
- **URL**: https://sites.google.com/site/shinnosuketakamichi/research-topics/jvs_corpus
- **ライセンス**: CC BY-SA 4.0
- **内容**: 日本語の音声データ

## 使用例

```bash
# 英語音声の文字起こし
python3 03_inference.py --compiled-path models/whisper-tiny-compiled-tp2 \
  --audio test_audio/librispeech_sample.wav

# 日本語音声の文字起こし
python3 03_inference.py --compiled-path models/whisper-tiny-compiled-tp2 \
  --audio test_audio/japanese_sample.wav --language ja

# 自動言語検出
python3 03_inference.py --compiled-path models/whisper-tiny-compiled-tp2 \
  --audio test_audio/unknown_language.wav
```
