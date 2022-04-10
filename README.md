# Python QOI (py-qoi)
[QOI (Quite OK Image format)](https://github.com/phoboslab/qoi) is a new lossless image format that achieves compression rates close to PNG with a 20x-50x faster encoding.

The idea here is (of course) not to beat the original implementation's performance since it's written in C. Rather, the main goal of this project is to implement it the "pythonic" way, with minimal dependencies. 

There's a [python wrapper](https://github.com/kodonnell/qoi) around the original C implementation, which retains the C performance.

## Requirements

The only requirement besides Python 3.7+ is Pillow to load and save images in formats other than QOI. You may install it using pip or any virtual environment.

## Usage

To encode an image:

    python3 src/qoi.py -e -f image_file.png

The input image may be of any [pillow-supported format](https://pillow.readthedocs.io/en/stable/handbook/image-file-formats.html).
A file with name image_file.qoi will be saved on the same folder as the original image.

To decode a QOI image:

    python3 src/qoi.py -d -f image_file.qoi

A file with name image_file.png will be saved on the same folder as the original image.


    usage: qoi.py [-h] [-e] [-d] [-f FILE_PATH]
    optional arguments:
      -h, --help            show this help message and exit
      -e, --encode
      -d, --decode
      -f FILE_PATH, --file-path FILE_PATH
                            path to image file to be encoded or decoded
