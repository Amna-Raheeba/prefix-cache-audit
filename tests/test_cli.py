"""Tests for the command line interface."""

import os

from prefix_cache_audit.cli import main


def test_default_command_is_demo(capsys):
    assert main([]) == 0
    out = capsys.readouterr().out
    assert "Prefix Cache Audit -- demo report" in out
    assert "mixed_kitchen_sink-3" in out


def test_demo_with_family_and_size(capsys):
    assert main(["demo", "--family", "stable", "--seed", "1",
                 "--requests", "4"]) == 0
    out = capsys.readouterr().out
    assert "stable-1" in out
    assert "Breaker pairs: 0 of 3" in out


def test_evaluate_command_writes_results(tmp_path, capsys):
    out_dir = str(tmp_path / "results")
    assert main(["evaluate", "--out", out_dir, "--seeds", "1"]) == 0
    assert os.path.exists(os.path.join(out_dir, "evaluation.json"))
    assert os.path.exists(os.path.join(out_dir, "evaluation.csv"))
    assert os.path.exists(os.path.join(out_dir,
                                       "evaluation_summary.md"))
    out = capsys.readouterr().out
    assert "Breaker detection" in out
