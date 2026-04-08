from __future__ import annotations

from pathlib import Path

import cv2

from icon_processor import IconProcessor


BASE_DIR = Path(__file__).resolve().parent
INPUT_CANDIDATES = [
    BASE_DIR / "B.png",
    BASE_DIR.parent / "B.png",
]
SVG_TAG_PATH = BASE_DIR / "debug_B_image_tag.svg"


def resolve_input_path() -> Path:
    for path in INPUT_CANDIDATES:
        if path.exists():
            return path
    raise FileNotFoundError("B.png not found in sandbox/output or sandbox root")


def main() -> None:
    input_path = resolve_input_path()
    image = cv2.imread(str(input_path), cv2.IMREAD_UNCHANGED)
    if image is None:
        raise FileNotFoundError(f"Failed to read image: {input_path}")

    processor = IconProcessor(contour_threshold=15, variance_threshold=800.0)
    complexity, svg_tag = processor.process_roi(image)

    print(f"input={input_path.name}")
    print(f"contour_count={complexity.contour_count}")
    print(f"variance={complexity.variance:.3f}")
    print(f"complex_icon={complexity.is_complex}")

    if svg_tag is None:
        raise RuntimeError("ROI is not complex enough for icon fallback")

    payload_length = len(svg_tag.split("base64,", 1)[1].split('"', 1)[0])
    SVG_TAG_PATH.write_text(svg_tag + "\n", encoding="utf-8")
    print(f"base64_length={payload_length}")
    print(svg_tag)


if __name__ == "__main__":
    main()
