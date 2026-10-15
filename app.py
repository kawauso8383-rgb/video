import os
import shutil
from fastapi import FastAPI, Form, UploadFile, File
from fastapi.responses import HTMLResponse
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

app = FastAPI()
os.makedirs("temp_uploads", exist_ok=True)

class HighlightSection(BaseModel):
    title: str = Field(description="動画の核となるショート動画用タイトル")
    start_time: float = Field(description="最も盛り上がる開始秒")
    end_time: float = Field(description="切り抜き終了秒（start_timeから20〜50秒以内）")
    hook_reason: str = Field(description="映像や音声の具体的な内容を踏まえた見どころ理由")
    telop_text: str = Field(description="画面冒頭に表示すべきおすすめテロップ")

@app.get("/", response_class=HTMLResponse)
def index():
    return """
    <!DOCTYPE html>
    <html lang="ja">
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>AI動画切り抜きアナライザー</title>
      <style>
        body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: #0b0f19; color: #f1f5f9; margin: 0; padding: 16px; }
        .container { max-width: 600px; margin: 0 auto; padding-bottom: 50px; }
        h1 { font-size: 20px; color: #38bdf8; margin-bottom: 4px; }
        .subtitle { font-size: 13px; color: #94a3b8; margin-bottom: 20px; }
        .card { background: #1e293b; padding: 18px; border-radius: 12px; border: 1px solid #334155; }
        label { display: block; margin-top: 14px; font-weight: bold; font-size: 13px; color: #cbd5e1; }
        label:first-of-type { margin-top: 0; }
        input[type="text"], input[type="file"] { width: 100%; padding: 11px; margin-top: 6px; border-radius: 8px; border: 1px solid #475569; background: #0f172a; color: #fff; box-sizing: border-box; font-size: 14px; }
        button { background: #0284c7; color: #fff; border: none; padding: 14px; font-size: 15px; font-weight: bold; border-radius: 8px; cursor: pointer; margin-top: 18px; width: 100%; }
        #loading { display: none; color: #38bdf8; font-weight: bold; text-align: center; margin: 20px 0; }
        .result-card { background: #1e293b; border-left: 4px solid #38bdf8; padding: 16px; margin-top: 20px; border-radius: 0 12px 12px 0; border: 1px solid #334155; }
        .time-badge { background: #0284c7; color: #fff; padding: 4px 10px; border-radius: 6px; font-weight: bold; font-size: 13px; display: inline-block; margin-bottom: 10px; }
        .box { background: #0f172a; padding: 12px; border-radius: 8px; margin: 8px 0; font-size: 14px; }
        video { width: 100%; max-height: 420px; border-radius: 8px; margin-top: 12px; background: #000; }
        .btn-seek { background: #2563eb; color: #fff; border: none; padding: 8px 12px; border-radius: 6px; font-size: 13px; font-weight: bold; cursor: pointer; margin-top: 6px; width: 100%; }
      </style>
    </head>
    <body>
      <div class="container">
        <h1>✂️ AI ショート動画切り抜きアナライザー</h1>
        <div class="subtitle">Geminiが映像と音声を直接解析し、真の見どころ区間を抽出</div>

        <div class="card">
          <label>① 解析する動画ファイル (mp4 / mov)</label>
          <input type="file" id="videoFile" accept="video/*" onchange="onFileChange(event)">
          <div id="fileInfo" style="font-size: 12px; color: #38bdf8; margin-top: 6px;"></div>

          <label>② 切り抜きたい基準・テーマ</label>
          <input type="text" id="focus" value="一番エモく感情が動くシーン、印象的な瞬間を30〜50秒で">

          <button onclick="analyzeVideo()">映像を直接AI解析して切り抜く</button>
        </div>

        <div id="loading">⚡ Geminiが映像と音声の内容を直接解析中（約20〜30秒）...</div>
        <div id="result"></div>
      </div>

      <script>
        let selectedFile = null;
        let clipStart = 0;
        let clipEnd = 0;

        function onFileChange(e) {
          selectedFile = e.target.files[0];
          if (!selectedFile) return;
          document.getElementById('fileInfo').innerText = `ファイル選択: ${selectedFile.name} (${Math.round(selectedFile.size / 1024 / 1024)} MB)`;
        }

        async function analyzeVideo() {
          const focus = document.getElementById('focus').value;
          if (!selectedFile) return alert('動画ファイルを選択してください');

          document.getElementById('loading').style.display = 'block';
          document.getElementById('result').innerHTML = '';

          const form = new FormData();
          form.append('file', selectedFile);
          form.append('focus', focus);

          try {
            const res = await fetch('/analyze_video', { method: 'POST', body: form });
            const data = await res.json();
            document.getElementById('loading').style.display = 'none';

            if (data.error) return alert('エラー: ' + data.error);

            clipStart = data.start_time;
            clipEnd = data.end_time;

            document.getElementById('result').innerHTML = `
              <div class="result-card">
                <div class="time-badge">⏱ 切り抜き区間: ${clipStart}秒 〜 ${clipEnd}秒 (尺: ${Math.round(clipEnd - clipStart)}秒)</div>
                <h3 style="margin: 6px 0; color: #f8fafc;">${data.title}</h3>
                
                <div style="font-size: 12px; color: #94a3b8; margin-top: 8px;">💡 AI解析による選定理由</div>
                <div class="box">${data.hook_reason}</div>

                <div style="font-size: 12px; color: #38bdf8; margin-top: 8px;">🔥 冒頭推奨テロップ</div>
                <div class="box" style="font-weight: bold; color: #facc15;">${data.telop_text}</div>

                <div style="font-size: 12px; color: #94a3b8; margin-top: 8px;">🎬 切り抜きプレビュー（区間内のみループ再生）</div>
                <button class="btn-seek" onclick="playClipRange()">▶ 切り抜き区間（${clipStart}秒〜${clipEnd}秒）を再生</button>
                <video id="previewVideo" controls playsinline></video>
              </div>
            `;

            const video = document.getElementById('previewVideo');
            video.src = URL.createObjectURL(selectedFile);
            
            // 指定の終了秒数に来たら自動で停止（または開始秒に戻す）
            video.ontimeupdate = function() {
              if (video.currentTime >= clipEnd) {
                video.pause();
                video.currentTime = clipStart;
              }
            };

            video.onloadedmetadata = function() {
              video.currentTime = clipStart;
            };
          } catch(e) {
            document.getElementById('loading').style.display = 'none';
            alert('解析エラー: ' + e);
          }
        }

        function playClipRange() {
          const video = document.getElementById('previewVideo');
          if (video) {
            video.currentTime = clipStart;
            video.play();
          }
        }
      </script>
    </body>
    </html>
    """

@app.post("/analyze_video")
async def analyze_video(file: UploadFile = File(...), focus: str = Form(...)):
    local_path = os.path.join("temp_uploads", file.filename)
    with open(local_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        api_key = os.getenv("GEMINI_API_KEY")
        client = genai.Client(api_key=api_key)

        # Gemini API に動画ファイルを直接アップロードしてマルチモーダル認識
        uploaded_video = client.files.upload(file=local_path)

        prompt = f"""
        添付された動画ファイルの内容（映像、登場人物の感情・表情、音声やセリフ）を詳細に解析してください。
        【切り抜き基準】: {focus}

        動画全体の中から、視聴者の興味を引きつける最も価値の高い区間（20秒〜50秒以内）をピンポイントで特定してください。
        - 映像と音声の内容に即した具体的な秒数（start_time, end_time）を出力すること。単に動画の最後を指定してはいけません。
        - 視聴離脱を防ぐためのテロップ案（telop_text）も具体的に提示すること。
        """

        response = client.models.generate_content(
            model="gemini-3.5-flash",
            contents=[uploaded_video, prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=HighlightSection,
                temperature=0.4,
            ),
        )

        # アップロードした一時ファイルをGemini側から削除
        client.files.delete(name=uploaded_video.name)
        if os.path.exists(local_path):
            os.remove(local_path)

        return HighlightSection.model_validate_json(response.text)

    except Exception as e:
        if os.path.exists(local_path):
            os.remove(local_path)
        return {"error": str(e)}
