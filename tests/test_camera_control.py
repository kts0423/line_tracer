# tests/test_camera_control.py
# Unit test for CameraController.auto_adjust method

import os
import sys
import numpy as np
import yaml
import pytest

# Add src directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))
from camera_control import CameraController

# Path to the config file
CONFIG_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../config.yaml"))

@pytest.fixture(scope="module")
def camera_controller():
    # Instantiate the controller
    ctrl = CameraController(CONFIG_PATH)
    yield ctrl
    # Cleanup
    ctrl.stop()


def test_auto_adjust_increase_exposure(camera_controller):
    # Given a very dark image, exposure should increase
    initial_exp = camera_controller.current_exp
    gray_dark = np.full((100, 100), 10, dtype=np.uint8)
    camera_controller.auto_adjust(gray_dark)
    assert camera_controller.current_exp > initial_exp, \
        f"Exposure did not increase for dark image: {camera_controller.current_exp} <= {initial_exp}"


def test_auto_adjust_decrease_exposure(camera_controller):
    # Given a very bright image, exposure should decrease
    # Reset to initial
    camera_controller.current_exp = yaml.safe_load(open(CONFIG_PATH))["camera"]["initial_exposure"]
    initial_exp = camera_controller.current_exp
    gray_bright = np.full((100, 100), 200, dtype=np.uint8)
    camera_controller.auto_adjust(gray_bright)
    assert camera_controller.current_exp < initial_exp, \
        f"Exposure did not decrease for bright image: {camera_controller.current_exp} >= {initial_exp}"
