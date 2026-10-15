import os
import shutil
from fastapi import FastAPI, Form, UploadFile, File
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from moviepy.video.io.VideoFileClip import VideoFileClip

app = FastAPI()

os.makedirs("uploads", exist_ok=True)
os.makedirs("output", exist_ok=True)
app.mount("/output", StaticFiles(directory="output"), name="output")

class HighlightSection(BaseModel):
    start_time: float = Field(description="切り抜き開始秒 (例: 12.5)")
    end_time: float = Field(description="切り抜き終了秒 (例: 42.0)")
    title: str = Field(description="切り抜き動画のタイトル・フック")
    reason: str = Field(description="ここを見どころとして選んだ理由")

def crop_to_vertical(clip):
    # 16:9 などの横長動画を中央基準で 9:16 の縦長にクロップ
    w, h = clip.size
    target_w = int(h * 9 / 16)
    if target_w < w:
        x_center = w / 2
        return clip.crop(x1=x_center - target_w / 2, y1=0, x2=x_center + target_w / 2, y2=h)
    return clip

@app.get("/", response_class=HTMLResponse)
def index():
    return """
    <!DOCTYPE html>
    <html lang="ja">
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>AI 動画切り抜きジェネレーター</title>
      <style>
        body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: #0b0f19; color: #f1f5f9; margin: 0; padding: 16px; }
        .container { max-width: 650px; margin: 0 auto; }
        h1 { font-size: 20px; color: #38bdf8; margin-bottom: 4px; }
        .subtitle { font-size: 13px; color: #94a3b8; margin-bottom: 20px; }
        .card { background: #1e293b; padding: 18px; border-radius: 12px; border: 1px solid #334155; }
        label { display: block; margin-top: 14px; font-weight: bold; font-size: 13px; }
        label:first-of-type { margin-top: 0; }
        input[type="text"], input[type="file"] { width: 100%; padding: 10px; margin-top: 6px; border-radius: 8px; border: 1px solid #475569; background: #0f172a; color: #fff; box-sizing: border-box; font-size: 14px; }
        button { background: #0284c7; color: #fff; border: none; padding: 14px; font-size: 15px; font-weight: bold; border-radius: 8px; cursor: pointer; margin-top: 18px; width: 100%; }
        #loading { display: none; color: #38bdf8; font-weight: bold; text-align: center; margin: 20px 0; }
        .result-box { background: #1e293b; padding: 16px; border-radius: 12px; border: 1px solid #38bdf8; margin-top: 20px; }
        video { width: 100%; max-height: 480px; border-radius: 8px; margin-top: 10px; background: #000; }
        .btn-download { display: block; text-align: center; background: #047857; color: #fff; padding: 12px; border-radius: 8px; text-decoration: none; font-weight: bold; margin-top: 12px; }
      </style>
    </head>
    <body>
      <div class="container">
        <h1>✂️ AI ショート動画切り抜きツール</h1>
        <div class="subtitle">元の動画から見どころを検出し、9:16縦型ショート動画を自動生成</div>
        
        <div class="card">
          <label>① 動画ファイルを選択 (mp4 / mov)</label>
          <input type="file" id="videoFile" accept="video/*">

          <label>② 切り抜きたい基準・注目ポイント</label>
          <input type="text" id="focus" value="一番話が盛り上がっている場面、インパクトのあるシーンを30秒前後で">

          <button onclick="processClip()">動画を解析して切り抜く</button>
        </div>

        <div id="loading">⚡ 動画を解析・切り抜き処理中です（約20〜40秒）...</div>
        <div id="result"></div>
      </div>

      <script>
        async function processClip() {
          const fileInput = document.getElementById('videoFile');
          const focus = document.getElementById('focus').value;
          if (!fileInput.files[0]) return alert('動画ファイルを選択してください');

          document.getElementById('loading').style.display = 'block';
          document.getElementById('result').innerHTML = '';

          const form = new FormData();
          form.append('file', fileInput.files[0]);
          form.append('focus', focus);

          try {
            const res = await fetch('/clip', { method: 'POST', body: form });
            const data = await res.json();
            document.getElementById('loading').style.display = 'none';

            if (data.error) return alert('エラー: ' + data.error);

            document.getElementById('result').innerHTML = `
              <div class="result-box">
                <h3 style="margin: 0; color: #38bdf8;">${data.title}</h3>
                <p style="font-size: 13px; color: #94a3b8; margin: 6px 0;">区間: ${data.start_time}秒 〜 ${data.end_time}秒</p>
                <p style="font-size: 14px;">${data.reason}</p>
                <video controls src="${data.video_url}"></video>
                <a class="btn-download" href="${data.video_url}" download="short_clip.mp4">📥 切り抜き動画を保存</a>
              </div>
            `;
          } catch(e) {
            document.getElementById('loading').style.display = 'none';
            alert('処理に失敗しました: ' + e);
          }
        }
      </script>
    </body>
    </html>
    """

@app.post("/clip")
async def clip_video(file: UploadFile = File(...), focus: str = Form(...)):
    save_path = os.path.join("uploads", file.filename)
    with open(save_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        clip = VideoFileClip(save_path)
        duration = clip.duration

        api_key = os.getenv("GEMINI_API_KEY")
        client = genai.Client(api_key=api_key)

        # 動画全体の長さから最適な切り抜き秒数を判断
        prompt = f"""
        総再生時間 {duration:.1f} 秒の動画です。
        【切り抜き基準】: {focus}
        動画全体の中から、ショート動画（20秒〜45秒程度）として最も見応えのある開始時間と終了時間を決定してください。
        開始時間は 0 以上、終了時間は {duration:.1f} 以下にしてください。
        """

        response = client.models.generate_content(
            model="gemini-3.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=HighlightSection,
            ),
        )
        data = HighlightSection.model_validate_json(response.text)

        # 切り抜き & 9:16 クロップ処理
        subclip = clip.subclip(data.start_time, min(data.end_time, duration))
        vertical_clip = crop_to_vertical(subclip)

        out_name = f"clip_{int(data.start_time)}_{int(data.end_time)}.mp4"
        out_path = os.path.join("output", out_name)
        
        vertical_clip.write_videofile(
            out_path,
            codec="libx264",
            audio_codec="aac",
            temp_audiofile="temp-audio.m4a",
            remove_temp=True,
            threads=2,
            logger=None
        )

        clip.close()
        subclip.close()
        vertical_clip.close()

        return {
            "title": data.title,
            "reason": data.reason,
            "start_time": data.start_time,
            "end_time": data.end_time,
            "video_url": f"/output/{out_name}"
        }

    except Exception as e:
        return {"error": str(e)}
