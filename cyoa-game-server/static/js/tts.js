/**
 * CYOA Text-to-Speech Module
 * 
 * Handles TTS audio generation and playback for assistant messages.
 * 
 * Features:
 * - Generate speech from text using OpenAI TTS
 * - Cache generated audio to avoid regeneration
 * - Play/pause/stop controls
 * - Auto-stop other audio when new one plays
 */

const CYOATTS = (function() {
  // === State ===
  let currentAudio = null;  // Currently playing Audio object
  let currentMessageIndex = null;  // Index of message currently playing
  let audioCache = new Map();  // Cache of audio URLs by message index
  
  // === Configuration ===
  const DEFAULT_VOICE = 'alloy';  // Can be: alloy, echo, fable, onyx, nova, shimmer
  const DEFAULT_MODEL = 'tts-1';  // or 'tts-1-hd' for higher quality
  
  // === Helper Functions ===
  
  /**
   * Get CSRF token from meta tag.
   */
  function getCSRFToken() {
    return document.querySelector('meta[name="csrf-token"]')?.content || '';
  }
  
  /**
   * Generate TTS audio for a message.
   * Returns the audio URL or throws an error.
   */
  async function generateAudio(text, voice = DEFAULT_VOICE, model = DEFAULT_MODEL) {
    try {
      const response = await fetch('/api/tts/generate', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCSRFToken(),
        },
        body: JSON.stringify({
          text: text,
          voice: voice,
          model: model,
        }),
      });
      
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || 'TTS generation failed');
      }
      
      const data = await response.json();
      
      if (data.status === 'completed') {
        return data.url;
      } else if (data.status === 'failed') {
        throw new Error(data.error || 'TTS generation failed');
      } else {
        // Should not happen with synchronous generation, but handle it
        throw new Error('TTS generation did not complete');
      }
    } catch (error) {
      console.error('TTS generation error:', error);
      throw error;
    }
  }
  
  /**
   * Play TTS audio for a message.
   * Stops any currently playing audio first.
   */
  async function playMessage(messageIndex, text, onPlay, onEnd, onError) {
    try {
      // Stop any currently playing audio
      stopAudio();
      
      // Check cache first
      let audioUrl = audioCache.get(messageIndex);
      
      // Generate if not cached
      if (!audioUrl) {
        audioUrl = await generateAudio(text);
        audioCache.set(messageIndex, audioUrl);
      }
      
      // Create and play audio
      const audio = new Audio(audioUrl);
      currentAudio = audio;
      currentMessageIndex = messageIndex;
      
      audio.onplay = () => {
        if (onPlay) onPlay(messageIndex);
      };
      
      audio.onended = () => {
        currentAudio = null;
        currentMessageIndex = null;
        if (onEnd) onEnd(messageIndex);
      };
      
      audio.onerror = (e) => {
        console.error('Audio playback error:', e);
        currentAudio = null;
        currentMessageIndex = null;
        if (onError) onError(messageIndex, 'Playback failed');
      };
      
      await audio.play();
      
    } catch (error) {
      console.error('Error playing message:', error);
      if (onError) onError(messageIndex, error.message);
    }
  }
  
  /**
   * Stop currently playing audio.
   */
  function stopAudio() {
    if (currentAudio) {
      currentAudio.pause();
      currentAudio.currentTime = 0;
      currentAudio = null;
      currentMessageIndex = null;
    }
  }
  
  /**
   * Pause currently playing audio.
   */
  function pauseAudio() {
    if (currentAudio) {
      currentAudio.pause();
    }
  }
  
  /**
   * Resume paused audio.
   */
  function resumeAudio() {
    if (currentAudio && currentAudio.paused) {
      currentAudio.play();
    }
  }
  
  /**
   * Check if a message is currently playing.
   */
  function isPlaying(messageIndex) {
    return currentMessageIndex === messageIndex && currentAudio && !currentAudio.paused;
  }
  
  /**
   * Get current playback state.
   */
  function getState() {
    return {
      playing: currentAudio && !currentAudio.paused,
      messageIndex: currentMessageIndex,
      currentTime: currentAudio ? currentAudio.currentTime : 0,
      duration: currentAudio ? currentAudio.duration : 0,
    };
  }
  
  /**
   * Clear audio cache (e.g., when starting new conversation).
   */
  function clearCache() {
    audioCache.clear();
    stopAudio();
  }
  
  // Public API
  return {
    playMessage,
    stopAudio,
    pauseAudio,
    resumeAudio,
    isPlaying,
    getState,
    clearCache,
  };
})();
