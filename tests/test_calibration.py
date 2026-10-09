from pathlib import Path

from latex_ia.calibration import infer_from_source
from latex_ia.models import Profile


def _write_tex(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "paper.tex"
    p.write_text(content)
    return p


def test_infer_ml_from_neurips_style(tmp_path):
    tex = _write_tex(tmp_path, r"\usepackage{neurips_2024} \begin{algorithm}")
    profile = infer_from_source(tex)
    assert profile.field == "machine-learning"
    assert profile.venue_type == "conference"


def test_infer_algorithms_heuristic(tmp_path):
    tex = _write_tex(tmp_path, r"\begin{algorithm} some content \end{algorithm}")
    profile = infer_from_source(tex)
    assert "algorithms-are-spec" in profile.spec_heuristics


def test_infer_labeled_equations_heuristic(tmp_path):
    tex = _write_tex(tmp_path, r"$\mathcal{L}$ \label{eq:loss}")
    profile = infer_from_source(tex)
    assert "labeled-equations-are-spec" in profile.spec_heuristics


def test_missing_file_returns_default():
    profile = infer_from_source(Path("/nonexistent/paper.tex"))
    assert isinstance(profile, Profile)
    assert profile.field == "unknown"


def test_keyword_field_detection(tmp_path):
    tex = _write_tex(
        tmp_path,
        "gradient loss neural train epoch batch " * 10,
    )
    profile = infer_from_source(tex)
    assert profile.field == "machine-learning"
