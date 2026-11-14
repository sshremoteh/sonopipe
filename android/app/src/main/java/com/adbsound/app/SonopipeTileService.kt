package com.adbsound.app

import android.content.Intent
import android.os.Build
import android.service.quicksettings.Tile
import android.service.quicksettings.TileService
import androidx.annotation.RequiresApi

@RequiresApi(Build.VERSION_CODES.N)
class SonopipeTileService : TileService() {

    override fun onStartListening() {
        super.onStartListening()
        updateTileState()
    }

    override fun onClick() {
        super.onClick()
        val tile = qsTile ?: return

        if (tile.state == Tile.STATE_ACTIVE) {
            // Stop service
            val stopIntent = Intent(this, AudioReceiverService::class.java).apply {
                action = AudioReceiverService.ACTION_STOP
            }
            startService(stopIntent)
            tile.state = Tile.STATE_INACTIVE
            tile.label = "Sonopipe (Off)"
        } else {
            // Start service
            val startIntent = Intent(this, AudioReceiverService::class.java).apply {
                action = AudioReceiverService.ACTION_START
                putExtra(AudioReceiverService.EXTRA_MODE, AudioReceiverService.MODE_SPEAKER)
            }
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                startForegroundService(startIntent)
            } else {
                startService(startIntent)
            }
            tile.state = Tile.STATE_ACTIVE
            tile.label = "Sonopipe (On)"
        }
        tile.updateTile()
    }

    private fun updateTileState() {
        val tile = qsTile ?: return
        tile.state = Tile.STATE_INACTIVE
        tile.label = "Sonopipe"
        tile.updateTile()
    }
}
