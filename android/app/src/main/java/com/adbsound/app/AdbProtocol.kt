package com.adbsound.app

import java.io.InputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder

/**
 * Protocol definition for ADBSound streaming.
 *
 * Header structure (16 bytes, little-endian):
 * - 0..5:   Magic bytes: 'A', 'D', 'B', 'S', 'N', 'D' (6 bytes)
 * - 6..7:   Protocol Version: uint16 (e.g. 1)
 * - 8..11:  Sample Rate: uint32 (e.g. 48000 or 44100)
 * - 12..13: Channels: uint16 (1 = Mono, 2 = Stereo)
 * - 14..15: Bits per sample: uint16 (16 for s16le)
 */
object AdbProtocol {
    val MAGIC_BYTES = byteArrayOf('A'.code.toByte(), 'D'.code.toByte(), 'B'.code.toByte(),
                                 'S'.code.toByte(), 'N'.code.toByte(), 'D'.code.toByte())
    val MIC_MAGIC_BYTES = byteArrayOf('A'.code.toByte(), 'D'.code.toByte(), 'B'.code.toByte(),
                                     'M'.code.toByte(), 'I'.code.toByte(), 'C'.code.toByte())
    const val HEADER_SIZE = 16
    const val CURRENT_VERSION: Short = 1

    fun createMicHeader(sampleRate: Int = 48000, channels: Int = 1): ByteArray {
        val bb = ByteBuffer.allocate(HEADER_SIZE).order(ByteOrder.LITTLE_ENDIAN)
        bb.put(MIC_MAGIC_BYTES)
        bb.putShort(CURRENT_VERSION)
        bb.putInt(sampleRate)
        bb.putShort(channels.toShort())
        bb.putShort(16.toShort())
        return bb.array()
    }

    data class AudioStreamConfig(
        val version: Short,
        val sampleRate: Int,
        val channels: Int,
        val bitsPerSample: Int
    )

    fun parseHeader(input: InputStream): AudioStreamConfig? {
        val buffer = ByteArray(HEADER_SIZE)
        var totalRead = 0
        while (totalRead < HEADER_SIZE) {
            val count = input.read(buffer, totalRead, HEADER_SIZE - totalRead)
            if (count == -1) return null
            totalRead += count
        }

        // Validate magic
        for (i in MAGIC_BYTES.indices) {
            if (buffer[i] != MAGIC_BYTES[i]) {
                return null
            }
        }

        val bb = ByteBuffer.wrap(buffer).order(ByteOrder.LITTLE_ENDIAN)
        bb.position(6)
        val version = bb.short
        val sampleRate = bb.int
        val channels = bb.short.toInt()
        val bitsPerSample = bb.short.toInt()

        if (sampleRate < 8000 || sampleRate > 192000 || channels !in 1..2 || bitsPerSample != 16) {
            return null
        }

        return AudioStreamConfig(version, sampleRate, channels, bitsPerSample)
    }
}
