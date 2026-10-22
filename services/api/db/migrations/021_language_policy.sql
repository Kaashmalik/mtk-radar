-- v0.27: language policy for English-first packaging.
--
-- Professional channels keep the public package in one language even when the
-- voiceover is local. Defaults:
--   metadata (title/description/hashtags/detail copy) → English
--   on-screen captions                               → English
--   narration (spoken voiceover)                     → English only
--
-- Urdu voiceover is opt-in: add "ur" to narration_languages in Settings.
-- Script text can still be generated per language; the policy controls what a
-- viewer hears and which package copy is published.

INSERT INTO settings (key, value, updated_by)
VALUES (
  'language_policy',
  '{
    "metadata_language": "en",
    "captions_language": "en",
    "narration_languages": ["en"],
    "default_narration_language": "en"
  }'::jsonb,
  'migration:021'
)
ON CONFLICT (key) DO NOTHING;
