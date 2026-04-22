"""Segmentation backend adapter layer."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from .config import PipelineConfig
from .segment import ComponentProposal, ImageInput, propose_components


class SegmentationBackend(Protocol):
    """Common interface for component proposal backends."""

    name: str

    def propose(
        self,
        image_input: ImageInput,
        output_dir: Path,
        cfg: PipelineConfig | None = None,
        text_image_input: ImageInput | None = None,
    ) -> list[ComponentProposal]:
        """Return component proposals for a pipeline stage."""


class SamBackendUnavailableError(RuntimeError):
    """Raised when a SAM-style backend is selected before installation."""


class OpenCvSegmentationBackend:
    """Default segmentation backend using the existing OpenCV proposal path."""

    name = 'opencv'

    def propose(
        self,
        image_input: ImageInput,
        output_dir: Path,
        cfg: PipelineConfig | None = None,
        text_image_input: ImageInput | None = None,
    ) -> list[ComponentProposal]:
        return propose_components(image_input, output_dir, cfg=cfg, text_image_input=text_image_input)


class SamSegmentationBackend:
    """Placeholder for future SAM-style segmentation integration."""

    def __init__(self, name: str) -> None:
        self.name = name

    def propose(
        self,
        image_input: ImageInput,
        output_dir: Path,
        cfg: PipelineConfig | None = None,
        text_image_input: ImageInput | None = None,
    ) -> list[ComponentProposal]:
        raise SamBackendUnavailableError(
            f"Segmentation backend '{self.name}' is not available in this build. "
            "Use segmentation_backend='opencv'."
        )


def get_segmentation_backend(name: str) -> SegmentationBackend:
    """Resolve a segmentation backend by name."""

    if name == 'opencv':
        return OpenCvSegmentationBackend()
    if name in {'sam_local', 'sam_api'}:
        return SamSegmentationBackend(name)
    raise ValueError(f'Unsupported segmentation backend: {name}')