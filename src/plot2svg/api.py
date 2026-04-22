"""Stable top-level API for external tool integrations."""

from __future__ import annotations

import base64
import json
from pathlib import Path
import shutil
from typing import Any
from uuid import uuid4

from .config import PipelineConfig
from .pipeline import run_pipeline


class Plot2SvgEngine:
    """Tool-oriented wrapper around the core Plot2SVG pipeline."""

    def __init__(
        self,
        *,
        execution_profile: str = 'balanced',
        enhancement_mode: str = 'auto',
        segmentation_backend: str = 'opencv',
        template_optimization: str = 'deterministic',
        emit_layout_template: bool = True,
        temp_root: str | Path | None = None,
    ) -> None:
        self.execution_profile = execution_profile
        self.enhancement_mode = enhancement_mode
        self.segmentation_backend = segmentation_backend
        self.template_optimization = template_optimization
        self.emit_layout_template = emit_layout_template
        self.temp_root = Path(temp_root) if temp_root is not None else Path('outputs/_api_tmp')

    def process_image(
        self,
        *,
        image_path: str | Path | None = None,
        image_base64: str | None = None,
        output_dir: str | Path | None = None,
    ) -> dict[str, Any]:
        """Process one image and return standardized SVG + scene graph output."""

        temp_input_dir: Path | None = None
        temp_output_dir: Path | None = None
        resolved_output_dir: Path | None = None
        try:
            resolved_input, temp_input_dir = self._resolve_input(image_path=image_path, image_base64=image_base64)
            if output_dir is None:
                temp_output_dir = self._make_temp_dir('plot2svg-out')
                resolved_output_dir = temp_output_dir
            else:
                resolved_output_dir = Path(output_dir)
            cfg = PipelineConfig(
                input_path=resolved_input,
                output_dir=resolved_output_dir,
                execution_profile=self.execution_profile,
                enhancement_mode=self.enhancement_mode,
                segmentation_backend=self.segmentation_backend,
                template_optimization=self.template_optimization,
                emit_layout_template=self.emit_layout_template,
            )
            artifacts = run_pipeline(cfg)
            scene_graph = self._safe_read_json(artifacts.scene_graph_path)
            svg_content = self._safe_read_text(artifacts.final_svg_path)
            return {
                'status': 'ok',
                'svg_content': svg_content,
                'scene_graph': scene_graph,
                'error': None,
                'artifacts': {
                    'output_dir': str(resolved_output_dir),
                    'scene_graph_path': str(artifacts.scene_graph_path),
                    'final_svg_path': str(artifacts.final_svg_path),
                    'components_path': str(artifacts.components_path) if artifacts.components_path is not None else None,
                    'template_svg_path': str(artifacts.template_svg_path) if artifacts.template_svg_path is not None else None,
                },
            }
        except Exception as exc:  # noqa: BLE001
            partial_scene_graph = self._safe_read_json(resolved_output_dir / 'scene_graph.json') if resolved_output_dir is not None else {}
            partial_svg = self._safe_read_text(resolved_output_dir / 'final.svg') if resolved_output_dir is not None else ''
            return {
                'status': 'error',
                'svg_content': partial_svg or self._error_svg(str(exc)),
                'scene_graph': partial_scene_graph,
                'error': {
                    'type': type(exc).__name__,
                    'message': str(exc),
                },
                'artifacts': {
                    'output_dir': str(resolved_output_dir) if resolved_output_dir is not None else None,
                    'scene_graph_path': str(resolved_output_dir / 'scene_graph.json') if resolved_output_dir is not None else None,
                    'final_svg_path': str(resolved_output_dir / 'final.svg') if resolved_output_dir is not None else None,
                    'components_path': str(resolved_output_dir / 'components.json') if resolved_output_dir is not None else None,
                    'template_svg_path': str(resolved_output_dir / 'template.svg') if resolved_output_dir is not None else None,
                },
            }
        finally:
            if temp_input_dir is not None:
                shutil.rmtree(temp_input_dir, ignore_errors=True)
            if temp_output_dir is not None:
                shutil.rmtree(temp_output_dir, ignore_errors=True)

    def process_image_json(
        self,
        *,
        image_path: str | Path | None = None,
        image_base64: str | None = None,
        output_dir: str | Path | None = None,
    ) -> str:
        """Return the standardized API payload as JSON."""

        return json.dumps(
            self.process_image(image_path=image_path, image_base64=image_base64, output_dir=output_dir),
            ensure_ascii=False,
        )

    def _resolve_input(
        self,
        *,
        image_path: str | Path | None,
        image_base64: str | None,
    ) -> tuple[Path, Path | None]:
        if image_path is None and image_base64 is None:
            raise ValueError('Either image_path or image_base64 must be provided.')
        if image_path is not None and image_base64 is not None:
            raise ValueError('Provide only one of image_path or image_base64.')
        if image_path is not None:
            resolved = Path(image_path)
            if not resolved.exists():
                raise FileNotFoundError(f'Input image not found: {resolved}')
            return resolved, None

        payload = image_base64 or ''
        if ',' in payload and payload.lstrip().startswith('data:'):
            payload = payload.split(',', 1)[1]
        binary = base64.b64decode(payload, validate=True)
        temp_dir = self._make_temp_dir('plot2svg-input')
        temp_path = temp_dir / 'input-image.png'
        temp_path.write_bytes(binary)
        return temp_path, temp_dir

    def _make_temp_dir(self, prefix: str) -> Path:
        self.temp_root.mkdir(parents=True, exist_ok=True)
        path = self.temp_root / f'{prefix}-{uuid4().hex}'
        path.mkdir(parents=True, exist_ok=False)
        return path

    def _safe_read_json(self, path: Path | None) -> dict[str, Any]:
        if path is None or not path.exists():
            return {}
        return json.loads(path.read_text(encoding='utf-8'))

    def _safe_read_text(self, path: Path | None) -> str:
        if path is None or not path.exists():
            return ''
        return path.read_text(encoding='utf-8')

    def _error_svg(self, message: str) -> str:
        escaped = message.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        return (
            "<svg xmlns='http://www.w3.org/2000/svg' width='640' height='120' viewBox='0 0 640 120'>"
            "<rect width='640' height='120' fill='#ffffff' stroke='#cc0000'/>"
            "<text x='16' y='34' font-size='20' fill='#cc0000'>plot2svg failed</text>"
            f"<text x='16' y='68' font-size='14' fill='#333333'>{escaped}</text>"
            '</svg>'
        )


def process_image(
    *,
    image_path: str | Path | None = None,
    image_base64: str | None = None,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Convenience function for one-shot external tool calls."""

    return Plot2SvgEngine().process_image(
        image_path=image_path,
        image_base64=image_base64,
        output_dir=output_dir,
    )
