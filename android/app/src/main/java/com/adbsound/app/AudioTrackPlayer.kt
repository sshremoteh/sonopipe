package com.adbsound.app

import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioTrack
import android.os.Build
import android.util.Log

class AudioTrackPlayer(
    val sampleRate: Int = 48000,
    val channels: Int = 2,
    val isCommunication: Boolean = false
) {
    companion object {
        private const val TAG = "AudioTrackPlayer"
    }

    private var audioTrack: AudioTrack? = null
    private var isPlaying = false
    private var currentVolume = 1.0f

    init {
        initTrack()
    }

    private fun initTrack() {
        val channelConfig = if (channels == 1) {
            AudioFormat.CHANNEL_OUT_MONO
        } else {
            AudioFormat.CHANNEL_OUT_STEREO
        }

        val encoding = AudioFormat.ENCODING_PCM_16BIT
        val minBufferSize = AudioTrack.getMinBufferSize(sampleRate, channelConfig, encoding)
        
        // For minimal latency, we use double minBufferSize or at least 4KB
        val bufferSize = (minBufferSize * 2).coerceAtLeast(4096)

        val usage = if (isCommunication) AudioAttributes.USAGE_VOICE_COMMUNICATION else AudioAttributes.USAGE_MEDIA
        val contentType = if (isCommunication) AudioAttributes.CONTENT_TYPE_SPEECH else AudioAttributes.CONTENT_TYPE_MUSIC

        val audioAttributes = AudioAttributes.Builder()
            .setUsage(usage)
            .setContentType(contentType)
            .setFlags(AudioAttributes.FLAG_LOW_LATENCY)
            .build()

        val audioFormat = AudioFormat.Builder()
            .setSampleRate(sampleRate)
            .setChannelMask(channelConfig)
            .setEncoding(encoding)
            .build()

        val builder = AudioTrack.Builder()
            .setAudioAttributes(audioAttributes)
            .setAudioFormat(audioFormat)
            .setBufferSizeInBytes(bufferSize)
            .setTransferMode(AudioTrack.MODE_STREAM)

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            builder.setPerformanceMode(AudioTrack.PERFORMANCE_MODE_LOW_LATENCY)
        }

        try {
            audioTrack = builder.build()
            audioTrack?.setVolume(currentVolume)
            Log.d(TAG, "AudioTrack initialized: sampleRate=$sampleRate, channels=$channels, bufferSize=$bufferSize")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to build AudioTrack", e)
        }
    }

    fun play() {
        if (!isPlaying) {
            try {
                audioTrack?.play()
                isPlaying = true
            } catch (e: Exception) {
                Log.e(TAG, "Error starting AudioTrack", e)
            }
        }
    }

    fun write(data: ByteArray, offset: Int, length: Int): Int {
        val track = audioTrack ?: return -1
        if (!isPlaying) {
            play()
        }
        return track.write(data, offset, length, AudioTrack.WRITE_BLOCKING)
    }

    fun setVolume(volume: Float) {
        currentVolume = volume.coerceIn(0.0f, 1.0f)
        try {
            audioTrack?.setVolume(currentVolume)
        } catch (e: Exception) {
            Log.e(TAG, "Error setting volume", e)
        }
    }

    fun stop() {
        if (isPlaying) {
            try {
                audioTrack?.stop()
            } catch (e: Exception) {
                Log.e(TAG, "Error stopping AudioTrack", e)
            } finally {
                isPlaying = false
            }
        }
    }

    fun release() {
        stop()
        try {
            audioTrack?.release()
        } catch (e: Exception) {
            Log.e(TAG, "Error releasing AudioTrack", e)
        } finally {
            audioTrack = null
        }
    }
}
