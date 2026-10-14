#!/usr/bin/env python3
# Copyright 2026 Tadej Janež <tadej.j@nez.si>
# SPDX-License-Identifier: Apache-2.0

import argparse
import base64
import os
import subprocess
import sys
import tempfile

import yt_dlp
from mutagen import File as MutagenFile
from mutagen.flac import FLAC, Picture

def log(msg):
    print(f'[partita] {msg}', file=sys.stderr)


def base_opts(args):
    opts = {'quiet': False, 'noprogress': False}
    if args.js_runtime:
        name, _, path = args.js_runtime.partition(':')
        opts['js_runtimes'] = {name.lower(): {'path': path or None}}
    else:
        # The Python API doesn't read yt-dlp's config files, so enable runtimes here.
        # yt-dlp ranks enabled runtimes by its own fixed preference (deno, node, quickjs, bun),
        # regardless of their order in this dict, and falls back to the next installed one if a
        # runtime fails.
        opts['js_runtimes'] = {'deno': {}, 'node': {}}
    if args.remote_components:
        opts['remote_components'] = args.remote_components
    return opts


def download_and_split(url, args):
    opts = base_opts(args)
    opts.update({
        'format': 'ba[acodec=opus]/ba',
        'paths': {'home': args.output_dir},
        'outtmpl': {
            'default': '%(title)s/%(title)s.%(ext)s',
            'chapter': '%(title)s/%(section_number)02d - %(section_title)s.%(ext)s',
            'thumbnail': '%(title)s/cover.%(ext)s',
        },
        'writethumbnail': True,
        'postprocessors': [
            {'key': 'FFmpegThumbnailsConvertor', 'format': 'jpg', 'when': 'before_dl'},
            {'key': 'FFmpegExtractAudio', 'preferredcodec': 'opus'},
            # Split before any cover art is embedded: ffmpeg cannot copy
            # an Opus file that already carries a picture.
            {'key': 'FFmpegSplitChapters'},
        ],
    })
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return ydl.sanitize_info(info)


def video_stream(url, args):
    """Return (stream URL, HTTP headers) of a small progressive video format."""
    opts = base_opts(args)
    opts.update({
        'quiet': True,
        'format': 'bv[height<=480][protocol^=http]/bv[protocol^=http]/bv',
    })
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    return info.get('url'), info.get('http_headers') or {}


def grab_frame(stream_url, headers, at, dest):
    header_str = ''.join(f'{k}: {v}\r\n' for k, v in headers.items())
    cmd = ['ffmpeg', '-loglevel', 'error', '-y']
    if header_str:
        cmd += ['-headers', header_str]
    cmd += ['-ss', f'{at:.2f}', '-i', stream_url, '-frames:v', '1', '-q:v', '2', dest]
    return subprocess.run(cmd).returncode == 0 and os.path.exists(dest)


def picture_from(jpg_path):
    pic = Picture()
    pic.type = 3  # front cover
    pic.mime = 'image/jpeg'
    pic.desc = 'Cover'
    with open(jpg_path, 'rb') as fh:
        pic.data = fh.read()
    return pic


def tag_file(path, tags, cover_jpg):
    audio = MutagenFile(path)
    if audio is None:
        log(f'Cannot tag {path}: unsupported format')
        return
    if audio.tags is None:
        audio.add_tags()
    audio.tags.clear()
    for key, value in tags.items():
        if value:
            audio[key] = str(value)
    if cover_jpg and os.path.exists(cover_jpg):
        pic = picture_from(cover_jpg)
        if isinstance(audio, FLAC):
            audio.clear_pictures()
            audio.add_picture(pic)
        else:  # Ogg Opus / Vorbis
            audio['METADATA_BLOCK_PICTURE'] = [base64.b64encode(pic.write()).decode('ascii')]
    audio.save()


def main():
    p = argparse.ArgumentParser(
        description='Download YouTube audio, split it by chapters and tag each part.')
    p.add_argument('url')
    p.add_argument('-o', '--output-dir', default='.', help='parent folder (default: current)')
    p.add_argument('--same-cover', action='store_true',
                   help='use the video thumbnail for every part instead of per-chapter frames')
    p.add_argument('--frame-offset', type=float, default=15,
                   help='seconds into each chapter to grab the cover frame (default: 15)')
    p.add_argument('--keep-full', action='store_true', help='keep the unsplit full-length file')
    p.add_argument('--js-runtime', metavar='RUNTIME[:PATH]',
                   help='JavaScript runtime for YouTube, e.g. node; '
                        'default: deno, falling back to node')
    p.add_argument('--remote-components', action='append', metavar='COMPONENT',
                   help='e.g. ejs:github if yt-dlp-ejs is not installed')
    args = p.parse_args()

    info = download_and_split(args.url, args)
    downloads = info.get('requested_downloads') or [{}]
    full_path = downloads[0].get('filepath') or info.get('filepath')
    folder = os.path.dirname(full_path) if full_path else args.output_dir
    chapters = [c for c in (info.get('chapters') or []) if c.get('filepath')]

    thumb = os.path.join(folder, 'cover.jpg')
    if not os.path.exists(thumb):
        thumb = None

    album = info.get('album') or info.get('title')
    artist = (info.get('artist') or info.get('creator')
              or info.get('channel') or info.get('uploader'))
    year = (info.get('release_year') or (info.get('upload_date') or '')[:4]) or None
    common = {
        'album': album,
        'artist': artist,
        'albumartist': artist,
        'date': year,
        'comment': info.get('webpage_url'),
    }

    if not chapters:
        log('No chapters found; tagging the full file only.')
        tag_file(full_path, {**common, 'title': info.get('title')}, thumb)
        return

    stream = headers = None
    if not args.same_cover:
        try:
            stream, headers = video_stream(args.url, args)
        except Exception as err:  # fall back to the thumbnail
            log(f'Could not get a video stream for chapter covers ({err}); using the thumbnail.')

    total = len(chapters)
    with tempfile.TemporaryDirectory() as tmp:
        for n, ch in enumerate(chapters, 1):
            cover = thumb
            if stream:
                length = ch['end_time'] - ch['start_time']
                at = ch['start_time'] + min(args.frame_offset, length / 3)
                frame = os.path.join(tmp, f'{n:02d}.jpg')
                if grab_frame(stream, headers, at, frame):
                    cover = frame
                else:
                    log(f'Frame grab failed for chapter {n}; using the thumbnail.')
            tag_file(ch['filepath'], {
                **common,
                'title': ch.get('title') or f'Part {n}',
                'tracknumber': n,
                'tracktotal': total,
            }, cover)
            log(f'Tagged {os.path.basename(ch["filepath"])}')

    if full_path and os.path.exists(full_path) and not args.keep_full:
        os.remove(full_path)
    log(f'Done: {total} files in {folder}')


if __name__ == '__main__':
    main()
