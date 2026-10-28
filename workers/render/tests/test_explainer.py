"""Research explainer track (M3) — scene plan, honesty rules, ASS, ffmpeg argv."""

import pytest

import explainer
from explainer import (base_video_cmd, cards_ass, eligible_brief, plan_scenes,
                       scene_manifest)

OFFER = {"id": "o1", "title": "Sleep-spindle memory study"}


def _brief(**extra):
    brief = {
        "id": "b1", "version": 2, "content_type": "explainer",
        "viewer_question": "Does a 20-minute nap really boost recall?",
        "angle": "What the preprint shows — and what it does not",
        "limitations": "Single lab, 48 participants, not peer reviewed.",
        "claims": [
            {"id": "c1", "claim_text": "Participants recalled 12% more words.",
             "claim_class": "author_reported", "status": "supported",
             "source_owner": "arXiv", "source_date": "2026-10-20",
             "scope": "n=48, ages 18-30"},
            {"id": "c2", "claim_text": "The effect lasts a week.",
             "claim_class": "author_reported", "status": "unknown",
             "source_url": "https://example.org/paper"},
            {"id": "c3", "claim_text": "Naps replace sleep entirely.",
             "claim_class": "editorial_analysis", "status": "contradicted"},
        ],
    }
    brief.update(extra)
    return brief


def test_only_current_explainer_briefs_are_eligible():
    assert eligible_brief({"current": _brief()})["id"] == "b1"
    assert eligible_brief({"current": _brief(content_type="tested_tutorial")}) is None
    assert eligible_brief({"current": None}) is None
    assert eligible_brief(None) is None
    empty = _brief(viewer_question=None, claims=[{"claim_text": "x y z", "status": "contradicted"}])
    assert eligible_brief({"current": empty}) is None, "nothing honest left to show"


def test_contradicted_claims_are_never_shown_and_unknown_is_labelled():
    scenes = plan_scenes(OFFER, _brief())
    kinds = [s["kind"] for s in scenes]
    assert kinds == ["title", "claim", "claim", "close"]
    shown = " ".join(s.get("body", "") for s in scenes)
    assert "replace sleep" not in shown
    unknown = next(s for s in scenes if s["claim_ids"] == ["c2"])
    assert "not yet independently confirmed" in unknown["heading"]
    supported = next(s for s in scenes if s["claim_ids"] == ["c1"])
    assert supported["heading"] == "The authors report"
    assert supported["source"] == "Source: arXiv · 2026-10-20"
    assert unknown["source"] == "Source: example.org"
    assert scenes[-1]["heading"] == "Limitations"


def test_permitted_wording_wins_over_raw_claim_text():
    brief = _brief()
    brief["claims"][0]["permitted_wording"] = "In this study, recall rose about 12%."
    body = plan_scenes(OFFER, brief)[1]["body"]
    assert body == "In this study, recall rose about 12%."


def test_timing_fills_the_measured_narration_with_a_floor_per_scene():
    scenes = plan_scenes(OFFER, _brief(), total_s=40.0)
    assert scenes[0]["start"] == 0.0
    assert scenes[-1]["end"] == pytest.approx(40.0, abs=0.01)
    for a, b in zip(scenes, scenes[1:]):
        assert a["end"] == pytest.approx(b["start"], abs=0.002), "contiguous"
    default = plan_scenes(OFFER, _brief())
    assert all(s["end"] - s["start"] == explainer.DEFAULT_SCENE_S for s in default)


def test_ass_escapes_override_blocks_from_claim_text():
    brief = _brief()
    brief["claims"][0]["claim_text"] = r"Evil {\pos(0,0)\fs400} injection"
    ass = cards_ass(plan_scenes(OFFER, brief))
    assert "{\\pos" not in ass and "\\fs400" not in ass
    assert "(/pos(0,0)/fs400) injection" in ass
    assert "PlayResX: 1920" in ass and "\\fad(350,350)" in ass


def test_base_video_is_mid_tone_with_motion_and_relative_paths():
    cmd = base_video_cmd("assets/explainer/cards.ass", "assets/explainer/base.mp4", 12.5)
    joined = " ".join(cmd)
    assert "color=c=0x1e2638:s=1920x1080:r=30:d=12.500" in joined
    assert "noise=alls=4:allf=t" in joined, "temporal grain keeps freeze QC honest"
    assert "subtitles=assets/explainer/cards.ass" in joined
    assert cmd[-1] == "assets/explainer/base.mp4" and "-an" in cmd
    with pytest.raises(ValueError):
        base_video_cmd("C:/abs/cards.ass", "out.mp4", 5)


def test_scene_manifest_is_hashed_and_deterministic():
    scenes = plan_scenes(OFFER, _brief(), total_s=30)
    a = scene_manifest("o1", _brief(), scenes)
    b = scene_manifest("o1", _brief(), plan_scenes(OFFER, _brief(), total_s=30))
    assert a["sha256"] == b["sha256"] and len(a["sha256"]) == 64
    assert a["brief_version"] == 2 and a["track"] == "explainer"
    assert {cid for s in a["scenes"] for cid in s["claim_ids"]} == {"c1", "c2"}


def test_vertical_cards_and_base_are_composed_natively():
    scenes = plan_scenes(OFFER, _brief())
    ass = cards_ass(scenes, "vertical")
    assert "PlayResX: 1080" in ass and "PlayResY: 1920" in ass
    assert "Style: Body,DejaVu Sans,66" in ass or ",66," in ass, "larger type on 9:16"
    cmd = base_video_cmd("c.ass", "b.mp4", 5, "vertical")
    assert "s=1080x1920" in " ".join(cmd)


def test_page_scenes_are_overlaid_with_motion_and_fades():
    cmd = base_video_cmd("c.ass", "b.mp4", 20, "landscape",
                         pages=[("assets/explainer/pages/p1.png", 4.0, 10.0)])
    joined = " ".join(cmd)
    assert "-loop 1 -framerate 30 -t 6.000 -i assets/explainer/pages/p1.png" in joined, \
        "the screenshot is looped only for its own scene"
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert "scale=1612:906" in graph
    assert "zoompan=z='min(1.05,1+0.05*on/180)'" in graph, "slow push-in, no `t` in scale"
    assert "setpts=PTS-STARTPTS+4.000/TB" in graph, "placed at the scene start"
    assert "fade=t=in:st=0" in graph and "alpha=1" in graph
    assert "eval=frame" not in graph
    assert "enable='between(t,4.000,10.000)'" in graph
    assert graph.endswith("[bg1]subtitles=c.ass[vout]")
    assert cmd[cmd.index("-map") + 1] == "[vout]"
    with pytest.raises(ValueError):
        base_video_cmd("c.ass", "b.mp4", 5, pages=[("C:/abs/p.png", 0, 2)])
