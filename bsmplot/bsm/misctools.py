from bsmutility.misctools import MiscTools


def bsm_initialize(frame, **kwargs):
    """module initialization"""
    MiscTools.initialize(frame, help_panel=False, **kwargs)
