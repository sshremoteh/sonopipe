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
import java.net.ServerSocket
import java.net.Socket
import java.net.SocketException

class AudioReceiverService : Service() {

    companion object {
        private const val TAG = "AudioReceiverService"
        const val CHANNEL_ID = "adbsound_playback_channel"
        const val NOTIFICATION_ID = 1001

        const val ACTION_START = "com.adbsound.app.START"
        const val ACTION_STOP = "com.adbsound.app.STOP"
        const val EXTRA_PORT = "extra_port"
        const val DEFAULT_PORT = 12850
    }

    data class ServiceState(
        val isRunning: Boolean = false,
        val isClientConnected: Boolean = false,
        val port: Int = DEFAULT_PORT,
        val sampleRate: Int = 48000,
        val channels: Int = 2,
        val totalBytesReceived: Long = 0,
        val bytesPerSecond: Long = 0,
        val errorMessage: String? = null
    )

    private val binder = LocalBinder()
    private val scope = CoroutineScope(Dispatchers.IO + Job())
    private var serverJob: Job? = null

    private var serverSocket: ServerSocket? = null
    private var currentClientSocket: Socket? = null
    private var player: AudioTrackPlayer? = null
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
                startListening(port)
            }
            ACTION_STOP -> {
                stopListening()
                stopSelf()
            }
        }
        return START_NOT_STICKY
    }

    fun startListening(port: Int) {
        if (_stateFlow.value.isRunning && _stateFlow.value.port == port) {
            return
        }

        stopListening()

        startForeground(NOTIFICATION_ID, buildNotification(getString(R.string.notification_listening)))

        try {
            wakeLock?.acquire(24 * 60 * 60 * 1000L /* 24 hours */)
        } catch (e: Exception) {
            Log.e(TAG, "Failed to acquire wake lock", e)
        }

        _stateFlow.value = ServiceState(isRunning = true, port = port)

        serverJob = scope.launch {
            runServerLoop(port)
        }
    }

    private suspend fun runServerLoop(port: Int) {
        try {
            serverSocket = ServerSocket(port).apply {
                reuseAddress = true
            }
            Log.d(TAG, "ServerSocket listening on port $port")

            while (scope.isActive && serverSocket != null && !serverSocket!!.isClosed) {
                _stateFlow.value = _stateFlow.value.copy(
                    isClientConnected = false,
                    errorMessage = null
                )
                updateNotification(getString(R.string.notification_listening))

                val client = try {
                    serverSocket!!.accept()
                } catch (e: SocketException) {
                    break
                }

                client.tcpNoDelay = true
                client.receiveBufferSize = 65536
                currentClientSocket = client
                Log.d(TAG, "Client connected from ${client.inetAddress}:${client.port}")

                _stateFlow.value = _stateFlow.value.copy(isClientConnected = true)
                updateNotification(getString(R.string.notification_streaming))

                handleClientStream(client)

                currentClientSocket = null
                player?.release()
                player = null
            }
        } catch (e: Exception) {
            Log.e(TAG, "Server error", e)
            _stateFlow.value = _stateFlow.value.copy(errorMessage = e.message)
        } finally {
            closeQuietly(serverSocket)
            serverSocket = null
            _stateFlow.value = _stateFlow.value.copy(isRunning = false, isClientConnected = false)
        }
    }

    private fun handleClientStream(client: Socket) {
        var inputStream: InputStream? = null
        try {
            inputStream = client.getInputStream()

            // 1. Read Protocol Header
            val config = AdbProtocol.parseHeader(inputStream)
            if (config == null) {
                Log.w(TAG, "Invalid ADB Sound header, closing connection")
                return
            }

            Log.i(TAG, "Audio stream config: $config")
            _stateFlow.value = _stateFlow.value.copy(
                sampleRate = config.sampleRate,
                channels = config.channels
            )

            // 2. Initialize AudioTrack
            player = AudioTrackPlayer(config.sampleRate, config.channels).apply {
                setVolume(currentVolume)
                play()
            }

            // 3. Audio Streaming Loop
            // Chunk size: 20ms of audio (sampleRate * channels * 2 bytes / 50)
            val chunkSize = (config.sampleRate * config.channels * 2 / 50).coerceIn(1024, 8192)
            val buffer = ByteArray(chunkSize)

            var totalBytes = _stateFlow.value.totalBytesReceived
            var bytesInWindow: Long = 0
            var lastStatsTime = System.currentTimeMillis()

            while (scope.isActive && !client.isClosed) {
                val bytesRead = inputStream.read(buffer, 0, buffer.size)
                if (bytesRead == -1) {
                    Log.d(TAG, "Stream ended by client")
                    break
                }

                player?.write(buffer, 0, bytesRead)

                totalBytes += bytesRead
                bytesInWindow += bytesRead

                val now = System.currentTimeMillis()
                val elapsed = now - lastStatsTime
                if (elapsed >= 1000) {
                    val rate = (bytesInWindow * 1000) / (elapsed * 1024) // KB/s
                    _stateFlow.value = _stateFlow.value.copy(
                        totalBytesReceived = totalBytes,
                        bytesPerSecond = rate
                    )
                    bytesInWindow = 0
                    lastStatsTime = now
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Exception during audio stream read/playback", e)
        } finally {
            closeQuietly(inputStream)
            closeQuietly(client)
        }
    }

    fun setVolume(volume: Float) {
        currentVolume = volume
        player?.setVolume(volume)
    }

    fun stopListening() {
        serverJob?.cancel()
        serverJob = null

        closeQuietly(currentClientSocket)
        currentClientSocket = null

        closeQuietly(serverSocket)
        serverSocket = null

        player?.release()
        player = null

        if (wakeLock?.isHeld == true) {
            try {
                wakeLock?.release()
            } catch (e: Exception) {
                Log.e(TAG, "Failed to release wake lock", e)
            }
        }

        _stateFlow.value = ServiceState(isRunning = false, isClientConnected = false)
        stopForeground(STOP_FOREGROUND_REMOVE)
    }

    override fun onDestroy() {
        stopListening()
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
                description = "ADBSound playback notification"
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
            .setContentTitle(getString(R.string.notification_title))
            .setContentText(contentText)
            .setSmallIcon(R.drawable.ic_speaker)
            .setContentIntent(pendingIntent)
            .addAction(R.drawable.ic_stop, getString(R.string.btn_stop), stopPendingIntent)
            .setOngoing(true)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .build()
    }

    private fun updateNotification(text: String) {
        val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        manager.notify(NOTIFICATION_ID, buildNotification(text))
    }
}
