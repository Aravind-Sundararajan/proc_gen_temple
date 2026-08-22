"""The document and its command stack.

What matters most is the invisible failure: a drag that leaves two hundred undo steps, a
listener that fires twice and rebuilds the mesh twice, a dirty flag that stays up after
the edit was undone.  None of those is loud, so each is pinned here.
"""

from pathlib import Path

import pytest

from mandapa.document import Command, Document, Macro, ReplaceDesign, SetLook, SetParams
from mandapa.io import load_temple
from mandapa.look import Look
from mandapa.params import MandapaParams

DATA = Path(__file__).parent / "data"
CAMERA = {"azimuth": -30.0, "elevation": 20.0, "distance": 250.0, "cx": 1.0, "cy": 2.0, "cz": 3.0}


@pytest.fixture
def doc() -> Document:
    return Document()


@pytest.fixture
def events(doc) -> list[str]:
    seen: list[str] = []
    doc.subscribe(seen.append)
    return seen


# ---- commands -----------------------------------------------------------------------------


def test_submit_undo_redo_round_trip(doc):
    doc.submit(SetParams({"pillars_x": 3}, text="Pillars"))
    assert doc.params.pillars_x == 3 and doc.can_undo and not doc.can_redo
    assert doc.undo_text == "Pillars" and doc.redo_text == ""
    assert doc.undo()
    assert doc.params.pillars_x == 4 and not doc.can_undo and doc.can_redo
    assert doc.redo_text == "Pillars"
    assert doc.redo()
    assert doc.params.pillars_x == 3 and doc.can_undo and not doc.can_redo


def test_undo_and_redo_on_empty_stacks_are_polite_no_ops(doc, events):
    assert doc.undo() is False and doc.redo() is False
    assert events == []


def test_a_new_submit_clears_the_redo_stack(doc):
    doc.submit(SetParams({"tiers": 2}))
    doc.undo()
    assert doc.can_redo
    doc.submit(SetParams({"tiers": 5}))
    assert not doc.can_redo and doc.redo_text == ""
    assert doc.params.tiers == 5


def test_the_commands_satisfy_the_protocol():
    for command in (
        SetParams({}),
        SetLook({}),
        ReplaceDesign(MandapaParams()),
        Macro([]),
    ):
        assert isinstance(command, Command)


def test_set_look_validates_before_touching_the_document(doc, events):
    with pytest.raises(ValueError):
        doc.submit(SetLook({"light_strength": -1.0}))
    assert doc.look == Look() and not doc.can_undo and not doc.dirty
    assert events == []


def test_set_params_with_an_unknown_field_leaves_no_trace(doc, events):
    with pytest.raises(TypeError):
        doc.submit(SetParams({"not_a_field": 1}))
    assert doc.params == MandapaParams() and not doc.can_undo and events == []


def test_replace_design_text_is_what_the_menu_says(doc):
    doc.submit(ReplaceDesign(MandapaParams(pillars_y=2), text="Apply preset 'Long hall'"))
    assert doc.undo_text == "Apply preset 'Long hall'"
    doc.undo()
    assert doc.redo_text == "Apply preset 'Long hall'"
    assert ReplaceDesign(MandapaParams()).text == "Replace design"


def test_replace_design_with_a_look_swaps_both_and_undoes_both(doc):
    doc.submit(ReplaceDesign(MandapaParams(pillars_y=2), Look(light_azimuth=10.0)))
    assert doc.params.pillars_y == 2 and doc.look.light_azimuth == 10.0
    doc.submit(SetLook({"ambient_strength": 0.5}))
    assert doc.look.ambient_strength == 0.5
    doc.undo()
    doc.undo()
    assert doc.params == MandapaParams() and doc.look == Look()


def test_replace_design_validates_the_look_before_touching_anything(doc, events):
    with pytest.raises(ValueError):
        doc.submit(ReplaceDesign(MandapaParams(tiers=1), Look(light_elevation=200.0)))
    assert doc.params == MandapaParams() and doc.look == Look()
    assert not doc.can_undo and not doc.dirty and events == []


def test_replace_design_without_a_look_leaves_the_look_alone(doc):
    doc.submit(SetLook({"rim_strength": 0.0}))
    seen: list[str] = []
    doc.subscribe(seen.append)
    doc.submit(ReplaceDesign(MandapaParams(tiers=1)))
    doc.undo()
    assert "look" not in seen
    assert doc.look.rim_strength == 0.0


# ---- coalescing and sealing -----------------------------------------------------------------


def test_a_drag_is_one_undo_step(doc):
    for value in (7.0, 8.0, 9.0):
        doc.submit(SetParams({"pillar_width": value}, coalesce="pillar_width"))
    assert doc.params.pillar_width == 9.0
    doc.undo()
    assert doc.params.pillar_width == 6.0 and not doc.can_undo
    doc.redo()
    assert doc.params.pillar_width == 9.0


def test_seal_starts_a_new_step(doc):
    for value in (7.0, 8.0):
        doc.submit(SetParams({"pillar_width": value}, coalesce="pillar_width"))
    doc.seal()
    doc.submit(SetParams({"pillar_width": 10.0}, coalesce="pillar_width"))
    doc.undo()
    assert doc.params.pillar_width == 8.0
    doc.undo()
    assert doc.params.pillar_width == 6.0 and not doc.can_undo


def test_a_different_key_starts_a_new_step(doc):
    doc.submit(SetParams({"pillar_width": 7.0}, coalesce="pillar_width"))
    doc.submit(SetParams({"tiers": 2}, coalesce="tiers"))
    doc.submit(SetParams({"tiers": 1}, coalesce="tiers"))
    doc.undo()
    assert doc.params.tiers == 3 and doc.params.pillar_width == 7.0
    doc.undo()
    assert doc.params.pillar_width == 6.0 and not doc.can_undo


def test_commands_without_a_key_never_coalesce(doc):
    doc.submit(SetParams({"tiers": 2}))
    doc.submit(SetParams({"tiers": 1}))
    doc.undo()
    assert doc.params.tiers == 2 and doc.can_undo


def test_undo_ends_a_coalescing_run(doc):
    doc.submit(SetParams({"tiers": 2}, coalesce="tiers"))
    doc.undo()
    doc.redo()
    doc.submit(SetParams({"tiers": 1}, coalesce="tiers"))
    doc.undo()
    assert doc.params.tiers == 2


def test_a_coalesced_run_remembers_the_earliest_before_of_every_key(doc):
    """One gesture that moves two fields (a proportional resize) undoes both."""
    doc.submit(SetParams({"footprint_x": 120.0}, coalesce="resize"))
    doc.submit(SetParams({"footprint_y": 130.0}, coalesce="resize"))
    doc.submit(SetParams({"footprint_x": 140.0}, coalesce="resize"))
    doc.undo()
    assert (doc.params.footprint_x, doc.params.footprint_y) == (100.0, 100.0)
    doc.redo()
    assert (doc.params.footprint_x, doc.params.footprint_y) == (140.0, 130.0)


def test_look_edits_coalesce_on_their_own_key_and_not_with_params(doc):
    doc.submit(SetParams({"tiers": 2}, coalesce="k"))
    doc.submit(SetLook({"light_azimuth": 1.0}, coalesce="k"))
    doc.submit(SetLook({"light_azimuth": 2.0}, coalesce="k"))
    doc.undo()
    assert doc.look.light_azimuth == -40.0 and doc.params.tiers == 2


# ---- macro ----------------------------------------------------------------------------------


def test_a_macro_is_one_undo_step(doc):
    doc.submit(
        Macro(
            [SetParams({"tiers": 2}), SetLook({"light_elevation": 10.0})],
            text="Apply preset",
        )
    )
    assert doc.params.tiers == 2 and doc.look.light_elevation == 10.0
    assert doc.undo_text == "Apply preset"
    doc.undo()
    assert doc.params.tiers == 3 and doc.look.light_elevation == 50.0 and not doc.can_undo
    doc.redo()
    assert doc.params.tiers == 2 and doc.look.light_elevation == 10.0


def test_a_macro_reverts_in_reverse_order(doc):
    doc.submit(Macro([SetParams({"tiers": 2}), SetParams({"tiers": 5})]))
    assert doc.params.tiers == 5
    doc.undo()
    assert doc.params.tiers == 3


def test_a_failing_macro_is_all_or_nothing(doc, events):
    with pytest.raises(ValueError):
        doc.submit(Macro([SetParams({"tiers": 2}), SetLook({"light_strength": -1.0})]))
    assert doc.params.tiers == 3 and not doc.can_undo and not doc.dirty


def test_a_macro_never_coalesces(doc):
    doc.submit(Macro([SetParams({"tiers": 2}, coalesce="t")]))
    doc.submit(Macro([SetParams({"tiers": 1}, coalesce="t")]))
    doc.undo()
    assert doc.params.tiers == 2 and doc.can_undo


# ---- dirty tracking -------------------------------------------------------------------------


def test_dirty_follows_the_design_through_undo_redo_and_save(doc, tmp_path):
    assert not doc.dirty
    doc.submit(SetParams({"tiers": 2}))
    assert doc.dirty
    doc.undo()
    assert not doc.dirty
    doc.redo()
    assert doc.dirty
    doc.save(tmp_path / "d.xml")
    assert not doc.dirty
    doc.undo()
    assert doc.dirty
    doc.redo()
    assert not doc.dirty


def test_dirty_is_by_value_not_by_history(doc):
    doc.submit(SetParams({"tiers": 2}))
    doc.submit(SetParams({"tiers": 3}))
    assert doc.can_undo and not doc.dirty


def test_mark_saved_clears_dirty_and_emits_history(doc, events):
    doc.submit(SetParams({"tiers": 2}))
    events.clear()
    doc.mark_saved()
    assert not doc.dirty and events == ["history"]


def test_the_camera_and_title_are_not_edits(doc, events):
    doc.camera = CAMERA
    doc.title = "A name"
    assert not doc.dirty and not doc.can_undo and events == []


# ---- listeners ------------------------------------------------------------------------------


def test_listeners_hear_each_event_once_per_step(doc, events):
    doc.submit(SetParams({"tiers": 2}))
    assert events == ["params", "history"]
    events.clear()
    doc.submit(ReplaceDesign(MandapaParams(tiers=1), Look(rim_strength=0.0)))
    assert events == ["params", "look", "history"]
    events.clear()
    doc.submit(Macro([SetParams({"tiers": 2}), SetParams({"tiers": 4}), SetLook({"rim_strength": 0.1})]))
    assert events == ["params", "look", "history"]
    events.clear()
    doc.undo()
    assert events == ["params", "look", "history"]
    events.clear()
    doc.redo()
    assert events == ["params", "look", "history"]


def test_listeners_see_the_finished_step(doc):
    seen = []

    def listener(event):
        seen.append((event, doc.can_undo, doc.undo_text, doc.params.tiers, doc.dirty))

    doc.subscribe(listener)
    doc.submit(SetParams({"tiers": 2}, text="Tiers"))
    assert seen == [("params", True, "Tiers", 2, True), ("history", True, "Tiers", 2, True)]


def test_unsubscribe_stops_delivery_and_is_idempotent(doc):
    seen: list[str] = []
    unsubscribe = doc.subscribe(seen.append)
    doc.submit(SetParams({"tiers": 2}))
    unsubscribe()
    unsubscribe()
    doc.submit(SetParams({"tiers": 1}))
    assert seen == ["params", "history"]


def test_a_listener_may_unsubscribe_itself_mid_delivery(doc):
    seen: list[str] = []

    def once(event):
        seen.append(event)
        stop()

    stop = doc.subscribe(once)
    doc.submit(SetParams({"tiers": 2}))
    assert seen == ["params"]


def test_the_path_setter_emits_path_and_updates_name(doc, events):
    doc.path = "x.xml"
    assert doc.name == "x" and doc.path == Path("x.xml") and events == ["path"]
    doc.path = None
    assert doc.name == "untitled"


# ---- revision ------------------------------------------------------------------------------


def test_revision_counts_design_changes_only(doc, tmp_path):
    assert doc.revision == 0
    doc.submit(SetParams({"tiers": 2}))
    assert doc.revision == 1
    doc.submit(SetLook({"rim_strength": 0.0}))
    assert doc.revision == 2
    doc.undo()
    assert doc.revision == 3
    doc.redo()
    assert doc.revision == 4
    doc.mark_saved()
    doc.path = "p.xml"
    doc.camera = CAMERA
    assert doc.revision == 4
    doc.submit(ReplaceDesign(MandapaParams(), Look()))
    assert doc.revision == 6


# ---- files ---------------------------------------------------------------------------------


def test_save_and_open_round_trip_including_camera_and_title(doc, tmp_path):
    doc.submit(SetParams({"pillars_x": 3}))
    doc.submit(SetLook({"light_azimuth": 12.0}))
    doc.title = "Three by four"
    path = tmp_path / "design.xml"
    assert doc.save(path, camera=CAMERA) == path
    assert doc.path == path and doc.name == "design" and doc.camera == CAMERA and not doc.dirty

    again = Document.open(path)
    assert again.params == doc.params and again.look == doc.look
    assert again.camera == CAMERA and again.title == "Three by four"
    assert again.path == path and again.name == "design"
    assert not again.dirty and not again.can_undo and not again.can_redo
    assert again.ignored == ()


def test_save_without_a_path_uses_the_documents_own(doc, tmp_path):
    with pytest.raises(ValueError, match="no path"):
        doc.save()
    path = tmp_path / "a.xml"
    doc.save(path)
    doc.submit(SetParams({"tiers": 1}))
    assert doc.save() == path
    assert load_temple(path).params.tiers == 1


def test_save_refuses_a_path_open_would_not_read_as_xml(doc, tmp_path):
    with pytest.raises(ValueError, match=".xml"):
        doc.save(tmp_path / "design.json")


def test_save_keeps_the_last_camera_when_none_is_given(doc, tmp_path):
    path = tmp_path / "a.xml"
    doc.save(path, camera=CAMERA)
    doc.save(path)
    assert load_temple(path).camera == CAMERA


def test_save_emits_path_then_history(doc, events, tmp_path):
    doc.save(tmp_path / "a.xml")
    assert events == ["path", "history"]


def test_save_writes_the_title_not_the_file_stem(doc, tmp_path):
    path = tmp_path / "stem.xml"
    doc.save(path)
    assert load_temple(path).name == ""


def test_open_a_legacy_json_is_untitled_but_keeps_the_stem_as_its_name():
    doc = Document.open(DATA / "legacy_params.json")
    assert doc.params == MandapaParams(pillars_x=3, pillars_y=2, footprint_x=90.5, roof_style="flat", steps=False)
    assert doc.look == Look() and doc.camera is None and doc.title == ""
    assert doc.path is None and doc.name == "legacy_params"
    assert doc.ignored == ("bogus",)
    assert not doc.dirty and not doc.can_undo
    with pytest.raises(ValueError, match="no path"):
        doc.save()


def test_open_a_legacy_json_written_by_the_cli(tmp_path):
    params = MandapaParams().randomized(9)
    params.save(tmp_path / "r.json")
    assert Document.open(tmp_path / "r.json").params == params


def test_open_the_hand_written_fixture():
    doc = Document.open(DATA / "hand_written_v1.xml")
    assert doc.params.footprint_x == 123.45678901234567
    assert doc.title == "Hand-written fixture" and doc.name == "hand_written_v1"
    assert doc.ignored == ("not_yet_a_param",)


def test_a_fresh_document_starts_clean_with_the_given_design():
    params, look = MandapaParams(tiers=1), Look(rim_strength=0.0)
    doc = Document(params, look, "some/where.xml")
    assert doc.params is params and doc.look is look
    assert doc.name == "where" and not doc.dirty and doc.revision == 0
