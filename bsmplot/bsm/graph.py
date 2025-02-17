import wx
import wx.py.dispatcher as dp
import numpy as np
import matplotlib
matplotlib.use('module://bsmplot.bsm.bsmbackend')
import matplotlib.pyplot as plt
from mplpanel import MPLPanel, Gcf
from bsmutility.bsminterface import InterfaceRename
from bsmutility.bsmxpm import polyline_svg
from bsmutility.utility import svg_to_bitmap

class DataDropTarget(wx.DropTarget):
    def __init__(self, canvas):
        wx.DropTarget.__init__(self)
        self.obj = wx.TextDataObject()
        self.SetDataObject(self.obj)
        self.canvas = canvas
        self.SetDefaultAction(wx.DragMove)

    def OnEnter(self, x, y, d):
        #self.canvas.OnEnter(x, y, d)
        return d

    def OnLeave(self):
        #self.frame.OnLeave()
        pass

    def OnDrop(self, x, y):
        return True

    def OnData(self, x, y, d):
        if not self.GetData():
            return wx.DragNone
        if wx.Platform != '__WXMSW__':
            ratio = self.canvas.device_pixel_ratio
        else:
            ratio = 1
        sz = self.canvas.GetSize()
        y = sz[1]-y
        fig = self.canvas.figure
        if len(fig.get_axes()) == 0:
            fig.gca()
        for i, ax in enumerate(fig.get_axes()):
            if ax.bbox.contains(x*ratio, y*ratio):
                # set the active axes here, and the caller will plot on it
                fig.sca(ax)
                dp.send('graph.drop', axes=ax, allowed=True)
                break
        return d

    def OnDragOver(self, x, y, d):
        #self.frame.OnDragOver(x, y, d)
        return d

class MatplotPanel(MPLPanel):

    def __init__(self, parent, title=None, num=-1, thisFig=None):
        MPLPanel.__init__(self, parent, title, num, thisFig)

        dp.connect(self.DataUpdated, 'graph.data_updated')

        dt = DataDropTarget(self.canvas)
        self.canvas.SetDropTarget(dt)

    def Destroy(self):
        dp.disconnect(self.DataUpdated, 'graph.data_updated')
        super().Destroy()

    def DataUpdated(self):
        updated_ax = []
        for ax in self.figure.get_axes():
            autorelim = False
            updated = False
            for l in ax.lines:
                if not hasattr(l, 'trace_signal'):
                    continue
                signal, num, path = l.trace_signal
                resp = dp.send(signal, num=num, path=path)
                if not resp:
                    continue
                # ignore the zmq when different "num"
                resp = [r for r in resp if len(r[1]) == 2 and r[1][0] is not None and r[1][1] is not None]
                if not resp:
                    continue
                x, y = resp[0][1]
                if x is None or y is None:
                    continue
                l.set_data(x, y)
                updated = True
                if hasattr(l, 'autorelim') and l.autorelim:
                    autorelim = True
            if updated:
                updated_ax.append(ax)
            if autorelim:
                #Need both of these in order to rescale
                ax.relim()
                ax.autoscale_view()
        dp.send('graph.axes_updated', figure=self.figure, axes=updated_ax)

    def simLoad(self, num):
        for ax in self.figure.get_axes():
            for l in ax.lines:
                if hasattr(l, 'trace'):
                    sz = len(l.get_ydata())
                    for s in l.trace:
                        if (not s) or (not s.startswith(str(num) + '.')):
                            continue
                        #dispatcher.send(signal='sim.trace_buf', objects=s, size=sz)

    def show(self):
        """show figure"""
        if self.IsShownOnScreen() is False:
            self.canvas.draw()
            dp.send('frame.show_panel', panel=self)

    def update_buffer(self, bufs):
        """update the data used in plot_trace"""
        for ax in self.figure.get_axes():
            for l in ax.lines:
                if hasattr(l, 'trace'):
                    x = l.trace[0]
                    y = l.trace[1]
                    if x is None:
                        if y in bufs:
                            l.set_data(np.arange(len(bufs[y])), bufs[y])
                    elif x in bufs or y in bufs:
                        xd = l.get_xdata()
                        yd = l.get_ydata()
                        if y in bufs:
                            yd = bufs[y]
                        if x in bufs:
                            xd = bufs[x]
                        if len(xd) != len(yd):
                            sz = min(len(xd), len(yd))
                            xd = xd[0:sz]
                            yd = yd[0:sz]
                        l.set_data(xd, yd)
                    if hasattr(l, 'autorelim') and l.autorelim:
                        #Need both of these in order to rescale
                        ax.relim()
                        ax.autoscale_view()
        self.canvas.draw()

    def plot_trace(self, x, y, autorelim, *args, **kwargs):
        """plot and trace"""
        if y is None:
            return
        if x is None:
            l, = self.figure.gca().plot(list(y.values())[0], *args, **kwargs)
            l.trace = [None, list(y.keys())[0]]
        else:
            xd = list(x.values())[0]
            yd = list(y.values())[0]
            if len(xd) != len(yd):
                sz = min(len(xd), len(yd))
                if sz > 0:
                    xd = xd[0:sz]
                    yd = yd[0:sz]
                else:
                    xd = 0
                    yd = 0
            l, = self.figure.gca().plot(xd, yd, *args, **kwargs)
            l.trace = [list(x.keys())[0], list(y.keys())[0]]
        l.autorelim = autorelim
        self.canvas.draw()


class Graph(InterfaceRename):
    kwargs = {}
    ID_NEW_FIGURE = wx.NOT_FOUND
    ID_PANE_CLOSE = wx.NewIdRef()
    ID_PANE_CLOSE_OTHERS = wx.NewIdRef()
    ID_PANE_CLOSE_ALL = wx.NewIdRef()
    MENU_NEW_FIG = 'File:New:Figure\tCtrl+P'

    icon = None

    @classmethod
    def initialize(cls, frame, **kwargs):
        super().initialize(frame, **kwargs)
        cls.kwargs = kwargs

        MatplotPanel.Initialize(frame, **kwargs)

        resp = dp.send('frame.add_menu',
                       path=cls.MENU_NEW_FIG,
                       rxsignal='bsm.figure')
        if resp:
            cls.ID_NEW_FIGURE = resp[0][1]

        if cls.ID_NEW_FIGURE is not wx.NOT_FOUND:
            dp.connect(cls.ProcessCommand, 'bsm.figure')
        dp.connect(cls.SetActive, 'frame.activate_panel')
        dp.connect(cls.OnBufferChanged, 'sim.buffer_changed')
        dp.connect(cls.PaneMenu, 'bsm.graph.pane_menu')

        cls.icon = svg_to_bitmap(polyline_svg, win=frame)

    @classmethod
    def PaneMenu(cls, pane, command):
        if not pane or not isinstance(pane.window, MatplotPanel):
            return
        if command == cls.ID_PANE_CLOSE:
            dp.send(signal='frame.delete_panel', panel=pane.window)
        elif command == cls.ID_PANE_CLOSE_OTHERS:
            mgrs = Gcf.get_all_fig_managers()
            for mgr in mgrs:
                if mgr == pane.window:
                    continue
                dp.send(signal='frame.delete_panel', panel=mgr)
        elif command == cls.ID_PANE_CLOSE_ALL:
            mgrs = Gcf.get_all_fig_managers()
            for mgr in mgrs:
                dp.send(signal='frame.delete_panel', panel=mgr)
        elif command == cls.ID_PANE_RENAME:
            cls.RenamePane(pane)

    @classmethod
    def initialized(cls):
        super().initialized()
        dp.send('shell.run',
                command='from matplotlib.pyplot import *',
                prompt=False,
                verbose=False,
                history=False)

    @classmethod
    def OnBufferChanged(cls, bufs):
        """the buffer has be changes, update the plot_trace"""
        for p in Gcf.get_all_fig_managers():
            p.update_buffer(bufs)

    @classmethod
    def SetActive(cls, pane):
        if pane and isinstance(pane, MatplotPanel):
            if MatplotPanel.GetActive() == pane:
                return
            MatplotPanel.SetActive(pane)

    @classmethod
    def uninitializing(cls):
        super().uninitializing()
        # before save perspective
        for mgr in Gcf.get_all_fig_managers():
            dp.send('frame.delete_panel', panel=mgr)
        dp.send('frame.delete_menu', path=cls.MENU_NEW_FIG, id=cls.ID_NEW_FIGURE)

    @classmethod
    def uninitialized(cls):
        dp.disconnect(cls.SetActive, 'frame.activate_panel')
        dp.disconnect(cls.OnBufferChanged, 'sim.buffer_changed')
        dp.disconnect(cls.PaneMenu, 'bsm.graph.pane_menu')
        super().uninitialized()

    @classmethod
    def ProcessCommand(cls, command):
        """process the menu command"""
        if command == cls.ID_NEW_FIGURE:
            plt.figure()

    @classmethod
    def AddFigure(cls, title=None, num=None, thisFig=None):
        fig = MatplotPanel.AddFigure(title, num, thisFig)
        direction = cls.kwargs.get('direction', 'top')
        # set the minsize to be large enough to avoid some following assert; it
        # will not eliminate all as if a page is added to a notebook, the
        # minsize of notebook is not the max of all its children pages (check
        # frameplus.py).
        # wxpython/ext/wxWidgets/src/gtk/bitmap.cpp(539): assert ""width > 0 &&
        # height > 0"" failed in Create(): invalid bitmap size
        dp.send('frame.add_panel',
                panel=fig,
                direction=direction,
                title=fig.GetTitle(),
                target=Gcf.get_active(),
                minsize=(75, 75),
                pane_menu={'rxsignal': 'bsm.graph.pane_menu',
                           'menu': [
                               {'id':cls.ID_PANE_RENAME, 'label':'Rename'},
                               {'type': wx.ITEM_SEPARATOR},
                               {'id':cls.ID_PANE_CLOSE, 'label':'Close\tCtrl+W'},
                               {'id':cls.ID_PANE_CLOSE_OTHERS, 'label':'Close Others'},
                               {'id':cls.ID_PANE_CLOSE_ALL, 'label':'Close All'},
                               ]},
                icon=cls.icon)
        return fig



def bsm_initialize(frame, **kwargs):
    """module initialization"""
    Graph.initialize(frame, **kwargs)
