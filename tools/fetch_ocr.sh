#!/bin/sh
# Download Tesseract OCR into .cache/ocr without installing anything system-wide.
# Debian's packages are downloaded (no root needed) and unpacked locally; the
# high-accuracy Arabic model comes from tesseract-ocr/tessdata_best.
#
# Run it:  LD_LIBRARY_PATH=.cache/ocr/root/usr/lib/x86_64-linux-gnu \
#          TESSDATA_PREFIX=.cache/ocr/tessdata \
#          .cache/ocr/root/usr/bin/tesseract page.png out -l ara --psm 4
set -e
cd "$(dirname "$0")/.."
mkdir -p .cache/ocr/debs .cache/ocr/tessdata
cd .cache/ocr/debs
apt download tesseract-ocr libtesseract5 libleptonica6
for f in *.deb; do dpkg-deb -x "$f" ../root; done
cd ..
cp -r root/usr/share/tesseract-ocr/5/tessdata/configs root/usr/share/tesseract-ocr/5/tessdata/tessconfigs tessdata/
curl -sSL -o tessdata/ara.traineddata https://github.com/tesseract-ocr/tessdata_best/raw/main/ara.traineddata
LD_LIBRARY_PATH="$PWD/root/usr/lib/x86_64-linux-gnu" root/usr/bin/tesseract --version | head -1
