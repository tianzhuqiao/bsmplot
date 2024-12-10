import wx.py.dispatcher as dp
from bsmutility.editor import Editor

class PyEditor(Editor):

    @classmethod
    def initialized(cls):
        super().initialized()
        dp.send(signal='shell.run',
                command='from bsmplot.bsm.editor import PyEditor as Editor',
                prompt=False,
                verbose=False,
                history=False)

    @classmethod
    def ignore_file_ext(cls):
        return ['.csv', '.ulg', '.mat', '.vcd']

def bsm_initialize(frame, **kwargs):
    """initialize the model"""
    PyEditor.initialize(frame, **kwargs)
