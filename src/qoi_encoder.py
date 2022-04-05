import array

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


def write_end(array: bytearray, write_pos: int) -> int:
    array[write_pos:write_pos + 7] = bytearray(0)
    array[write_pos + 7] = 1
    return write_pos + 8


def encode_img(img: Image.Image, srgb: bool):
    width, height = img.size
    if img.mode == 'RGBA':
        alpha = True
    elif img.mode == 'RGB':
        alpha = False
    else:
        raise ValueError(f'Image of non-supported mode: {img.mode}')
    img_bytes = img.tobytes()
    output = encode(img_bytes, width, height, alpha, srgb)
    return output


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


if __name__ == '__main__':
    img = Image.open('jpeg_img.jpg')
    output = encode_img(img, True)
    with open('test.qoi', 'wb') as qoi:
        qoi.write(output)
