"""The interrupted full run must retain expensive batches across restarts."""
import importlib.util
from pathlib import Path
import numpy as np
import pytest
import torch

SPEC = importlib.util.spec_from_file_location('community_resume', Path(__file__).with_name('resume_community.py'))
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def test_batch_restart_reuses_only_identical_waveform_and_mask_and_rejects_corruption(tmp_path):
    calls = []
    def model(waveforms, masks):
        calls.append(True)
        return np.asarray([[7., 11.]], dtype=np.float32)
    waveforms, masks = torch.ones((1, 1, 4)), torch.ones((1, 2))
    first = runner.CachedEmbedding(model, tmp_path)
    np.testing.assert_array_equal(first(waveforms, masks=masks), [[7., 11.]])
    restarted = runner.CachedEmbedding(model, tmp_path)
    np.testing.assert_array_equal(restarted(waveforms, masks=masks), [[7., 11.]])
    assert len(calls) == 1 and restarted.reused == 1
    restarted(waveforms*2, masks=masks)
    restarted(waveforms, masks=masks*0)
    assert len(calls) == 3
    # Alter every file so the test cannot accidentally choose a different key.
    for path in tmp_path.glob('*.npy'):
        path.write_bytes(b'corrupt')
    with pytest.raises(RuntimeError, match='integrity mismatch'):
        restarted(waveforms, masks=masks)
    assert len(calls) == 3
