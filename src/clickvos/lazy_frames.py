"""Bounded JPEG loading with the pinned SAM2 eager loader's exact preprocessing."""
from collections import OrderedDict
from pathlib import Path
import tempfile

import torch


class BoundedVideoFrames:
    def __init__(self, frames: list[Path], image_size: int, capacity: int = 8):
        if not frames or capacity < 1:
            raise ValueError("nonempty frames and positive capacity required")
        self.frames = tuple(frames)
        self.image_size = image_size
        self.capacity = capacity
        self.cache = OrderedDict()
        self.mean = torch.tensor((.485, .456, .406), dtype=torch.float32)[:, None, None]
        self.std = torch.tensor((.229, .224, .225), dtype=torch.float32)[:, None, None]

    def __len__(self):
        return len(self.frames)

    def __getitem__(self, index: int):
        if not isinstance(index, int) or not 0 <= index < len(self):
            raise IndexError(index)
        if index in self.cache:
            self.cache.move_to_end(index)
            return self.cache[index]
        from sam2.utils.misc import _load_img_as_tensor
        image, _, _ = _load_img_as_tensor(str(self.frames[index]), self.image_size)
        # Eager SAM2 assigns the helper's float64 image into a float32 tensor BEFORE
        # normalization. Normalize in that same order, including on CPU offload.
        image = image.to(dtype=torch.float32)
        image.sub_(self.mean).div_(self.std)
        self.cache[index] = image
        if len(self.cache) > self.capacity:
            self.cache.popitem(last=False)
        return image


def init_bounded_state(predictor, config, frames: list[Path]):
    if not config.model.offload_video_to_cpu:
        raise ValueError("bounded frames require CPU video offload")
    with tempfile.TemporaryDirectory(prefix="clickvos-init-") as folder:
        (Path(folder) / "00000.jpg").symlink_to(frames[0].resolve())
        state = predictor.init_state(folder, offload_video_to_cpu=True,
                                     offload_state_to_cpu=config.model.offload_state_to_cpu)
    state["images"] = BoundedVideoFrames(frames, predictor.image_size)
    state["num_frames"] = len(frames)
    return state
