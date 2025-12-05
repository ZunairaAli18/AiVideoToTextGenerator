from flask import Flask, request, jsonify
import os
from moviepy import VideoFileClip
import whisper
from flask_cors import CORS 
import soundfile as sf
import librosa
import threading
import numpy as np
import json

app = Flask(__name__)
CORS(app)

# Ensure 'uploads' and 'chunks' folders exist
upload_folder = 'uploads'
chunks_folder = 'chunks'
for folder in [upload_folder, chunks_folder]:
    if not os.path.exists(folder):
        os.makedirs(folder)

# Store transcription status
transcription_status = {}

# Load Whisper model once at startup (reuse for all requests)
print("Loading Whisper model at startup...")
whisper_model = whisper.load_model("base")
print("Whisper model loaded!")

def extract_audio(video_path, audio_path):
    """Extract audio from video file"""
    video = VideoFileClip(video_path)
    video.audio.write_audiofile(audio_path, logger=None)
    video.close()

def split_audio_into_chunks(audio_data, sample_rate, chunk_duration=30):
    """
    Split audio into chunks of specified duration (in seconds)
    Returns list of audio chunks
    """
    chunk_samples = chunk_duration * sample_rate
    total_samples = len(audio_data)
    
    chunks = []
    for i in range(0, total_samples, chunk_samples):
        chunk = audio_data[i:i + chunk_samples]
        chunks.append(chunk)
    
    print(f"Split audio into {len(chunks)} chunks of ~{chunk_duration} seconds each")
    return chunks

def save_chunks_to_file(task_id, chunks):
    """Save chunks to a JSON file"""
    chunks_file_path = os.path.join(chunks_folder, f"{task_id}_chunks.json")
    
    chunks_data = {
        "task_id": task_id,
        "total_chunks": len(chunks),
        "chunks": [
            {
                "chunk_number": idx + 1,
                "text": chunk,
                "timestamp": f"{idx * 30}-{(idx + 1) * 30}s"
            }
            for idx, chunk in enumerate(chunks)
        ]
    }
    
    with open(chunks_file_path, 'w', encoding='utf-8') as f:
        json.dump(chunks_data, f, ensure_ascii=False, indent=2)
    
    print(f"Chunks saved to: {chunks_file_path}")
    return chunks_file_path

def transcribe_audio_chunked(audio_path, task_id):
    """Transcribe audio file in chunks using Whisper"""
    try:
        print(f"Audio file path: {audio_path}")
        
        # Convert to absolute path
        abs_audio_path = os.path.abspath(audio_path)
        print(f"Absolute audio path: {abs_audio_path}")
        
        if not os.path.exists(abs_audio_path):
            raise FileNotFoundError(f"Audio file {abs_audio_path} does not exist")

        # Update status
        transcription_status[task_id] = {
            "status": "processing", 
            "progress": "Loading audio...",
            "chunks": [],
            "percent": 0
        }

        # Load audio using librosa
        print("Loading audio with librosa...")
        audio_data, sample_rate = librosa.load(abs_audio_path, sr=16000)
        
        # Calculate total duration
        duration = len(audio_data) / sample_rate
        print(f"Audio duration: {duration:.2f} seconds")
        
        # Split audio into 30-second chunks
        chunk_duration = 30  # seconds
        chunks = split_audio_into_chunks(audio_data, sample_rate, chunk_duration)
        
        # Transcribe each chunk
        full_transcription = []
        total_chunks = len(chunks)
        
        for idx, chunk in enumerate(chunks, 1):
            print(f"Transcribing chunk {idx}/{total_chunks}...")
            
            # Transcribe chunk
            result = whisper_model.transcribe(
                chunk,
                fp16=False,
                language="en",
                verbose=False
            )
            
            chunk_text = result['text'].strip()
            if chunk_text:
                full_transcription.append(chunk_text)
            
            print(f"Chunk {idx} done: {chunk_text[:50]}...")
            
            # Update progress with new chunk text
            progress_percent = int((idx / total_chunks) * 100)
            transcription_status[task_id] = {
                "status": "processing",
                "progress": f"Processing chunk {idx}/{total_chunks} ({progress_percent}%)",
                "percent": progress_percent,
                "chunks": full_transcription.copy(),  # Send all chunks processed so far
                "current_chunk": chunk_text  # Send just the new chunk
            }
        
        # Save chunks to file
        chunks_file = save_chunks_to_file(task_id, full_transcription)
        
        # Combine all transcriptions
        final_text = " ".join(full_transcription)
        print(f"Transcription completed! Total length: {len(final_text)} characters")
        
        return final_text, chunks_file
        
    except Exception as e:
        print(f"Error during transcription: {e}")
        import traceback
        traceback.print_exc()
        raise e

def transcribe_async(task_id, audio_path):
    """Background transcription task"""
    try:
        text, chunks_file = transcribe_audio_chunked(audio_path, task_id)
        transcription_status[task_id] = {
            "status": "completed", 
            "transcription": text,
            "chunks": transcription_status[task_id].get("chunks", []),
            "chunks_file": chunks_file,
            "percent": 100
        }
    except Exception as e:
        transcription_status[task_id] = {
            "status": "failed", 
            "error": str(e),
            "percent": 0
        }

@app.route('/upload_video', methods=['POST'])
def upload_video():
    try:
        # Get video file from request
        if 'file' not in request.files:
            return jsonify({"error": "No file provided"}), 400
            
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({"error": "No file selected"}), 400

        # Save file to the 'uploads' folder
        video_path = os.path.join(upload_folder, file.filename)
        file.save(video_path)
        print(f"Video saved to: {video_path}")
        
        # Define audio path
        audio_filename = 'extracted_audio.wav'
        audio_path = os.path.join(upload_folder, audio_filename)
        
        # Extract audio
        print(f"Extracting audio to: {audio_path}")
        extract_audio(video_path, audio_path)
        
        # Check if extraction was successful
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio extraction failed - file {audio_path} does not exist")

        print(f"Audio file {audio_path} exists, proceeding with transcription")

        # Generate unique task ID
        import uuid
        task_id = str(uuid.uuid4())
        
        # Initialize status
        transcription_status[task_id] = {
            "status": "queued",
            "progress": "Starting transcription...",
            "percent": 0
        }
        
        # Start transcription in background thread
        thread = threading.Thread(target=transcribe_async, args=(task_id, audio_path))
        thread.daemon = True
        thread.start()
        
        # Return task ID immediately
        return jsonify({
            "task_id": task_id,
            "message": "Transcription started. Use /status endpoint to check progress."
        })
    
    except Exception as e:
        print(f"Error occurred: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/status/<task_id>', methods=['GET'])
def check_status(task_id):
    """Check transcription status"""
    if task_id not in transcription_status:
        return jsonify({"error": "Task not found"}), 404
    
    return jsonify(transcription_status[task_id])

@app.route('/chunks/<task_id>', methods=['GET'])
def get_chunks(task_id):
    """Get chunks for a specific task"""
    chunks_file_path = os.path.join(chunks_folder, f"{task_id}_chunks.json")
    
    if not os.path.exists(chunks_file_path):
        return jsonify({"error": "Chunks file not found"}), 404
    
    try:
        with open(chunks_file_path, 'r', encoding='utf-8') as f:
            chunks_data = json.load(f)
        return jsonify(chunks_data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "model_loaded": whisper_model is not None})

if __name__ == '__main__':
    app.run(debug=True, threaded=True)