import sys
import os
import traceback
import keyword
from bsmutility.surface import GLSurface


def bsm_initialize(frame, **kwargs):
    """module initialization"""
    GLSurface.initialize(frame, **kwargs)
