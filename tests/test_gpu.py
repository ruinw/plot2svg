"""Tests for the GPU abstraction layer."""

import numpy as np
import pytest

from plot2svg.gpu import (
    canny,
    clahe_apply,
    filter2d,
    gaussian_blur,
    gpu_available,
    gpu_device_name,
    gpu_status_summary,
    resize,
    threshold,
)


# ---------------------------------------------------------------------------
# Detection helpers
# ---------------------------------------------------------------------------

def test_gpu_available_returns_bool():
    assert isinstance(gpu_available(), bool)


def test_gpu_device_name_returns_str():
    name = gpu_device_name()
    assert isinstance(name, str)
    assert len(name) > 0


def test_gpu_status_summary_keys():
    status = gpu_status_summary()
    assert "opencv_cuda" in status
    assert "ocr_cuda" in status
    assert "device_name" in status
    assert isinstance(status["opencv_cuda"], bool)
    assert isinstance(status["ocr_cuda"], bool)


# ---------------------------------------------------------------------------
# Wrapper functions — functional parity with cv2 originals
# ---------------------------------------------------------------------------

@pytest.fixture()
def gray_image():
    """100x100 synthetic grayscale image with a gradient."""
    return np.tile(np.arange(100, dtype=np.uint8), (100, 1))


@pytest.fixture()
def color_image():
    """100x100 synthetic BGR image."""
    return np.random.default_rng(42).integers(0, 256, (100, 100, 3), dtype=np.uint8)


def test_gaussian_blur_shape(gray_image):
    result = gaussian_blur(gray_image, (5, 5), 0)
    assert result.shape == gray_image.shape
    assert result.dtype == gray_image.dtype


def test_resize_output_size(gray_image):
    result = resize(gray_image, (50, 50))
    assert result.shape == (50, 50)


def test_threshold_returns_tuple_and_binary(gray_image):
    retval, binary = threshold(gray_image, 0, 255, 0)  # cv2.THRESH_BINARY == 0
    assert isinstance(retval, (int, float))
    assert binary.shape == gray_image.shape
    unique = set(np.unique(binary))
    assert unique <= {0, 255}


def test_canny_output_shape(gray_image):
    result = canny(gray_image, 80, 160)
    assert result.shape == gray_image.shape


def test_clahe_apply_shape(gray_image):
    result = clahe_apply(gray_image, clip_limit=2.0, tile_grid_size=(8, 8))
    assert result.shape == gray_image.shape
    assert result.dtype == gray_image.dtype


def test_filter2d_shape(color_image):
    kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]], dtype=np.float32)
    result = filter2d(color_image, -1, kernel)
    assert result.shape == color_image.shape
