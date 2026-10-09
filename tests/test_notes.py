from __future__ import annotations

from latex_ia.notes import NoteEntry, find_prior_answer, load_notes, save_note


class TestFindPriorAnswer:
    def test_empty_notes_returns_none(self):
        assert find_prior_answer("What is the learning rate?", []) is None

    def test_exact_match_returns_entry(self):
        note = NoteEntry(question="What is the learning rate?", answer="0.001", unit_id="impl:opt")
        result = find_prior_answer("What is the learning rate?", [note])
        assert result is note

    def test_similar_question_above_threshold(self):
        note = NoteEntry(
            question="What is the learning rate schedule?",
            answer="cosine decay",
            unit_id="impl:opt",
        )
        result = find_prior_answer("What is the learning rate decay?", [note])
        assert result is note

    def test_dismissed_entry_not_returned(self):
        note = NoteEntry(
            question="What is the batch size?",
            answer="128",
            unit_id="impl:train",
            dismissed=True,
        )
        assert find_prior_answer("What is the batch size?", [note]) is None

    def test_empty_answer_not_returned(self):
        note = NoteEntry(question="What is the batch size?", answer="", unit_id="impl:train")
        assert find_prior_answer("What is the batch size?", [note]) is None

    def test_below_threshold_returns_none(self):
        note = NoteEntry(
            question="Describe the architecture of the decoder.",
            answer="transformer",
            unit_id="impl:dec",
        )
        # "learning rate" shares almost no words with "architecture of the decoder"
        assert find_prior_answer("What is the learning rate?", [note]) is None

    def test_best_match_returned_among_multiple(self):
        weak = NoteEntry(question="What optimizer is used?", answer="adam", unit_id="u1")
        strong = NoteEntry(
            question="What is the learning rate for the optimizer?",
            answer="1e-3",
            unit_id="u2",
        )
        result = find_prior_answer("What is the learning rate for the optimizer?", [weak, strong])
        assert result is strong


class TestSaveAndLoad:
    def test_save_and_reload(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        save_note("What is d_model?", "512", "impl:enc")
        notes = load_notes()
        assert len(notes) == 1
        assert notes[0].question == "What is d_model?"
        assert notes[0].answer == "512"

    def test_update_existing_entry(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        save_note("What is d_model?", "512", "impl:enc")
        save_note("What is d_model?", "768", "impl:enc")
        notes = load_notes()
        assert len(notes) == 1
        assert notes[0].answer == "768"

    def test_dismissed_flag(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        save_note("Irrelevant question?", "", "impl:enc", dismissed=True)
        notes = load_notes()
        assert notes[0].dismissed is True
