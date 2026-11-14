"""
ADBSound streaming protocol definition.
"""

import struct

MAGIC_BYTES = b"ADBSND"
HEADER_SIZE = 16
PROTOCOL_VERSION = 1
DEFAULT_PORT = 12850
DEFAULT_SAMPLE_RATE = 48000
DEFAULT_CHANNELS = 2
DEFAULT_BITS_PER_SAMPLE = 16


def create_header(
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    channels: int = DEFAULT_CHANNELS,
    bits_per_sample: int = DEFAULT_BITS_PER_SAMPLE,
    version: int = PROTOCOL_VERSION,
) -> bytes:
    """Pack the 16-byte protocol header."""
    return struct.pack(
        "<6sHIHH",
        MAGIC_BYTES,
        version,
        sample_rate,
        channels,
        bits_per_sample,
    )


def parse_header(data: bytes) -> dict:
    """Unpack and validate the 16-byte protocol header."""
    if len(data) < HEADER_SIZE:
        raise ValueError(f"Header too short: expected {HEADER_SIZE} bytes, got {len(data)}")

    magic, version, sample_rate, channels, bits_per_sample = struct.unpack(
        "<6sHIHH", data[:HEADER_SIZE]
    )

    if magic != MAGIC_BYTES:
        raise ValueError(f"Invalid magic bytes: expected {MAGIC_BYTES}, got {magic}")

    return {
        "version": version,
        "sample_rate": sample_rate,
        "channels": channels,
        "bits_per_sample": bits_per_sample,
    }
