# partita

Download a YouTube video's audio, split it into one file per chapter, and tag each part so music
players show it as an album.

It's useful for long recordings like symphonies and concertos, where each chapter is a movement.

*Partita* is Italian for "a part" or "a division". In Baroque music it names a piece made of
several movements, such as Bach's partitas for solo violin. This tool does the same thing with a
long recording: it divides it into its parts.

```
Vivaldi： The Four Seasons/
├── 01 - Spring (La primavera), RV 269.opus
├── 02 - Summer (L'estate), RV 315.opus
├── 03 - Autumn (L'autunno), RV 293.opus
├── 04 - Winter (L'inverno), RV 297.opus
└── cover.jpg
```

## What it does

- Downloads the best Opus audio stream and remuxes it into an `.opus` (Ogg) file, without
  re-encoding.
- Splits the audio at the video's chapters, using [yt-dlp](https://github.com/yt-dlp/yt-dlp)'s
  chapter splitting.
- Tags every part with Vorbis comments: `title` (chapter name), `album` (video title), `artist`,
  `albumartist`, `tracknumber`, `tracktotal`, `date`, and the source URL in `comment`.
- Embeds a cover in every part, keeping the original aspect ratio. Each cover is a frame from the
  video a few seconds into that chapter, so the parts don't all share one image. With
  `--same-cover`, every part gets the video thumbnail instead.

## Requirements

- Python 3.11+
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) (Python package)
- [mutagen](https://github.com/quodlibet/mutagen)
- [ffmpeg](https://ffmpeg.org) and ffprobe
- For YouTube: [yt-dlp-ejs](https://github.com/yt-dlp/ejs) and a JavaScript runtime, either
  [deno](https://deno.land) or Node.js. See [JavaScript runtimes](#javascript-runtimes).

On Fedora:

```bash
sudo dnf install yt-dlp python3-mutagen
```

On Fedora 44 and later, `yt-dlp` pulls in `python3-yt-dlp-ejs`, which in turn requires Node.js,
so nothing else is needed for YouTube.

For ffmpeg, use either the full `ffmpeg` from RPM Fusion or Fedora's `ffmpeg-free`.

## Usage

```bash
./partita.py 'https://www.youtube.com/watch?v=VIDEO_ID' -o ~/Music
```

| Option | Description |
|---|---|
| `-o, --output-dir DIR` | Parent folder for the album folder (default: current directory) |
| `--same-cover` | Use the video thumbnail as the cover for every part |
| `--frame-offset SECONDS` | How far into each chapter to grab the cover frame (default: 15) |
| `--keep-full` | Keep the unsplit full-length file |
| `--js-runtime RUNTIME[:PATH]` | Use only this JavaScript runtime, e.g. `node` or `quickjs` |
| `--remote-components COMPONENT` | Download yt-dlp's JavaScript solver, e.g. `ejs:github` |

If the video has no chapters, the script tags the full file and leaves it unsplit.

### JavaScript runtimes

YouTube hides its stream URLs behind JavaScript challenges. yt-dlp solves them with scripts from
[yt-dlp-ejs](https://github.com/yt-dlp/ejs), run by a separate JavaScript runtime.

By default partita enables both deno and Node.js. yt-dlp then ranks the enabled runtimes by its
own fixed preference (deno, then Node.js, then QuickJS, then Bun), skips any that aren't installed,
and tries the rest in that order. So deno is used when both are installed, and Node.js takes over
if deno is missing or fails.

`--js-runtime` overrides this and enables only the runtime you name. For example, `--js-runtime
node` uses Node.js even when deno is installed, and `--js-runtime deno:/opt/deno/bin/deno` points
to a specific binary.

`--remote-components` is only needed when the `yt-dlp-ejs` package isn't installed; yt-dlp then
downloads the solver scripts from the named source.

## Notes

- The script splits the audio *before* embedding covers. ffmpeg can't stream-copy an Opus file
  that already contains a picture, so running yt-dlp's `--embed-thumbnail` and `--split-chapters`
  together fails.
- Some players cache one cover per album and show the first track's cover on every track, even
  when each file has its own. [Amberol](https://gitlab.gnome.org/World/amberol) does this; see
  [issue #352](https://gitlab.gnome.org/World/amberol/-/issues/352).

## License

[Apache License 2.0](LICENSE)
