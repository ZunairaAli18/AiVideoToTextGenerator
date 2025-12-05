'use client';

import { useState } from 'react';
import axios from 'axios';

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [status, setStatus] = useState<string>('');
  const [transcription, setTranscription] = useState<string>('');
  const [isProcessing, setIsProcessing] = useState<boolean>(false);

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    if (event.target.files) {
      setFile(event.target.files[0]);
    }
  };

  const handleFileUpload = async () => {
    if (!file) {
      alert('Please select a file');
      return;
    }

    const formData = new FormData();
    formData.append('file', file);

    try {
      setStatus('Uploading...');
      setIsProcessing(true);
      const response = await axios.post('http://localhost:5000/upload_video', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });
      const { task_id } = response.data;
      setTaskId(task_id);
      setStatus('Transcription started...');
      monitorTaskStatus(task_id);
    } catch (error) {
      console.error('Error uploading video:', error);
      setStatus('Error occurred during file upload');
      setIsProcessing(false);
    }
  };

  const monitorTaskStatus = async (taskId: string) => {
    const interval = setInterval(async () => {
      try {
        const response = await axios.get(`http://localhost:5000/status/${taskId}`);
        const { status, progress, transcription, percent } = response.data;

        if (status === 'completed') {
          clearInterval(interval);
          setStatus('Transcription completed');
          setTranscription(transcription);
          setIsProcessing(false);
        } else {
          setStatus(`Processing: ${progress} (${percent}%)`);
        }
      } catch (error) {
        clearInterval(interval);
        console.error('Error checking status:', error);
        setStatus('Error checking transcription status');
        setIsProcessing(false);
      }
    }, 5000); // Poll every 5 seconds


  };
  const handleDownload = () => {
    // Create a Blob from the transcription text
    const blob = new Blob([transcription], { type: 'text/plain' });

    // Create a link element to download the file
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = 'transcription.txt'; // File name
    link.click(); // Trigger the download
  };

  return (
    <div className="min-h-screen bg-gray-700 text-neonwhite flex flex-col items-center justify-center">
      <h1 className="text-4xl font-extrabold text-red-600 text-center text-neonred mb-8">Video to Text Transcription</h1>

      <div className="bg-gray-800 p-6 rounded-lg shadow-lg w-96">
       <input
          type="file"
          onChange={handleFileChange}
          className="mb-4 px-4 py-2 w-full rounded-md border-2 border-neonred text-neonwhite bg-gray-400 focus:outline-none focus:ring-2 focus:ring-neonred"
        />
        <button
          onClick={handleFileUpload}
          className="w-full py-2 px-4 bg-red-600 text-black rounded-md font-bold hover:bg-white hover:text-black transition duration-300"
          disabled={isProcessing}
        >
          {isProcessing ? (
            <span className="text-xl text-white ">Uploading...</span>  /* Change text size and color for uploading */
          ) : (
            'Upload Video'
          )}
        </button>
      </div>

      {status && (
        <p className="text-center text-lg text-white mt-4">
          {isProcessing ? (
            <span className="text-xl text-yellow-300">{status}</span>  /* Change the status text size and color */
          ) : (
            status
          )}
        </p>
      )}

      {transcription && (
        <div className="bg-gray-900 p-4 mt-6 rounded-md shadow-lg w-400 max-h-120 overflow-y-auto">
          <h2 className="text-xl font-semibold text-neonred mb-4">Transcription:</h2>
          <p className="text-white">{transcription}</p>
        
        </div>
      )}
      {/* Download Button */}
      {transcription && (
        <button
          onClick={handleDownload}
          className="fixed bottom-10 w-64 py-2 px-4 bg-blue-600 text-white rounded-md font-bold text-lg hover:bg-blue-700 transition duration-300"
        >
          Download Transcription
        </button>
      )}
    </div>
  );
}
