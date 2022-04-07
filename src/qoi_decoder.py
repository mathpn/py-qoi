import array

from typing import Tuple


QOI_OP_INDEX = 0x00  # 00xxxxxx
QOI_OP_DIFF = 0x40  # 01xxxxxx
QOI_OP_LUMA = 0x80  # 10xxxxxx
QOI_OP_RUN = 0xc0  # 11xxxxxx
QOI_OP_RGB = 0xfe  # 11111110
QOI_OP_RGBA = 0xff  # 11111111
QOI_MASK_2 = 0xc0  # 11000000


with open('test.qoi', 'rb') as qoi_file:
    qoi_bytes = qoi_file.read()


def hash_pixel(values) -> int:
    r, g, b, a = values
    return (r * 3 + g * 5 + b * 7 + a * 11) % 64


def read_32_bits(array: bytearray, read_pos: int) -> Tuple[int, int]:
    b1 = array[read_pos + 0]
    b2 = array[read_pos + 1]
    b3 = array[read_pos + 2]
    b4 = array[read_pos + 3]
    read_pos += 4
    return b1 << 24 | b2 << 16 | b3 << 8 | b4, read_pos


def decode(file_bytes: bytes):
    read_pos = 0
    header_magic, read_pos = read_32_bits(file_bytes, read_pos)
    width, read_pos = read_32_bits(file_bytes, read_pos)
    height, read_pos = read_32_bits(file_bytes, read_pos)
    channels = file_bytes[read_pos]
    read_pos += 1
    colorspace = file_bytes[read_pos]
    read_pos += 1

    hash_array = [array.array('h', [0, 0, 0, 255]) for _ in range(64)]
    out_size = width * height * channels
    pixel_data = bytearray(out_size)
    px_value = array.array('h', [0, 0, 0, 255])
    run = 0
    for i in range(-channels, out_size, channels):
        index_pos = hash_pixel(px_value)
        hash_array[index_pos][:] = px_value
        if i >= 0:
            for j in range(channels):
                pixel_data[i + j] = px_value[j]

        if run > 0:
            run -= 1
            continue

        if read_pos >= len(file_bytes) - channels:
            break

        b1 = file_bytes[read_pos]
        read_pos += 1

        if b1 == QOI_OP_RGB:
            for j in range(3):
                px_value[j] = file_bytes[read_pos + j]
            read_pos += 3
            continue

        if b1 == QOI_OP_RGBA:
            px_value[:] = array.array(
                'h', tuple(file_bytes[read_pos:read_pos + 4])
            )
            read_pos += 4
            continue

        if (b1 & QOI_MASK_2) == QOI_OP_INDEX:
            px_value[:] = hash_array[b1]
            continue

        if (b1 & QOI_MASK_2) == QOI_OP_DIFF:
            px_value[0] = (px_value[0] + ((b1 >> 4) & 0x03) - 2) % 256
            px_value[1] = (px_value[1] + ((b1 >> 2) & 0x03) - 2) % 256
            px_value[2] = (px_value[2] + (b1 & 0x03) - 2) % 256
            continue

        if (b1 & QOI_MASK_2) == QOI_OP_LUMA:
            b2 = file_bytes[read_pos]
            read_pos += 1
            vg = ((b1 & 0x3f) % 256) - 32
            px_value[0] = (px_value[0] + vg - 8 + ((b2 >> 4) & 0x0f)) % 256
            px_value[1] = (px_value[1] + vg) % 256
            px_value[2] = (px_value[2] + vg - 8 + (b2 & 0x0f)) % 256
            continue

        if (b1 & QOI_MASK_2) == QOI_OP_RUN:
            run = (b1 & 0x3f)

    return pixel_data


if __name__ == '__main__':
    pass
