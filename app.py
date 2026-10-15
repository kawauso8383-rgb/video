import os
from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

app = FastAPI()

class HighlightSection(BaseModel):
    title: str = Field(description="ショート動画のフックになるタイトル案")
    start_time: float = Field(description="切り抜き開始秒 (例: 15.0)")
    end_time: float = Field(description="切り抜き終了秒 (例: 45.0)")
    hook_reason: str = Field(description="ここを切り抜くべき理由・見どころ解説")
    telop_text: str = Field(description="画面冒頭に表示すべきおすすめテロップ文")

@app.get("/", response_class=HTMLResponse)
def index():
    return """
    <!DOCTYPE html>
    <html lang="ja">
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>ショート動画クリッパー</title>
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
        .btn-seek { background: #2563eb; color: #fff; border: none; padding: 8px 12px; border-radius: 6px; font-size: 12px; cursor: pointer; margin-top: 6px; }
      </style>
    </head>
    <body>
      <div class="container">
        <h1>✂️ AI ショート動画切り抜きアナライザー</h1>
        <div class="subtitle">動画を選択すると、秒数を自動計測してAIがバズる区間をピンポイント判定</div>

        <div class="card">
          <label>① 動画ファイルを選択 (mp4 / mov)</label>
          <input type="file" id="videoFile" accept="video/*" onchange="loadDuration(event)">
          <div id="fileInfo" style="font-size: 12px; color: #38bdf8; margin-top: 6px;"></div>

          <label>② 切り抜きたい基準・テーマ</label>
          <input type="text" id="focus" value="一番エモくて感情が高まるシーンを50秒前後で">

          <button onclick="analyzeClip()">AIで最適な切り抜き区間を判定する</button>
        </div>

        <div id="loading">⚡ Geminiが最適なカット区間を算出中...</div>
        <div id="result"></div>
      </div>

      <script>
        let totalDuration = 0;
        let selectedFile = null;

        function loadDuration(e) {
          selectedFile = e.target.files[0];
          if (!selectedFile) return;

          const tempVideo = document.createElement('video');
          tempVideo.preload = 'metadata';
          tempVideo.src = URL.createObjectURL(selectedFile);
          tempVideo.onloadedmetadata = function() {
            totalDuration = tempVideo.duration;
            document.getElementById('fileInfo').innerText = `動画の長さ: ${Math.round(totalDuration)} 秒 読み込み完了`;
          };
        }

        async function analyzeClip() {
          const focus = document.getElementById('focus').value;
          if (!selectedFile) return alert('動画ファイルを選択してください');
          if (totalDuration === 0) return alert('動画の読み込み中です。少々お待ちください');

          document.getElementById('loading').style.display = 'block';
          document.getElementById('result').innerHTML = '';

          const form = new FormData();
          form.append('duration', totalDuration);
          form.append('filename', selectedFile.name);
          form.append('focus', focus);

          try {
            const res = await fetch('/analyze', { method: 'POST', body: form });
            const data = await res.json();
            document.getElementById('loading').style.display = 'none';

            document.getElementById('result').innerHTML = `
              <div class="result-card">
                <div class="time-badge">⏱ 切り抜き区間: ${data.start_time}秒 〜 ${data.end_time}秒 (尺: ${Math.round(data.end_time - data.start_time)}秒)</div>
                <h3 style="margin: 6px 0; color: #f8fafc;">${data.title}</h3>
                
                <div style="font-size: 12px; color: #94a3b8; margin-top: 8px;">💡 見どころ解説</div>
                <div class="box">${data.hook_reason}</div>

                <div style="font-size: 12px; color: #38bdf8; margin-top: 8px;">🔥 冒頭推奨テロップ</div>
                <div class="box" style="font-weight: bold; color: #facc15;">${data.telop_text}</div>

                <div style="font-size: 12px; color: #94a3b8; margin-top: 8px;">🎬 該当区間から再生</div>
                <button class="btn-seek" onclick="jumpTo(${data.start_time})">▶ 開始位置 (${data.start_time}秒) から再生</button>
                <video id="previewVideo" controls playsinline></video>
              </div>
            `;

            const video = document.getElementById('previewVideo');
            video.src = URL.createObjectURL(selectedFile);
            video.onloadedmetadata = function() {
              video.currentTime = data.start_time;
            };
          } catch(e) {
            document.getElementById('loading').style.display = 'none';
            alert('解析エラー: ' + e);
          }
        }

        function jumpTo(sec) {
          const video = document.getElementById('previewVideo');
          if (video) {
            video.currentTime = sec;
            video.play();
          }
        }
      </script>
    </body>
    </html>
    """

@app.post("/analyze")
def analyze(duration: float = Form(...), filename: str = Form(...), focus: str = Form(...)):
    api_key = os.getenv("GEMINI_API_KEY")
    client = genai.Client(api_key=api_key)

    prompt = f"""
    動画ファイル名: {filename}
    動画の総尺: {duration:.1f} 秒
    ユーザーの切り抜き要望: {focus}

    この動画をTikTokやYouTube Shortsで最も伸びるショート動画として切り抜くための設計をしてください。
    - start_time は 0 以上、end_time は {duration:.1f} 以下。
    - 尺（end_time - start_time）は20秒〜60秒以内に収めること。
    - 視聴者の離脱を防ぐための「冒頭テロップ文（telop_text）」も考案すること。
    """

    response = client.models.generate_content(
        model="gemini-3.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=HighlightSection,
            temperature=0.7,
        ),
    )
    return HighlightSection.model_validate_json(response.text)
