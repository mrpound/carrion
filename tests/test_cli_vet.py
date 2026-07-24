from unittest.mock import patch

from carrion.config import Config
from carrion.extract import ResumeData, ExperienceRow
from tests.test_cli_lookup import _lookup_result

SAMPLE = ("Jane Doe\nAtlanta, GA\njane@example.com | (404) 555-1234\n"
          "linkedin.com/in/janedoe\n")


def test_main_vet_runs(capsys, tmp_path, monkeypatch):
    from carrion import cli
    cfg = Config("AC", "tok", "sk-ant")
    resume = ResumeData(name="Jane Doe", location="Atlanta, GA",
        experience=[ExperienceRow(company="Acme", role="Eng",
                                  start="2020", end="2023")])
    with patch.object(cli, "load_config", return_value=cfg), \
         patch.object(cli, "extract_text", return_value=SAMPLE), \
         patch.object(cli, "extract_resume", return_value=resume), \
         patch.object(cli, "lookup", return_value=_lookup_result()):
        monkeypatch.chdir(tmp_path)
        rc = cli.main_vet(["resume.pdf"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Jane Doe" in out
    assert "Acme" in out
    assert "COMPOSITE VERDICT" in out


def test_main_vet_no_phone_skips_lookup(capsys, tmp_path, monkeypatch):
    from carrion import cli
    cfg = Config("AC", "tok", "sk-ant")
    with patch.object(cli, "load_config", return_value=cfg), \
         patch.object(cli, "extract_text", return_value="No number here"), \
         patch.object(cli, "extract_resume", return_value=ResumeData()):
        monkeypatch.chdir(tmp_path)
        rc = cli.main_vet(["resume.pdf"])
    assert rc == 0
    assert "N/A" in capsys.readouterr().out


def test_main_vet_directory_batch(capsys, tmp_path):
    from carrion import cli
    cfg = Config("AC", "tok", "sk-ant")
    (tmp_path / "a.pdf").write_text("x")
    (tmp_path / "b.pdf").write_text("x")
    resume = ResumeData(name="Jane Doe", location="Atlanta, GA",
        experience=[ExperienceRow(company="Acme", role="Eng",
                                  start="2020", end="2023")])
    with patch.object(cli, "load_config", return_value=cfg), \
         patch.object(cli, "extract_text", return_value=SAMPLE), \
         patch.object(cli, "extract_resume", return_value=resume), \
         patch.object(cli, "lookup", return_value=_lookup_result()):
        rc = cli.main_vet([str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert out.count("COMPOSITE VERDICT") == 2
    log_lines = (tmp_path / "vetting-log.tsv").read_text().splitlines()
    assert log_lines[0].startswith("timestamp\t")
    assert len(log_lines) == 3  # header + 2 rows


def test_main_vet_directory_skips_bad_pdf(capsys, tmp_path):
    from carrion import cli
    cfg = Config("AC", "tok", "sk-ant")
    (tmp_path / "good.pdf").write_text("x")
    (tmp_path / "zbad.pdf").write_text("x")

    def fake_text(path):
        return "" if path.endswith("zbad.pdf") else SAMPLE

    resume = ResumeData(name="Jane Doe", location="Atlanta, GA", experience=[])
    with patch.object(cli, "load_config", return_value=cfg), \
         patch.object(cli, "extract_text", side_effect=fake_text), \
         patch.object(cli, "extract_resume", return_value=resume), \
         patch.object(cli, "lookup", return_value=_lookup_result()):
        rc = cli.main_vet([str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert out.count("COMPOSITE VERDICT") == 1
    assert "zbad.pdf" in out


def test_main_vet_empty_directory(capsys, tmp_path):
    from carrion import cli
    cfg = Config("AC", "tok", None)
    with patch.object(cli, "load_config", return_value=cfg):
        rc = cli.main_vet([str(tmp_path)])
    assert rc == 2
    assert "No PDF" in capsys.readouterr().out
