import os
import requests
from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

app = FastAPI()

os.makedirs("output", exist_ok=True)
app.mount("/output", StaticFiles(directory="output"), name="output")

class Scene(BaseModel):
    cut_number: int = Field(description="カット番号 (1, 2, 3...)")
    narration: str = Field(description="ナレーション原稿（日本語・3〜5秒。エモく感情が乗るように）")
    visual_description_ja: str = Field(description="シーンの映像説明（日本語）")
    image_prompt_en: str = Field(description="画像生成AI用の英語プロンプト。末尾に --ar 9:16")

class VideoScript(BaseModel):
    title: str = Field(description="動画タイトル")
    scenes: list[Scene] = Field(description="シーンリスト（5〜6カット）")

# VOICEVOX Web API を使った自然な日本語音声生成
def generate_voicevox_audio(text: str, filename: str, speaker_id: int):
    api_url = "https://voicevox.su-shiki.com/api/voicevox"
    params = {
        "text": text,
        "speaker": speaker_id
    }
    response = requests.post(f"{api_url}/audio-query", params=params)
    if response.status_code != 200:
        raise Exception(f"Voicevox query error: {response.text}")
    
    query_data = response.json()
    # 落ち着いた語り口にするため話速をわずかに調整 (0.95倍)
    query_data["speedScale"] = 0.95
    
    synth_res = requests.post(
        f"{api_url}/synthesis",
        params={"speaker": speaker_id},
        json=query_data
    )
    if synth_res.status_code == 200:
        with open(filename, "wb") as f:
            f.write(synth_res.content)
    else:
        raise Exception(f"Voicevox synthesis error: {synth_res.text}")

@app.get("/", response_class=HTMLResponse)
def index():
    return """
    <!DOCTYPE html>
    <html lang="ja">
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>ショート動画ジェネレーター</title>
      <style>
        body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 16px; }
        .container { max-width: 800px; margin: 0 auto; }
        h1 { font-size: 20px; color: #38bdf8; margin-bottom: 16px; }
        .card { background: #1e293b; padding: 16px; border-radius: 12px; margin-bottom: 20px; border: 1px solid #334155; }
        label { display: block; margin-top: 12px; font-weight: bold; font-size: 13px; }
        input, select { width: 100%; padding: 10px; margin-top: 6px; border-radius: 8px; border: 1px solid #475569; background: #0f172a; color: #fff; box-sizing: border-box; font-size: 14px; }
        button { background: #0284c7; color: #fff; border: none; padding: 14px; font-size: 15px; font-weight: bold; border-radius: 8px; cursor: pointer; margin-top: 16px; width: 100%; }
        .scene-card { background: #1e293b; border-left: 4px solid #38bdf8; padding: 14px; margin-bottom: 14px; border-radius: 0 8px 8px 0; }
        .prompt-box { background: #0f172a; padding: 10px; border-radius: 6px; font-family: monospace; font-size: 12px; color: #a5f3fc; word-break: break-all; margin: 8px 0; }
        .btn-action { background: #334155; color: #fff; width: 100%; padding: 10px; font-size: 13px; margin-top: 6px; border: none; border-radius: 6px; cursor: pointer; text-decoration: none; display: inline-block; text-align: center; box-sizing: border-box; }
        .btn-download { background: #047857; }
        #loading { display: none; color: #38bdf8; font-weight: bold; text-align: center; margin: 20px 0; }
        audio { width: 100%; margin: 8px 0; }
      </style>
    </head>
    <body>
      <div class="container">
        <h1>🎬 ショート動画 構成・音声ビルダー</h1>
        <div class="card">
          <label>① 動画のテーマ・アイデア</label>
          <input type="text" id="theme" placeholder="例: 閉店間際のガソリンスタンド、静寂とオレンジの光">
          
          <label>② 画風・キャラクターの一貫性指示</label>
          <input type="text" id="style" value="アニメ調、新海誠風の光と影、黒髪ショートヘアで青いパーカーの青年">

          <label>③ ナレーションの声質（VOICEVOX）</label>
          <select id="voice">
            <option value="13">青山龍星（渋く深みのある大人のナレーション声・イチオシ）</option>
            <option value="2">四国めたん（落ち着いた明瞭な女性声）</option>
            <option value="11">玄野武宏（穏やかな青年・解説風）</option>
            <option value="9">波音リツ（少し低めのクールな女性声）</option>
          </select>
          
          <button onclick="generate()">構成・プロンプト・音声を生成する</button>
        </div>

        <div id="loading">⚡ 日本語音声を生成中です（約10〜15秒）...</div>
        <div id="results"></div>
      </div>

      <script>
        async function generate() {
          const theme = document.getElementById('theme').value;
          const style = document.getElementById('style').value;
          const voice = document.getElementById('voice').value;
          if (!theme) return alert('テーマを入力してください');

          document.getElementById('loading').style.display = 'block';
          document.getElementById('results').innerHTML = '';

          const form = new FormData();
          form.append('theme', theme);
          form.append('style', style);
          form.append('voice', voice);

          try {
            const res = await fetch('/generate', { method: 'POST', body: form });
            const data = await res.json();
            document.getElementById('loading').style.display = 'none';

            let html = `<h2>${data.title}</h2>`;
            data.scenes.forEach(s => {
              const audioUrl = `/output/cut_${String(s.cut_number).padStart(2, '0')}.wav?t=${Date.now()}`;
              html += `
                <div class="scene-card">
                  <h3>Cut ${s.cut_number}</h3>
                  <p><strong>🗣️ ナレーション:</strong> ${s.narration}</p>
                  <audio controls src="${audioUrl}"></audio>
                  <a class="btn-action btn-download" href="${audioUrl}" download="cut_${String(s.cut_number).padStart(2, '0')}.wav">📥 音声（Cut ${s.cut_number}）をダウンロード</a>
                  <p><strong>🎬 構図:</strong> ${s.visual_description_ja}</p>
                  <div class="prompt-box" id="p_${s.cut_number}">${s.image_prompt_en}</div>
                  <button class="btn-action" onclick="copyPrompt('p_${s.cut_number}')">プロンプトをコピー</button>
                </div>
              `;
            });
            document.getElementById('results').innerHTML = html;
          } catch(e) {
            document.getElementById('loading').style.display = 'none';
            alert('エラーが発生しました: ' + e);
          }
        }

        function copyPrompt(id) {
          const text = document.getElementById(id).innerText;
          navigator.clipboard.writeText(text);
          alert('コピーしました！');
        }
      </script>
    </body>
    </html>
    """

@app.post("/generate")
def run_generation(theme: str = Form(...), style: str = Form(...), voice: str = Form("13")):
    api_key = os.getenv("GEMINI_API_KEY")
    client = genai.Client(api_key=api_key)
    
    system_instruction = f"""
    あなたはショート動画ディレクターです。テンポの良いショート動画（30秒前後・5〜6カット）の構成を作成してください。
    【画風・キャラ指示】: {style}
    ※ 上記特徴を全カットの image_prompt_en に含め、末尾に --ar 9:16 を付けてください。
    ※ ナレーションは短く簡潔に、聞き取りやすい言葉遣いにしてください。
    """
    
    response = client.models.generate_content(
        model="gemini-3.5-flash",
        contents=f"テーマ: {theme}",
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json",
            response_schema=VideoScript,
            temperature=0.7,
        ),
    )
    data = VideoScript.model_validate_json(response.text)

    for scene in data.scenes:
        cut_name = f"cut_{scene.cut_number:02d}.wav"
        path = os.path.join("output", cut_name)
        generate_voicevox_audio(scene.narration, path, int(voice))

    return data
