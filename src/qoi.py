import argparse
import array
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

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


@dataclass
class Pixel:
    px_bytes: bytearray = field(init=False)

    def __post_init__(self):
        self.px_bytes = bytearray((0, 0, 0, 255))

    def update(self, values: bytes) -> None:
        n_channels = len(values)
        if n_channels not in (3, 4):
            raise ValueError('a tuple of 3 or 4 values should be provided')

        self.px_bytes[0:n_channels] = values

    def __str__(self) -> str:
        r, g, b, a = self.px_bytes
        return f'R: {r} G: {g} B: {b} A: {a}'

    @property
    def bytes(self) -> bytes:
        return bytes(self.px_bytes)

    @property
    def hash(self) -> int:
        r, g, b, a = self.px_bytes
        return (r * 3 + g * 5 + b * 7 + a * 11) % 64

    @property
    def red(self) -> int:
        return self.px_bytes[0]

    @property
    def green(self) -> int:
        return self.px_bytes[1]

    @property
    def blue(self) -> int:
        return self.px_bytes[2]

    @property
    def alpha(self) -> int:
        return self.px_bytes[3]



def write_32_bits(value: int, data_array: bytearray, write_pos: int) -> int:
    data_array[write_pos + 0] = (0xff000000 & value) >> 24
    data_array[write_pos + 1] = (0x00ff0000 & value) >> 16
    data_array[write_pos + 2] = (0x0000ff00 & value) >> 8
    data_array[write_pos + 3] = (0x000000ff & value)
    return write_pos + 4


def read_32_bits(data_array: bytearray, read_pos: int) -> Tuple[int, int]:
    b1 = data_array[read_pos + 0]
    b2 = data_array[read_pos + 1]
    b3 = data_array[read_pos + 2]
    b4 = data_array[read_pos + 3]
    read_pos += 4
    return b1 << 24 | b2 << 16 | b3 << 8 | b4, read_pos


def write_end(data_array: bytearray, write_pos: int) -> int:
    data_array[write_pos:write_pos + 7] = bytearray(0)
    data_array[write_pos + 7] = 1
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
        img_bytes[i:i + channels]for i in range(0, len(img_bytes), channels)
    )
    out_array = bytearray(14 + total_size * (5 if alpha else 4) + 8)
    hash_array = [Pixel() for _ in range(64)]

    # write header
    write_pos = 0
    write_pos = write_32_bits(QOI_MAGIC, out_array, write_pos)
    write_pos = write_32_bits(width, out_array, write_pos)
    write_pos = write_32_bits(height, out_array, write_pos)
    out_array[write_pos] = 4 if alpha else 3
    out_array[write_pos + 1] = 0 if srgb else 1

    # encode pixels
    run = 0
    prev_px_value = Pixel()
    px_value = Pixel()
    write_pos: int = 14
    for i, px in enumerate(pixel_data):
        prev_px_value.update(px_value.bytes)
        px_value.update(px)

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

        index_pos = px_value.hash
        if hash_array[index_pos] == px_value:
            out_array[write_pos] = QOI_OP_INDEX | index_pos
            write_pos += 1
            continue

        hash_array[index_pos].update(px_value.bytes)

        if px_value.alpha != prev_px_value.alpha:
            out_array[write_pos] = QOI_OP_RGBA
            out_array[write_pos + 1] = px_value.red
            out_array[write_pos + 2] = px_value.green
            out_array[write_pos + 3] = px_value.blue
            out_array[write_pos + 4] = px_value.alpha
            write_pos += 5
            continue

        vr = px_value.red - prev_px_value.red
        vg = px_value.green - prev_px_value.green
        vb = px_value.blue - prev_px_value.blue

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
        out_array[write_pos + 1] = px_value.red
        out_array[write_pos + 2] = px_value.green
        out_array[write_pos + 3] = px_value.blue
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

    hash_array = [Pixel() for _ in range(64)]
    out_size = width * height * channels
    pixel_data = bytearray(out_size)
    px_value = Pixel()
    run = 0
    for i in range(-channels, out_size, channels):
        index_pos = px_value.hash
        hash_array[index_pos].update(px_value.bytes)
        if i >= 0:
            pixel_data[i:i + channels] = px_value.bytes

        if run > 0:
            run -= 1
            continue

        if read_pos >= len(file_bytes) - channels:
            break

        b1 = file_bytes[read_pos]
        read_pos += 1

        if b1 == QOI_OP_RGB:
            px_value.update(file_bytes[read_pos:read_pos + 3])
            read_pos += 3
            continue

        if b1 == QOI_OP_RGBA:
            px_value.update(file_bytes[read_pos:read_pos + 4])
            read_pos += 4
            continue

        if (b1 & QOI_MASK_2) == QOI_OP_INDEX:
            px_value.update(hash_array[b1].bytes)
            continue

        if (b1 & QOI_MASK_2) == QOI_OP_DIFF:
            red = (px_value.red + ((b1 >> 4) & 0x03) - 2) % 256
            green = (px_value.green + ((b1 >> 2) & 0x03) - 2) % 256
            blue = (px_value.blue + (b1 & 0x03) - 2) % 256
            px_value.update(bytes((red, green, blue)))
            continue

        if (b1 & QOI_MASK_2) == QOI_OP_LUMA:
            b2 = file_bytes[read_pos]
            read_pos += 1
            vg = ((b1 & 0x3f) % 256) - 32
            red = (px_value.red + vg - 8 + ((b2 >> 4) & 0x0f)) % 256
            green = (px_value.green + vg) % 256
            blue = (px_value.blue + vg - 8 + (b2 & 0x0f)) % 256
            px_value.update(bytes((red, green, blue)))
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
