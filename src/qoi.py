import argparse
import array
from typing import Dict, Tuple

from PIL import Image


# chunk tags
QOI_OP_INDEX = 0x00  # 00xxxxxx
QOI_OP_DIFF = 0x40  # 01xxxxxx
QOI_OP_LUMA = 0x80  # 10xxxxxx
QOI_OP_RUN = 0xc0  # 11xxxxxx
QOI_OP_RGB = 0xfe  # 11111110
QOI_OP_RGBA = 0xff  # 11111111
QOI_MASK_2 = 0xc0  # 11000000


QOI_MAGIC = ord('q') << 24 | ord('o') << 16 | ord('i') << 8 | ord('f')


def hash_pixel(values) -> int:
    r, g, b, a = values
    return (r * 3 + g * 5 + b * 7 + a * 11) % 64


def write_32_bits(value: int, array: bytearray, write_pos: int) -> int:
    array[write_pos + 0] = (0xff000000 & value) >> 24
    array[write_pos + 1] = (0x00ff0000 & value) >> 16
    array[write_pos + 2] = (0x0000ff00 & value) >> 8
    array[write_pos + 3] = (0x000000ff & value)
    return write_pos + 4


def read_32_bits(array: bytearray, read_pos: int) -> Tuple[int, int]:
    b1 = array[read_pos + 0]
    b2 = array[read_pos + 1]
    b3 = array[read_pos + 2]
    b4 = array[read_pos + 3]
    read_pos += 4
    return b1 << 24 | b2 << 16 | b3 << 8 | b4, read_pos


def write_end(array: bytearray, write_pos: int) -> int:
    array[write_pos:write_pos + 7] = bytearray(0)
    array[write_pos + 7] = 1
    return write_pos + 8


def encode_img(img: Image.Image, srgb: bool, out_path: str) -> None:
    width, height = img.size
    if img.mode == 'RGBA':
        alpha = True
    elif img.mode == 'RGB':
        alpha = False
    else:
        raise ValueError(f'Image of non-supported mode: {img.mode}')
    img_bytes = img.tobytes()
    output = encode(img_bytes, width, height, alpha, srgb)

    with open(out_path, 'wb') as qoi:
        qoi.write(output)


def decode_to_img(img_bytes: bytes, out_path: str) -> None:
    out = decode(img_bytes)

    size = (out['width'], out['height'])
    img = Image.frombuffer(out['channels'], size, bytes(out['bytes']), 'raw')
    img.save(out_path, 'png')


def encode(img_bytes: bytes, width: int, height: int, alpha: bool, srgb: bool):
    total_size = height * width
    channels = 4 if alpha else 3
    pixel_data = (
        tuple(img_bytes[i:i + channels])
        for i in range(0, len(img_bytes), channels)
    )
    out_array = bytearray(14 + total_size * (5 if alpha else 4) + 8)
    hash_array = [array.array('h', [0] * 4) for _ in range(64)]

    # write header
    write_pos = 0
    write_pos = write_32_bits(QOI_MAGIC, out_array, write_pos)
    write_pos = write_32_bits(width, out_array, write_pos)
    write_pos = write_32_bits(height, out_array, write_pos)
    out_array[write_pos] = 4 if alpha else 3
    out_array[write_pos + 1] = 0 if srgb else 1

    # encode pixels
    run = 0
    prev_px_value = array.array('h', [0, 0, 0, 255])
    px_value = array.array('h', [0, 0, 0, 255])
    write_pos: int = 14
    for i, px in enumerate(pixel_data):
        prev_px_value[:] = px_value

        if len(px) == 4:
            px_value = array.array('h', px)
        else:
            for j in range(3):
                px_value[j] = px[j]

        if px_value == prev_px_value:
            run += 1
            if run == 62 or (i + 1) >= total_size:
                out_array[write_pos] = QOI_OP_RUN | (run - 1)
                write_pos += 1
                run = 0
            continue

        if run:
            out_array[write_pos] = QOI_OP_RUN | (run - 1)
            write_pos += 1
            run = 0

        index_pos = hash_pixel(px_value)
        if hash_array[index_pos] == px_value:
            out_array[write_pos] = QOI_OP_INDEX | index_pos
            write_pos += 1
            continue

        hash_array[index_pos][:] = px_value
        if px_value[3] != prev_px_value[3]:  # alpha channel
            out_array[write_pos] = QOI_OP_RGBA
            out_array[write_pos + 1] = px_value[0]
            out_array[write_pos + 2] = px_value[1]
            out_array[write_pos + 3] = px_value[2]
            out_array[write_pos + 4] = px_value[3]
            write_pos += 5
            continue

        vr = px_value[0] - prev_px_value[0]
        vg = px_value[1] - prev_px_value[1]
        vb = px_value[2] - prev_px_value[2]

        vg_r = vr - vg
        vg_b = vb - vg

        if all(-3 < x < 2 for x in (vr, vg, vb)):
            out_array[write_pos] = QOI_OP_DIFF | (vr + 2) << 4 | (vg + 2) << 2 | (vb + 2)
            write_pos += 1
            continue
        elif all(-9 < x < 8 for x in (vg_r, vg_b)) and -33 < vg < 32:
            out_array[write_pos] = QOI_OP_LUMA | (vg + 32)
            out_array[write_pos + 1] = (vg_r + 8) << 4 | (vg_b + 8)
            write_pos += 2
            continue

        out_array[write_pos] = QOI_OP_RGB
        out_array[write_pos + 1] = px_value[0]
        out_array[write_pos + 2] = px_value[1]
        out_array[write_pos + 3] = px_value[2]
        write_pos += 4

    write_pos = write_end(out_array, write_pos)
    return out_array[0:write_pos]


def decode(file_bytes: bytes) -> Dict:
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

    out = {
        'width': width, 'height': height,
        'channels': 'RGB' if channels == 3 else 'RGBA',
        'colorspace': colorspace
    }

    out['bytes'] = pixel_data

    return out


def replace_extension(path: str, extension: str) -> str:
    old_extension = path.split('.')[-1]
    new_path = path.replace(old_extension, extension)
    return new_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-e', '--encode', action='store_true', default=False)
    parser.add_argument('-d', '--decode', action='store_true', default=False)
    parser.add_argument(
        '-f', '--file-path', type=str,
        help='path to image file to be encoded or decoded')
    args = parser.parse_args()

    if args.encode:
        try:
            img = Image.open(args.file_path)
        except Exception as exc:
            print(f'image load failed: {exc}')
            return

        out_path = replace_extension(args.file_path, 'qoi')
        encode_img(img, out_path, out_path)

    if args.decode:
        with open(args.file_path, 'rb') as qoi:
            file_bytes = qoi.read()

        out_path = replace_extension(args.file_path, 'png')
        decode_to_img(file_bytes, out_path)


if __name__ == '__main__':
    main()
