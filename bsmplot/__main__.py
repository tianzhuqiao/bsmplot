import os
import shutil
import multiprocessing
import ctypes
import wx
import click
from bsmutility.utility import create_shortcut
from .mainframe import MainFrame
from .version import __version__, PROJECT_NAME
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(True)
    wx.PyApp.IsDisplayAvailable = lambda _: True
except:
    pass


class RunApp(wx.App):
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        wx.App.__init__(self, redirect=False)

    def OnInit(self):
        wx.Log.SetActiveTarget(wx.LogStderr())

        self.SetAssertMode(wx.APP_ASSERT_DIALOG)

        frame = MainFrame(None, **self.kwargs)
        frame.Show(True)
        self.SetTopWindow(frame)
        self.frame = frame
        return True


@click.command()
@click.version_option(__version__)
@click.option('--config',
              '-c',
              default=PROJECT_NAME,
              help=f"Set configuration file name, default '{PROJECT_NAME}'.")
@click.option('--path',
              '-p',
              multiple=True,
              type=click.Path(exists=True),
              help="Add external module path.")
@click.option('--ignore-perspective',
              '-i',
              is_flag=True,
              help="Do not load perspective.")
@click.option('--spawn',
              is_flag=True,
              help="Start a process with method 'spawn'.")
@click.option('--debug',
              is_flag=True,
              help='Run in debug mode.')
@click.option('--init', is_flag=True, help=f"Initialize {PROJECT_NAME}, e.g, create desktop shortcut.")
@click.option('--uninit', is_flag=True, help=f"Uninitialize {PROJECT_NAME}, e.g, delete desktop shortcut.")
@click.argument('module', nargs=-1)
def main(config, path, ignore_perspective, spawn, debug, module, init, uninit):
    if spawn and hasattr(multiprocessing, 'set_start_method'):
        multiprocessing.set_start_method('spawn')
    if init or uninit:
        folder, _ = os.path.split(__file__)
        icns = f'{folder}/ico/mainframe.icns'
        ico = f'{folder}/ico/mainframe.ico'
        svg = f'{folder}/ico/mainframe.svg'
        targets = create_shortcut(PROJECT_NAME, icns, ico, svg)
        if uninit:
            if targets is None:
                click.secho('Can\'t find the created shortcuts!', fg='red')
                return
            for target in targets:
                if os.path.isdir(target):
                    shutil.rmtree(target)
                elif os.path.isfile(target):
                    os.remove(target)
        return
    app = RunApp(config=config,
                 ignore_perspective=ignore_perspective,
                 path=path,
                 module=module,
                 debug=debug)
    app.MainLoop()


if __name__ == '__main__':
    main()
