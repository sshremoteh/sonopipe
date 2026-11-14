package com.adbsound.app

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.Binder
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import android.util.Log
import androidx.core.app.NotificationCompat
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import java.io.InputStream
import java.io.OutputStream
import java.net.ServerSocket
import java.net.Socket
import java.net.SocketException
import kotlin.math.sqrt

class AudioReceiverService : Service() {

    companion object {
        private const val TAG = "AudioReceiverService"
        const val CHANNEL_ID = "adbsound_playback_channel"
        const val NOTIFICATION_ID = 1001

        const val ACTION_START = "com.adbsound.app.START"
        const val ACTION_STOP = "com.adbsound.app.STOP"
        const val EXTRA_PORT = "extra_port"
        const val EXTRA_MIC_PORT = "extra_mic_port"
        const val EXTRA_MODE = "extra_mode"

        const val MODE_SPEAKER = 0
        const val MODE_MIC = 1
        const val MODE_DUPLEX = 2

        const val DEFAULT_PORT = 12850
        const val DEFAULT_MIC_PORT = 12851
    }

    data class ServiceState(
        val isRunning: Boolean = false,
        val mode: Int = MODE_SPEAKER,
        val isSpeakerConnected: Boolean = false,
        val isMicConnected: Boolean = false,
        val port: Int = DEFAULT_PORT,
        val micPort: Int = DEFAULT_MIC_PORT,
        val sampleRate: Int = 48000,
        val channels: Int = 2,
        val totalBytesReceived: Long = 0,
        val bytesPerSecond: Long = 0,
        val totalBytesSent: Long = 0,
        val micRmsLevel: Float = 0.0f,
        val errorMessage: String? = null
    )

    private val binder = LocalBinder()
    private val scope = CoroutineScope(Dispatchers.IO + Job())
    private var speakerServerJob: Job? = null
    private var micServerJob: Job? = null

    private var speakerServerSocket: ServerSocket? = null
    private var currentSpeakerClientSocket: Socket? = null

    private var micServerSocket: ServerSocket? = null
    private var currentMicClientSocket: Socket? = null

    private var player: AudioTrackPlayer? = null
    private var micSource: AudioRecordSource? = null
    private var wakeLock: PowerManager.WakeLock? = null

    private val _stateFlow = MutableStateFlow(ServiceState())
    val stateFlow: StateFlow<ServiceState> = _stateFlow.asStateFlow()

    private var currentVolume = 1.0f

    inner class LocalBinder : Binder() {
        fun getService(): AudioReceiverService = this@AudioReceiverService
    }

    override fun onBind(intent: Intent?): IBinder = binder

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
        val powerManager = getSystemService(Context.POWER_SERVICE) as PowerManager
        wakeLock = powerManager.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "ADBSound::AudioStreamWakeLock")
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val action = intent?.action ?: ACTION_START
        when (action) {
            ACTION_START -> {
                val port = intent?.getIntExtra(EXTRA_PORT, DEFAULT_PORT) ?: DEFAULT_PORT
                val micPort = intent?.getIntExtra(EXTRA_MIC_PORT, DEFAULT_MIC_PORT) ?: DEFAULT_MIC_PORT
                val mode = intent?.getIntExtra(EXTRA_MODE, MODE_SPEAKER) ?: MODE_SPEAKER
                startServiceStreams(port, micPort, mode)
            }
            ACTION_STOP -> {
                stopAllStreams()
                stopSelf()
            }
        }
        return START_NOT_STICKY
    }

    fun startServiceStreams(port: Int, micPort: Int, mode: Int) {
        stopAllStreams()

        startForeground(NOTIFICATION_ID, buildNotification("Sonopipe active"))

        try {
            wakeLock?.acquire(24 * 60 * 60 * 1000L)
        } catch (e: Exception) {
            Log.e(TAG, "Failed to acquire wake lock", e)
        }

        _stateFlow.value = ServiceState(
            isRunning = true,
            mode = mode,
            port = port,
            micPort = micPort
        )

        // 1. Launch Speaker Server if applicable
        if (mode == MODE_SPEAKER || mode == MODE_DUPLEX) {
            speakerServerJob = scope.launch {
                runSpeakerServerLoop(port)
            }
        }

        // 2. Launch Mic Server if applicable
        if (mode == MODE_MIC || mode == MODE_DUPLEX) {
            micServerJob = scope.launch {
                runMicServerLoop(micPort)
            }
        }
    }

    // --- SPEAKER RECEIVER LOOP ---
    private suspend fun runSpeakerServerLoop(port: Int) {
        try {
            speakerServerSocket = ServerSocket(port).apply { reuseAddress = true }
            Log.d(TAG, "Speaker ServerSocket listening on port $port")

            while (scope.isActive && speakerServerSocket != null && !speakerServerSocket!!.isClosed) {
                _stateFlow.value = _stateFlow.value.copy(isSpeakerConnected = false)
                updateNotification()

                val client = try {
                    speakerServerSocket!!.accept()
                } catch (e: SocketException) {
                    break
                }

                client.tcpNoDelay = true
                client.receiveBufferSize = 65536
                currentSpeakerClientSocket = client

                _stateFlow.value = _stateFlow.value.copy(isSpeakerConnected = true)
                updateNotification()

                handleSpeakerClientStream(client)

                currentSpeakerClientSocket = null
                player?.release()
                player = null
            }
        } catch (e: Exception) {
            Log.e(TAG, "Speaker server error", e)
            _stateFlow.value = _stateFlow.value.copy(errorMessage = e.message)
        } finally {
            closeQuietly(speakerServerSocket)
            speakerServerSocket = null
        }
    }

    private fun handleSpeakerClientStream(client: Socket) {
        var inputStream: InputStream? = null
        try {
            inputStream = client.getInputStream()

            val config = AdbProtocol.parseHeader(inputStream) ?: return
            _stateFlow.value = _stateFlow.value.copy(
                sampleRate = config.sampleRate,
                channels = config.channels
            )

            player = AudioTrackPlayer(
                sampleRate = config.sampleRate,
                channels = config.channels,
                isCommunication = (_stateFlow.value.mode == MODE_DUPLEX)
            ).apply {
                setVolume(currentVolume)
                play()
            }

            val chunkSize = (config.sampleRate * config.channels * 2 / 50).coerceIn(1024, 8192)
            val buffer = ByteArray(chunkSize)

            var totalBytes = _stateFlow.value.totalBytesReceived
            var bytesInWindow: Long = 0
            var lastStatsTime = System.currentTimeMillis()

            while (scope.isActive && !client.isClosed) {
                val bytesRead = inputStream.read(buffer, 0, buffer.size)
                if (bytesRead == -1) break

                player?.write(buffer, 0, bytesRead)
                totalBytes += bytesRead
                bytesInWindow += bytesRead

                val now = System.currentTimeMillis()
                val elapsed = now - lastStatsTime
                if (elapsed >= 1000) {
                    val rate = (bytesInWindow * 1000) / (elapsed * 1024)
                    _stateFlow.value = _stateFlow.value.copy(
                        totalBytesReceived = totalBytes,
                        bytesPerSecond = rate
                    )
                    bytesInWindow = 0
                    lastStatsTime = now
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Speaker client error", e)
        } finally {
            closeQuietly(inputStream)
            closeQuietly(client)
        }
    }

    // --- MICROPHONE TRANSMITTER LOOP ---
    private suspend fun runMicServerLoop(port: Int) {
        try {
            micServerSocket = ServerSocket(port).apply { reuseAddress = true }
            Log.d(TAG, "Mic ServerSocket listening on port $port")

            while (scope.isActive && micServerSocket != null && !micServerSocket!!.isClosed) {
                _stateFlow.value = _stateFlow.value.copy(isMicConnected = false)
                updateNotification()

                val client = try {
                    micServerSocket!!.accept()
                } catch (e: SocketException) {
                    break
                }

                client.tcpNoDelay = true
                client.sendBufferSize = 65536
                currentMicClientSocket = client

                _stateFlow.value = _stateFlow.value.copy(isMicConnected = true)
                updateNotification()

                handleMicClientStream(client)

                currentMicClientSocket = null
                micSource?.release()
                micSource = null
            }
        } catch (e: Exception) {
            Log.e(TAG, "Mic server error", e)
        } finally {
            closeQuietly(micServerSocket)
            micServerSocket = null
        }
    }

    private fun handleMicClientStream(client: Socket) {
        var outputStream: OutputStream? = null
        try {
            outputStream = client.getOutputStream()

            // Send 16-byte ADBMIC header
            val header = AdbProtocol.createMicHeader(sampleRate = 48000, channels = 1)
            outputStream.write(header)
            outputStream.flush()

            micSource = AudioRecordSource(sampleRate = 48000, channels = 1)
            if (!micSource!!.start()) {
                Log.e(TAG, "Failed to start AudioRecordSource")
                return
            }

            val chunkSize = 960 * 2 // 20ms of mono 16-bit PCM = 1920 bytes
            val buffer = ByteArray(chunkSize)
            var totalSent: Long = 0

            while (scope.isActive && !client.isClosed) {
                val readCount = micSource!!.read(buffer, 0, buffer.size)
                if (readCount > 0) {
                    outputStream.write(buffer, 0, readCount)
                    totalSent += readCount

                    // Calculate RMS level for UI
                    var sum = 0.0
                    val sampleCount = readCount / 2
                    for (i in 0 until sampleCount) {
                        val sample = (buffer[i * 2 + 1].toInt() shl 8) or (buffer[i * 2].toInt() and 0xFF)
                        sum += sample * sample
                    }
                    val rms = (sqrt(sum / sampleCount) / 32768.0).toFloat().coerceIn(0.0f, 1.0f)
                    _stateFlow.value = _stateFlow.value.copy(
                        totalBytesSent = totalSent,
                        micRmsLevel = rms
                    )
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Mic stream exception", e)
        } finally {
            closeQuietly(outputStream)
            closeQuietly(client)
        }
    }

    fun setVolume(volume: Float) {
        currentVolume = volume
        player?.setVolume(volume)
    }

    fun stopAllStreams() {
        speakerServerJob?.cancel()
        speakerServerJob = null

        micServerJob?.cancel()
        micServerJob = null

        closeQuietly(currentSpeakerClientSocket)
        currentSpeakerClientSocket = null

        closeQuietly(currentMicClientSocket)
        currentMicClientSocket = null

        closeQuietly(speakerServerSocket)
        speakerServerSocket = null

        closeQuietly(micServerSocket)
        micServerSocket = null

        player?.release()
        player = null

        micSource?.release()
        micSource = null

        if (wakeLock?.isHeld == true) {
            try {
                wakeLock?.release()
            } catch (e: Exception) {
                Log.e(TAG, "Failed to release wake lock", e)
            }
        }

        _stateFlow.value = ServiceState(isRunning = false)
        stopForeground(STOP_FOREGROUND_REMOVE)
    }

    override fun onDestroy() {
        stopAllStreams()
        super.onDestroy()
    }

    private fun closeQuietly(closeable: java.io.Closeable?) {
        try {
            closeable?.close()
        } catch (_: Exception) {}
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                getString(R.string.notification_channel_name),
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "Sonopipe audio service"
                setShowBadge(false)
            }
            val manager = getSystemService(NotificationManager::class.java)
            manager.createNotificationChannel(channel)
        }
    }

    private fun buildNotification(contentText: String): Notification {
        val launchIntent = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_SINGLE_TOP
        }
        val pendingIntent = PendingIntent.getActivity(
            this, 0, launchIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val stopIntent = Intent(this, AudioReceiverService::class.java).apply {
            action = ACTION_STOP
        }
        val stopPendingIntent = PendingIntent.getService(
            this, 1, stopIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("Sonopipe Audio Service")
            .setContentText(contentText)
            .setSmallIcon(R.drawable.ic_speaker)
            .setContentIntent(pendingIntent)
            .addAction(R.drawable.ic_stop, getString(R.string.btn_stop), stopPendingIntent)
            .setOngoing(true)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .build()
    }

    private fun updateNotification() {
        val text = when (_stateFlow.value.mode) {
            MODE_MIC -> "Microphone active (Port ${_stateFlow.value.micPort})"
            MODE_DUPLEX -> "Duplex headset active (Speaker & Mic)"
            else -> "Speaker active (Port ${_stateFlow.value.port})"
        }
        val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        manager.notify(NOTIFICATION_ID, buildNotification(text))
    }
}
