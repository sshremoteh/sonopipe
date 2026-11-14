package com.adbsound.app

import android.Manifest
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.ServiceConnection
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.os.IBinder
import android.widget.SeekBar
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import com.adbsound.app.databinding.ActivityMainBinding
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch
import java.util.Locale

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private var service: AudioReceiverService? = null
    private var isBound = false

    private val requestNotificationPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { isGranted ->
        if (!isGranted) {
            Toast.makeText(this, "Notification permission is needed to run background service", Toast.LENGTH_SHORT).show()
        }
    }

    private val requestMicPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { isGranted ->
        if (!isGranted) {
            Toast.makeText(this, "Microphone permission is required to stream mic", Toast.LENGTH_SHORT).show()
        }
    }

    private val connection = object : ServiceConnection {
        override fun onServiceConnected(name: ComponentName?, binder: IBinder?) {
            val localBinder = binder as AudioReceiverService.LocalBinder
            service = localBinder.getService()
            isBound = true
            observeServiceState()
        }

        override fun onServiceDisconnected(name: ComponentName?) {
            service = null
            isBound = false
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        checkPermissions()
        setupListeners()
    }

    override fun onStart() {
        super.onStart()
        val intent = Intent(this, AudioReceiverService::class.java)
        bindService(intent, connection, Context.BIND_AUTO_CREATE)
    }

    override fun onStop() {
        super.onStop()
        if (isBound) {
            unbindService(connection)
            isBound = false
        }
    }

    private fun checkPermissions() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS)
                != PackageManager.PERMISSION_GRANTED) {
                requestNotificationPermissionLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
            }
        }
    }

    private fun setupListeners() {
        binding.toggleModeGroup.addOnButtonCheckedListener { _, checkedId, isChecked ->
            if (isChecked && (checkedId == R.id.btnModeMic || checkedId == R.id.btnModeDuplex)) {
                if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO)
                    != PackageManager.PERMISSION_GRANTED) {
                    requestMicPermissionLauncher.launch(Manifest.permission.RECORD_AUDIO)
                }
            }
        }

        binding.btnToggleService.setOnClickListener {
            val isRunning = service?.stateFlow?.value?.isRunning ?: false
            if (isRunning) {
                val intent = Intent(this, AudioReceiverService::class.java).apply {
                    action = AudioReceiverService.ACTION_STOP
                }
                startService(intent)
            } else {
                val mode = when (binding.toggleModeGroup.checkedButtonId) {
                    R.id.btnModeMic -> AudioReceiverService.MODE_MIC
                    R.id.btnModeDuplex -> AudioReceiverService.MODE_DUPLEX
                    else -> AudioReceiverService.MODE_SPEAKER
                }

                if (mode != AudioReceiverService.MODE_SPEAKER &&
                    ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO)
                    != PackageManager.PERMISSION_GRANTED) {
                    requestMicPermissionLauncher.launch(Manifest.permission.RECORD_AUDIO)
                    return@setOnClickListener
                }

                val portStr = binding.etPort.text.toString().trim()
                val port = portStr.toIntOrNull() ?: AudioReceiverService.DEFAULT_PORT
                val intent = Intent(this, AudioReceiverService::class.java).apply {
                    action = AudioReceiverService.ACTION_START
                    putExtra(AudioReceiverService.EXTRA_PORT, port)
                    putExtra(AudioReceiverService.EXTRA_MODE, mode)
                }
                ContextCompat.startForegroundService(this, intent)
            }
        }

        binding.seekVolume.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(seekBar: SeekBar?, progress: Int, fromUser: Boolean) {
                binding.tvVolumeLabel.text = "Volume: $progress%"
                service?.setVolume(progress / 100.0f)
            }

            override fun onStartTrackingTouch(seekBar: SeekBar?) {}
            override fun onStopTrackingTouch(seekBar: SeekBar?) {}
        })

        binding.etPort.setOnFocusChangeListener { _, hasFocus ->
            if (!hasFocus) {
                val port = binding.etPort.text.toString().trim()
                binding.tvAdbCommand.text = "adb forward tcp:$port tcp:$port"
            }
        }
    }

    private fun observeServiceState() {
        lifecycleScope.launch {
            service?.stateFlow?.collectLatest { state ->
                updateUi(state)
            }
        }
    }

    private fun updateUi(state: AudioReceiverService.ServiceState) {
        val isConnected = state.isSpeakerConnected || state.isMicConnected
        val modeText = when (state.mode) {
            AudioReceiverService.MODE_MIC -> "Microphone"
            AudioReceiverService.MODE_DUPLEX -> "Duplex Headset"
            else -> "Speaker"
        }

        if (!state.isRunning) {
            binding.statusIndicator.backgroundTintList =
                ContextCompat.getColorStateList(this, R.color.status_red)
            binding.tvStatusTitle.text = getString(R.string.status_stopped)
            binding.tvStatusSub.text = "Select mode and press Start"
            binding.btnToggleService.text = getString(R.string.btn_start)
            binding.btnToggleService.setBackgroundColor(
                ContextCompat.getColor(this, R.color.accent_blue)
            )
            binding.etPort.isEnabled = true
            binding.toggleModeGroup.isEnabled = true
        } else if (isConnected) {
            binding.statusIndicator.backgroundTintList =
                ContextCompat.getColorStateList(this, R.color.status_green)
            binding.tvStatusTitle.text = "$modeText: Streaming Active"
            binding.tvStatusSub.text = "Transmitting audio with PC via ADB"
            binding.btnToggleService.text = getString(R.string.btn_stop)
            binding.btnToggleService.setBackgroundColor(
                ContextCompat.getColor(this, R.color.accent_red)
            )
            binding.etPort.isEnabled = false
            binding.toggleModeGroup.isEnabled = false
        } else {
            binding.statusIndicator.backgroundTintList =
                ContextCompat.getColorStateList(this, R.color.status_yellow)
            binding.tvStatusTitle.text = "$modeText: Listening"
            binding.tvStatusSub.text = "Waiting for ADB connection from PC..."
            binding.btnToggleService.text = getString(R.string.btn_stop)
            binding.btnToggleService.setBackgroundColor(
                ContextCompat.getColor(this, R.color.accent_red)
            )
            binding.etPort.isEnabled = false
            binding.toggleModeGroup.isEnabled = false
        }

        val ip = getDeviceWifiIp() ?: "Wi-Fi not connected"
        val cmdText = if (state.mode == AudioReceiverService.MODE_MIC) {
            "USB: adb forward tcp:${state.micPort} tcp:${state.micPort}\nWi-Fi IP: $ip"
        } else if (state.mode == AudioReceiverService.MODE_DUPLEX) {
            "USB: adb forward tcp:${state.port} tcp:${state.port}\n     adb forward tcp:${state.micPort} tcp:${state.micPort}\nWi-Fi IP: $ip"
        } else {
            "USB: adb forward tcp:${state.port} tcp:${state.port}\nWi-Fi IP: $ip"
        }
        binding.tvAdbCommand.text = cmdText

        val channelText = if (state.channels == 1) getString(R.string.channel_mono) else getString(R.string.channel_stereo)
        binding.tvAudioSpecs.text = String.format(
            Locale.US,
            "%d Hz • %s • 16-bit PCM",
            state.sampleRate,
            channelText
        )

        val mb = state.totalBytesReceived / (1024.0 * 1024.0)
        binding.tvStats.text = String.format(
            Locale.US,
            "%.1f MB transferred • %d KB/s",
            mb,
            state.bytesPerSecond
        )

        state.errorMessage?.let { msg ->
            binding.tvStatusSub.text = "Error: $msg"
        }
    }

    private fun getDeviceWifiIp(): String? {
        try {
            val interfaces = java.util.Collections.list(java.net.NetworkInterface.getNetworkInterfaces())
            for (intf in interfaces) {
                if (intf.name.contains("wlan") || intf.name.contains("ap")) {
                    val addrs = java.util.Collections.list(intf.inetAddresses)
                    for (addr in addrs) {
                        if (!addr.isLoopbackAddress && addr is java.net.Inet4Address) {
                            return addr.hostAddress
                        }
                    }
                }
            }
        } catch (_: Exception) {}
        return null
    }
}
