import os
import shutil
from fastapi import FastAPI, Form, UploadFile, File
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import mido
from mido import MidiFile, MidiTrack, Message, MetaMessage

app = FastAPI()

os.makedirs("uploads", exist_ok=True)
os.makedirs("output", exist_ok=True)
app.mount("/output", StaticFiles(directory="output"), name="output")

BASS_DRUM = 36
SNARE_DRUM = 38
CLOSED_HIHAT = 42
CRASH_CYMBAL = 49
LOW_TOM = 45
MID_TOM = 47
HIGH_TOM = 50

def generate_drums_from_piano(piano_midi_path: str, output_midi_path: str, style: str):
    mid_in = MidiFile(piano_midi_path)
    mid_out = MidiFile(ticks_per_beat=mid_in.ticks_per_beat)
    tpb = mid_in.ticks_per_beat

    drum_track = MidiTrack()
    mid_out.tracks.append(drum_track)

    tempo = 500000
    for track in mid_in.tracks:
        for msg in track:
            if msg.type == 'set_tempo':
                tempo = msg.tempo
                break
    bpm = round(mido.tempo2bpm(tempo))
    drum_track.append(MetaMessage('set_tempo', tempo=tempo, time=0))
    drum_track.append(MetaMessage('track_name', name='AI Generated Drums', time=0))

    events = []
    for track in mid_in.tracks:
        abs_time = 0
        for msg in track:
            abs_time += msg.time
            if msg.type == 'note_on' and msg.velocity > 0:
                events.append((abs_time, msg.note, msg.velocity))

    events.sort(key=lambda x: x[0])
    total_ticks = max([e[0] for e in events]) if events else tpb * 16

    bass_ticks = set()
    for abs_time, note, vel in events:
        if note < 60:
            quantized = round(abs_time / (tpb / 4)) * int(tpb / 4)
            bass_ticks.add(quantized)

    drum_hits = []
    measure_ticks = tpb * 4
    current_tick = 0
    measure_count = 0

    preview_events = []

    while current_tick <= total_ticks + measure_ticks:
        is_measure_start = (current_tick % measure_ticks == 0)
        is_fourth_measure = (measure_count % 4 == 3)

        if is_measure_start and (measure_count % 2 == 0):
            drum_hits.append((current_tick, CRASH_CYMBAL, 95, tpb // 2))

        for step in range(16):
            tick = current_tick + step * (tpb // 4)
            sub_step = step % 4

            if is_fourth_measure and step >= 12:
                tom_note = HIGH_TOM if step == 12 else (MID_TOM if step in (13, 14) else LOW_TOM)
                drum_hits.append((tick, tom_note, 90 + (step - 12) * 5, tpb // 8))
                drum_hits.append((tick, SNARE_DRUM, 80, tpb // 8))
                continue

            if style == "rock":
                if step % 2 == 0:
                    drum_hits.append((tick, CLOSED_HIHAT, 85 if sub_step == 0 else 70, tpb // 8))
            elif style == "ballad":
                if sub_step == 0:
                    drum_hits.append((tick, CLOSED_HIHAT, 65, tpb // 4))
            else:
                hh_vel = 80 if sub_step == 0 else (60 if sub_step == 2 else 45)
                drum_hits.append((tick, CLOSED_HIHAT, hh_vel, tpb // 8))

            if step in (4, 12):
                drum_hits.append((tick, SNARE_DRUM, 95, tpb // 4))

            if step == 0:
                drum_hits.append((tick, BASS_DRUM, 100, tpb // 4))
            elif tick in bass_ticks and step not in (4, 12):
                drum_hits.append((tick, BASS_DRUM, 85, tpb // 4))
            elif style == "rock" and step in (10,):
                drum_hits.append((tick, BASS_DRUM, 90, tpb // 4))

        current_tick += measure_ticks
        measure_count += 1

    # Webプレビュー用に秒単位のイベント配列を作成
    seconds_per_tick = (tempo / 1000000.0) / tpb
    for abs_time, note, vel, dur in drum_hits:
        t_sec = abs_time * seconds_per_tick
        sound_type = "kick"
        if note == SNARE_DRUM:
            sound_type = "snare"
        elif note == CLOSED_HIHAT:
            sound_type = "hihat"
        elif note in (LOW_TOM, MID_TOM, HIGH_TOM):
            sound_type = "tom"
        elif note == CRASH_CYMBAL:
            sound_type = "crash"
        preview_events.append({"time": round(t_sec, 3), "sound": sound_type})

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
    return bpm, preview_events

@app.get("/", response_class=HTMLResponse)
def index():
    return """
    <!DOCTYPE html>
    <html lang="ja">
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>AI ピアノドラムビルダー</title>
      <style>
        body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: #0b0f19; color: #f1f5f9; margin: 0; padding: 16px; }
        .container { max-width: 600px; margin: 0 auto; padding-bottom: 50px; }
        h1 { font-size: 22px; color: #38bdf8; margin-bottom: 4px; }
        .subtitle { font-size: 13px; color: #94a3b8; margin-bottom: 20px; }
        .card { background: #1e293b; padding: 18px; border-radius: 12px; border: 1px solid #334155; }
        label { display: block; margin-top: 14px; font-weight: bold; font-size: 13px; color: #cbd5e1; }
        label:first-of-type { margin-top: 0; }
        input[type="file"], select { width: 100%; padding: 11px; margin-top: 6px; border-radius: 8px; border: 1px solid #475569; background: #0f172a; color: #fff; box-sizing: border-box; font-size: 14px; }
        button.btn-primary { background: #0284c7; color: #fff; border: none; padding: 14px; font-size: 15px; font-weight: bold; border-radius: 8px; cursor: pointer; margin-top: 18px; width: 100%; }
        #loading { display: none; color: #38bdf8; font-weight: bold; text-align: center; margin: 20px 0; }
        .result-card { background: #1e293b; border-left: 4px solid #10b981; padding: 16px; margin-top: 20px; border-radius: 0 12px 12px 0; border: 1px solid #334155; }
        .btn-play { background: #10b981; color: #fff; border: none; padding: 12px; border-radius: 8px; font-size: 15px; font-weight: bold; width: 100%; cursor: pointer; margin-top: 10px; }
        .btn-stop { background: #ef4444; color: #fff; border: none; padding: 12px; border-radius: 8px; font-size: 15px; font-weight: bold; width: 100%; cursor: pointer; margin-top: 10px; display: none; }
        .btn-download { display: block; text-align: center; background: #334155; color: #fff; padding: 12px; border-radius: 8px; text-decoration: none; font-weight: bold; margin-top: 12px; font-size: 14px; }
      </style>
    </head>
    <body>
      <div class="container">
        <h1>🥁 AI ピアノドラムビルダー</h1>
        <div class="subtitle">ピアノ演奏MIDIを解析し、最適なドラムパターンを即座に試聴・生成</div>

        <div class="card">
          <label>① ピアノのMIDIファイル (.mid)</label>
          <input type="file" id="midiFile" accept=".mid,.midi">

          <label>② ドラムの曲調・スタイル</label>
          <select id="style">
            <option value="pop">エモーショナル・ポップス (躍動感のある16ビート)</option>
            <option value="ballad">静かなバラード (落ち着いたビート)</option>
            <option value="rock">ストレート・ロック (骨太な8ビート & フィルイン)</option>
          </select>

          <button class="btn-primary" onclick="generateDrums()">ドラムパターンを生成する</button>
        </div>

        <div id="loading">⚡ ピアノ打点を解析してドラムパターンを構築中...</div>
        <div id="result"></div>
      </div>

      <script>
        let audioCtx = null;
        let previewEvents = [];
        let scheduledTimeouts = [];

        function initAudio() {
          if (!audioCtx) {
            audioCtx = new (window.AudioContext || window.webkitAudioContext)();
          }
        }

        function playSound(type) {
          if (!audioCtx) return;
          const t = audioCtx.currentTime;

          if (type === 'kick') {
            const osc = audioCtx.createOscillator();
            const gain = audioCtx.createGain();
            osc.frequency.setValueAtTime(140, t);
            osc.frequency.exponentialRampToValueAtTime(30, t + 0.15);
            gain.gain.setValueAtTime(1, t);
            gain.gain.exponentialRampToValueAtTime(0.001, t + 0.2);
            osc.connect(gain);
            gain.connect(audioCtx.destination);
            osc.start(t);
            osc.stop(t + 0.2);
          } else if (type === 'snare') {
            const bufferSize = audioCtx.sampleRate * 0.15;
            const buffer = audioCtx.createBuffer(1, bufferSize, audioCtx.sampleRate);
            const data = buffer.getChannelData(0);
            for (let i = 0; i < bufferSize; i++) data[i] = Math.random() * 2 - 1;
            const noise = audioCtx.createBufferSource();
            noise.buffer = buffer;
            const gain = audioCtx.createGain();
            gain.gain.setValueAtTime(0.7, t);
            gain.gain.exponentialRampToValueAtTime(0.01, t + 0.15);
            noise.connect(gain);
            gain.connect(audioCtx.destination);
            noise.start(t);
          } else if (type === 'hihat') {
            const bufferSize = audioCtx.sampleRate * 0.05;
            const buffer = audioCtx.createBuffer(1, bufferSize, audioCtx.sampleRate);
            const data = buffer.getChannelData(0);
            for (let i = 0; i < bufferSize; i++) data[i] = Math.random() * 2 - 1;
            const noise = audioCtx.createBufferSource();
            noise.buffer = buffer;
            const filter = audioCtx.createBiquadFilter();
            filter.type = 'highpass';
            filter.frequency.value = 7000;
            const gain = audioCtx.createGain();
            gain.gain.setValueAtTime(0.3, t);
            gain.gain.exponentialRampToValueAtTime(0.01, t + 0.05);
            noise.connect(filter);
            filter.connect(gain);
            gain.connect(audioCtx.destination);
            noise.start(t);
          } else if (type === 'tom' || type === 'crash') {
            const osc = audioCtx.createOscillator();
            const gain = audioCtx.createGain();
            osc.frequency.setValueAtTime(type === 'tom' ? 100 : 250, t);
            osc.frequency.exponentialRampToValueAtTime(40, t + 0.3);
            gain.gain.setValueAtTime(0.5, t);
            gain.gain.exponentialRampToValueAtTime(0.01, t + 0.3);
            osc.connect(gain);
            gain.connect(audioCtx.destination);
            osc.start(t);
            osc.stop(t + 0.3);
          }
        }

        function startPlayback() {
          initAudio();
          if (audioCtx.state === 'suspended') audioCtx.resume();
          stopPlayback();

          document.getElementById('btnPlay').style.display = 'none';
          document.getElementById('btnStop').style.display = 'block';

          previewEvents.forEach(ev => {
            const tid = setTimeout(() => {
              playSound(ev.sound);
            }, ev.time * 1000);
            scheduledTimeouts.push(tid);
          });
        }

        function stopPlayback() {
          scheduledTimeouts.forEach(clearTimeout);
          scheduledTimeouts = [];
          const playBtn = document.getElementById('btnPlay');
          const stopBtn = document.getElementById('btnStop');
          if (playBtn) playBtn.style.display = 'block';
          if (stopBtn) stopBtn.style.display = 'none';
        }

        async function generateDrums() {
          const fileInput = document.getElementById('midiFile');
          const style = document.getElementById('style').value;
          if (!fileInput.files[0]) return alert('ピアノのMIDIファイルを選択してください');

          document.getElementById('loading').style.display = 'block';
          document.getElementById('result').innerHTML = '';
          stopPlayback();

          const form = new FormData();
          form.append('file', fileInput.files[0]);
          form.append('style', style);

          try {
            const res = await fetch('/generate_drums', { method: 'POST', body: form });
            const data = await res.json();
            document.getElementById('loading').style.display = 'none';

            if (data.error) return alert('エラー: ' + data.error);

            previewEvents = data.events;

            document.getElementById('result').innerHTML = `
              <div class="result-card">
                <h3 style="margin: 0; color: #34d399;">🥁 ドラムパターン生成完了！ (BPM: ${data.bpm})</h3>
                <p style="font-size: 13px; color: #94a3b8; margin: 8px 0;">ブラウザ上で直接試聴できます。下のボタンを押してリズムを確認してください。</p>
                <button id="btnPlay" class="btn-play" onclick="startPlayback()">▶ ドラムを試聴再生する</button>
                <button id="btnStop" class="btn-stop" onclick="stopPlayback()">⏹ 停止</button>
                <a class="btn-download" href="${data.download_url}" download="ai_drums.mid">📥 MIDIファイルを保存 (.mid)</a>
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
        bpm, events = generate_drums_from_piano(in_path, out_path, style)
        return {
            "status": "success",
            "bpm": bpm,
            "events": events,
            "download_url": f"/output/{out_filename}"
        }
    except Exception as e:
        return {"error": str(e)}
