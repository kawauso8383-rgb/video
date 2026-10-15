import os
import shutil
from fastapi import FastAPI, Form, UploadFile, File
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import mido
from mido import MidiFile, MidiTrack, Message, MetaMessage

app = FastAPI()

os.makedirs("uploads", exist_ok=True)
os.makedirs("output", exist_ok=True)
app.mount("/output", StaticFiles(directory="output"), name="output")

# General MIDI の標準ドラムノート番号 (Channel 10 / 9-indexed: 9)
BASS_DRUM = 36      # バスドラム (キック)
SNARE_DRUM = 38     # アコースティックスネア
CLOSED_HIHAT = 42   # クローズドハイハット
OPEN_HIHAT = 46     # オープンハイハット
CRASH_CYMBAL = 49   # クラッシュシンバル
LOW_TOM = 45        # ロータム
MID_TOM = 47        # ミッドタム
HIGH_TOM = 50       # ハイタム

def generate_drums_from_piano(piano_midi_path: str, output_midi_path: str, style: str):
    mid_in = MidiFile(piano_midi_path)
    mid_out = MidiFile(ticks_per_beat=mid_in.ticks_per_beat)
    tpb = mid_in.ticks_per_beat

    # ドラム専用トラックを作成
    drum_track = MidiTrack()
    mid_out.tracks.append(drum_track)

    # テンポ情報の取得またはデフォルト設定 (120 BPM)
    tempo = 500000
    for track in mid_in.tracks:
        for msg in track:
            if msg.type == 'set_tempo':
                tempo = msg.tempo
                break
    drum_track.append(MetaMessage('set_tempo', tempo=tempo, time=0))
    drum_track.append(MetaMessage('track_name', name='AI Generated Drums', time=0))

    # ピアノトラックの全ノートオンイベントを絶対時間(ticks)で抽出
    events = []
    for track in mid_in.tracks:
        abs_time = 0
        for msg in track:
            abs_time += msg.time
            if msg.type == 'note_on' and msg.velocity > 0:
                events.append((abs_time, msg.note, msg.velocity))

    events.sort(key=lambda x: x[0])
    total_ticks = max([e[0] for e in events]) if events else tpb * 16

    # ピアノの左手（低音部: C4=60より下）の打点タイムスタンプを抽出
    bass_ticks = set()
    for abs_time, note, vel in events:
        if note < 60:
            # 16分音符単位にクオンタイズ（タイミング補正）して集約
            quantized = round(abs_time / (tpb / 4)) * int(tpb / 4)
            bass_ticks.add(quantized)

    # ドラムの打鍵予約リスト: (abs_time, note, velocity, duration)
    drum_hits = []
    measure_ticks = tpb * 4  # 4/4拍子の1小節
    current_tick = 0

    measure_count = 0
    while current_tick <= total_ticks + measure_ticks:
        is_measure_start = (current_tick % measure_ticks == 0)
        is_fourth_measure = (measure_count % 4 == 3)  # 4小節目ごとのフィルイン判定

        # --- 1. シンバル (小節頭や展開ポイント) ---
        if is_measure_start and (measure_count % 2 == 0):
            drum_hits.append((current_tick, CRASH_CYMBAL, 95, tpb // 2))

        # 1小節内の16ステップ（16分音符ごと）を組み立て
        for step in range(16):
            tick = current_tick + step * (tpb // 4)
            sub_step = step % 4  # 拍内位置 (0: 表拍, 2: 裏拍)

            # --- 2. フィルイン (4小節目の後半ステップ 12〜15) ---
            if is_fourth_measure and step >= 12:
                tom_note = HIGH_TOM if step == 12 else (MID_TOM if step in (13, 14) else LOW_TOM)
                drum_hits.append((tick, tom_note, 90 + (step - 12) * 5, tpb // 8))
                drum_hits.append((tick, SNARE_DRUM, 80, tpb // 8))
                continue

            # --- 3. ハイハット (ジャンルに応じたビート刻み) ---
            if style == "rock":
                # 8ビート (表・裏)
                if step % 2 == 0:
                    drum_hits.append((tick, CLOSED_HIHAT, 85 if sub_step == 0 else 70, tpb // 8))
            elif style == "ballad":
                # 4分音符刻みで静かに
                if sub_step == 0:
                    drum_hits.append((tick, CLOSED_HIHAT, 65, tpb // 4))
            else:
                # 定番の16ビート / ポップス
                hh_vel = 80 if sub_step == 0 else (60 if sub_step == 2 else 45)
                drum_hits.append((tick, CLOSED_HIHAT, hh_vel, tpb // 8))

            # --- 4. スネアドラム (基本は2拍目・4拍目: step 4 と 12) ---
            if step in (4, 12):
                drum_hits.append((tick, SNARE_DRUM, 95, tpb // 4))

            # --- 5. バスドラム (キック) ---
            # ピアノの左手低音と同期、または小節頭(step 0)
            if step == 0:
                drum_hits.append((tick, BASS_DRUM, 100, tpb // 4))
            elif tick in bass_ticks and step not in (4, 12):
                # ピアノが低音を弾いているタイミングに自然に追従
                drum_hits.append((tick, BASS_DRUM, 85, tpb // 4))
            elif style == "rock" and step in (10,):
                # ロック定番の裏打ちキック
                drum_hits.append((tick, BASS_DRUM, 90, tpb // 4))

        current_tick += measure_ticks
        measure_count += 1

    # ドラム打点リストをMIDIイベント（Delta Time形式）に変換
    # Note On と Note Off をフラットに展開
    raw_events = []
    for abs_time, note, vel, dur in drum_hits:
        raw_events.append((abs_time, 'note_on', note, vel))
        raw_events.append((abs_time + dur, 'note_off', note, 0))

    raw_events.sort(key=lambda x: (x[0], 0 if x[1] == 'note_off' else 1))

    last_time = 0
    for abs_time, ev_type, note, vel in raw_events:
        delta = abs_time - last_time
        drum_track.append(Message(ev_type, channel=9, note=note, velocity=vel, time=delta))
        last_time = abs_time

    mid_out.save(output_midi_path)


@app.get("/", response_class=HTMLResponse)
def index():
    return """
    <!DOCTYPE html>
    <html lang="ja">
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>AI ピアノ伴奏ドラムジェネレーター</title>
      <style>
        body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: #0b0f19; color: #f1f5f9; margin: 0; padding: 16px; }
        .container { max-width: 600px; margin: 0 auto; padding-bottom: 50px; }
        h1 { font-size: 22px; color: #38bdf8; margin-bottom: 4px; }
        .subtitle { font-size: 13px; color: #94a3b8; margin-bottom: 20px; }
        .card { background: #1e293b; padding: 18px; border-radius: 12px; border: 1px solid #334155; }
        label { display: block; margin-top: 14px; font-weight: bold; font-size: 13px; color: #cbd5e1; }
        label:first-of-type { margin-top: 0; }
        input[type="file"], select { width: 100%; padding: 11px; margin-top: 6px; border-radius: 8px; border: 1px solid #475569; background: #0f172a; color: #fff; box-sizing: border-box; font-size: 14px; }
        button { background: #0284c7; color: #fff; border: none; padding: 14px; font-size: 15px; font-weight: bold; border-radius: 8px; cursor: pointer; margin-top: 18px; width: 100%; }
        #loading { display: none; color: #38bdf8; font-weight: bold; text-align: center; margin: 20px 0; }
        .result-card { background: #1e293b; border-left: 4px solid #10b981; padding: 16px; margin-top: 20px; border-radius: 0 12px 12px 0; border: 1px solid #334155; }
        .btn-download { display: block; text-align: center; background: #059669; color: #fff; padding: 13px; border-radius: 8px; text-decoration: none; font-weight: bold; margin-top: 12px; font-size: 15px; }
      </style>
    </head>
    <body>
      <div class="container">
        <h1>🥁 AI ピアノドラムビルダー</h1>
        <div class="subtitle">ピアノの演奏MIDIを解析し、左手リズム・小節感に完璧同期するドラムトラックを生成</div>

        <div class="card">
          <label>① ピアノのMIDIファイル (.mid)</label>
          <input type="file" id="midiFile" accept=".mid,.midi">

          <label>② ドラムの曲調・スタイル</label>
          <select id="style">
            <option value="pop">エモーショナル・ポップス (躍動感のある16ビート)</option>
            <option value="ballad">静かなバラード (4つ打ちハイハットと優しいスネア)</option>
            <option value="rock">ストレート・ロック (骨太な8ビート & フィルイン)</option>
          </select>

          <button onclick="generateDrums()">最適なドラムMIDIを自動生成する</button>
        </div>

        <div id="loading">⚡ ピアノ演奏の打点を解析してドラムパターンを生成中...</div>
        <div id="result"></div>
      </div>

      <script>
        async function generateDrums() {
          const fileInput = document.getElementById('midiFile');
          const style = document.getElementById('style').value;
          if (!fileInput.files[0]) return alert('ピアノのMIDIファイルを選択してください');

          document.getElementById('loading').style.display = 'block';
          document.getElementById('result').innerHTML = '';

          const form = new FormData();
          form.append('file', fileInput.files[0]);
          form.append('style', style);

          try {
            const res = await fetch('/generate_drums', { method: 'POST', body: form });
            const data = await res.json();
            document.getElementById('loading').style.display = 'none';

            if (data.error) return alert('エラー: ' + data.error);

            document.getElementById('result').innerHTML = `
              <div class="result-card">
                <h3 style="margin: 0; color: #34d399;">🥁 ドラムMIDIが完成しました！</h3>
                <p style="font-size: 13px; color: #94a3b8; margin: 8px 0;">ピアノの低音アタックとBPMにぴったり同期したドラムトラックです。DAW（GarageBand等）のドラムトラックにドラッグ＆ドロップして鳴らしてください。</p>
                <a class="btn-download" href="${data.download_url}" download="ai_drums.mid">📥 ドラムMIDI (.mid) をダウンロード</a>
              </div>
            `;
          } catch(e) {
            document.getElementById('loading').style.display = 'none';
            alert('生成に失敗しました: ' + e);
          }
        }
      </script>
    </body>
    </html>
    """

@app.post("/generate_drums")
async def process_midi(file: UploadFile = File(...), style: str = Form("pop")):
    in_path = os.path.join("uploads", file.filename)
    with open(in_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    out_filename = f"drums_{os.path.splitext(file.filename)[0]}.mid"
    out_path = os.path.join("output", out_filename)

    try:
        generate_drums_from_piano(in_path, out_path, style)
        return {
            "status": "success",
            "download_url": f"/output/{out_filename}"
        }
    except Exception as e:
        return {"error": str(e)}
