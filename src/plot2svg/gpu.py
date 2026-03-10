"""GPU acceleration layer for Plot2SVG.

Provides thin wrappers around OpenCV operations that transparently use
CUDA when available, falling back to CPU otherwise.  Every public
function accepts and returns plain ``np.ndarray`` — GpuMat upload /
download is fully internal.
"""

from __future__ import annotations

import cv2
import numpy as np


# ---------------------------------------------------------------------------
# CUDA detection
# ---------------------------------------------------------------------------

_CUDA_AVAILABLE: bool = False
_DEVICE_NAME: str = "CPU"

try:
    _device_count = cv2.cuda.getCudaEnabledDeviceCount()
    if _device_count > 0:
        _CUDA_AVAILABLE = True
        _DEVICE_NAME = f"CUDA ({_device_count} device(s))"
except (AttributeError, cv2.error):
    pass

# Minimum image dimension to justify GPU upload/download overhead.
_MIN_GPU_DIM = 512


def gpu_available() -> bool:
    """Return *True* when OpenCV was built with CUDA and a device is present."""
    return _CUDA_AVAILABLE


def gpu_device_name() -> str:
    """Human-readable device description."""
    return _DEVICE_NAME


def gpu_status_summary() -> dict[str, object]:
    """Combined GPU status for both OpenCV-CUDA and ONNX-Runtime CUDA."""
    ocr_cuda = False
    ort_device = "CPU"
    try:
        from .ocr import should_use_ocr_cuda
        import onnxruntime as ort
        providers = ort.get_available_providers()
        ort_device = ort.get_device()
        ocr_cuda = should_use_ocr_cuda(providers, ort_device)
    except Exception:
        pass
    device_name = _DEVICE_NAME
    if ocr_cuda and not _CUDA_AVAILABLE:
        device_name = f"GPU (OCR via ONNX Runtime CUDA)"
    return {
        "opencv_cuda": _CUDA_AVAILABLE,
        "ocr_cuda": ocr_cuda,
        "device_name": device_name,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _worth_gpu(img: np.ndarray) -> bool:
    """Heuristic: skip GPU path for tiny images where transfer > compute."""
    return _CUDA_AVAILABLE and min(img.shape[0], img.shape[1]) >= _MIN_GPU_DIM


# ---------------------------------------------------------------------------
# Public wrappers
# ---------------------------------------------------------------------------

def gaussian_blur(img: np.ndarray, ksize: tuple[int, int], sigma: float) -> np.ndarray:
    """GaussianBlur — CUDA accelerated when beneficial."""
    if _worth_gpu(img):
        try:
            gpu_img = cv2.cuda_GpuMat()
            gpu_img.upload(img)
            filt = cv2.cuda.createGaussianFilter(
                img.dtype, img.dtype, ksize, sigma,
            )
            gpu_out = filt.apply(gpu_img)
            return gpu_out.download()
        except Exception:
            pass
    return cv2.GaussianBlur(img, ksize, sigma)


def resize(
    img: np.ndarray,
    dsize: tuple[int, int],
    interpolation: int = cv2.INTER_LINEAR,
) -> np.ndarray:
    """cv2.resize — CUDA accelerated when beneficial."""
    if _worth_gpu(img):
        try:
            gpu_img = cv2.cuda_GpuMat()
            gpu_img.upload(img)
            gpu_out = cv2.cuda.resize(gpu_img, dsize, interpolation=interpolation)
            return gpu_out.download()
        except Exception:
            pass
    return cv2.resize(img, dsize, interpolation=interpolation)


def threshold(
    img: np.ndarray,
    thresh: float,
    maxval: float,
    type_flag: int,
) -> tuple[float, np.ndarray]:
    """cv2.threshold — CUDA accelerated when beneficial.

    Returns ``(retval, binary)`` just like ``cv2.threshold``.
    """
    if _worth_gpu(img):
        try:
            gpu_img = cv2.cuda_GpuMat()
            gpu_img.upload(img)
            retval, gpu_out = cv2.cuda.threshold(gpu_img, thresh, maxval, type_flag)
            return retval, gpu_out.download()
        except Exception:
            pass
    return cv2.threshold(img, thresh, maxval, type_flag)


def canny(img: np.ndarray, threshold1: float, threshold2: float) -> np.ndarray:
    """Canny edge detection — CUDA accelerated when beneficial."""
    if _worth_gpu(img):
        try:
            gpu_img = cv2.cuda_GpuMat()
            gpu_img.upload(img)
            detector = cv2.cuda.createCannyEdgeDetector(threshold1, threshold2)
            gpu_out = detector.detect(gpu_img)
            return gpu_out.download()
        except Exception:
            pass
    return cv2.Canny(img, threshold1, threshold2)


def clahe_apply(
    img: np.ndarray,
    clip_limit: float = 2.0,
    tile_grid_size: tuple[int, int] = (8, 8),
) -> np.ndarray:
    """CLAHE — CUDA accelerated when beneficial."""
    if _worth_gpu(img):
        try:
            gpu_img = cv2.cuda_GpuMat()
            gpu_img.upload(img)
            clahe_obj = cv2.cuda.createCLAHE(clipLimit=clip_limit, tileGridSize=tile_grid_size)
            gpu_out = clahe_obj.apply(gpu_img, cv2.cuda.Stream.Null())
            return gpu_out.download()
        except Exception:
            pass
    clahe_obj = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=tile_grid_size)
    return clahe_obj.apply(img)


def filter2d(
    img: np.ndarray,
    ddepth: int,
    kernel: np.ndarray,
) -> np.ndarray:
    """cv2.filter2D — CUDA accelerated when beneficial."""
    if _worth_gpu(img):
        try:
            gpu_img = cv2.cuda_GpuMat()
            gpu_img.upload(img)
            filt = cv2.cuda.createLinearFilter(
                img.dtype, img.dtype, kernel,
            )
            gpu_out = filt.apply(gpu_img)
            return gpu_out.download()
        except Exception:
            pass
    return cv2.filter2D(img, ddepth, kernel)
