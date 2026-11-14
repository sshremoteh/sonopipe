package com.adbsound.app

import android.annotation.SuppressLint
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.media.audiofx.AcousticEchoCanceler
import android.media.audiofx.NoiseSuppressor
import android.util.Log

/**
 * High-performance low-latency AudioRecord microphone capture source.
 * Captures 16-bit PCM audio with hardware Echo Cancellation and Noise Suppression.
 */
class AudioRecordSource(
    val sampleRate: Int = 48000,
    val channels: Int = 1
) {
    companion object {
        private const val TAG = "AudioRecordSource"
    }

    private var audioRecord: AudioRecord? = null
    private var echoCanceler: AcousticEchoCanceler? = null
    private var noiseSuppressor: NoiseSuppressor? = null
    private var isRecording = false

    val channelConfig = if (channels == 2) AudioFormat.CHANNEL_IN_STEREO else AudioFormat.CHANNEL_IN_MONO
    val encoding = AudioFormat.ENCODING_PCM_16BIT
    val minBufferSize = AudioRecord.getMinBufferSize(sampleRate, channelConfig, encoding)
    val bufferSize = (minBufferSize * 2).coerceAtLeast(2048)

    @SuppressLint("MissingPermission")
    fun start(): Boolean {
        if (isRecording) return true

        try {
            audioRecord = AudioRecord(
                MediaRecorder.AudioSource.VOICE_COMMUNICATION,
                sampleRate,
                channelConfig,
                encoding,
                bufferSize
            )

            if (audioRecord?.state != AudioRecord.STATE_INITIALIZED) {
                Log.w(TAG, "VOICE_COMMUNICATION failed, falling back to MIC source")
                audioRecord?.release()
                audioRecord = AudioRecord(
                    MediaRecorder.AudioSource.MIC,
                    sampleRate,
                    channelConfig,
                    encoding,
                    bufferSize
                )
            }

            val session = audioRecord?.audioSessionId ?: 0
            if (session != 0) {
                if (AcousticEchoCanceler.isAvailable()) {
                    try {
                        echoCanceler = AcousticEchoCanceler.create(session)?.apply {
                            enabled = true
                        }
                    } catch (e: Exception) {
                        Log.w(TAG, "Could not enable AcousticEchoCanceler: ${e.message}")
                    }
                }
                if (NoiseSuppressor.isAvailable()) {
                    try {
                        noiseSuppressor = NoiseSuppressor.create(session)?.apply {
                            enabled = true
                        }
                    } catch (e: Exception) {
                        Log.w(TAG, "Could not enable NoiseSuppressor: ${e.message}")
                    }
                }
            }

            audioRecord?.startRecording()
            isRecording = true
            Log.i(TAG, "AudioRecord started: rate=$sampleRate, channels=$channels, bufferSize=$bufferSize")
            return true
        } catch (e: Exception) {
            Log.e(TAG, "Failed to start AudioRecord: ${e.message}", e)
            release()
            return false
        }
    }

    fun read(buffer: ByteArray, offset: Int, length: Int): Int {
        val record = audioRecord ?: return -1
        if (!isRecording) return -1
        return record.read(buffer, offset, length)
    }

    fun stop() {
        if (isRecording) {
            try {
                audioRecord?.stop()
            } catch (e: Exception) {
                Log.e(TAG, "Error stopping AudioRecord", e)
            } finally {
                isRecording = false
            }
        }
    }

    fun release() {
        stop()
        try {
            echoCanceler?.release()
            noiseSuppressor?.release()
            audioRecord?.release()
        } catch (e: Exception) {
            Log.e(TAG, "Error releasing AudioRecord", e)
        } finally {
            echoCanceler = null
            noiseSuppressor = null
            audioRecord = null
        }
    }
}
