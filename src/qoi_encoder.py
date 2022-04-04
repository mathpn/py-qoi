import array

from PIL import Image


def hash_pixel(values) -> int:
    r, g, b, a = values
    return (r * 3 + g * 5 + b * 7 + a * 11) % 64

# chunk tags
QOI_OP_INDEX = 0x00  # 00xxxxxx
QOI_OP_DIFF = 0x40  # 01xxxxxx
QOI_OP_LUMA = 0x80  # 10xxxxxx
QOI_OP_RUN = 0xc0  # 11xxxxxx
QOI_OP_RGB = 0xfe  # 11111110
QOI_OP_RGBA = 0xff  # 11111111
QOI_MASK_2 = 0xc0  # 11000000


def main(img_path: str):
    img = Image.open(img_path)
    size = img.size[0] * img.size[1]
    if img.mode == 'RGBA':
        alpha = True
    elif img.mode == 'RGB':
        alpha = False
    else:
        raise ValueError(f'Image of non-supported mode: {img.mode}')
    pixel_data = img.getdata()
    out_array = bytearray(14 + size * (5 if alpha else 4) + 8)
    hash_array = [array.array('h', [0] * 4) for _ in range(64)]
    # TODO write header
    run = 0
    prev_px_value = array.array('h', [0, 0, 0, 255])
    px_value = array.array('h', [0, 0, 0, 255])
    write_pos: int = 14
    for i, px in enumerate(pixel_data):
        prev_px_value[:] = px_value

        if len(px) == 4:
            px_value = array.array('h', px)
        else:
            for i in range(3):
                px_value[i] = px[i]

        if px_value == prev_px_value:
            run += 1
            if run == 62 or i == size:
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

    # TODO final padding
    return out_array[0:write_pos]


if __name__ == '__main__':
    main('jpeg_img.jpg')
