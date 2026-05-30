let audioContext = null;
let mediaStream = null;
let source = null;
let processor = null;
let socket = null;

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (!message || message.type !== "ORBIT_OFFSCREEN_START") return false;

  startCapture(message)
    .then(() => sendResponse({ ok: true }))
    .catch((error) => {
      console.error("Orbit offscreen capture failed:", error);
      sendResponse({ ok: false, error: String(error) });
    });
  return true;
});

async function startCapture(config) {
  await stopCapture();

  try {
    const audioFormat = config.audioFormat || {};
    const sampleRate = Number(audioFormat.sampleRate || 16000);
    const channels = Number(audioFormat.channels || 1);

    mediaStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        mandatory: {
          chromeMediaSource: "tab",
          chromeMediaSourceId: config.streamId
        }
      },
      video: false
    });

    audioContext = new AudioContext({ sampleRate });
    await audioContext.resume();
    const actualSampleRate = audioContext.sampleRate;

    socket = new WebSocket(config.webSocketUrl);
    socket.binaryType = "arraybuffer";
    await waitForSocketOpen(socket);
    const activeSocket = socket;
    activeSocket.addEventListener("close", () => {
      if (socket !== activeSocket) return;
      socket = null;
      void stopCapture();
    });
    activeSocket.send(JSON.stringify({
      type: "start",
      encoding: "linear16",
      sample_rate: actualSampleRate,
      channels,
      session_id: config.sessionId,
      meeting_id: config.meetingId
    }));

    source = audioContext.createMediaStreamSource(mediaStream);
    processor = audioContext.createScriptProcessor(4096, 1, 1);
    processor.onaudioprocess = (event) => {
      if (!socket || socket.readyState !== WebSocket.OPEN) return;
      const pcm16 = convertToMonoPcm16(event.inputBuffer);
      if (pcm16.byteLength > 0) socket.send(pcm16.buffer);
    };

    source.connect(audioContext.destination);
    source.connect(processor);
    processor.connect(audioContext.destination);
  } catch (error) {
    await stopCapture();
    throw error;
  }
}

async function stopCapture() {
  if (source) {
    source.disconnect();
    source = null;
  }
  if (processor) {
    processor.disconnect();
    processor = null;
  }
  if (audioContext) {
    await audioContext.close();
    audioContext = null;
  }
  if (mediaStream) {
    for (const track of mediaStream.getTracks()) track.stop();
    mediaStream = null;
  }
  const activeSocket = socket;
  socket = null;
  if (activeSocket && activeSocket.readyState !== WebSocket.CLOSED) {
    if (activeSocket.readyState === WebSocket.OPEN) {
      activeSocket.send(JSON.stringify({ type: "stop" }));
    }
    activeSocket.close();
  }
}

function waitForSocketOpen(targetSocket) {
  return new Promise((resolve, reject) => {
    targetSocket.onopen = resolve;
    targetSocket.onerror = () => reject(new Error("Orbit audio WebSocket failed to open."));
    targetSocket.onclose = () => reject(new Error("Orbit audio WebSocket closed before opening."));
  });
}

function convertToMonoPcm16(inputBuffer) {
  const length = inputBuffer.length;
  const channels = inputBuffer.numberOfChannels;
  const output = new Int16Array(length);

  for (let index = 0; index < length; index += 1) {
    let sample = 0;
    for (let channel = 0; channel < channels; channel += 1) {
      sample += inputBuffer.getChannelData(channel)[index];
    }
    sample /= Math.max(channels, 1);
    sample = Math.max(-1, Math.min(1, sample));
    output[index] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
  }

  return output;
}
