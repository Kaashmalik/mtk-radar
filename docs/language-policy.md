# Language & packaging policy

> **English-first packaging, opt-in local voiceover.**

MTK RADAR separates three things that are easy to conflate:

| Layer | What it controls | Default |
|---|---|---|
| **Voiceover** | the language the narrator speaks | English only |
| **Package copy** | title, description, hashtags, cover text and CTA | English |
| **On-screen captions** | the burned-in/SRT caption style and language | English |

This matches the common South Asian YouTube pattern: an English title,
description and thumbnail with a local-language voiceover. The public package
stays searchable and shareable; the viewer can still hear their preferred
language.

## Defaults

`settings.language_policy` is seeded by migration `021_language_policy.sql`:

```json
{
  "metadata_language": "en",
  "captions_language": "en",
  "narration_languages": ["en"],
  "default_narration_language": "en"
}
```

`urdu_voiceover_enabled` is computed by the API and is `false` until `ur` is
added to `narration_languages`.

## Enabling Urdu voiceover

Open **Settings → Language policy** and tick **Enable Urdu voiceover**. This
allows the renderer to produce an Urdu-spoken version of a video. It does not
change the title, description, hashtags, cover or on-screen captions — the
settings UI keeps those English and only exposes the spoken language.

The API enforces the same policy:

- Content Studio rejects a generation request for a disabled voiceover
  language.
- The renderer skips disabled languages and renders only allowed ones.
- Render registration rejects a disabled language.
- Scheduling rejects a disabled voiceover language.
- `GET /render-candidates` only queues allowed languages.

Enable Urdu before generating an Urdu script or rendering an Urdu version.
No worker can speak a disabled language, even if an old queue row still points
at it.

## On-screen captions

Captions are generated deterministically from the capture step log, so they
describe what the viewer is actually seeing. The caption generator:

- splits long steps into readable ~84-character chunks instead of one
  eight-second wall of text;
- keeps timing monotonic and honours real step timestamps;
- uses **DejaVu Sans** for English by default (installed on the render host);
- uses larger type, safe margins and smart wrapping for 9:16;
- can use a different installed font via `MTK_CAPTION_FONT` (for example
  `MTK_CAPTION_FONT=Inter`).

SRT/VTT files are still written for platform-native upload. The ASS file is
the burned-in version.

## API

```text
GET /settings/language_policy
PUT /settings/language_policy
```

`PUT` body:

```json
{
  "value": {
    "metadata_language": "en",
    "captions_language": "en",
    "narration_languages": ["en", "ur"],
    "default_narration_language": "ur"
  }
}
```

Validation rules:

- `metadata_language`, `captions_language` and every narration language must
  be `en` or `ur`;
- `narration_languages` must be a non-empty list and is deduplicated;
- `default_narration_language` must be one of the enabled narration languages.

## Safety

Language policy does not weaken any truth or safety gate. Human approval,
evidence/domain checks, script-hash binding, redaction review, expiry and
correction auto-pause all still apply to every language. An Urdu voiceover is
a production option, not a shortcut around verification.
