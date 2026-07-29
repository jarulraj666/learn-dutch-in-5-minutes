# Google Colab Parkiet TTS Setup Guide

This guide explains how to run Parkiet Dutch TTS on Google Colab and connect to it from your local machine.

## Why Use Remote Parkiet?

- **Avoid local resource constraints**: Parkiet requires 10+ GB RAM, GPU highly recommended
- **Free GPU**: Google Colab provides free GPU access
- **Always-on inference**: Set up a Colab instance to run continuously
- **Scalable**: Can run multiple requests in parallel

## Prerequisites

1. **Google Account** - For Google Colab access
2. **ngrok Account** - Free tier for tunneling (https://ngrok.com)
3. **Local machine** - With the Dutch Language Video Generation pipeline

## Step 1: Get ngrok Token & Add to Colab Secrets

1. Go to https://dashboard.ngrok.com/auth
2. Sign up for free (or log in)
3. Copy your **Auth Token** (looks like `ngrk_xxxx_xxxxxxxxxxxx...`)

4. **Add to Colab Secrets**:
   - Open your Colab notebook
   - Click the 🔑 **Secrets** icon on the left sidebar (near Files)
   - Click **+ Add new secret**
   - Name: `NGROK_AUTH_TOKEN`
   - Value: Paste your auth token
   - Click **Save**

## Step 2: Create & Setup Colab Notebook

1. Go to https://colab.research.google.com
2. Create new notebook: `File` → `New notebook`
3. Copy the **complete code** from below into separate cells (one cell per code block)

### Cell 1: Install Dependencies
```python
!pip install -q transformers torch soundfile fastapi uvicorn pyngrok python-multipart
print("✓ Dependencies installed")
```

### Cell 2: Configure ngrok with Secret
```python
from pyngrok import ngrok
from google.colab import userdata

# Get auth token from Colab Secrets (secure, no hardcoding!)
try:
    NGROK_AUTH_TOKEN = userdata.get("NGROK_AUTH_TOKEN")
    ngrok.set_auth_token(NGROK_AUTH_TOKEN)
    print("✓ ngrok configured from Colab Secrets")
except userdata.SecretNotFoundError:
    print("⚠ ERROR: NGROK_AUTH_TOKEN not found in Colab Secrets")
    print("Please add it via 🔑 Secrets icon and re-run this cell")
    raise
```

### Cell 3: Load Parkiet Model
```python
print("Loading Parkiet model (this may take ~2 minutes)...")

from transformers import pipeline
import torch

tts_pipeline = pipeline(
    "text-to-speech",
    model="pevers/parkiet",
    device=0 if torch.cuda.is_available() else -1
)

print(f"✓ Parkiet loaded successfully")
print(f"  GPU available: {torch.cuda.is_available()}")
print(f"  Model: pevers/parkiet")
```

### Cell 4: Create FastAPI Server
```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import soundfile as sf
import numpy as np
import io
import base64

app = FastAPI(title="Parkiet TTS API")

class TextToSpeechRequest(BaseModel):
    text: str
    speaker: str = "[S1]"

class TextToSpeechResponse(BaseModel):
    status: str
    message: str
    audio_base64: str = None
    duration_seconds: float = None

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "model": "parkiet",
        "device": "GPU" if torch.cuda.is_available() else "CPU"
    }

@app.post("/generate_voice", response_model=TextToSpeechResponse)
async def generate_voice(request: TextToSpeechRequest):
    """Generate speech from Dutch text"""
    try:
        if not request.text:
            raise HTTPException(status_code=400, detail="Text cannot be empty")
        
        text_with_speaker = request.text
        if not text_with_speaker.startswith("[S"):
            text_with_speaker = f"{request.speaker} {request.text}"
        
        print(f"Generating: {text_with_speaker}")
        wav = tts_pipeline(text_with_speaker)
        
        audio_data = np.array(wav["audio"])
        sample_rate = wav["sampling_rate"]
        duration = len(audio_data) / sample_rate
        
        buffer = io.BytesIO()
        sf.write(buffer, audio_data, sample_rate, format='WAV')
        buffer.seek(0)
        audio_base64 = base64.b64encode(buffer.read()).decode()
        
        return TextToSpeechResponse(
            status="success",
            message=f"Generated audio for: {request.text}",
            audio_base64=audio_base64,
            duration_seconds=duration
        )
    
    except Exception as e:
        print(f"Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
async def root():
    return {
        "name": "Parkiet TTS API",
        "endpoints": {
            "health": "/health (GET)",
            "generate_voice": "/generate_voice (POST)"
        }
    }

print("✓ FastAPI app created")
```

### Cell 5: Start Server & Expose with ngrok
```python
import uvicorn
from threading import Thread
import time

def run_server():
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="error")

server_thread = Thread(target=run_server, daemon=True)
server_thread.start()

print("⏳ Starting server...")
time.sleep(3)

try:
    public_url = ngrok.connect(8000)
    print(f"\n{'='*70}")
    print(f"✓ PUBLIC API URL:")
    print(f"  {public_url}")
    print(f"{'='*70}\n")
    print("💾 SAVE THIS URL! Use it in .env file on local machine\n")
except Exception as e:
    print(f"❌ Error: {e}")
```

### Cell 6: Test in Colab (Optional)
```python
import requests

print("Testing API locally...")

# Health check
r = requests.get("http://localhost:8000/health")
print(f"✓ Health: {r.json()['status']}")

# Test generation
test = {"text": "Hallo, hoe gaat het?", "speaker": "[S1]"}
r = requests.post("http://localhost:8000/generate_voice", json=test)
result = r.json()

print(f"✓ Test generation:")
print(f"  Text: {test['text']}")
print(f"  Duration: {result['duration_seconds']:.2f}s")

# Play in Colab
if result['audio_base64']:
    from IPython.display import Audio
    import base64
    audio_bytes = base64.b64decode(result['audio_base64'])
    display(Audio(audio_bytes, rate=22050))
```

### Cell 7: Keep Server Alive
```python
import time

print("✓ Server is running! Keep this notebook open.")
print(f"Public URL: {public_url}\n")

# Keep printing status every minute
while True:
    time.sleep(60)
    print(f"[{time.strftime('%H:%M:%S')}] ✓ Server active and ready")
```

## Step 3: Configure Local Machine

1. **Copy the public URL** from Colab Cell 5 (e.g., `https://xxxx-xxxx-xxxx.ngrok.io`)

2. **Update `.env` file** in your DutchLanguageVideoGeneration directory:
```bash
TTS_PROVIDER=parkiet
PARKIET_COLAB_URL=https://YOUR_NGROK_URL_HERE
```

Or set environment variable:
```bash
export PARKIET_COLAB_URL="https://YOUR_NGROK_URL_HERE"
```

## Step 4: Run Pipeline with Remote Parkiet

```bash
cd /path/to/DutchLanguageVideoGeneration

# Option 1: Using .env file
source .venv311/bin/activate
python -m pipeline.test_stage_2_voice_generation

# Option 2: Using environment variable
export PARKIET_COLAB_URL="https://xxxx-xxxx-xxxx.ngrok.io"
python -m pipeline.test_stage_2_voice_generation
```

## Troubleshooting

### "Cannot connect to Colab"
- ✓ Verify ngrok URL is correct (copy-paste from Cell 5)
- ✓ Verify Colab Cell 5 is still running
- ✓ Check if ngrok tunnel is active: visit the URL in browser
- ✓ Verify firewall isn't blocking HTTPS

### "Model loading takes too long"
- This is normal for first load (Parkiet is 1.6B params)
- Model gets cached after first run
- Subsequent requests should be much faster (~2-5 seconds per line)

### "Colab session timed out"
- Google Colab sessions can timeout after 12-30 hours of inactivity
- Click `Reconnect` button or restart the notebook
- Keep the notebook tab active if possible

### "Audio quality issues"
- Check text encoding (should be valid UTF-8 Dutch)
- Verify speaker tags are `[S1]` or `[S2]`
- Check Colab GPU utilization in Cell 5

## Performance Tips

1. **Batch multiple requests**: Send several lines at once is faster than one at a time
2. **Keep Colab running**: Don't interrupt the notebook session
3. **Monitor ngrok bandwidth**: Free tier has limits
4. **Consider upgraded ngrok**: For production use

## Advanced: Custom Colab Setup

To customize Colab behavior, modify Cell 4 FastAPI server:

```python
# Example: Custom response with metadata
@app.post("/generate_voice_extended")
async def generate_voice_extended(request: TextToSpeechRequest):
    # Your custom logic here
    pass
```

## See Also

- [Parkiet Model](https://huggingface.co/pevers/parkiet)
- [ngrok Documentation](https://ngrok.com/docs)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Remote Parkiet Client](./remote_parkiet_client.py)
