# Stems — a multitrack player concept

**Concept mockup. Not affiliated with or endorsed by Spotify or any artist.**

A phone-friendly, Spotify-styled now-playing screen for an original demo song. A **Multitrack** button opens the stems the artist chose to share. Each stem can be muted, soloed and rebalanced without losing sync, because every part is a sample-aligned buffer on one playhead.

This is a design prototype you can click through. It is not the Spotify app, it does not use the Spotify logo, and the artist is fictional.

## Demo

Open the site, press play, then **Multitrack**.

- Mute or solo any stem. Solo **Backing vocals** and you will hear that they only enter on the chorus.
- Drag a stem's volume. **Reset mix** returns to the artist mix.
- Scrub the seek bar, or tap a waveform. Play and pause stay in time across all six stems.
- On a phone the artwork shrinks so the mixer fits under your thumb. On a wide screen the mixer sits beside the artwork.

## The song

**Glass Garden** by **Mira Ellison** (fictional). Original synthesis, not a recording of anyone else's music.

| | |
| --- | --- |
| Key | A minor |
| Tempo | 112 BPM |
| Length | about 71 seconds, 32 bars |
| Form | intro, verse, chorus, break, final chorus, fade |

Stems, all the same length and sample-aligned:

1. Lead vocal — a synthesized melody (an "ah" vowel, not a real singer)
2. Backing vocals — harmony, chorus only
3. Drums — kick, snare, clap, hats
4. Bass
5. Guitar — plucked chords
6. Keys — a soft pad

## Regenerate the audio

The stems are generated, not sampled.

```bash
python3 tools/render_stems.py
```

Requires Python 3 with numpy, and ffmpeg with libmp3lame. The script writes `audio/*.mp3` and `audio/peaks.json`.

## Nederlands

Dit is een concept van een multitrack-weergave: in de now-playing schakel je een nummer naar losse sporen (stems). De artiest bepaalt welke sporen beschikbaar zijn. Elk spoor kan aan of uit, solo, en in volume. De demo-song *Glass Garden* van de fictieve artiest Mira Ellison is zelf gemaakt (geen bestaand auteursrechtelijk beschermd materiaal) en speelt synchroon via de Web Audio API.

Conceptmockup. Niet gelieerd aan of goedgekeurd door Spotify of enige artiest.

## License

The player code and the original synthesized audio in this repository are released under the MIT license. See [LICENSE](LICENSE).
